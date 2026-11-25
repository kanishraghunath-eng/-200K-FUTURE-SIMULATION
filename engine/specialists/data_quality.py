"""Input-quality checks for equally spaced positive close-price series."""
import math


def validate_price_series(prices, min_observations=3, max_abs_return=5.0):
    if not isinstance(min_observations, int) or min_observations < 2:
        raise ValueError("min_observations must be an integer >= 2")
    if not math.isfinite(float(max_abs_return)) or max_abs_return <= 0:
        raise ValueError("max_abs_return must be finite and > 0")
    try:
        values = [float(x) for x in prices]
    except (TypeError, ValueError):
        raise ValueError("prices must be a numeric sequence") from None
    if len(values) < min_observations:
        raise ValueError(f"at least {min_observations} prices are required")
    if any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError("prices must be finite and strictly positive")
    returns = [values[i] / values[i-1] - 1 for i in range(1, len(values))]
    if any(abs(r) > max_abs_return for r in returns):
        raise ValueError("implausible single-period return; inspect input data")
    return {"valid": True, "observations": len(values), "returns": len(returns),
            "min_price": min(values), "max_price": max(values),
            "max_abs_return_observed": max(abs(r) for r in returns)}
