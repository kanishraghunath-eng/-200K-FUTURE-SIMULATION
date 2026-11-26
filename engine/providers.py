"""Pluggable market-data provider interfaces and local CSV adapter.

Network providers can implement PriceDataProvider without coupling the
simulation engine to a vendor SDK or API credential.
"""
from abc import ABC, abstractmethod
import csv
from pathlib import Path


class PriceDataProvider(ABC):
    name = "abstract"

    @abstractmethod
    def fetch(self, dataset, start=None, end=None):
        """Return {'provider': name, 'source': provenance, 'rows': canonical_rows}."""
        raise NotImplementedError


class CsvProvider(PriceDataProvider):
    name = "csv"

    def __init__(self, path, timestamp_column="date", close_column="close"):
        self.path = Path(path)
        self.timestamp_column = timestamp_column
        self.close_column = close_column

    def fetch(self, dataset, start=None, end=None):
        from .canonical_data import canonicalize_rows
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            raw = list(csv.DictReader(handle))
        rows = canonicalize_rows(raw, self.timestamp_column, self.close_column,
                                 dataset.currency, dataset.price_field)
        if start is not None:
            rows = [r for r in rows if r["timestamp"] >= start]
        if end is not None:
            rows = [r for r in rows if r["timestamp"] <= end]
        return {"provider": self.name, "source": str(self.path),
                "raw_observations": len(raw), "rows": rows}


class ProviderRegistry:
    def __init__(self):
        self._providers = {}

    def register(self, provider):
        name = getattr(provider, "name", None)
        if not name or name == "abstract" or name in self._providers:
            raise ValueError("provider must have a unique non-empty name")
        self._providers[name] = provider

    def get(self, name):
        if name not in self._providers:
            raise ValueError(f"provider is not registered: {name}")
        return self._providers[name]

    def names(self):
        return tuple(sorted(self._providers))
