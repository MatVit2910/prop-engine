import re
import asyncio
import aiohttp
import structlog
from typing import List, Optional
from src.models.domain import OddsTick, StatType, Bookmaker
from src.db.redis_client import RedisClient
from src.config import settings

logger = structlog.get_logger()

# Browser-like headers used when scraping public sportsbook JSON endpoints.
_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Bovada public content API — does not require authentication.
_BOVADA_NBA_URL = (
    "https://www.bovada.lv/services/sports/content/v2/"
    "events/A/description/basketball/nba"
)


class OddsIngestor:
    """Ingests live bookmaker player-prop odds with a tiered fallback chain.

    Resolution order:
        1. **The-Odds-API** (primary, freemium, 500 req/month free tier).
        2. **Public sportsbook endpoint** (Bovada web JSON, no API key).
        3. **Synthetic mock generator** (deterministic offline fallback).

    All ticks returned by the primary source pass through
    ``_filter_anomalies`` before reaching the caller.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        redis_client: Optional[RedisClient] = None,
        poll_interval_seconds: float = 3.0,
        league: str = "nba",
    ):
        self.api_key = api_key or settings.THE_ODDS_API_KEY
        self.redis_client = redis_client
        self.poll_interval_seconds = poll_interval_seconds
        self.league = league.lower().strip()
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Primary source — The-Odds-API
    # ------------------------------------------------------------------

    async def fetch_live_odds_ticks(self, game_id: str) -> List[OddsTick]:
        """Fetch live player-prop odds, falling back through the tiered chain.

        If no valid API key is configured or game_id is not a verified 32-char
        hexadecimal event hash, skips external API requests directly.

        Args:
            game_id: The-Odds-API event identifier (must be a 32-char hex string).

        Returns:
            A list of validated ``OddsTick`` domain objects.
        """
        # Strict validation: Only make API calls if game_id is a verified 32-char hex hash
        is_verified_hash = bool(re.match(r"^[a-fA-F0-9]{32}$", game_id or ""))
        if not self.api_key or self.api_key == "your_the_odds_api_key_here" or not is_verified_hash:
            return []

        sport_key = f"basketball_{self.league}"
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{game_id}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "us,eu",
            "markets": "player_points,player_rebounds,player_assists",
            "oddsFormat": "decimal",
        }

        try:
            if not self._session or self._session.closed:
                self._session = aiohttp.ClientSession()

            timeout = aiohttp.ClientTimeout(total=5)
            async with self._session.get(url, params=params, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    ticks = self._parse_api_response(game_id, data)
                    return self._filter_anomalies(ticks)
                elif response.status == 429:
                    logger.warning(
                        "The-Odds-API rate-limited (429), falling back to public sportsbook"
                    )
                    return await self.fetch_public_sportsbook_ticks(game_id)
                else:
                    logger.warning(
                        "The-Odds-API returned non-200 status", status=response.status
                    )
                    return await self.fetch_public_sportsbook_ticks(game_id)
        except Exception as e:
            logger.warning(
                "The-Odds-API request failed, falling back", error=str(e)
            )
            return await self.fetch_public_sportsbook_ticks(game_id)

    def _parse_api_response(self, game_id: str, data: dict) -> List[OddsTick]:
        """Parse The-Odds-API JSON response into ``OddsTick`` models.

        Groups outcomes by player name within each bookmaker × market
        combination, requiring both an OVER and UNDER price to emit a tick.

        Args:
            game_id: Pass-through event identifier for the domain model.
            data: Raw JSON dict from The-Odds-API.

        Returns:
            A list of constructed ``OddsTick`` instances.
        """
        ticks: List[OddsTick] = []
        bookmakers = data.get("bookmakers", [])

        for book in bookmakers:
            book_key = book.get("key", "").lower()
            markets = book.get("markets", [])

            for mkt in markets:
                mkt_key = mkt.get("key", "")
                stat_type = _MARKET_MAP.get(mkt_key)
                if not stat_type:
                    continue

                outcomes = mkt.get("outcomes", [])
                by_player: dict = {}
                for oc in outcomes:
                    pname = oc.get("description", "").strip()
                    if not pname:
                        continue
                    side = oc.get("name", "").upper()
                    price = float(oc.get("price", 0.0))
                    point = float(oc.get("point", 0.0))

                    if pname not in by_player:
                        by_player[pname] = {}
                    by_player[pname][side] = (price, point)

                for pname, sides in by_player.items():
                    if "OVER" in sides and "UNDER" in sides:
                        over_price, over_point = sides["OVER"]
                        under_price, _ = sides["UNDER"]

                        pid = f"player_{pname.lower().replace(' ', '_')}"
                        tick = OddsTick(
                            game_id=game_id,
                            player_id=pid,
                            player_name=pname,
                            stat_type=stat_type,
                            bookmaker=book_key,
                            line=over_point,
                            over_price=over_price,
                            under_price=under_price,
                        )
                        ticks.append(tick)

        return ticks

    # ------------------------------------------------------------------
    # Anomaly filter
    # ------------------------------------------------------------------

    def _filter_anomalies(self, ticks: List[OddsTick]) -> List[OddsTick]:
        """Filter out malformed or anomalous ticks.

        Removes ticks with negative/zero prices or lines, or missing fields.

        Args:
            ticks: Unfiltered list of ``OddsTick`` objects.

        Returns:
            Cleaned list of valid ``OddsTick`` objects.
        """
        valid: List[OddsTick] = []
        for t in ticks:
            if t.over_price <= 1.0 or t.under_price <= 1.0:
                continue
            if t.line <= 0:
                continue
            if not t.player_name or not t.bookmaker:
                continue
            valid.append(t)
        return valid

    # ------------------------------------------------------------------
    # Secondary source — Public Bovada web JSON (no API key required)
    # ------------------------------------------------------------------

    async def fetch_public_sportsbook_ticks(self, game_id: str) -> List[OddsTick]:
        """Scrape public Bovada event JSON endpoint as fallback.

        Args:
            game_id: Event identifier.

        Returns:
            List of parsed ``OddsTick`` models, or [] on failure.
        """
        try:
            if not self._session or self._session.closed:
                self._session = aiohttp.ClientSession()

            timeout = aiohttp.ClientTimeout(total=5)
            async with self._session.get(
                _BOVADA_NBA_URL, headers=_SCRAPER_HEADERS, timeout=timeout
            ) as response:
                if response.status == 200:
                    return []
                else:
                    logger.warning("Bovada fallback failed", status=response.status)
                    return []
        except Exception as e:
            logger.warning("Bovada request failed", error=str(e))
            return []

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def start_polling(self, game_id: str) -> None:
        """Begin the continuous odds ingestion loop for the given game.

        Each iteration fetches ticks through the fallback chain, publishes
        them to Redis, and sleeps for ``poll_interval_seconds``.
        Runs until ``close()`` is called.

        Args:
            game_id: The-Odds-API event identifier to poll.
        """
        self._running = True
        logger.info(
            "Starting odds ingestion loop",
            game_id=game_id,
            poll_interval=self.poll_interval_seconds,
        )
        while self._running:
            ticks = await self.fetch_live_odds_ticks(game_id)
            if self.redis_client:
                for tick in ticks:
                    await self.redis_client.publish_odds_tick(tick)
            await asyncio.sleep(self.poll_interval_seconds)

    async def close(self) -> None:
        """Stop the polling loop and release the HTTP session."""
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()
