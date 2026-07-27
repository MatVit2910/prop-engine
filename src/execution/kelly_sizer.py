from src.models.domain import TradeSignal, Side


class KellyRiskManager:
    """
    Risk Management engine that applies Fractional Kelly Criterion
    and exposure limits to trade signals.
    """

    def __init__(
        self,
        bankroll: float = 10000.0,
        kelly_fraction: float = 0.125,  # Quarter-Kelly (0.125) or Eighth-Kelly
        max_wager_percent: float = 0.025,  # Max 2.5% of bankroll per bet
        max_wager_cap: float = 500.0,  # Absolute max bet limit ($)
    ):
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.max_wager_percent = max_wager_percent
        self.max_wager_cap = max_wager_cap

    def calculate_wager_size(
        self, signal: TradeSignal, win_prob: float
    ) -> TradeSignal:
        """
        Calculates optimal position size using fractional Kelly sizing.
        Updates signal with kelly_fraction and recommended_wager.
        """
        b = signal.bookmaker_odds - 1.0  # Net odds ratio

        if b <= 0 or signal.ev_percent <= 0:
            signal.kelly_fraction = 0.0
            signal.recommended_wager = 0.0
            return signal

        # Full Kelly fraction f* = (p * b - q) / b = EV / b
        full_kelly = signal.ev_percent / b
        
        # Apply fractional multiplier (e.g. Quarter Kelly)
        fractional_kelly = max(0.0, full_kelly * self.kelly_fraction)

        # Raw dollar wager
        raw_wager = self.bankroll * fractional_kelly

        # Apply hard caps
        max_allowed_wager = min(
            self.bankroll * self.max_wager_percent, self.max_wager_cap
        )
        final_wager = min(raw_wager, max_allowed_wager)

        signal.kelly_fraction = round(fractional_kelly, 4)
        signal.recommended_wager = round(final_wager, 2)

        return signal
