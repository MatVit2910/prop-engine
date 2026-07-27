from scipy.optimize import brentq
import math

def shin_dejuice(over_decimal: float, under_decimal: float):
    o1, o2 = over_decimal, under_decimal
    p1_raw, p2_raw = 1.0 / o1, 1.0 / o2
    S = p1_raw + p2_raw

    if abs(S - 1.0) < 1e-6:
        return (p1_raw, p2_raw)

    def objective(z):
        # Using exact True Probability formula for Shin's method
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
        return (p1_fair, p2_fair)
    except Exception:
        # Fallback to simple approximation if root solver fails
        delta = (S - 1.0) / (S * (o1 + o2 - 2.0) if (o1 + o2 - 2.0) != 0 else 1e-6)
        z = max(0.0, min(0.99, delta))
        term1 = math.sqrt(z**2 + 4 * (1 - z) * (p1_raw**2) / S)
        p1_fair = (term1 - z) / (2 * (1 - z))
        p2_fair = 1.0 - p1_fair
        return (p1_fair, p2_fair)

print(shin_dejuice(1.90, 1.90))
print(shin_dejuice(1.90, 1.85))
