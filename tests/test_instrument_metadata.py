import unittest
from engine.instrument import InstrumentMetadata, validate_observation_timestamp


class InstrumentMetadataTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(
            symbol="NIFTY50", asset_class="equity_index", venue="NSE",
            timezone="Asia/Kolkata", quote_currency="INR", interval="1d",
            periods_per_year=252, price_basis="close",
        )

    def test_valid_metadata_round_trip(self):
        metadata = InstrumentMetadata(**self.base)
        result = metadata.to_dict()
        self.assertEqual(result["symbol"], "NIFTY50")
        self.assertEqual(result["periods_per_year"], 252)
        self.assertEqual(result["corporate_actions"], "unverified")

    def test_rejects_unknown_asset_class(self):
        values = dict(self.base, asset_class="imaginary")
        with self.assertRaises(ValueError):
            InstrumentMetadata(**values)

    def test_rejects_invalid_timezone(self):
        values = dict(self.base, timezone="Mars/Olympus")
        with self.assertRaises(ValueError):
            InstrumentMetadata(**values)

    def test_rejects_missing_futures_roll_method(self):
        values = dict(self.base, asset_class="commodity_future")
        with self.assertRaises(ValueError):
            InstrumentMetadata(**values)

    def test_rejects_invalid_period_count(self):
        values = dict(self.base, periods_per_year=0)
        with self.assertRaises(ValueError):
            InstrumentMetadata(**values)

    def test_timestamp_requires_timezone(self):
        metadata = InstrumentMetadata(**self.base)
        with self.assertRaises(ValueError):
            validate_observation_timestamp("2026-11-26T09:15:00", metadata)
        stamp = validate_observation_timestamp("2026-11-26T09:15:00+05:30", metadata)
        self.assertEqual(stamp.utcoffset().total_seconds(), 19800)


if __name__ == "__main__":
    unittest.main()
