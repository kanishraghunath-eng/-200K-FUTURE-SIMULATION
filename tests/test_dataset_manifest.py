import unittest

from engine.dataset_manifest import DatasetManifest


class DatasetManifestTests(unittest.TestCase):
    def make_manifest(self, **overrides):
        values = {
            "instrument_id": "NIFTY50",
            "asset_class": "equity_index",
            "source": "test-fixture",
            "currency": "INR",
            "interval": "daily",
            "timezone": "Asia/Kolkata",
            "calendar": "NSE",
            "adjustment_basis": "unknown",
            "row_count": 250,
        }
        values.update(overrides)
        return DatasetManifest(**values)

    def test_valid_equity_index_manifest(self):
        result = self.make_manifest().validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["asset_class"], "equity_index")

    def test_valid_24x7_crypto_metadata(self):
        manifest = self.make_manifest(
            instrument_id="BTC-USD", asset_class="crypto",
            currency="USD", interval="1h", periods_per_year=8760, timezone="UTC",
            calendar=None, adjustment_basis="not_applicable")
        self.assertTrue(manifest.validate()["valid"])

    def test_rejects_unknown_asset_class(self):
        with self.assertRaisesRegex(ValueError, "asset_class"):
            self.make_manifest(asset_class="prediction_market").validate()

    def test_rejects_bad_currency_code(self):
        with self.assertRaisesRegex(ValueError, "currency"):
            self.make_manifest(currency="usd").validate()

    def test_rejects_invalid_timezone(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.make_manifest(timezone="Mars/Olympus").validate()

    def test_rejects_reversed_observation_range(self):
        with self.assertRaisesRegex(ValueError, "first_observation"):
            self.make_manifest(
                first_observation="2026-12-31",
                last_observation="2026-01-01").validate()

    def test_futures_require_roll_method(self):
        with self.assertRaisesRegex(ValueError, "futures_roll_method"):
            self.make_manifest(
                asset_class="commodity_future",
                instrument_id="WTI-front-month").validate()

    def test_intraday_requires_explicit_annualization(self):
        with self.assertRaisesRegex(ValueError, "periods_per_year"):
            self.make_manifest(interval="5m").validate()

    def test_coarse_interval_annualization_defaults(self):
        self.assertEqual(self.make_manifest(interval="weekly").effective_periods_per_year, 52)
        self.assertEqual(self.make_manifest(interval="monthly").effective_periods_per_year, 12)
        self.assertEqual(self.make_manifest(asset_class="crypto").effective_periods_per_year, 365)

    def test_explicit_intraday_annualization(self):
        item = self.make_manifest(interval="5m", periods_per_year=19656)
        self.assertEqual(item.effective_periods_per_year, 19656)

    def test_manifest_serializes_after_validation(self):
        data = self.make_manifest().to_dict()
        self.assertEqual(data["currency"], "INR")
        self.assertEqual(data["interval"], "daily")


if __name__ == "__main__":
    unittest.main()
