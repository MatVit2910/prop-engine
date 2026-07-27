import asyncio
import signal
import structlog
from typing import Dict
from src.models.domain import PlayerGameState, StatType, Bookmaker
from src.db.redis_client import RedisClient
from src.db.postgres_client import PostgresClient
from src.db.db_init import initialize_database
from src.pricing.vig_stripper import VigStripper
from src.pricing.poisson_pricer import PoissonPricer
from src.execution.ev_evaluator import EVEvaluator
from src.execution.kelly_sizer import KellyRiskManager
from src.execution.alert_dispatcher import AlertDispatcher
from src.ingestion.odds_ingestor import OddsIngestor
from src.ingestion.gamestate_ingestor import GamestateIngestor
from src.config import settings

from src.ingestion.game_finder import GameDiscoveryService

logger = structlog.get_logger()


class LiveEngineDaemon:
    def __init__(self, league: Optional[str] = None):
        self.league = (league or settings.LEAGUE).lower().strip()
        self.redis_client = RedisClient(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        self.postgres_client = PostgresClient(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
        )
        self.odds_ingestor = OddsIngestor(
            redis_client=self.redis_client, league=self.league
        )
        self.gamestate_ingestor = GamestateIngestor(
            redis_client=self.redis_client, league=self.league
        )
        self.game_finder = GameDiscoveryService()
        self.ev_evaluator = EVEvaluator(
            min_ev_threshold=settings.MIN_EV_THRESHOLD,
            min_edge_over_consensus=settings.MIN_EDGE_OVER_CONSENSUS,
        )
        self.risk_manager = KellyRiskManager(
            bankroll=settings.BANKROLL_AMOUNT,
            kelly_fraction=settings.KELLY_FRACTION,
            max_wager_cap=settings.MAX_WAGER_CAP,
        )
        self.alert_dispatcher = AlertDispatcher()
        self.running = False

    async def setup(self):
        logger.info("Initializing DB & Redis connections...", league=self.league.upper())
        await self.redis_client.connect()
        await initialize_database()
        await self.postgres_client.connect()

    async def run_pricing_loop(self, game_id: str, odds_api_id: Optional[str] = None):
        logger.info(
            "Starting continuous real-time pricing and +EV evaluation loop...",
            game_id=game_id,
            league=self.league.upper(),
        )

        # League-specific regulation specs
        reg_mins = 40.0 if self.league == "wnba" else 48.0
        max_fouls = 5 if self.league == "wnba" else 6
        target_odds_id = odds_api_id or game_id
        
        # Register initial player state
        player_name = "A'ja Wilson" if self.league == "wnba" else "Stephen Curry"
        player_id = "player_wilson" if self.league == "wnba" else "player_curry"
        target_line = 21.5 if self.league == "wnba" else 28.5
        
        player_state = PlayerGameState(
            game_id=game_id,
            player_id=player_id,
            player_name=player_name,
            projected_total_minutes=30.0 if self.league == "wnba" else 34.0,
            elapsed_minutes_played=10.0,
            accumulated_stats={StatType.POINTS: 10},
            base_rate_per_minute={StatType.POINTS: 0.70 if self.league == "wnba" else 0.85},
        )
        self.gamestate_ingestor.register_player(player_state)

        while self.running:
            try:
                # 1. Fetch Latest Market Ticks
                ticks = await self.odds_ingestor.fetch_live_odds_ticks(target_odds_id)

                # 2. Extract Sharp Consensus (Pinnacle/Circa)
                pinnacle_tick = next(
                    (t for t in ticks if t.bookmaker == Bookmaker.PINNACLE.value and t.player_id == player_state.player_id),
                    ticks[0] if ticks else None,
                )

                if pinnacle_tick:
                    sharp_over_fair, sharp_under_fair = VigStripper.power_dejuice(
                        pinnacle_tick.over_price, pinnacle_tick.under_price
                    )
                else:
                    sharp_over_fair, sharp_under_fair = 0.50, 0.50

                # 3. Compute Inhomogeneous Poisson True Probability
                rem_seconds = 1800 if self.league == "wnba" else 2160
                pricing = PoissonPricer.price_player_prop(
                    player_state=player_state,
                    stat_type=StatType.POINTS,
                    target_line=target_line,
                    remaining_regulation_seconds=rem_seconds,
                    period=2,
                    regulation_minutes=reg_mins,
                    max_fouls=max_fouls,
                )

                # 4. Evaluate +EV Signals & Size Wagers
                for tick in ticks:
                    # Log tick to TimescaleDB
                    try:
                        await self.postgres_client.log_odds_tick(tick)
                    except Exception:
                        pass

                    signal = self.ev_evaluator.evaluate_quote(
                        pricing=pricing,
                        quote=tick,
                        consensus_fair_over_prob=sharp_over_fair,
                        consensus_fair_under_prob=sharp_under_fair,
                        player_name=player_state.player_name,
                    )

                    if signal:
                        signal = self.risk_manager.calculate_wager_size(signal, win_prob=pricing.true_over_prob)
                        
                        # Log Trade Signal to TimescaleDB & Publish to Redis
                        try:
                            await self.postgres_client.log_trade_signal(signal)
                        except Exception:
                            pass
                        await self.redis_client.publish_trade_signal(signal)

                        # Alert via Dispatcher
                        await self.alert_dispatcher.dispatch_signal(signal)

            except Exception as e:
                logger.error("Error in pricing loop iteration", error=str(e))

            await asyncio.sleep(2.0)

    async def start(self, game_id: Optional[str] = None):
        self.running = True
        await self.setup()

        odds_api_id = None
        if not game_id:
            logger.info("Auto-discovering active live games...", league=self.league.upper())
            discovered_games = await self.game_finder.discover_live_games(league=self.league)
            if discovered_games:
                active_game = discovered_games[0]
                game_id = active_game.espn_game_id or active_game.game_id
                odds_api_id = active_game.odds_api_id
                logger.info(
                    "Auto-discovered live game",
                    league=self.league.upper(),
                    teams=f"{active_game.away_team} @ {active_game.home_team}",
                    status=active_game.status,
                    espn_id=game_id,
                    odds_api_id=odds_api_id,
                )
            else:
                logger.info(
                    "No active live games currently found in progress.",
                    league=self.league.upper(),
                )
                return

        if game_id:
            await self.run_pricing_loop(game_id, odds_api_id=odds_api_id)

    async def stop(self):
        self.running = False
        logger.info("Shutting down engine daemon gracefully...")
        await self.odds_ingestor.close()
        await self.gamestate_ingestor.close()
        await self.game_finder.close()
        await self.alert_dispatcher.close()
        await self.redis_client.close()
        await self.postgres_client.close()


async def main():
    daemon = LiveEngineDaemon()

    def handle_signal():
        asyncio.create_task(daemon.stop())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    try:
        await daemon.start()
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
