import asyncio
import structlog
from src.models.domain import PlayerGameState, StatType, Bookmaker
from src.db.redis_client import RedisClient
from src.db.postgres_client import PostgresClient
from src.pricing.vig_stripper import VigStripper
from src.pricing.poisson_pricer import PoissonPricer
from src.execution.ev_evaluator import EVEvaluator
from src.execution.kelly_sizer import KellyRiskManager
from src.ingestion.odds_ingestor import OddsIngestor
from src.ingestion.gamestate_ingestor import GamestateIngestor

logger = structlog.get_logger()


async def run_engine_pipeline():
    logger.info("Initializing Live NBA Player Props Pricing & +EV Engine...")

    # 1. Initialize Clients & Risk Manager
    redis_client = RedisClient()
    postgres_client = PostgresClient()
    ev_evaluator = EVEvaluator(min_ev_threshold=0.03, min_edge_over_consensus=0.015)
    risk_manager = KellyRiskManager(bankroll=10000.0, kelly_fraction=0.125)

    # 2. Setup Player State
    curry_state = PlayerGameState(
        game_id="game_nba_001",
        player_id="player_curry",
        player_name="Stephen Curry",
        projected_total_minutes=34.0,
        elapsed_minutes_played=12.0,  # End Q1
        accumulated_stats={StatType.POINTS: 11},
        base_rate_per_minute={StatType.POINTS: 0.85},
    )

    gamestate_ingestor = GamestateIngestor(redis_client=redis_client)
    gamestate_ingestor.register_player(curry_state)

    odds_ingestor = OddsIngestor(redis_client=redis_client)

    # 3. Simulate Live Tick Processing Loop
    logger.info("Simulating live market quotes and pricing update loop...")
    ticks = await odds_ingestor.fetch_mock_odds_ticks(curry_state.game_id)

    # Calculate Sharp Consensus Fair Line (Pinnacle/Circa)
    pinnacle_tick = next(
        (t for t in ticks if t.bookmaker == Bookmaker.PINNACLE.value and t.player_id == curry_state.player_id),
        ticks[0],
    )
    sharp_over_fair, sharp_under_fair = VigStripper.power_dejuice(
        pinnacle_tick.over_price, pinnacle_tick.under_price
    )

    # Calculate Quantitative True Odds via Inhomogeneous Poisson
    pricing = PoissonPricer.price_player_prop(
        player_state=curry_state,
        stat_type=StatType.POINTS,
        target_line=28.5,
        remaining_regulation_seconds=2160,  # 36 remaining game minutes
        period=2,
    )

    logger.info(
        "Quantitative Model True Odds",
        player=curry_state.player_name,
        target_line=pricing.target_line,
        true_over_prob=pricing.true_over_prob,
        fair_over_decimal=pricing.fair_over_decimal,
        sharp_consensus_over_prob=round(sharp_over_fair, 4),
    )

    # Evaluate Quotes for +EV Trades across Soft Books
    for tick in ticks:
        signal = ev_evaluator.evaluate_quote(
            pricing=pricing,
            quote=tick,
            consensus_fair_over_prob=sharp_over_fair,
            consensus_fair_under_prob=sharp_under_fair,
            player_name=curry_state.player_name,
        )
        if signal:
            signal = risk_manager.calculate_wager_size(signal, win_prob=pricing.true_over_prob)
            logger.info(
                "🔥 +EV TRADE SIGNAL DETECTED 🔥",
                signal_id=signal.signal_id,
                bookmaker=signal.bookmaker,
                side=signal.side.value,
                line=signal.line,
                book_odds=signal.bookmaker_odds,
                fair_odds=signal.fair_odds,
                ev_percent=f"{signal.ev_percent * 100:.2f}%",
                recommended_wager=f"${signal.recommended_wager:.2f}",
            )


if __name__ == "__main__":
    asyncio.run(run_engine_pipeline())
