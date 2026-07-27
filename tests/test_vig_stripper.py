import pytest
from src.pricing.vig_stripper import VigStripper


def test_american_decimal_conversion():
    assert VigStripper.american_to_decimal(-110) == pytest.approx(1.909, abs=1e-3)
    assert VigStripper.american_to_decimal(+150) == pytest.approx(2.50, abs=1e-2)

    assert VigStripper.decimal_to_american(1.909) == pytest.approx(-110, abs=1)
    assert VigStripper.decimal_to_american(2.50) == pytest.approx(150, abs=1)


def test_multiplicative_dejuice():
    # Line -110 / -110 -> 1.909 / 1.909
    fair_over, fair_under = VigStripper.multiplicative_dejuice(1.909, 1.909)
    assert fair_over == pytest.approx(0.50, abs=1e-3)
    assert fair_under == pytest.approx(0.50, abs=1e-3)


def test_power_dejuice():
    # Asymmetric favorite line: 1.30 vs 3.50 (raw prob: 0.769 + 0.285 = 1.054)
    fair_over, fair_under = VigStripper.power_dejuice(1.30, 3.50)
    assert fair_over + fair_under == pytest.approx(1.0, abs=1e-4)
    assert fair_over > 0.70
    assert fair_under < 0.30


def test_shin_dejuice():
    fair_over, fair_under = VigStripper.shin_dejuice(1.909, 1.909)
    assert fair_over + fair_under == pytest.approx(1.0, abs=1e-4)
    assert fair_over == pytest.approx(0.50, abs=1e-2)
