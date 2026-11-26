"""Validated instrument and observation metadata for multi-market inputs.

This module defines metadata only; it does not fetch, repair, or resample prices.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ASSET_CLASSES = {
    "equity", "equity_index", "etf", "fx", "commodity_spot",
    "commodity_future", "bond", "bond_index", "crypto_spot",
    "crypto_derivative", "other",
}
PRICE_BASES = {"close", "adjusted_close", "settlement", "mid", "last"}
CORPORATE_ACTION_STATES = {"reviewed", "unverified", "not_applicable"}


@dataclass(frozen=True)
class InstrumentMetadata:
    """Explicit context required to interpret a dated price series.

    periods_per_year must be chosen for the supplied observation interval and
    market convention; no universal 252-period assumption is made here.
    """
    symbol: str
    asset_class: str
    venue: str
    timezone: str
    quote_currency: str
    interval: str
    periods_per_year: int
    price_basis: str
    calendar_id: Optional[str] = None
    corporate_actions: str = "unverified"
    contract_roll_method: Optional[str] = None
    provider: Optional[str] = None

    def __post_init__(self):
        for field in ("symbol", "asset_class", "venue", "timezone",
                      "quote_currency", "interval", "price_basis"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
        if self.asset_class not in ASSET_CLASSES:
            raise ValueError(f"unsupported asset_class: {self.asset_class}")
        if self.price_basis not in PRICE_BASES:
            raise ValueError(f"unsupported price_basis: {self.price_basis}")
        if self.corporate_actions not in CORPORATE_ACTION_STATES:
            raise ValueError("corporate_actions must be reviewed, unverified, or not_applicable")
        if not isinstance(self.periods_per_year, int) or isinstance(self.periods_per_year, bool) or self.periods_per_year <= 0:
            raise ValueError("periods_per_year must be a positive integer")
        if self.interval != "irregular" and not self.interval.endswith(("s", "m", "h", "d", "w")):
            raise ValueError("interval must use a documented unit (e.g. 1m, 1h, 1d, 1w) or 'irregular'")
        if self.asset_class == "commodity_future" and not self.contract_roll_method:
            raise ValueError("commodity futures require an explicit contract_roll_method")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown IANA timezone: {self.timezone}") from None
        if self.quote_currency != self.quote_currency.upper():
            raise ValueError("quote_currency must be uppercase")

    def to_dict(self):
        """Return a JSON-friendly metadata mapping."""
        return asdict(self)


def validate_observation_timestamp(value, metadata):
    """Parse an ISO timestamp and require timezone-aware input.

    Naive timestamps are rejected so providers cannot silently inherit a
    machine-local timezone. Conversion to market timezone is left to adapters.
    """
    if not isinstance(metadata, InstrumentMetadata):
        raise TypeError("metadata must be an InstrumentMetadata instance")
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamp must be ISO-8601") from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("timestamp must include an explicit timezone offset")
    return stamp
