import aiohttp
import structlog
from typing import Optional
from src.models.domain import TradeSignal
from src.config import settings

logger = structlog.get_logger()


class AlertDispatcher:
    """
    Dispatches real-time +EV trading alerts to Webhook endpoints (Discord / Telegram / JSON Webhook).
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.WEBHOOK_URL
        self._session: Optional[aiohttp.ClientSession] = None

    async def dispatch_signal(self, signal: TradeSignal):
        """Emits structured +EV trade signal alert."""
        logger.info(
            "🚨 DISPATCHING +EV SIGNAL ALERT 🚨",
            signal_id=signal.signal_id,
            player=signal.player_name,
            bookmaker=signal.bookmaker.upper(),
            side=signal.side.value,
            line=signal.line,
            odds=signal.bookmaker_odds,
            ev=f"{signal.ev_percent * 100:.2f}%",
            wager=f"${signal.recommended_wager:.2f}",
        )

        if not self.webhook_url:
            return

        payload = {
            "content": f"🔥 **+EV Player Prop Signal** 🔥\n"
            f"**Player**: {signal.player_name}\n"
            f"**Market**: {signal.stat_type.value.upper()} {signal.side.value} {signal.line}\n"
            f"**Bookmaker**: `{signal.bookmaker.upper()}` @ **{signal.bookmaker_odds}** (Fair: {signal.fair_odds})\n"
            f"**Expected Value (+EV)**: **+{signal.ev_percent * 100:.2f}%**\n"
            f"**Kelly Recommended Wager**: **${signal.recommended_wager:.2f}** ({signal.kelly_fraction * 100:.2f}% Kelly)\n"
            f"**Consensus Fair Prob**: {signal.consensus_fair_prob * 100:.1f}%",
            "username": "+EV Prop Bot",
        }

        try:
            if not self._session or self._session.closed:
                self._session = aiohttp.ClientSession()

            async with self._session.post(self.webhook_url, json=payload, timeout=3) as resp:
                if resp.status in (200, 204):
                    logger.info("Alert dispatched to webhook successfully.")
                else:
                    logger.warning("Webhook dispatch returned status", status=resp.status)
        except Exception as e:
            logger.warning("Failed to dispatch alert to webhook", error=str(e))

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
