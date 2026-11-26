"""Market-agnostic metadata contract for reproducible price datasets.

This module describes dataset provenance and sampling conventions. It does not
fetch data, infer exchange calendars, or certify corporate-action adjustments.
"""
from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ASSET_CLASSES = {
    "equity_index", "equity", "etf", "fx", "commodity_spot",
    "commodity_future", "crypto", "other",
}
INTERVALS = {
    "tick", "1m", "5m", "15m", "30m", "1h", "4h",
    "daily", "weekly", "monthly",
}
ADJUSTMENT_BASES = {
    "raw", "split_adjusted", "total_return_adjusted",
    "provider_adjusted", "not_applicable", "unknown",
}


@dataclass(frozen=True)
class DatasetManifest:
    """Explicit context required to interpret a dated close-price series."""

    instrument_id: str
    asset_class: str
    source: str
    currency: str
    interval: str
    price_field: str = "close"
    timezone: Optional[str] = None
    calendar: Optional[str] = None
    adjustment_basis: str = "unknown"
    corporate_actions_reviewed: bool = False
    first_observation: Optional[str] = None
    last_observation: Optional[str] = None
    row_count: Optional[int] = None
    data_sha256: Optional[str] = None
    futures_roll_method: Optional[str] = None
    notes: Optional[str] = None

    def validate(self):
        errors = []
        for name in ("instrument_id", "source", "currency", "interval", "price_field"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{name} must be a non-empty string")

        if self.asset_class not in ASSET_CLASSES:
            errors.append(f"asset_class must be one of: {', '.join(sorted(ASSET_CLASSES))}")
        if isinstance(self.currency, str):
            if len(self.currency) != 3 or not self.currency.isalpha() or self.currency.upper() != self.currency:
                errors.append("currency must be a three-letter uppercase currency/unit code")
        if self.interval not in INTERVALS:
            errors.append(f"interval must be one of: {', '.join(sorted(INTERVALS))}")
        if self.adjustment_basis not in ADJUSTMENT_BASES:
            errors.append(f"adjustment_basis must be one of: {', '.join(sorted(ADJUSTMENT_BASES))}")
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                errors.append("timezone must be a valid IANA timezone name")
        for name in ("first_observation", "last_observation"):
            value = getattr(self, name)
            if value is not None:
                try:
                    date.fromisoformat(value)
                except (TypeError, ValueError):
                    errors.append(f"{name} must be an ISO date (YYYY-MM-DD)")
        if self.first_observation and self.last_observation:
            try:
                if date.fromisoformat(self.first_observation) > date.fromisoformat(self.last_observation):
                    errors.append("first_observation must not be after last_observation")
            except (TypeError, ValueError):
                pass
        if self.row_count is not None and (not isinstance(self.row_count, int) or self.row_count < 0):
            errors.append("row_count must be a non-negative integer")
        if self.data_sha256 is not None:
            digest = self.data_sha256
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                errors.append("data_sha256 must be a 64-character hexadecimal SHA-256 digest")
        if self.asset_class == "commodity_future" and not self.futures_roll_method:
            errors.append("commodity futures require an explicit futures_roll_method")
        if errors:
            raise ValueError("; ".join(errors))
        return {"valid": True, "instrument_id": self.instrument_id,
                "asset_class": self.asset_class, "interval": self.interval}

    def to_dict(self):
        """Return JSON-serializable metadata after validation."""
        self.validate()
        return asdict(self)
