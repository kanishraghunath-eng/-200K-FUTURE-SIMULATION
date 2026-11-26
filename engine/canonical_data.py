"""Canonical rows and market-interval validation for multi-asset datasets.

Validation is intentionally non-destructive: no sorting, filling, resampling,
timezone guessing, currency conversion, or corporate-action adjustment occurs.
"""
from datetime import datetime
import math


def parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from None


def canonicalize_rows(rows, timestamp_column="date", close_column="close",
                      currency=None, price_basis=None):
    """Map provider columns to timestamp/close/currency/price_basis fields."""
    output = []
    for number, row in enumerate(rows, 1):
        if timestamp_column not in row or close_column not in row:
            raise ValueError(f"missing configured timestamp/close column at row {number}")
        canonical = {
            "timestamp": row[timestamp_column],
            "close": row[close_column],
            "currency": row.get("currency", currency),
            "price_basis": row.get("price_basis", price_basis),
        }
        for field in ("open", "high", "low", "volume"):
            if row.get(field) not in (None, ""):
                canonical[field] = row[field]
        output.append(canonical)
    return output


def validate_canonical_rows(rows, manifest, require_timezone=False):
    """Return structured errors/warnings against a validated DatasetManifest."""
    manifest.validate()
    rows = list(rows)
    errors, warnings, stamps, closes = [], [], [], []
    if len(rows) < 3:
        errors.append({"code": "too_few_observations", "message": "at least 3 observations are required"})
    for i, row in enumerate(rows, 1):
        try:
            stamp = parse_timestamp(row.get("timestamp"))
            if require_timezone and (stamp.tzinfo is None or stamp.utcoffset() is None):
                raise ValueError("explicit timezone offset required")
            stamps.append(stamp)
        except (AttributeError, ValueError) as exc:
            stamps.append(None)
            errors.append({"code": "invalid_timestamp", "row": i, "message": str(exc)})
        try:
            close = float(row.get("close"))
            if not math.isfinite(close) or close <= 0:
                raise ValueError
            closes.append(close)
        except (AttributeError, TypeError, ValueError):
            closes.append(None)
            errors.append({"code": "invalid_close", "row": i})
        if row.get("currency") not in (None, manifest.currency):
            errors.append({"code": "currency_mismatch", "row": i})
        if row.get("price_basis") not in (None, manifest.price_field):
            errors.append({"code": "price_basis_mismatch", "row": i})
        ohlc_fields = ("open", "high", "low")
        present_ohlc = [field for field in ohlc_fields if row.get(field) not in (None, "")]
        if present_ohlc and len(present_ohlc) != 3:
            errors.append({"code": "incomplete_ohlc", "row": i})
        elif len(present_ohlc) == 3 and closes[-1] is not None:
            try:
                o, h, low = (float(row[field]) for field in ohlc_fields)
                if not all(math.isfinite(x) and x > 0 for x in (o, h, low)):
                    raise ValueError
                if h < max(o, low, closes[-1]) or low > min(o, h, closes[-1]):
                    errors.append({"code": "inconsistent_ohlc_range", "row": i})
            except (TypeError, ValueError):
                errors.append({"code": "invalid_ohlc", "row": i})
        if row.get("volume") not in (None, ""):
            try:
                volume = float(row["volume"])
                if not math.isfinite(volume) or volume < 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append({"code": "invalid_volume", "row": i})
    valid_stamps = [(i, stamp) for i, stamp in enumerate(stamps, 1) if stamp is not None]
    awareness = {stamp.utcoffset() is not None for _, stamp in valid_stamps}
    if len(awareness) > 1:
        errors.append({"code": "mixed_timezone_awareness"})
    for (prev_i, prev), (cur_i, cur) in zip(valid_stamps, valid_stamps[1:]):
        if cur <= prev:
            errors.append({"code": "timestamps_not_strictly_increasing", "row": cur_i})
            continue
        delta = (cur - prev).total_seconds()
        interval = manifest.interval
        if interval.endswith(("m", "h")) or interval == "tick":
            expected = {"1m":60,"5m":300,"15m":900,"30m":1800,
                        "1h":3600,"4h":14400}.get(interval)
            if expected and delta != expected:
                warnings.append({"code":"interval_spacing_mismatch","row":cur_i,
                                 "expected_seconds":expected,"actual_seconds":delta})
        elif interval == "daily":
            # Exchange holidays and weekends are calendar-dependent; don't
            # require fixed 24h gaps for daily bars.
            if delta > 4 * 86400:
                warnings.append({"code":"large_daily_gap_check_calendar","row":prev_i})
        elif interval == "weekly" and delta > 14 * 86400:
            warnings.append({"code":"large_weekly_gap","row":prev_i})
        elif interval == "monthly" and delta > 62 * 86400:
            warnings.append({"code":"large_monthly_gap","row":prev_i})
    for i in range(1, len(closes)):
        if closes[i-1] is not None and closes[i] is not None:
            change = abs(closes[i] / closes[i-1] - 1.0)
            if change > 5.0:
                warnings.append({"code":"extreme_return_review_required","row":i+1})
    return {
        "valid": not errors, "errors": errors, "warnings": warnings,
        "observations": len(rows), "valid_close_count": sum(x is not None for x in closes),
        "instrument_id": manifest.instrument_id, "interval": manifest.interval,
        "currency": manifest.currency, "price_field": manifest.price_field,
        "first_timestamp": stamps[0].isoformat() if stamps and stamps[0] else None,
        "last_timestamp": stamps[-1].isoformat() if stamps and stamps[-1] else None,
        "repair_performed": False,
    }
