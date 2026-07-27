import math
from typing import Tuple
from scipy.optimize import brentq


class VigStripper:
    """
    Quantitative module for stripping bookmaker margin (vig/juice) to extract
    true consensus probabilities from market odds.
    """

    @staticmethod
    def american_to_decimal(american_odds: float) -> float:
        """Converts American odds (-110, +150) to Decimal odds (1.909, 2.50)."""
        if american_odds > 0:
            return 1.0 + (american_odds / 100.0)
        else:
            return 1.0 + (100.0 / abs(american_odds))

    @staticmethod
    def decimal_to_american(decimal_odds: float) -> float:
        """Converts Decimal odds (1.909, 2.50) to American odds (-110, +150)."""
        if decimal_odds >= 2.0:
            return round((decimal_odds - 1.0) * 100.0, 2)
        else:
            return round(-100.0 / (decimal_odds - 1.0), 2)

    @classmethod
    def multiplicative_dejuice(
        cls, over_decimal: float, under_decimal: float
    ) -> Tuple[float, float]:
        """
        Standard proportional de-juicing.
        Returns (fair_over_prob, fair_under_prob).
        """
        raw_over_prob = 1.0 / over_decimal
        raw_under_prob = 1.0 / under_decimal
        overround = raw_over_prob + raw_under_prob
        return (raw_over_prob / overround, raw_under_prob / overround)

    @classmethod
    def power_dejuice(
        cls, over_decimal: float, under_decimal: float
    ) -> Tuple[float, float]:
        """
        Power method de-juicing: solves (1/o1)^k + (1/o2)^k = 1 for k.
        Accounting for favorite-longshot bias in asymmetrical odds.
        """
        raw_over_prob = 1.0 / over_decimal
        raw_under_prob = 1.0 / under_decimal

        if abs(raw_over_prob + raw_under_prob - 1.0) < 1e-6:
            return (raw_over_prob, raw_under_prob)

        def objective(k: float) -> float:
            return (raw_over_prob ** k) + (raw_under_prob ** k) - 1.0

        # Numerical root finding for exponent k
        try:
            k_opt = brentq(objective, 0.01, 10.0)
            fair_over = raw_over_prob ** k_opt
            fair_under = raw_under_prob ** k_opt
            return (fair_over, fair_under)
        except Exception:
            # Fallback to multiplicative if root solver fails
            return cls.multiplicative_dejuice(over_decimal, under_decimal)

    @classmethod
    def shin_dejuice(
        cls, over_decimal: float, under_decimal: float
    ) -> Tuple[float, float]:
        """
        Shin's method de-juicing: assumes a fraction 'z' of informed traders
        and solves for true probability p.
        Uses exact numerical root-finding to guarantee probabilities sum to 1.0.
        """
        o1, o2 = over_decimal, under_decimal
        p1_raw, p2_raw = 1.0 / o1, 1.0 / o2
        S = p1_raw + p2_raw

        if abs(S - 1.0) < 1e-6:
            return (p1_raw, p2_raw)

        def objective(z: float) -> float:
            term1 = math.sqrt(z**2 + 4 * (1 - z) * (p1_raw**2) / S)
            term2 = math.sqrt(z**2 + 4 * (1 - z) * (p2_raw**2) / S)
            p1 = (term1 - z) / (2 * (1 - z))
            p2 = (term2 - z) / (2 * (1 - z))
            return p1 + p2 - 1.0

        try:
            # z represents proportion of insider trading, must be in [0, 1)
            z_opt = brentq(objective, 0.0, 0.9999)
            term1 = math.sqrt(z_opt**2 + 4 * (1 - z_opt) * (p1_raw**2) / S)
            p1_fair = (term1 - z_opt) / (2 * (1 - z_opt))
            p2_fair = 1.0 - p1_fair
            return (max(0.0001, min(0.9999, p1_fair)), max(0.0001, min(0.9999, p2_fair)))
        except Exception:
            # Fallback to simple approximation if root solver fails
            delta = (S - 1.0) / (S * (o1 + o2 - 2.0) if (o1 + o2 - 2.0) != 0 else 1e-6)
            z = max(0.0, min(0.99, delta))
            term1 = math.sqrt(z**2 + 4 * (1 - z) * (p1_raw**2) / S)
            p1_fair = (term1 - z) / (2 * (1 - z))
            p2_fair = 1.0 - p1_fair
            return (max(0.0001, min(0.9999, p1_fair)), max(0.0001, min(0.9999, p2_fair)))
