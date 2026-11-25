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


def _parse_iso(raw, row_number):
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            return datetime.combine(date.fromisoformat(str(raw)), datetime.min.time())
        except (TypeError, ValueError):
            raise ValueError(f"invalid ISO date/timestamp at row {row_number}") from None


def audit_dated_prices(records, expected_interval=None, max_abs_return=5.0):
    """Collect detectable data errors and warnings without repairing input rows."""
    if expected_interval not in (None, "calendar_daily", "business_daily"):
        raise ValueError("unsupported expected_interval")
    if not math.isfinite(float(max_abs_return)) or max_abs_return <= 0:
        raise ValueError("max_abs_return must be finite and > 0")
    rows = list(records)
    errors, warnings, parsed, closes = [], [], [], []
    if len(rows) < 3:
        errors.append({"code": "too_few_observations", "message": "at least 3 dated observations are required"})
    for i, row in enumerate(rows, 1):
        try:
            parsed.append(_parse_iso(row.get("date"), i))
        except (AttributeError, ValueError) as exc:
            parsed.append(None)
            errors.append({"code": "invalid_timestamp", "row": i, "message": str(exc)})
        try:
            close = float(row.get("close"))
            if not math.isfinite(close) or close <= 0:
                raise ValueError
            closes.append(close)
        except (AttributeError, TypeError, ValueError):
            closes.append(None)
            errors.append({"code": "invalid_close", "row": i,
                           "message": f"close must be finite and positive at row {i}"})
    seen = {}
    for i, stamp in enumerate(parsed, 1):
        if stamp is None:
            continue
        if stamp in seen:
            errors.append({"code": "duplicate_timestamp", "row": i,
                           "message": f"duplicate timestamp at row {i} (first seen at row {seen[stamp]})"})
        else:
            seen[stamp] = i
        if expected_interval == "business_daily" and stamp.weekday() >= 5:
            errors.append({"code": "weekend_observation", "row": i,
                           "message": f"weekend observation at row {i}"})
    valid_stamps = [(i, d) for i, d in enumerate(parsed, 1) if d is not None]
    for (prev_i, prev), (cur_i, cur) in zip(valid_stamps, valid_stamps[1:]):
        if cur < prev:
            errors.append({"code": "out_of_order_timestamp", "row": cur_i,
                           "message": f"timestamps are not strictly increasing at row {cur_i}"})
        seconds = (cur - prev).total_seconds()
        if expected_interval == "calendar_daily" and abs(seconds - 86400) > 1:
            errors.append({"code": "interval_mismatch", "row": cur_i,
                           "message": f"timestamps are not equally spaced calendar-daily observations at row {cur_i}"})
        elif seconds > 3 * 86400:
            warnings.append({"code": "possible_missing_session", "row": prev_i,
                             "message": f"gap greater than 3 days after row {prev_i}; verify market calendar"})
    valid_prices = [x for x in closes if x is not None]
    for i in range(1, len(closes)):
        if closes[i-1] is not None and closes[i] is not None:
            change = closes[i] / closes[i-1] - 1
            if abs(change) > max_abs_return:
                errors.append({"code": "implausible_return", "row": i + 1,
                               "message": f"implausible single-period return at row {i + 1}"})
    if len(valid_prices) < 3 and len(rows) >= 3:
        # Invalid close rows are already reported above; this adds no duplicate error.
        pass
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "observations": len(rows), "valid_close_count": len(valid_prices),
            "currency": None, "interval_check": expected_interval or "not specified",
            "possible_missing_session_after_rows": sorted({w["row"] for w in warnings})}


def validate_dated_prices(records, currency=None, expected_interval=None,
                          corporate_actions_reviewed=False, collect_all_errors=False,
                          max_abs_return=5.0):
    """Validate ISO-dated closes; fail-fast remains the v2.2.0 default."""
    if collect_all_errors:
        rows = list(records)
        audit = audit_dated_prices(rows, expected_interval, max_abs_return)
        audit["currency"] = currency
        audit["corporate_actions"] = "user_reviewed" if corporate_actions_reviewed else "unverified"
        if audit["valid"]:
            dates = [_parse_iso(row.get("date"), i) for i, row in enumerate(rows, 1)]
            closes = [float(row["close"]) for row in rows]
            deltas = [(dates[i] - dates[i-1]).total_seconds() for i in range(1, len(dates))]
            audit.update({"equal_spacing_seconds": len(set(round(x, 3) for x in deltas)) == 1,
                          "first_timestamp": dates[0].isoformat(), "last_timestamp": dates[-1].isoformat(),
                          "price_series": validate_price_series(closes, max_abs_return=max_abs_return)})
        return audit
    rows = list(records)
    if len(rows) < 3:
        raise ValueError("at least 3 dated observations are required")
    dates, closes = [], []
    for index, row in enumerate(rows):
        parsed = _parse_iso(row.get("date"), index + 1)
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
            "price_series": validate_price_series(closes, max_abs_return=max_abs_return)}
