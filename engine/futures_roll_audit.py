"""Auditable futures continuous-series roll checks from contract-level observations.

This module never infers roll rules from a vendor continuous ticker. It requires
individual contract observations and an explicitly declared selection method.
"""
from collections import defaultdict
from datetime import date, timedelta
import math


REQUIRED_FIELDS = {
    "date", "contract_symbol", "expiry_date", "close", "volume", "open_interest"
}
ROLL_METHODS = {"calendar", "volume", "open_interest"}
ADJUSTMENT_METHODS = {"none", "difference", "ratio"}


def audit_contract_chain(rows, roll_method, roll_days_before_expiry=5,
                         adjustment_method="ratio"):
    if roll_method not in ROLL_METHODS:
        raise ValueError(f"roll_method must be one of {sorted(ROLL_METHODS)}")
    if adjustment_method not in ADJUSTMENT_METHODS:
        raise ValueError(f"adjustment_method must be one of {sorted(ADJUSTMENT_METHODS)}")
    if not isinstance(roll_days_before_expiry, int) or roll_days_before_expiry < 0:
        raise ValueError("roll_days_before_expiry must be a non-negative integer")

    grouped = defaultdict(list)
    errors = []
    for row_number, source in enumerate(rows, 1):
        missing = REQUIRED_FIELDS - set(source)
        if missing:
            errors.append({
                "code": "missing_contract_fields", "row": row_number,
                "fields": sorted(missing),
            })
            continue
        try:
            trade_date = date.fromisoformat(str(source["date"])[:10])
            expiry_date = date.fromisoformat(str(source["expiry_date"])[:10])
            close = float(source["close"])
            volume = float(source["volume"])
            open_interest = float(source["open_interest"])
            symbol = str(source["contract_symbol"]).strip()
            if not symbol or expiry_date <= trade_date:
                raise ValueError
            if not math.isfinite(close) or close <= 0:
                raise ValueError
            if not math.isfinite(volume) or volume < 0:
                raise ValueError
            if not math.isfinite(open_interest) or open_interest < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append({"code": "invalid_contract_observation", "row": row_number})
            continue
        grouped[trade_date].append({
            "date": trade_date.isoformat(), "contract_symbol": symbol,
            "expiry_date": expiry_date, "close": close, "volume": volume,
            "open_interest": open_interest,
        })

    active = []
    for trade_date in sorted(grouped):
        contracts = grouped[trade_date]
        symbols = [item["contract_symbol"] for item in contracts]
        if len(symbols) != len(set(symbols)):
            errors.append({
                "code": "duplicate_contract_for_date", "date": trade_date.isoformat()
            })
            continue
        if roll_method == "calendar":
            threshold = trade_date + timedelta(days=roll_days_before_expiry)
            eligible = [x for x in contracts if x["expiry_date"] > threshold]
            if not eligible:
                errors.append({
                    "code": "no_calendar_eligible_contract",
                    "date": trade_date.isoformat(),
                })
                continue
            selected = min(eligible, key=lambda x: (x["expiry_date"], x["contract_symbol"]))
        elif roll_method == "volume":
            selected = max(
                contracts,
                key=lambda x: (x["volume"], -x["expiry_date"].toordinal(),
                               x["contract_symbol"]),
            )
        else:
            selected = max(
                contracts,
                key=lambda x: (x["open_interest"], -x["expiry_date"].toordinal(),
                               x["contract_symbol"]),
            )
        active.append({
            "date": trade_date.isoformat(),
            "contract_symbol": selected["contract_symbol"],
            "expiry_date": selected["expiry_date"].isoformat(),
            "close": selected["close"],
        })

    roll_events = []
    for previous, current in zip(active, active[1:]):
        if previous["contract_symbol"] == current["contract_symbol"]:
            continue
        current_date = date.fromisoformat(current["date"])
        same_day = {
            x["contract_symbol"]: x for x in grouped[current_date]
        }
        old_contract = same_day.get(previous["contract_symbol"])
        new_contract = same_day.get(current["contract_symbol"])
        if old_contract is None or new_contract is None:
            errors.append({
                "code": "roll_overlap_missing",
                "date": current["date"],
                "old_contract": previous["contract_symbol"],
                "new_contract": current["contract_symbol"],
            })
            continue
        old_close = old_contract["close"]
        new_close = new_contract["close"]
        roll_events.append({
            "date": current["date"],
            "old_contract": previous["contract_symbol"],
            "new_contract": current["contract_symbol"],
            "old_contract_close": old_close,
            "new_contract_close": new_close,
            "difference_adjustment": old_close - new_close,
            "ratio_adjustment": old_close / new_close,
            "declared_adjustment_method": adjustment_method,
        })

    status = "verified" if active and roll_events and not errors else (
        "insufficient_roll_events" if active and not roll_events and not errors else "failed"
    )
    return {
        "status": status,
        "roll_method": roll_method,
        "roll_days_before_expiry": roll_days_before_expiry,
        "adjustment_method": adjustment_method,
        "input_observations": len(rows),
        "trading_dates": len(grouped),
        "active_contract_observations": len(active),
        "active_contracts": active,
        "roll_events": roll_events,
        "errors": errors,
        "limitations": [
            "Verification applies only to the supplied contract-level dataset and declared rule.",
            "A vendor continuous-futures ticker without contract-level constituents cannot be verified by this audit.",
            "Roll adjustment continuity does not validate margin, liquidity, execution costs, or economic performance.",
        ],
    }
