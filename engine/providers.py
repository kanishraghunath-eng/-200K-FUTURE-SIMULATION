"""Pluggable market-data provider interfaces and local CSV adapter.

Network providers can implement PriceDataProvider without coupling the
simulation engine to a vendor SDK or API credential.
"""
from abc import ABC, abstractmethod
import csv
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import json
import os
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
                "source_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
                "raw_observations": len(raw), "rows": rows}


class YahooFinanceChartProvider(PriceDataProvider):
    """Public Yahoo chart endpoint adapter; availability/rate limits are external."""
    name = "yahoo"

    def __init__(self, include_ohlcv=True):
        self.include_ohlcv = bool(include_ohlcv)

    def fetch(self, dataset, start=None, end=None):
        interval_map = {"daily": "1d", "weekly": "1wk", "monthly": "1mo",
                        "1m": "1m", "5m": "5m", "15m": "15m",
                        "30m": "30m", "1h": "60m"}
        if dataset.interval not in interval_map:
            raise ValueError("Yahoo adapter does not support this interval")
        if dataset.price_field not in {"close", "adjusted_close"}:
            raise ValueError("Yahoo adapter supports close or adjusted_close only")
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
        quote = indicators.get("quote", [{}])[0]
        adjusted = dataset.price_field in {"adjusted_close", "adjclose"}
        if adjusted:
            values = indicators.get("adjclose", [{}])[0].get("adjclose")
            basis = "provider_adjusted"
        else:
            values = quote.get("close")
            basis = "raw"
        stamps = item.get("timestamp") or []
        if values is None or len(stamps) != len(values):
            raise RuntimeError("Yahoo price series is missing or misaligned")
        rows = []
        for index, (stamp, value) in enumerate(zip(stamps, values)):
            if value is None:
                continue
            row = {"timestamp": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                   "close": value, "currency": dataset.currency,
                   "price_basis": dataset.price_field}
            if not adjusted and self.include_ohlcv:
                for field in ("open", "high", "low", "volume"):
                    series = quote.get(field)
                    if series and index < len(series) and series[index] is not None:
                        row[field] = series[index]
            rows.append(row)
        if len(rows) < 3:
            raise RuntimeError("Yahoo returned fewer than three usable observations")
        return {"provider": self.name, "source": url, "raw_observations": len(stamps),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "provider_price_basis": basis,
                "ohlcv_included": bool(not adjusted and self.include_ohlcv),
                "rows": rows}


class StooqCsvProvider(PriceDataProvider):
    """Public Stooq daily CSV adapter; symbols must use Stooq's vendor notation."""
    name = "stooq"

    def fetch(self, dataset, start=None, end=None):
        if dataset.interval != "daily":
            raise ValueError("Stooq adapter currently supports daily data only")
        if dataset.price_field != "close":
            raise ValueError("Stooq adapter supplies raw close only")
        params = {"s": dataset.instrument_id.lower(), "i": "d"}
        if start:
            params["d1"] = start.replace("-", "")
        if end:
            params["d2"] = end.replace("-", "")
        url = "https://stooq.com/q/d/l/?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "200k-future-simulation/2.3"})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw_bytes = response.read()
        raw = raw_bytes.decode("utf-8-sig")
        import csv as _csv
        from io import StringIO
        source_rows = list(_csv.DictReader(StringIO(raw)))
        rows = []
        for source_row in source_rows:
            if not source_row.get("Date") or not source_row.get("Close"):
                continue
            row = {"timestamp": source_row["Date"], "close": source_row["Close"],
                   "currency": dataset.currency, "price_basis": dataset.price_field}
            for field in ("Open", "High", "Low", "Volume"):
                if source_row.get(field) not in (None, ""):
                    row[field.lower()] = source_row[field]
            rows.append(row)
        if len(rows) < 3:
            raise RuntimeError("Stooq returned fewer than three usable observations")
        return {"provider": self.name, "source": url,
                "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "raw_observations": len(source_rows), "rows": rows}


class EodhdProvider(PriceDataProvider):
    """EODHD daily EOD adapter; the public demo token has limited symbol coverage."""
    name = "eodhd"

    def fetch(self, dataset, start=None, end=None):
        if dataset.interval != "daily":
            raise ValueError("EODHD adapter currently supports daily data only")
        if dataset.price_field not in {"close", "adjusted_close"}:
            raise ValueError("EODHD adapter supports close or adjusted_close only")
        token = os.environ.get("EODHD_API_TOKEN", "demo")
        params = {"api_token": token, "period": "d", "fmt": "json"}
        if start:
            params["from"] = start[:10]
        if end:
            params["to"] = end[:10]
        url = "https://eodhd.com/api/eod/" + urllib.parse.quote(dataset.instrument_id) + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "200k-future-simulation/2.3",
                                                       "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("EODHD returned a non-list EOD payload")
        rows = []
        field = "adjusted_close" if dataset.price_field == "adjusted_close" else "close"
        for item in payload:
            value = item.get(field)
            if value is None:
                continue
            row = {"timestamp": item.get("date"), "close": value,
                   "currency": dataset.currency, "price_basis": dataset.price_field}
            if dataset.price_field == "close":
                for field in ("open", "high", "low", "volume"):
                    if item.get(field) is not None:
                        row[field] = item[field]
            rows.append(row)
        if len(rows) < 3:
            raise RuntimeError("EODHD returned fewer than three usable observations")
        return {"provider": self.name, "source": url,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_observations": len(payload), "rows": rows}


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
