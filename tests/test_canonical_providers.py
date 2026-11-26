import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from engine.dataset_manifest import DatasetManifest
from engine.canonical_data import canonicalize_rows, validate_canonical_rows
from engine.providers import (CsvProvider, ProviderRegistry, YahooFinanceChartProvider, StooqCsvProvider, EodhdProvider)
from scripts.evaluate_dataset_manifest_oos import evaluate_dataset


def manifest(**overrides):
    values = dict(instrument_id="TEST", asset_class="equity_index",
                  source="fixture", currency="INR", interval="daily", periods_per_year=252,
                  timezone="Asia/Kolkata", calendar="NSE",
                  adjustment_basis="unknown")
    values.update(overrides)
    return DatasetManifest(**values)


class CanonicalValidationTests(unittest.TestCase):
    def test_valid_daily_rows(self):
        rows = canonicalize_rows([
            {"date":"2026-01-05","close":"100"},
            {"date":"2026-01-06","close":"101"},
            {"date":"2026-01-07","close":"99"},
        ], currency="INR", price_basis="close")
        self.assertTrue(validate_canonical_rows(rows, manifest())["valid"])

    def test_rejects_out_of_order_rows_without_repair(self):
        rows = canonicalize_rows([
            {"date":"2026-01-07","close":"99"},
            {"date":"2026-01-05","close":"100"},
            {"date":"2026-01-06","close":"101"},
        ])
        audit = validate_canonical_rows(rows, manifest())
        self.assertFalse(audit["valid"])
        self.assertEqual(rows[0]["timestamp"], "2026-01-07")

    def test_rejects_currency_mismatch(self):
        rows = [{"timestamp":d,"close":p,"currency":"USD"} for d,p in [
            ("2026-01-05",100),("2026-01-06",101),("2026-01-07",99)]]
        self.assertFalse(validate_canonical_rows(rows, manifest())["valid"])

    def test_intraday_gap_is_reported(self):
        m = manifest(interval="5m", periods_per_year=19656)
        rows = [{"timestamp":d,"close":p} for d,p in [
            ("2026-01-05T09:15:00+05:30",100),
            ("2026-01-05T09:20:00+05:30",101),
            ("2026-01-05T09:30:00+05:30",99)]]
        audit = validate_canonical_rows(rows,m,require_timezone=True)
        self.assertTrue(audit["valid"])
        self.assertIn("interval_spacing_mismatch",{w["code"] for w in audit["warnings"]})

    def test_duplicate_timestamp_rejected(self):
        rows = [{"timestamp":d,"close":p} for d,p in [
            ("2026-01-05",100),("2026-01-05",101),("2026-01-06",99)]]
        self.assertFalse(validate_canonical_rows(rows,manifest())["valid"])


class FakeResponse:
    def __init__(self, body):
        self.body = body
        self.status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


class ProviderTests(unittest.TestCase):
    def test_csv_provider_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"prices.csv"
            path.write_text("date,close\n2026-01-05,100\n2026-01-06,101\n2026-01-07,99\n",
                            encoding="utf-8")
            provider = CsvProvider(path)
            result = provider.fetch(manifest())
            self.assertEqual(len(result["rows"]),3)
            registry = ProviderRegistry()
            registry.register(provider)
            self.assertEqual(registry.names(),("csv",))
            self.assertIs(registry.get("csv"),provider)

    def test_yahoo_rejects_unsupported_four_hour_interval(self):
        with self.assertRaisesRegex(ValueError, "does not support"):
            YahooFinanceChartProvider().fetch(manifest(interval="4h", periods_per_year=1638))

    def test_yahoo_provider_maps_chart_payload(self):
        import json
        import datetime
        stamps = [int(datetime.datetime(2026, 1, d, tzinfo=datetime.timezone.utc).timestamp())
                  for d in (5, 6, 7)]
        payload = {"chart":{"result":[{"timestamp":stamps,
                   "indicators":{"quote":[{"close":[100,101,99]}]}}],"error":None}}
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            result = YahooFinanceChartProvider().fetch(manifest())
        self.assertEqual(result["provider"], "yahoo")
        self.assertEqual([float(x["close"]) for x in result["rows"]], [100,101,99])

    def test_stooq_provider_maps_daily_csv(self):
        body = b"Date,Open,High,Low,Close,Volume\n2026-01-05,100,101,99,100,10\n2026-01-06,101,102,100,101,11\n2026-01-07,99,100,98,99,12\n"
        with patch("urllib.request.urlopen", return_value=FakeResponse(body)):
            result = StooqCsvProvider().fetch(manifest(instrument_id="spy.us"))
        self.assertEqual(result["provider"], "stooq")
        self.assertEqual(len(result["rows"]), 3)

    def test_eodhd_provider_maps_adjusted_close(self):
        import json
        payload = [{"date":"2026-01-05","close":100,"adjusted_close":99},
                   {"date":"2026-01-06","close":101,"adjusted_close":100},
                   {"date":"2026-01-07","close":99,"adjusted_close":98}]
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            result = EodhdProvider().fetch(manifest(price_field="adjusted_close"))
        self.assertEqual(result["provider"], "eodhd")
        self.assertEqual([float(x["close"]) for x in result["rows"]], [99,100,98])

    def test_stooq_rejects_adjusted_close_request(self):
        with self.assertRaisesRegex(ValueError, "raw close"):
            StooqCsvProvider().fetch(manifest(price_field="adjusted_close"))

    def test_manifest_runner_labels_short_history_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"short.csv"
            path.write_text("date,close\n2026-01-01,100\n2026-01-02,101\n2026-01-03,99\n",
                            encoding="utf-8")
            item = {
                "instrument_id":"DEMO", "asset_class":"equity_index",
                "source":"synthetic plumbing fixture", "currency":"INR",
                "interval":"daily", "timezone":"Asia/Kolkata",
                "adjustment_basis":"unknown", "provider":"csv", "path":str(path),
                "horizon":2, "min_train":3, "estimation_window":3,
            }
            result = evaluate_dataset(item, paths=20)
            self.assertEqual(result["status"], "insufficient_data")
            self.assertGreater(result["required_observations"], result["observations"])


if __name__ == "__main__":
    unittest.main()
