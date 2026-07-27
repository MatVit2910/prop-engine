import json
import redis.asyncio as redis
from typing import Optional, Dict, Any
from src.models.domain import PlayerGameState, OddsTick, TradeSignal


class RedisClient:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.host = host
        self.port = port
        self.redis: Optional[redis.Redis] = None

    async def connect(self):
        if not self.redis:
            self.redis = redis.Redis(
                host=self.host, port=self.port, decode_responses=True
            )

    async def close(self):
        if self.redis:
            await self.redis.close()
            self.redis = None

    async def save_player_state(self, state: PlayerGameState):
        if not self.redis:
            await self.connect()
        key = f"gamestate:{state.game_id}:{state.player_id}"
        await self.redis.set(key, state.model_dump_json())

    async def get_player_state(
        self, game_id: str, player_id: str
    ) -> Optional[PlayerGameState]:
        if not self.redis:
            await self.connect()
        key = f"gamestate:{game_id}:{player_id}"
        raw = await self.redis.get(key)
        if raw:
            return PlayerGameState.model_validate_json(raw)
        return None

    async def publish_odds_tick(self, tick: OddsTick):
        if not self.redis:
            await self.connect()
        channel = f"ticks:{tick.game_id}:{tick.player_id}"
        await self.redis.publish(channel, tick.model_dump_json())

    async def publish_trade_signal(self, signal: TradeSignal):
        if not self.redis:
            await self.connect()
        channel = f"signals:{signal.game_id}"
        await self.redis.publish(channel, signal.model_dump_json())
