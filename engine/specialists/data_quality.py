"""Validation helpers for price series and dated observations."""
import math
from datetime import date, datetime

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

def validate_dated_prices(records, currency=None, expected_interval=None,
                          corporate_actions_reviewed=False):
    """Validate ISO-dated closes; exchange holidays are never guessed."""
    rows = list(records)
    if len(rows) < 3:
        raise ValueError("at least 3 dated observations are required")
    dates, closes = [], []
    for index, row in enumerate(rows):
        raw = row.get("date")
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            try:
                parsed = datetime.combine(date.fromisoformat(str(raw)), datetime.min.time())
            except (TypeError, ValueError):
                raise ValueError(f"invalid ISO date/timestamp at row {index + 1}") from None
        dates.append(parsed)
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            raise ValueError(f"missing or non-numeric close at row {index + 1}") from None
        if not math.isfinite(close) or close <= 0:
            raise ValueError(f"close must be finite and positive at row {index + 1}")
        closes.append(close)
    if any(dates[i] == dates[i-1] for i in range(1, len(dates))):
        raise ValueError("duplicate timestamps detected")
    if any(dates[i] < dates[i-1] for i in range(1, len(dates))):
        raise ValueError("timestamps must be strictly increasing; sort explicitly")
    deltas = [(dates[i] - dates[i-1]).total_seconds() for i in range(1, len(dates))]
    if expected_interval == "calendar_daily" and any(abs(x - 86400) > 1 for x in deltas):
        raise ValueError("timestamps are not equally spaced calendar-daily observations")
    if expected_interval not in (None, "calendar_daily", "business_daily"):
        raise ValueError("unsupported expected_interval")
    if expected_interval == "business_daily" and any(d.weekday() >= 5 for d in dates):
        raise ValueError("weekend observations found in business-daily series")
    gap_indices = [i + 1 for i, seconds in enumerate(deltas)
                   if seconds > (86400 if expected_interval == "calendar_daily" else 3 * 86400)]
    return {"valid": True, "observations": len(rows), "currency": currency,
            "interval_check": expected_interval or "not specified",
            "corporate_actions": "user_reviewed" if corporate_actions_reviewed else "unverified",
            "equal_spacing_seconds": len(set(round(x, 3) for x in deltas)) == 1,
            "possible_missing_session_after_rows": gap_indices,
            "first_timestamp": dates[0].isoformat(), "last_timestamp": dates[-1].isoformat(),
            "price_series": validate_price_series(closes)}
