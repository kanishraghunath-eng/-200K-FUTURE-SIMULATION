import csv
import tempfile
import unittest
from pathlib import Path
import numpy as np
from engine.data_io import load_price_csv
from engine.monte_carlo import simulate_price_paths
from engine.report import build_simulation_report, report_to_json
from engine.specialists import validate_dated_prices


class V22Tests(unittest.TestCase):
    def test_streamed_summary_matches_full_paths(self):
        prices = [100 + i * 0.1 + np.sin(i / 3) for i in range(80)]
        full = simulate_price_paths(prices, 12, paths=1200, seed=19)
        streamed = simulate_price_paths(prices, 12, paths=1200, seed=19,
                                        chunk_size=137, return_paths=False,
                                        entry=full["paths"][0, 0],
                                        target=full["paths"][0, 0] * 1.05,
                                        stop=full["paths"][0, 0] * 0.95)
        self.assertIsNone(streamed["paths"])
        self.assertEqual(streamed["summary"]["path_count"], 1200)
        self.assertEqual(streamed["summary"]["storage_mode"], "streamed_summary")
        self.assertAlmostEqual(streamed["summary"]["terminal_mean"],
                               full["paths"][:, -1].mean(), places=10)

    def test_streamed_barrier_probabilities_sum_to_one(self):
        prices = [100 + i * 0.1 + np.sin(i / 3) for i in range(80)]
        result = simulate_price_paths(prices, 8, paths=500, seed=4, return_paths=False,
                                      entry=110, target=115, stop=105)
        summary = result["summary"]
        total = sum(summary[k] for k in ("target_first_probability", "stop_first_probability",
                     "neither_probability", "same_step_ambiguous_probability"))
        self.assertAlmostEqual(total, 1.0, places=12)

    def test_csv_loader(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prices.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "close"])
                writer.writeheader()
                for day, close in [("2026-01-05", 100), ("2026-01-06", 101), ("2026-01-07", 102)]:
                    writer.writerow({"date": day, "close": close})
            data = load_price_csv(path, currency="INR", expected_interval="calendar_daily",
                                  corporate_actions_reviewed=True)
            self.assertEqual(data["prices"], [100.0, 101.0, 102.0])
            self.assertTrue(data["validation"]["valid"])

    def test_duplicate_timestamps_rejected(self):
        rows = [{"date": "2026-01-01", "close": 100},
                {"date": "2026-01-01", "close": 101},
                {"date": "2026-01-02", "close": 102}]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_dated_prices(rows)

    def test_report_json(self):
        sim = {"metadata": {"paths": 200000, "steps": 20, "seed": 7,
                            "model": "GBM", "drift_mode": "zero",
                            "annualized_drift": 0, "annualized_volatility": .2},
               "summary": {"path_count": 200000}}
        report = build_simulation_report(sim, risk_metrics={"var": .03})
        self.assertIn("EDUCATIONAL_SCENARIO_ANALYSIS_ONLY", report_to_json(report))


if __name__ == "__main__":
    unittest.main()
