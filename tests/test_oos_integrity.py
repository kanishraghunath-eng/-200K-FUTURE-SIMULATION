import unittest
from unittest.mock import patch

import numpy as np

from engine.backtest import _barrier_class, walk_forward_barrier_diagnostic
from engine.providers import YahooFinanceChartProvider
from engine.dataset_manifest import DatasetManifest
from scripts.evaluate_multi_market_oos import (
    apply_holm_adjustment, block_bootstrap_skill_interval,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


def manifest(price_field="close"):
    return DatasetManifest(
        instrument_id="TEST", asset_class="equity_index", source="fixture",
        currency="INR", interval="daily", periods_per_year=252,
        timezone="Asia/Kolkata", calendar="NSE", adjustment_basis="unknown",
        price_field=price_field,
    )


class WalkForwardIntegrityTests(unittest.TestCase):
    @staticmethod
    def series(length=190):
        # Deterministic positive series with mild variation; fixture only.
        x = np.arange(length, dtype=float)
        return 100.0 * np.exp(0.0004 * x + 0.012 * np.sin(x / 5.0)
                              + 0.004 * np.sin(x / 1.7))

    def run_diagnostic(self, prices):
        return walk_forward_barrier_diagnostic(
            prices, target_pct=0.02, stop_pct=0.02, horizon=3,
            min_train=60, estimation_window=60, calibration_window=30,
            min_calibration_observations=5, paths=40, seed=19,
            periods_per_year=252,
        )

    def test_past_forecasts_do_not_change_when_future_prices_change(self):
        original = self.series()
        changed = original.copy()
        changed[135:] *= np.linspace(1.15, 1.35, len(changed[135:]))
        before = self.run_diagnostic(original)
        after = self.run_diagnostic(changed)

        # Forecasts through origin 125 have no access to the modified future.
        left = [row for row in before["rows"] if row["index"] <= 125]
        right = [row for row in after["rows"] if row["index"] <= 125]
        self.assertEqual([x["index"] for x in left], [x["index"] for x in right])
        for a, b in zip(left, right):
            np.testing.assert_array_equal(a["predicted"], b["predicted"])
            np.testing.assert_array_equal(a["raw_predicted"], b["raw_predicted"])
            np.testing.assert_array_equal(a["baseline_predicted"], b["baseline_predicted"])

    def test_calibration_history_only_uses_matured_labels(self):
        prices = self.series(150)
        calls = []
        original = _barrier_class

        def tracked(values, origin, horizon, entry_offset, target_pct, stop_pct):
            calls.append((origin, len(calls)))
            return original(values, origin, horizon, entry_offset, target_pct, stop_pct)

        with patch("engine.backtest._barrier_class", side_effect=tracked):
            self.run_diagnostic(prices)

        # For each forecast origin, the first label call is its current outcome.
        # All following calls in that iteration are historical baseline labels;
        # each must have fully matured by the current origin.
        cursor = 0
        first_origin = 60
        for origin in range(first_origin, len(prices) - 3):
            self.assertEqual(calls[cursor][0], origin)
            cursor += 1
            history_start = max(0, origin - 60)
            expected_history = list(range(history_start, origin - 3 + 1))
            observed_history = [calls[cursor + j][0] for j in range(len(expected_history))]
            self.assertEqual(observed_history, expected_history)
            self.assertTrue(all(label_origin + 3 <= origin for label_origin in observed_history))
            cursor += len(expected_history)
        self.assertEqual(cursor, len(calls))

    def test_fixed_seed_is_reproducible(self):
        prices = self.series(145)
        first = self.run_diagnostic(prices)
        second = self.run_diagnostic(prices)
        self.assertEqual(first["multiclass_brier_score"], second["multiclass_brier_score"])
        self.assertEqual(first["rows"], second["rows"])



class StatisticalValidationTests(unittest.TestCase):
    def test_block_bootstrap_is_reproducible_and_reports_uncertainty(self):
        rows = []
        for i in range(120):
            baseline = 0.50 + (0.01 if i % 2 else -0.01)
            model = baseline - 0.04
            rows.append({
                "baseline_brier_score": baseline,
                "brier_score": model,
                "_bootstrap_segment": "fold-A" if i < 60 else "fold-B",
            })
        first = block_bootstrap_skill_interval(rows, block_length=5,
                                               replicates=200, seed=17)
        second = block_bootstrap_skill_interval(rows, block_length=5,
                                                replicates=200, seed=17)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "estimated")
        self.assertEqual(first["brier_skill_ci_95"], second["brier_skill_ci_95"])
        self.assertGreater(first["brier_skill_ci_95"][0], 0.0)
        self.assertEqual(first["replicates"], 200)

    def test_holm_adjustment_is_monotonic_and_family_scoped(self):
        def score(p):
            return {"block_bootstrap": {"one_sided_bootstrap_p_value": p}}
        datasets = {
            "A": {"oos_validation": {"aggregate_oos_by_gate": {
                "0": score(0.01), "1": score(0.03)}}},
            "B": {"oos_validation": {"aggregate_oos_by_gate": {
                "0": score(0.04)}}},
        }
        apply_holm_adjustment(datasets)
        adjusted = sorted(
            item["block_bootstrap"]["holm_adjusted_p_value"]
            for dataset in datasets.values()
            for item in dataset["oos_validation"]["aggregate_oos_by_gate"].values()
        )
        self.assertEqual(adjusted, sorted(adjusted))
        self.assertEqual(adjusted, [0.03, 0.06, 0.06])
        for dataset in datasets.values():
            for item in dataset["oos_validation"]["aggregate_oos_by_gate"].values():
                self.assertEqual(item["block_bootstrap"]["holm_family_size"], 3)


class ProviderPriceBasisTests(unittest.TestCase):
    def test_yahoo_adjusted_close_does_not_mix_raw_ohlc(self):
        import datetime
        import json

        stamps = [
            int(datetime.datetime(2026, 1, day, tzinfo=datetime.timezone.utc).timestamp())
            for day in (5, 6, 7)
        ]
        payload = {"chart": {"result": [{
            "timestamp": stamps,
            "indicators": {
                "quote": [{"open": [100, 101, 102], "high": [102, 103, 104],
                           "low": [99, 100, 101], "close": [101, 102, 103],
                           "volume": [10, 11, 12]}],
                "adjclose": [{"adjclose": [90, 91, 92]}],
            },
        }], "error": None}}
        with patch("urllib.request.urlopen",
                   return_value=FakeResponse(json.dumps(payload).encode())):
            result = YahooFinanceChartProvider().fetch(
                manifest(price_field="adjusted_close")
            )
        self.assertEqual([row["close"] for row in result["rows"]], [90, 91, 92])
        for row in result["rows"]:
            self.assertNotIn("open", row)
            self.assertNotIn("high", row)
            self.assertNotIn("low", row)
            self.assertNotIn("volume", row)


if __name__ == "__main__":
    unittest.main()
