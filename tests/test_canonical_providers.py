import tempfile
import unittest
from pathlib import Path

from engine.dataset_manifest import DatasetManifest
from engine.canonical_data import canonicalize_rows, validate_canonical_rows
from engine.providers import CsvProvider, ProviderRegistry


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


if __name__ == "__main__":
    unittest.main()
