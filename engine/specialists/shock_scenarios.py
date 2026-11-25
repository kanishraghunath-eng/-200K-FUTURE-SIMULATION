"""Transparent deterministic price-shock scenarios; no forecasting claim."""
import math


def apply_price_shock(prices, shock_pct, start_index=0):
    values = [float(x) for x in prices]
    if not values or any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError("prices must be a non-empty sequence of finite positive values")
    if not math.isfinite(float(shock_pct)) or shock_pct <= -100:
        raise ValueError("shock_pct must be finite and greater than -100")
    if not isinstance(start_index, int) or not 0 <= start_index < len(values):
        raise ValueError("start_index must point to an existing observation")
    multiplier = 1 + shock_pct / 100
    return [x if i < start_index else x * multiplier for i, x in enumerate(values)]
