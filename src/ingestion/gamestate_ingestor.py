import asyncio
import aiohttp
import structlog
from typing import Optional, Dict, List, Any
from src.models.domain import PlayByPlayEvent, PlayerGameState, StatType
from src.db.redis_client import RedisClient

logger = structlog.get_logger()

# ESPN public API base URL template — free, unthrottled, no API key required.
ESPN_SUMMARY_URL_TEMPLATE = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary"
)


class GamestateIngestor:
    """Ingests NBA/WNBA play-by-play events via the ESPN public API.

    Fetches live game summaries, parses play-by-play text into domain
    ``PlayByPlayEvent`` models, updates accumulated ``PlayerGameState``
    stats, and persists state to Redis.
    """

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        poll_interval_seconds: float = 2.0,
        league: str = "nba",
    ):
        self.redis_client = redis_client
        self.active_players: Dict[str, PlayerGameState] = {}
        self.poll_interval_seconds = poll_interval_seconds
        self.league = league.lower().strip()
        self.period_seconds = 600 if self.league == "wnba" else 720
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
        # Tracks the most recently ingested play ID for de-duplication.
        self._last_event_id: Optional[str] = None

    def register_player(self, player_state: PlayerGameState) -> None:
        """Register a ``PlayerGameState`` to be tracked and updated by this ingestor.

        Args:
            player_state: The player state model to register. Keyed by
                ``player_state.player_id``.
        """
        self.active_players[player_state.player_id] = player_state

    # ------------------------------------------------------------------
    # ESPN fetch
    # ------------------------------------------------------------------

    async def fetch_espn_game_state(self, game_id: str) -> List[PlayByPlayEvent]:
        """Fetch the latest play-by-play events from the ESPN public API.

        Hits ``site.api.espn.com`` with the given ESPN numeric *game_id*
        (e.g. ``"401584689"``), parses the JSON payload, and returns only
        **new** events not yet seen (de-duplicated via ``_last_event_id``).

        Args:
            game_id: ESPN event identifier.

        Returns:
            A list of new ``PlayByPlayEvent`` domain objects, possibly empty.
        """
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        url = (
            f"{ESPN_SUMMARY_URL_TEMPLATE.format(league=self.league)}?event={game_id}"
        )
        events: List[PlayByPlayEvent] = []
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self._session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    events = self._parse_espn_events(game_id, data)
                else:
                    logger.warning(
                        "ESPN API returned non-200 status", status=response.status
                    )
        except Exception as e:
            logger.warning("ESPN API request failed", error=str(e))

        return events

    # ------------------------------------------------------------------
    # ESPN payload parser
    # ------------------------------------------------------------------

    def _parse_espn_events(
        self, game_id: str, data: Dict[str, Any]
    ) -> List[PlayByPlayEvent]:
        """Parse the ESPN summary JSON into a list of ``PlayByPlayEvent`` models.

        Applies naive text-matching on the ``"text"`` field of each play to
        classify shot makes (2pt / 3pt / FT), rebounds, assists, and fouls.

        De-duplication: plays with an ``id`` ≤ ``_last_event_id`` are skipped.
        After a successful parse pass, ``_last_event_id`` is advanced to the
        last play in the list regardless of whether it yielded an event.

        Args:
            game_id: ESPN event identifier (pass-through for model).
            data: Raw JSON dict from the ESPN summary endpoint.

        Returns:
            A list of parsed ``PlayByPlayEvent`` domain objects.
        """
        events: List[PlayByPlayEvent] = []
        try:
            plays: List[Dict[str, Any]] = data.get("plays", [])

            for play in plays:
                play_id = play.get("id")

                # Skip already-ingested plays.
                if self._last_event_id and int(play_id) <= int(self._last_event_id):
                    continue

                text = play.get("text", "").lower()
                period = play.get("period", {}).get("number", 1)
                clock_display = play.get("clock", {}).get("displayValue", "12:00")

                try:
                    mins, secs = clock_display.split(":")
                    clock_seconds = int(mins) * 60 + int(float(secs))
                except ValueError:
                    clock_seconds = 0

                elapsed = (period - 1) * self.period_seconds + (
                    self.period_seconds - clock_seconds
                )

                stat_delta: Dict[StatType, int] = {}
                points_scored = 0
                event_type = "other"

                # --- Naive text classification ---
                # Production enhancement: use regex or ESPN's own type IDs.
                if "makes" in text or "made" in text:
                    event_type = "made_shot"
                    if "three point" in text:
                        points_scored = 3
                        stat_delta[StatType.POINTS] = 3
                    elif "free throw" in text:
                        points_scored = 1
                        stat_delta[StatType.POINTS] = 1
                    else:
                        points_scored = 2
                        stat_delta[StatType.POINTS] = 2
                elif "rebound" in text:
                    event_type = "rebound"
                    stat_delta[StatType.REBOUNDS] = 1
                elif "assist" in text:
                    event_type = "assist"
                    stat_delta[StatType.ASSISTS] = 1
                elif "foul" in text:
                    event_type = "foul"

                if stat_delta or event_type == "foul":
                    # TODO: Map ESPN participant IDs → internal player_id.
                    # For now, route all events to the first registered player.
                    if self.active_players:
                        pid = next(iter(self.active_players))
                    else:
                        pid = "player_mock"

                    events.append(
                        PlayByPlayEvent(
                            game_id=game_id,
                            event_id=play_id,
                            period=period,
                            clock_seconds=clock_seconds,
                            elapsed_total_seconds=elapsed,
                            player_id=pid,
                            player_name="Mapped Player",
                            event_type=event_type,
                            points_scored=points_scored,
                            stat_delta=stat_delta,
                            raw_payload=play,
                        )
                    )

            # Advance the cursor to the latest play regardless of event emission.
            if plays:
                self._last_event_id = plays[-1].get("id")

        except Exception as e:
            logger.error("Error parsing ESPN payload", error=str(e))

        return events

    # ------------------------------------------------------------------
    # State mutation
    # ------------------------------------------------------------------

    async def process_event(self, event: PlayByPlayEvent) -> None:
        """Apply a single play-by-play event to the tracked player state.

        Updates ``accumulated_stats``, ``fouls``, and ``elapsed_minutes_played``
        on the matching ``PlayerGameState``, then persists to Redis.

        Args:
            event: The parsed play-by-play event to apply.
        """
        if not event.player_id or event.player_id not in self.active_players:
            return

        player = self.active_players[event.player_id]

        # Update stats
        for stat, delta in event.stat_delta.items():
            current = player.accumulated_stats.get(stat, 0)
            player.accumulated_stats[stat] = current + delta

        # Update foul count if applicable
        if event.event_type == "foul":
            player.fouls += 1

        # Update elapsed playing time approximation (e.g. 0.4 min increment)
        player.elapsed_minutes_played = min(
            player.projected_total_minutes, player.elapsed_minutes_played + 0.4
        )

        logger.info(
            "Updated player state",
            player=player.player_name,
            stats=player.accumulated_stats,
            fouls=player.fouls,
        )

        if self.redis_client:
            await self.redis_client.save_player_state(player)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def start_polling(self, game_id: str) -> None:
        """Begin the continuous ESPN polling loop for the given game.

        Runs until ``close()`` is called.  Each iteration fetches new plays
        from ESPN, applies them via ``process_event``, and sleeps for
        ``poll_interval_seconds``.

        Args:
            game_id: ESPN event identifier to poll.
        """
        self._running = True
        logger.info(
            "Starting ESPN gamestate ingestion loop",
            game_id=game_id,
            poll_interval=self.poll_interval_seconds,
        )
        while self._running:
            events = await self.fetch_espn_game_state(game_id)
            for evt in events:
                await self.process_event(evt)

            await asyncio.sleep(self.poll_interval_seconds)

    async def close(self) -> None:
        """Stop the polling loop and release the HTTP session."""
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()
