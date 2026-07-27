import pytest
from src.models.domain import Side, StatType, TradeSignal
from src.execution.kelly_sizer import KellyRiskManager


def test_kelly_sizer_calculation():
    risk_mgr = KellyRiskManager(
        bankroll=10000.0,
        kelly_fraction=0.25,  # Quarter Kelly
        max_wager_percent=0.05,
        max_wager_cap=500.0,
    )

    # Signal: Model True Prob = 0.55, Book Odds = 2.10 (Decimal, +110)
    # EV = 0.55 * 2.10 - 1 = 0.155 (15.5%)
    signal = TradeSignal(
        signal_id="sig_test_1",
        game_id="game_1",
        player_id="player_1",
        player_name="LeBron James",
        stat_type=StatType.POINTS,
        side=Side.OVER,
        line=25.5,
        bookmaker="draftkings",
        bookmaker_odds=2.10,
        fair_odds=1.818,
        ev_percent=0.155,
        kelly_fraction=0.0,
        recommended_wager=0.0,
        consensus_fair_prob=0.50,
    )

    sized_signal = risk_mgr.calculate_wager_size(signal, win_prob=0.55)

    assert sized_signal.kelly_fraction > 0
    assert sized_signal.recommended_wager > 0
    assert sized_signal.recommended_wager <= 500.0
