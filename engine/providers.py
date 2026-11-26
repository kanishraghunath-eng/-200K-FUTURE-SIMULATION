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
        action_events = []
        provider_events = item.get("events", {}) or {}
        for event_type in ("dividends", "splits"):
            event_map = provider_events.get(event_type, {}) or {}
            for event_key, event in event_map.items():
                event = event or {}
                event_stamp = event.get("date", event_key)
                try:
                    event_date = datetime.fromtimestamp(
                        int(event_stamp), timezone.utc
                    ).date().isoformat()
                except (TypeError, ValueError, OverflowError):
                    continue
                normalized = {"date": event_date, "type": event_type}
                if event_type == "dividends":
                    if event.get("amount") is None:
                        continue
                    normalized["amount"] = float(event["amount"])
                else:
                    numerator = event.get("numerator")
                    denominator = event.get("denominator")
                    if numerator is None or denominator in (None, 0):
                        continue
                    normalized["numerator"] = float(numerator)
                    normalized["denominator"] = float(denominator)
                action_events.append(normalized)
        action_events.sort(key=lambda x: (x["date"], x["type"]))
        actions_bytes = json.dumps(
            action_events, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {"provider": self.name, "source": url, "raw_observations": len(stamps),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "provider_price_basis": basis,
                "ohlcv_included": bool(not adjusted and self.include_ohlcv),
                "corporate_actions": {
                    "source": "Yahoo chart events",
                    "events": action_events,
                    "dividend_count": sum(x["type"] == "dividends" for x in action_events),
                    "split_count": sum(x["type"] == "splits" for x in action_events),
                    "sha256": hashlib.sha256(actions_bytes).hexdigest(),
                },
                "rows": rows}


class StooqCsvProvider(PriceDataProvider):
    """Public Stooq daily CSV adapter; symbols must use Stooq's vendor notation."""
    name = "stooq"

    def fetch(self, dataset, start=None, end=None):
        if dataset.interval != "daily":
            raise ValueError("Stooq adapter currently supports daily data only")
        if dataset.price_field != "close":
            raise ValueError("Stooq adapter supplies raw close only")
        api_key = os.environ.get("STOOQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "Stooq now requires an API key for historical CSV downloads; "
                "configure STOOQ_API_KEY in the runtime secret store"
            )
        params = {"s": dataset.instrument_id.lower(), "i": "d", "apikey": api_key}
        if start:
            params["d1"] = start.replace("-", "")
        if end:
            params["d2"] = end.replace("-", "")
        url = "https://stooq.com/q/d/l/?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "200k-future-simulation/2.3"})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw_bytes = response.read()
        raw = raw_bytes.decode("utf-8-sig")
        lowered = raw.lstrip().lower()
        if ("get your apikey" in lowered or "api key" in lowered
                or "daily hits limit" in lowered or "exceeded" in lowered
                or lowered.startswith("<!doctype") or lowered.startswith("<html")):
            raise RuntimeError(
                "Stooq returned an authentication, quota, or challenge response; "
                "verify STOOQ_API_KEY and provider access"
            )
        import csv as _csv
        from io import StringIO
        reader = _csv.DictReader(StringIO(raw))
        if not reader.fieldnames or not {"Date", "Close"}.issubset(set(reader.fieldnames)):
            raise RuntimeError(
                "Stooq response is not the expected Date/Open/High/Low/Close/Volume CSV"
            )
        source_rows = list(reader)
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
        # Keep the credential out of provenance URLs and all generated reports.
        safe_url = urllib.parse.urlunsplit(
            (urllib.parse.urlsplit(url).scheme, urllib.parse.urlsplit(url).netloc,
             urllib.parse.urlsplit(url).path,
             urllib.parse.urlencode({k: v for k, v in params.items() if k != "apikey"}),
             "")
        )
        return {"provider": self.name, "source": safe_url,
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

    def fetch_corporate_actions(self, dataset, start=None, end=None):
        """Fetch EODHD dividend and split histories for independent reconciliation."""
        token = os.environ.get("EODHD_API_TOKEN", "demo").strip()
        if not token:
            raise RuntimeError("EODHD_API_TOKEN is required for corporate-action reconciliation")
        result = {}
        for action_type in ("div", "splits"):
            params = {"api_token": token, "fmt": "json"}
            if start:
                params["from"] = start[:10]
            if end:
                params["to"] = end[:10]
            url = (
                "https://eodhd.com/api/" + action_type + "/"
                + urllib.parse.quote(dataset.instrument_id)
                + "?" + urllib.parse.urlencode(params)
            )
            request = urllib.request.Request(
                url, headers={"User-Agent": "200k-future-simulation/2.3",
                              "Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, list):
                raise RuntimeError(
                    f"EODHD {action_type} endpoint returned a non-list response"
                )
            result[action_type] = {
                "events": payload,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source": "https://eodhd.com/api/" + action_type + "/"
                          + urllib.parse.quote(dataset.instrument_id),
            }
        return result


def reconcile_corporate_actions(yahoo_actions, independent_actions,
                                amount_tolerance=1e-5):
    """Strictly compare dated dividend amounts and split ratios across vendors."""
    yahoo_events = (yahoo_actions or {}).get("events", [])
    independent_dividends = (independent_actions or {}).get("div", {}).get("events", [])
    independent_splits = (independent_actions or {}).get("splits", {}).get("events", [])

    def index_events(events, kind):
        indexed = {}
        for event in events:
            event_date = str(event.get("date", ""))[:10]
            if not event_date:
                continue
            if event_date in indexed:
                raise ValueError(f"duplicate {kind} event date: {event_date}")
            indexed[event_date] = event
        return indexed

    yahoo_divs = index_events(
        [x for x in yahoo_events if x.get("type") == "dividends"], "Yahoo dividend"
    )
    yahoo_splits = index_events(
        [x for x in yahoo_events if x.get("type") == "splits"], "Yahoo split"
    )
    eodhd_divs = index_events(independent_dividends, "EODHD dividend")
    eodhd_splits = index_events(independent_splits, "EODHD split")

    def compare_dividends():
        if set(yahoo_divs) != set(eodhd_divs):
            return False, "dividend event dates differ between providers"
        for event_date, yahoo_event in yahoo_divs.items():
            eodhd_event = eodhd_divs[event_date]
            eodhd_amount = eodhd_event.get("unadjustedValue", eodhd_event.get("value"))
            if eodhd_amount is None or yahoo_event.get("amount") is None:
                return False, f"dividend amount missing on {event_date}"
            left, right = float(yahoo_event["amount"]), float(eodhd_amount)
            if abs(left - right) > amount_tolerance * max(1.0, abs(left), abs(right)):
                return False, f"dividend amount differs on {event_date}"
        return True, None

    def split_ratio(event):
        value = event.get("split")
        if isinstance(value, str) and "/" in value:
            left, right = value.split("/", 1)
            return float(left) / float(right)
        if event.get("numerator") is not None and event.get("denominator") not in (None, 0):
            return float(event["numerator"]) / float(event["denominator"])
        return None

    def compare_splits():
        if set(yahoo_splits) != set(eodhd_splits):
            return False, "split event dates differ between providers"
        for event_date, yahoo_event in yahoo_splits.items():
            independent_ratio = split_ratio(eodhd_splits[event_date])
            yahoo_ratio = float(yahoo_event["numerator"]) / float(yahoo_event["denominator"])
            if independent_ratio is None or abs(independent_ratio - yahoo_ratio) > amount_tolerance:
                return False, f"split ratio differs on {event_date}"
        return True, None

    div_ok, div_error = compare_dividends()
    split_ok, split_error = compare_splits()
    errors = [x for x in (div_error, split_error) if x]
    return {
        "status": "matched" if div_ok and split_ok else "mismatch",
        "yahoo_dividend_count": len(yahoo_divs),
        "independent_dividend_count": len(eodhd_divs),
        "yahoo_split_count": len(yahoo_splits),
        "independent_split_count": len(eodhd_splits),
        "errors": errors,
        "method": "Exact event-date match; dividend unadjustedValue (fallback value) and split-ratio comparison",
        "limitations": [
            "Event agreement does not independently prove the adjusted-close calculation is correct.",
            "Missing or differently classified vendor events fail the reconciliation.",
        ],
    }


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
