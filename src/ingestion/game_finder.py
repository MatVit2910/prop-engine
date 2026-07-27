import asyncio
import aiohttp
import structlog
from typing import List, Optional, Dict, Any
from src.models.domain import LiveGameInfo
from src.config import settings

logger = structlog.get_logger()

# ESPN Scoreboard Base URL
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard"
)

# Headers for HTTP requests
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class GameDiscoveryService:
    """Discovers live games currently in progress for NBA or WNBA.

    Queries the free ESPN Scoreboard API and The-Odds-API to find live games,
    match event IDs, and return active ``LiveGameInfo`` models.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.THE_ODDS_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    async def discover_live_games(
        self, league: str = "nba"
    ) -> List[LiveGameInfo]:
        """Discover live in-progress games for the specified league ('nba' or 'wnba').

        Args:
            league: Basketball league identifier ('nba' or 'wnba').

        Returns:
            List of ``LiveGameInfo`` objects representing live or upcoming games.
        """
        league_clean = league.lower().strip()
        if league_clean not in ("nba", "wnba"):
            league_clean = "nba"

        espn_games = await self.fetch_espn_scoreboard(league_clean)
        odds_events = await self.fetch_odds_api_events(league_clean)

        def _get_team_tokens(name: str) -> set:
            name_clean = name.lower().replace("l.a.", "la").replace(".", "")
            return {w for w in name_clean.split() if len(w) > 2}

        # Fuse ESPN telemetry with Odds-API event hashes
        live_games: List[LiveGameInfo] = []

        for eg in espn_games:
            matched_odds_id = None
            eg_home_tokens = _get_team_tokens(eg.home_team)
            eg_away_tokens = _get_team_tokens(eg.away_team)

            # Attempt to match Odds-API hash by team name tokens
            for oe in odds_events:
                oe_home_tokens = _get_team_tokens(oe.get("home_team", ""))
                oe_away_tokens = _get_team_tokens(oe.get("away_team", ""))

                home_match = bool(eg_home_tokens & oe_home_tokens)
                away_match = bool(eg_away_tokens & oe_away_tokens)

                if home_match or away_match:
                    matched_odds_id = oe.get("id")
                    break

            eg.odds_api_id = matched_odds_id
            live_games.append(eg)

        return live_games

    async def fetch_espn_scoreboard(self, league: str) -> List[LiveGameInfo]:
        """Fetch active/live games from the ESPN scoreboard API.

        Args:
            league: Basketball league identifier ('nba' or 'wnba').

        Returns:
            List of ``LiveGameInfo`` parsed from ESPN JSON.
        """
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        url = ESPN_SCOREBOARD_URL.format(league=league)
        games: List[LiveGameInfo] = []

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self._session.get(
                url, headers=_HEADERS, timeout=timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    events = data.get("events", [])
                    for evt in events:
                        espn_id = str(evt.get("id"))
                        status_obj = evt.get("status", {}).get("type", {})
                        state = status_obj.get("state", "").lower()

                        # Status mapping: "in" means currently in progress
                        status_str = "IN_PROGRESS" if state == "in" else state.upper()

                        competitions = evt.get("competitions", [{}])[0]
                        competitors = competitions.get("competitors", [])

                        home_team, away_team = "Home Team", "Away Team"
                        for comp in competitors:
                            if comp.get("homeAway") == "home":
                                home_team = comp.get("team", {}).get(
                                    "displayName", "Home Team"
                                )
                            elif comp.get("homeAway") == "away":
                                away_team = comp.get("team", {}).get(
                                    "displayName", "Away Team"
                                )

                        period = evt.get("status", {}).get("period", 1)
                        clock = evt.get("status", {}).get(
                            "displayValue", "12:00"
                        )
                        raw_date = evt.get("date")
                        chicago_display = None
                        if raw_date:
                            try:
                                from datetime import datetime
                                import zoneinfo
                                dt_utc = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                                dt_chicago = dt_utc.astimezone(zoneinfo.ZoneInfo("America/Chicago"))
                                chicago_display = dt_chicago.strftime("%a, %b %d @ %I:%M %p (Chicago Time)")
                            except Exception:
                                chicago_display = raw_date

                        games.append(
                            LiveGameInfo(
                                game_id=f"{league}_{espn_id}",
                                league=league,
                                home_team=home_team,
                                away_team=away_team,
                                period=period,
                                clock_display=clock,
                                status=status_str,
                                espn_game_id=espn_id,
                                start_time_utc=raw_date,
                                scheduled_chicago_display=chicago_display,
                            )
                        )
                else:
                    logger.warning(
                        "ESPN Scoreboard returned non-200 status",
                        status=response.status,
                        league=league,
                    )
        except Exception as e:
            logger.warning(
                "ESPN Scoreboard request failed", error=str(e), league=league
            )

        return games

    async def fetch_odds_api_events(self, league: str) -> List[Dict[str, Any]]:
        """Fetch event listings from The-Odds-API.

        Args:
            league: Basketball league identifier ('nba' or 'wnba').

        Returns:
            List of event raw dicts from The-Odds-API.
        """
        if not self.api_key or self.api_key == "your_the_odds_api_key_here":
            return []

        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        sport_key = f"basketball_{league}"
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
        params = {"apiKey": self.api_key}

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self._session.get(
                url, params=params, timeout=timeout
            ) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.warning(
                "The-Odds-API event discovery failed", error=str(e), league=league
            )

        return []

    async def fetch_game_roster(self, espn_game_id: str, league: str = "nba") -> List[str]:
        """Fetch live active player rosters for a given ESPN game ID.
        Supports both IN_PROGRESS and PREGAME/UPCOMING game statuses.

        Args:
            espn_game_id: ESPN game identifier.
            league: Basketball league ('nba' or 'wnba').

        Returns:
            List of player display names parsed from ESPN boxscore and team JSON.
        """
        if not espn_game_id:
            return []

        league_clean = league.lower().strip()
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league_clean}/summary?event={espn_game_id}"
        players: List[str] = []
        team_ids: List[str] = []

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=_HEADERS, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        boxscore = data.get("boxscore", {})
                        
                        # Stage 1: In-progress boxscore players
                        player_teams = boxscore.get("players", [])
                        for pteam in player_teams:
                            stats = pteam.get("statistics", [])
                            for stat_grp in stats:
                                athletes = stat_grp.get("athletes", [])
                                for ath in athletes:
                                    athlete_obj = ath.get("athlete", {})
                                    name = athlete_obj.get("displayName") or athlete_obj.get("shortName")
                                    if name and name not in players:
                                        players.append(name)

                        # Extract team IDs for pregame fallback
                        for titem in boxscore.get("teams", []):
                            tid = str(titem.get("team", {}).get("id", ""))
                            if tid and tid not in team_ids:
                                team_ids.append(tid)

                        # Stage 2: Stat leaders
                        for leader_grp in data.get("leaders", []):
                            for cat in leader_grp.get("leaders", []):
                                for l_ath in cat.get("leaders", []):
                                    name = l_ath.get("athlete", {}).get("displayName")
                                    if name and name not in players:
                                        players.append(name)

                # Stage 3: Pregame full team roster fallback
                if len(players) < 5 and team_ids:
                    for tid in team_ids:
                        team_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league_clean}/teams/{tid}/roster"
                        try:
                            async with session.get(team_url, headers=_HEADERS, timeout=timeout) as t_resp:
                                if t_resp.status == 200:
                                    t_data = await t_resp.json()
                                    for ath in t_data.get("athletes", []):
                                        name = ath.get("fullName") or ath.get("displayName")
                                        if name and name not in players:
                                            players.append(name)
                        except Exception:
                            pass
        except Exception as e:
            logger.warning("ESPN game summary roster fetch failed", error=str(e), espn_id=espn_game_id)

        return players

    async def fetch_game_roster_by_team(self, espn_game_id: str, league: str = "nba") -> Dict[str, List[str]]:
        """Fetch player rosters grouped by team for a given ESPN game ID.

        Args:
            espn_game_id: ESPN game identifier.
            league: Basketball league ('nba' or 'wnba').

        Returns:
            Dict mapping team display name to list of player names.
        """
        if not espn_game_id:
            return {}

        league_clean = league.lower().strip()
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league_clean}/summary?event={espn_game_id}"
        roster_by_team: Dict[str, List[str]] = {}

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=_HEADERS, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        boxscore = data.get("boxscore", {})

                        # Collect team IDs and names
                        teams_info: List[Dict[str, str]] = []
                        for titem in boxscore.get("teams", []):
                            team = titem.get("team", {})
                            tid = str(team.get("id", ""))
                            tname = team.get("displayName") or team.get("shortDisplayName") or f"Team {tid}"
                            if tid:
                                teams_info.append({"id": tid, "name": tname})
                                roster_by_team[tname] = []

                # Fetch each team's roster
                for tinfo in teams_info:
                    team_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league_clean}/teams/{tinfo['id']}/roster"
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(team_url, headers=_HEADERS, timeout=timeout) as t_resp:
                                if t_resp.status == 200:
                                    t_data = await t_resp.json()
                                    for ath in t_data.get("athletes", []):
                                        name = ath.get("fullName") or ath.get("displayName")
                                        if name:
                                            roster_by_team[tinfo["name"]].append(name)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("ESPN team roster fetch failed", error=str(e), espn_id=espn_game_id)

        return roster_by_team

    async def close(self) -> None:
        """Release HTTP session resources."""
        if self._session and not self._session.closed:
            await self._session.close()
