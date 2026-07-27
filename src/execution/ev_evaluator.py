from typing import Optional
from src.models.domain import Side, StatType, ModelPricingResult, OddsTick, TradeSignal


class EVEvaluator:
    """
    Evaluates expected value (+EV) of available market quotes against
    internal quantitative model true probabilities.
    """

    def __init__(self, min_ev_threshold: float = 0.03, min_edge_over_consensus: float = 0.015):
        self.min_ev_threshold = min_ev_threshold
        self.min_edge_over_consensus = min_edge_over_consensus

    def evaluate_quote(
        self,
        pricing: ModelPricingResult,
        quote: OddsTick,
        consensus_fair_over_prob: float,
        consensus_fair_under_prob: float,
        player_name: str,
    ) -> Optional[TradeSignal]:
        """
        Compares quote against model pricing to identify +EV opportunities on Over or Under.
        """
        if pricing.target_line != quote.line:
            return None

        signals = []

        # 1. Evaluate OVER Side
        model_over_p = pricing.true_over_prob
        book_over_odds = quote.over_price  # Decimal
        ev_over = (model_over_p * book_over_odds) - 1.0
        edge_over = model_over_p - consensus_fair_over_prob

        if ev_over >= self.min_ev_threshold and edge_over >= self.min_edge_over_consensus:
            signal_id = f"SIG-{quote.game_id}-{quote.player_id}-OVER-{int(quote.line * 10)}"
            signals.append(
                TradeSignal(
                    signal_id=signal_id,
                    game_id=quote.game_id,
                    player_id=quote.player_id,
                    player_name=player_name,
                    stat_type=pricing.stat_type,
                    side=Side.OVER,
                    line=quote.line,
                    bookmaker=quote.bookmaker,
                    bookmaker_odds=book_over_odds,
                    fair_odds=pricing.fair_over_decimal,
                    ev_percent=round(ev_over, 4),
                    kelly_fraction=0.0,  # Will be populated by KellyRiskManager
                    recommended_wager=0.0,
                    consensus_fair_prob=round(consensus_fair_over_prob, 4),
                )
            )

        # 2. Evaluate UNDER Side
        model_under_p = pricing.true_under_prob
        book_under_odds = quote.under_price  # Decimal
        ev_under = (model_under_p * book_under_odds) - 1.0
        edge_under = model_under_p - consensus_fair_under_prob

        if ev_under >= self.min_ev_threshold and edge_under >= self.min_edge_over_consensus:
            signal_id = f"SIG-{quote.game_id}-{quote.player_id}-UNDER-{int(quote.line * 10)}"
            signals.append(
                TradeSignal(
                    signal_id=signal_id,
                    game_id=quote.game_id,
                    player_id=quote.player_id,
                    player_name=player_name,
                    stat_type=pricing.stat_type,
                    side=Side.UNDER,
                    line=quote.line,
                    bookmaker=quote.bookmaker,
                    bookmaker_odds=book_under_odds,
                    fair_odds=pricing.fair_under_decimal,
                    ev_percent=round(ev_under, 4),
                    kelly_fraction=0.0,
                    recommended_wager=0.0,
                    consensus_fair_prob=round(consensus_fair_under_prob, 4),
                )
            )

        # Return highest EV signal if available
        if signals:
            signals.sort(key=lambda s: s.ev_percent, reverse=True)
            return signals[0]

        return None
