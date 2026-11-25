"""Historical volatility diagnostics from equally spaced positive prices."""
import math


def volatility_profile(prices, periods_per_year=252):
    values = [float(x) for x in prices]
    if len(values) < 3 or any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError("at least three finite, positive prices are required")
    if not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    returns = [math.log(values[i] / values[i-1]) for i in range(1, len(values))]
    mean = sum(returns) / len(returns)
    variance = sum((x-mean)**2 for x in returns) / (len(returns)-1)
    daily = math.sqrt(variance)
    return {"log_return_count": len(returns), "mean_log_return": mean,
            "period_volatility": daily, "annualized_volatility": daily * math.sqrt(periods_per_year),
            "periods_per_year": periods_per_year}
