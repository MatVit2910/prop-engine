from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class StatType(str, Enum):
    POINTS = "points"
    REBOUNDS = "rebounds"
    ASSISTS = "assists"
    POINTS_REBOUNDS_ASSISTS = "points_rebounds_assists"
    THREE_POINTERS_MADE = "three_pointers_made"


class Bookmaker(str, Enum):
    PINNACLE = "pinnacle"
    CIRCA = "circa"
    DRAFTKINGS = "draftkings"
    FANDUEL = "fanduel"
    BETMGM = "betmgm"
    CAESARS = "caesars"


class Side(str, Enum):
    OVER = "OVER"
    UNDER = "UNDER"


class LiveGameInfo(BaseModel):
    game_id: str
    league: str = "nba"
    home_team: str
    away_team: str
    period: int = 1
    clock_display: str = "12:00"
    status: str = "IN_PROGRESS"  # IN_PROGRESS, PREGAME, HALFTIME, FINAL
    espn_game_id: Optional[str] = None
    odds_api_id: Optional[str] = None
    start_time_utc: Optional[str] = None
    scheduled_chicago_display: Optional[str] = None


class OddsTick(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    game_id: str
    player_id: str
    player_name: str
    stat_type: StatType
    bookmaker: str
    line: float
    over_price: float  # Decimal odds (e.g. 1.91)
    under_price: float  # Decimal odds (e.g. 1.91)
    implied_over_prob: Optional[float] = None
    implied_under_prob: Optional[float] = None


class PlayByPlayEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    game_id: str
    event_id: str
    period: int  # 1, 2, 3, 4, 5+ for OT
    clock_seconds: int  # Seconds remaining in period (0-720)
    elapsed_total_seconds: int  # Total elapsed seconds in regulation (0-2880)
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    event_type: str  # e.g., 'made_shot', 'missed_shot', 'free_throw', 'foul', 'sub'
    points_scored: int = 0
    stat_delta: Dict[StatType, int] = Field(default_factory=dict)
    home_score: int = 0
    away_score: int = 0
    raw_payload: Dict[str, Any] = Field(default_factory=dict)


class PlayerGameState(BaseModel):
    game_id: str
    player_id: str
    player_name: str
    projected_total_minutes: float = 34.0
    elapsed_minutes_played: float = 0.0
    accumulated_stats: Dict[StatType, int] = Field(
        default_factory=lambda: {
            StatType.POINTS: 0,
            StatType.REBOUNDS: 0,
            StatType.ASSISTS: 0,
        }
    )
    fouls: int = 0
    is_on_court: bool = True
    base_rate_per_minute: Dict[StatType, float] = Field(
        default_factory=lambda: {
            StatType.POINTS: 0.65,
            StatType.REBOUNDS: 0.20,
            StatType.ASSISTS: 0.15,
        }
    )


class ModelPricingResult(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    game_id: str
    player_id: str
    stat_type: StatType
    target_line: float
    current_stat_tally: int
    remaining_seconds: int
    lambda_rem: float
    true_over_prob: float
    true_under_prob: float
    fair_over_decimal: float
    fair_under_decimal: float


class TradeSignal(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    signal_id: str
    game_id: str
    player_id: str
    player_name: str
    stat_type: StatType
    side: Side
    line: float
    bookmaker: str
    bookmaker_odds: float
    fair_odds: float
    ev_percent: float
    kelly_fraction: float
    recommended_wager: float
    consensus_fair_prob: float
    status: str = "LOGGED"
