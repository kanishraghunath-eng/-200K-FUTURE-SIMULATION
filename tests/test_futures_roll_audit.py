import unittest

from engine.futures_roll_audit import audit_contract_chain


class FuturesRollAuditTests(unittest.TestCase):
    @staticmethod
    def chain():
        return [
            {"date": "2026-01-01", "contract_symbol": "GC_F26",
             "expiry_date": "2026-01-15", "close": 100.0,
             "volume": 1000, "open_interest": 1200},
            {"date": "2026-01-01", "contract_symbol": "GC_G26",
             "expiry_date": "2026-03-15", "close": 101.0,
             "volume": 800, "open_interest": 900},
            {"date": "2026-01-09", "contract_symbol": "GC_F26",
             "expiry_date": "2026-01-15", "close": 102.0,
             "volume": 1100, "open_interest": 1200},
            {"date": "2026-01-09", "contract_symbol": "GC_G26",
             "expiry_date": "2026-03-15", "close": 103.0,
             "volume": 900, "open_interest": 1000},
            {"date": "2026-01-10", "contract_symbol": "GC_F26",
             "expiry_date": "2026-01-15", "close": 102.5,
             "volume": 900, "open_interest": 1100},
            {"date": "2026-01-10", "contract_symbol": "GC_G26",
             "expiry_date": "2026-03-15", "close": 103.5,
             "volume": 1200, "open_interest": 1300},
            {"date": "2026-01-11", "contract_symbol": "GC_G26",
             "expiry_date": "2026-03-15", "close": 104.0,
             "volume": 1300, "open_interest": 1400},
        ]

    def test_calendar_roll_requires_overlap_and_reports_adjustment(self):
        result = audit_contract_chain(
            self.chain(), roll_method="calendar",
            roll_days_before_expiry=5, adjustment_method="ratio",
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(len(result["roll_events"]), 1)
        self.assertEqual(result["roll_events"][0]["old_contract"], "GC_F26")
        self.assertEqual(result["roll_events"][0]["new_contract"], "GC_G26")
        self.assertAlmostEqual(result["roll_events"][0]["ratio_adjustment"], 102.5 / 103.5)

    def test_missing_overlap_fails_roll_verification(self):
        rows = [
            {"date": "2026-01-01", "contract_symbol": "GC_F26",
             "expiry_date": "2026-01-15", "close": 100, "volume": 100, "open_interest": 100},
            {"date": "2026-01-10", "contract_symbol": "GC_G26",
             "expiry_date": "2026-03-15", "close": 103, "volume": 200, "open_interest": 200},
        ]
        result = audit_contract_chain(rows, roll_method="calendar", roll_days_before_expiry=5)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["code"], "roll_overlap_missing")

    def test_continuous_series_without_roll_event_is_not_verified(self):
        rows = [self.chain()[0], self.chain()[2]]
        result = audit_contract_chain(rows, roll_method="calendar", roll_days_before_expiry=5)
        self.assertEqual(result["status"], "insufficient_roll_events")

    def test_rejects_unknown_roll_method(self):
        with self.assertRaisesRegex(ValueError, "roll_method"):
            audit_contract_chain(self.chain(), roll_method="vendor_magic")


if __name__ == "__main__":
    unittest.main()
