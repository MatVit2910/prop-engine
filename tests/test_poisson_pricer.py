import pytest
from src.models.domain import StatType, PlayerGameState
from src.pricing.poisson_pricer import PoissonPricer


def test_poisson_pricer_over_under():
    player_state = PlayerGameState(
        game_id="game_123",
        player_id="player_curry",
        player_name="Stephen Curry",
        projected_total_minutes=34.0,
        elapsed_minutes_played=12.0,  # End of Q1
        accumulated_stats={StatType.POINTS: 10},
        base_rate_per_minute={StatType.POINTS: 0.85},
    )

    # Line: 28.5 Points, 36 minutes remaining in game (Q2, Q3, Q4)
    pricing = PoissonPricer.price_player_prop(
        player_state=player_state,
        stat_type=StatType.POINTS,
        target_line=28.5,
        remaining_regulation_seconds=2160,  # 36 minutes
        period=2,
    )

    assert pricing.target_line == 28.5
    assert pricing.current_stat_tally == 10
    assert pricing.true_over_prob + pricing.true_under_prob == pytest.approx(1.0, abs=1e-3)
    assert 0.0 < pricing.true_over_prob < 1.0
    assert pricing.fair_over_decimal > 1.0
    assert pricing.fair_under_decimal > 1.0


def test_poisson_pricer_foul_penalty():
    penalty_normal = PoissonPricer.calculate_foul_penalty(fouls=1, period=1)
    penalty_trouble = PoissonPricer.calculate_foul_penalty(fouls=3, period=1)

    assert penalty_normal == 1.0
    assert penalty_trouble < 1.0
