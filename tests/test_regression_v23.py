import csv
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from engine.data_io import load_price_csv
from engine.monte_carlo import simulate_price_paths
from engine.report import build_simulation_report
from engine.specialists import audit_dated_prices, validate_dated_prices
from engine.specialists.numerical_stability import iter_gbm_path_chunks


def synthetic_prices(n=700):
    # Deterministic, non-degenerate log-return series with drift and volatility.
    t = np.arange(n - 1, dtype=float)
    returns = 0.00025 + 0.012 * np.sin(t * 0.37) + 0.006 * np.cos(t * 0.11)
    return 100.0 * np.exp(np.r_[0.0, np.cumsum(returns)])


class V23DriftTests(unittest.TestCase):
    def test_gbm_primitive_accepts_arithmetic_drift(self):
        _, chunk, _ = next(iter_gbm_path_chunks(100.0, 0.2, 0.0, 4, paths=2, seed=1))
        np.testing.assert_allclose(chunk[:, -1], 100.0 * math.exp(0.2))

    def test_corrected_metadata_matches_historical_log_drift(self):
        p = synthetic_prices()
        result = simulate_price_paths(p, 20, paths=100, seed=3)
        expected = np.diff(np.log(p)).mean() * 252
        self.assertAlmostEqual(result["metadata"]["annualized_drift"], expected)
        self.assertAlmostEqual(result["metadata"]["simulated_log_drift"], expected)

    def test_corrected_and_legacy_have_exact_seeded_drift_offset(self):
        p = synthetic_prices()
        corrected = simulate_price_paths(p, 12, paths=300, seed=77)
        legacy = simulate_price_paths(p, 12, paths=300, seed=77, drift_convention="legacy")
        sigma = corrected["metadata"]["annualized_volatility"]
        offset = np.log(corrected["paths"][:, -1] / legacy["paths"][:, -1])
        np.testing.assert_allclose(offset, 0.5 * sigma ** 2, rtol=1e-10, atol=1e-10)

    def test_legacy_metadata_preserves_v22_drift(self):
        p = synthetic_prices()
        result = simulate_price_paths(p, 10, paths=20, drift_convention="legacy")
        m = result["metadata"]
        self.assertAlmostEqual(m["annualized_arithmetic_drift"], m["annualized_drift"])
        self.assertAlmostEqual(m["simulated_log_drift"],
                               m["annualized_drift"] - 0.5 * m["annualized_volatility"] ** 2)

    def test_zero_mode_has_zero_arithmetic_drift(self):
        result = simulate_price_paths(synthetic_prices(), 10, paths=50, drift_mode="zero")
        self.assertEqual(result["metadata"]["annualized_arithmetic_drift"], 0.0)

    def test_zero_mode_simulation_remains_constant_for_zero_volatility(self):
        result = simulate_price_paths([100.0] * 8, 5, paths=12, drift_mode="zero")
        np.testing.assert_allclose(result["paths"], 100.0)

    def test_invalid_drift_convention_rejected(self):
        with self.assertRaisesRegex(ValueError, "drift_convention"):
            simulate_price_paths(synthetic_prices(), 5, paths=5, drift_convention="unknown")

    def test_backtest_accepts_legacy_convention(self):
        from engine.backtest import walk_forward_barrier_diagnostic
        result = walk_forward_barrier_diagnostic(synthetic_prices(90), min_train=60,
                    horizon=5, paths=10, drift_convention="legacy")
        self.assertEqual(result["drift_convention"], "legacy")


class V23DataAuditTests(unittest.TestCase):
    def test_audit_collects_multiple_error_categories(self):
        rows = [
            {"date": "2026-01-03", "close": "100"},
            {"date": "2026-01-02", "close": "0"},
            {"date": "2026-01-03", "close": "1000"},
            {"date": "2026-01-04", "close": "10000"},
        ]
        audit = audit_dated_prices(rows)
        codes = {item["code"] for item in audit["errors"]}
        self.assertFalse(audit["valid"])
        self.assertTrue({"invalid_close", "duplicate_timestamp",
                         "out_of_order_timestamp", "implausible_return"}.issubset(codes))

    def test_audit_detects_non_adjacent_duplicate(self):
        rows = [{"date": "2026-01-01", "close": 100},
                {"date": "2026-01-02", "close": 101},
                {"date": "2026-01-01", "close": 102}]
        codes = {x["code"] for x in audit_dated_prices(rows)["errors"]}
        self.assertIn("duplicate_timestamp", codes)

    def test_default_validator_remains_fail_fast(self):
        rows = [{"date": "2026-01-01", "close": 100},
                {"date": "2026-01-01", "close": 101},
                {"date": "2026-01-02", "close": 102}]
        with self.assertRaisesRegex(ValueError, "duplicate timestamps"):
            validate_dated_prices(rows)

    def test_gap_over_three_days_is_warning(self):
        rows = [{"date": "2026-01-05", "close": 100},
                {"date": "2026-01-06", "close": 101},
                {"date": "2026-01-12", "close": 102}]
        audit = audit_dated_prices(rows)
        self.assertTrue(any(x["code"] == "possible_missing_session" for x in audit["warnings"]))

    def test_two_day_gap_is_not_warned(self):
        rows = [{"date": "2026-01-05", "close": 100},
                {"date": "2026-01-06", "close": 101},
                {"date": "2026-01-08", "close": 102}]
        self.assertFalse(audit_dated_prices(rows)["warnings"])

    def test_business_daily_weekend_is_error(self):
        rows = [{"date": "2026-01-09", "close": 100},
                {"date": "2026-01-10", "close": 101},
                {"date": "2026-01-12", "close": 102}]
        codes = {x["code"] for x in audit_dated_prices(rows, "business_daily")["errors"]}
        self.assertIn("weekend_observation", codes)

    def test_unsupported_interval_is_configuration_error(self):
        with self.assertRaisesRegex(ValueError, "unsupported expected_interval"):
            audit_dated_prices([], expected_interval="hourly")

    def test_collect_all_csv_returns_no_prices_when_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text("date,close\n2026-01-01,100\n2026-01-01,0\n2026-01-02,102\n",
                            encoding="utf-8")
            loaded = load_price_csv(path, collect_all_errors=True)
            self.assertIsNone(loaded["prices"])
            self.assertFalse(loaded["validation"]["valid"])
            self.assertGreaterEqual(len(loaded["validation"]["errors"]), 2)

    def test_collect_all_accepts_one_shot_iterable(self):
        rows = ({"date": d, "close": c} for d, c in [
            ("2026-01-05", 100), ("2026-01-06", 101), ("2026-01-07", 102)])
        result = validate_dated_prices(rows, collect_all_errors=True)
        self.assertTrue(result["valid"])
        self.assertEqual(result["observations"], 3)

    def test_report_includes_drift_metadata(self):
        sim = simulate_price_paths(synthetic_prices(), 5, paths=5)
        report = build_simulation_report(sim)
        self.assertEqual(report["assumptions"]["drift_convention"], "corrected")
        self.assertIn("simulated_log_drift", report["assumptions"])


if __name__ == "__main__":
    unittest.main()
