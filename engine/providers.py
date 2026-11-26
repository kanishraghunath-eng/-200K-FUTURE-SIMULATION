"""Pluggable market-data provider interfaces and local CSV adapter.

Network providers can implement PriceDataProvider without coupling the
simulation engine to a vendor SDK or API credential.
"""
from abc import ABC, abstractmethod
import csv
from pathlib import Path
from datetime import datetime, timezone
import json
import time
import urllib.error
import urllib.parse
import urllib.request


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


class YahooFinanceChartProvider(PriceDataProvider):
    """Public Yahoo chart endpoint adapter; availability/rate limits are external."""
    name = "yahoo"

    def fetch(self, dataset, start=None, end=None):
        interval_map = {"daily": "1d", "weekly": "1wk", "monthly": "1mo",
                        "1m": "1m", "5m": "5m", "15m": "15m",
                        "30m": "30m", "1h": "60m", "4h": "60m"}
        if dataset.interval not in interval_map:
            raise ValueError("Yahoo adapter does not support this interval")
        now = int(datetime.now(timezone.utc).timestamp())
        start_ts = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()) if start else 946684800
        end_ts = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp()) if end else now
        query = urllib.parse.urlencode({"period1": start_ts, "period2": end_ts,
                                        "interval": interval_map[dataset.interval],
                                        "events": "div,splits", "includeAdjustedClose": "true"})
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(dataset.instrument_id) + "?" + query
        request = urllib.request.Request(url, headers={"User-Agent": "200k-future-simulation/2.3"})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        chart = payload.get("chart", {})
        if chart.get("error") or not chart.get("result"):
            raise RuntimeError("Yahoo chart returned no usable result")
        item = chart["result"][0]
        indicators = item.get("indicators", {})
        if dataset.price_field in {"adjusted_close", "adjclose"}:
            values = indicators.get("adjclose", [{}])[0].get("adjclose")
            basis = "provider_adjusted"
        else:
            values = indicators.get("quote", [{}])[0].get("close")
            basis = "raw"
        stamps = item.get("timestamp") or []
        if values is None or len(stamps) != len(values):
            raise RuntimeError("Yahoo price series is missing or misaligned")
        rows = [{"timestamp": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                 "close": value, "currency": dataset.currency,
                 "price_basis": dataset.price_field}
                for ts, value in zip(stamps, values) if value is not None]
        if len(rows) < 3:
            raise RuntimeError("Yahoo returned fewer than three usable observations")
        return {"provider": self.name, "source": url, "raw_observations": len(stamps),
                "provider_price_basis": basis, "rows": rows}


class StooqCsvProvider(PriceDataProvider):
    """Public Stooq daily CSV adapter; symbols must use Stooq's vendor notation."""
    name = "stooq"

    def fetch(self, dataset, start=None, end=None):
        if dataset.interval != "daily":
            raise ValueError("Stooq adapter currently supports daily data only")
        params = {"s": dataset.instrument_id.lower(), "i": "d"}
        if start:
            params["d1"] = start.replace("-", "")
        if end:
            params["d2"] = end.replace("-", "")
        url = "https://stooq.com/q/d/l/?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "200k-future-simulation/2.3"})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8-sig")
        import csv as _csv
        from io import StringIO
        source_rows = list(_csv.DictReader(StringIO(raw)))
        rows = [{"timestamp": row["Date"], "close": row["Close"],
                 "currency": dataset.currency, "price_basis": dataset.price_field}
                for row in source_rows if row.get("Date") and row.get("Close")]
        if len(rows) < 3:
            raise RuntimeError("Stooq returned fewer than three usable observations")
        return {"provider": self.name, "source": url,
                "raw_observations": len(source_rows), "rows": rows}


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
