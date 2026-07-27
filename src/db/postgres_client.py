import asyncpg
from typing import Optional
from src.models.domain import OddsTick, PlayByPlayEvent, ModelPricingResult, TradeSignal


class PostgresClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "quant_user",
        password: str = "quant_password",
        database: str = "nba_props_db",
    ):
        self.dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def log_odds_tick(self, tick: OddsTick):
        if not self.pool:
            await self.connect()
        query = """
            INSERT INTO odds_ticks (
                timestamp, game_id, player_id, player_name, stat_type,
                bookmaker, line, over_price, under_price,
                implied_over_prob, implied_under_prob
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                tick.timestamp,
                tick.game_id,
                tick.player_id,
                tick.player_name,
                tick.stat_type.value,
                tick.bookmaker,
                tick.line,
                tick.over_price,
                tick.under_price,
                tick.implied_over_prob,
                tick.implied_under_prob,
            )

    async def log_trade_signal(self, signal: TradeSignal):
        if not self.pool:
            await self.connect()
        query = """
            INSERT INTO trade_signals (
                timestamp, signal_id, game_id, player_id, player_name,
                stat_type, side, line, bookmaker, bookmaker_odds,
                fair_odds, ev_percent, kelly_fraction, recommended_wager,
                consensus_fair_prob, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                signal.timestamp,
                signal.signal_id,
                signal.game_id,
                signal.player_id,
                signal.player_name,
                signal.stat_type.value,
                signal.side.value,
                signal.line,
                signal.bookmaker,
                signal.bookmaker_odds,
                signal.fair_odds,
                signal.ev_percent,
                signal.kelly_fraction,
                signal.recommended_wager,
                signal.consensus_fair_prob,
                signal.status,
            )
