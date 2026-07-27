import math
from scipy.stats import poisson
from typing import Dict, Optional
from src.models.domain import StatType, PlayerGameState, ModelPricingResult


class PoissonPricer:
    """
    Inhomogeneous Poisson Live Pricing Engine for Player Props.
    Dynamically adjusts accumulation rate based on game pace, foul trouble,
    and blowout risk.
    """

    @staticmethod
    def calculate_foul_penalty(
        fouls: int, period: int, max_fouls: int = 6
    ) -> float:
        """Penalty factor for foul trouble.

        Adjusts threshold dynamically if max_fouls is 5 (WNBA) vs 6 (NBA).
        """
        foul_offset = 6 - max_fouls  # 1 for WNBA, 0 for NBA
        effective_fouls = fouls + foul_offset

        if period == 1 and effective_fouls >= 2:
            return 0.60
        elif period == 2 and effective_fouls >= 3:
            return 0.70
        elif period == 3 and effective_fouls >= 4:
            return 0.75
        elif period >= 4 and effective_fouls >= 5:
            return 0.80
        return 1.0

    @staticmethod
    def calculate_blowout_factor(
        score_diff: int, clock_remaining_seconds: int
    ) -> float:
        """Blowout penalty factor: reduces starters' projected remaining minutes

        if score differential is high in late stages (Q4).
        """
        # If Q4 (< 720s remaining in regulation) and differential > 18
        if clock_remaining_seconds < 720 and abs(score_diff) > 18:
            # Sigmoidal dropoff
            severity = (abs(score_diff) - 18) / 10.0
            return max(0.3, 1.0 - (0.25 * severity))
        return 1.0

    @classmethod
    def price_player_prop(
        cls,
        player_state: PlayerGameState,
        stat_type: StatType,
        target_line: float,
        remaining_regulation_seconds: int,
        period: int = 1,
        score_diff: int = 0,
        pace_multiplier: float = 1.0,
        regulation_minutes: float = 48.0,
        max_fouls: int = 6,
    ) -> ModelPricingResult:
        """Calculates live fair Over/Under probabilities for a given player prop line.

        Args:
            regulation_minutes: Total game regulation minutes (48.0 for NBA, 40.0 for WNBA).
            max_fouls: Maximum allowed fouls before ejection (6 for NBA, 5 for WNBA).
        """
        current_tally = player_state.accumulated_stats.get(stat_type, 0)
        base_rate = player_state.base_rate_per_minute.get(stat_type, 0.5)

        # 1. Remaining Minute Projection
        total_remaining_game_minutes = remaining_regulation_seconds / 60.0

        # Projected fraction of remaining game minutes player will actually play
        if player_state.projected_total_minutes > 0:
            minute_fraction = max(
                0.0,
                (player_state.projected_total_minutes - player_state.elapsed_minutes_played)
                / regulation_minutes,
            )
        else:
            minute_fraction = total_remaining_game_minutes / regulation_minutes

        projected_remaining_minutes = total_remaining_game_minutes * min(1.0, minute_fraction * 1.35)

        # 2. Adjustments
        foul_factor = cls.calculate_foul_penalty(
            player_state.fouls, period, max_fouls=max_fouls
        )
        blowout_factor = cls.calculate_blowout_factor(score_diff, remaining_regulation_seconds)

        effective_rate_per_min = base_rate * pace_multiplier * foul_factor * blowout_factor
        lambda_rem = max(0.001, effective_rate_per_min * projected_remaining_minutes)

        # 3. Poisson Probability Mass Distribution
        # Line is typically X.5 (e.g., 24.5). Needs (target_line + 0.5 - current_tally)
        needed_rem = target_line - current_tally

        if needed_rem < 0:
            # Already hit the over!
            true_over_prob = 0.9999
            true_under_prob = 0.0001
        else:
            # Over threshold is floor(needed_rem)
            k_threshold = math.floor(needed_rem)
            # P(X_rem <= k_threshold) is CDF of Poisson
            cum_under_prob = poisson.cdf(k_threshold, lambda_rem)
            true_under_prob = float(cum_under_prob)
            true_over_prob = max(0.0001, 1.0 - true_under_prob)

        # Clean probability bounds
        true_over_prob = max(0.0001, min(0.9999, true_over_prob))
        true_under_prob = max(0.0001, min(0.9999, true_under_prob))

        fair_over_decimal = round(1.0 / true_over_prob, 3)
        fair_under_decimal = round(1.0 / true_under_prob, 3)

        return ModelPricingResult(
            game_id=player_state.game_id,
            player_id=player_state.player_id,
            stat_type=stat_type,
            target_line=target_line,
            current_stat_tally=current_tally,
            remaining_seconds=remaining_regulation_seconds,
            lambda_rem=round(lambda_rem, 4),
            true_over_prob=round(true_over_prob, 4),
            true_under_prob=round(true_under_prob, 4),
            fair_over_decimal=fair_over_decimal,
            fair_under_decimal=fair_under_decimal,
        )
