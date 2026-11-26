import json
import os
import math
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from scripts.evaluate_multi_market_oos import cross_provider_check
from scripts.benchmark_200k import run_case, synthetic_history
from engine.monte_carlo import simulate_price_paths


class FakeResponse:
    status = 200
    def __init__(self, body): self.body = body.encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.body


class IndependentProviderTests(unittest.TestCase):
    def test_eodhd_demo_data_compares_adjusted_daily_returns(self):
        start = date(2024, 1, 1)
        yahoo, vendor = [], []
        for i in range(130):
            day = (start + timedelta(days=i)).isoformat()
            value = 100.0 * math.exp(0.001 * i + 0.0002 * math.sin(i))
            yahoo.append((day, value))
            vendor.append({"date": day, "adjusted_close": value * 2.0})
        with patch("scripts.evaluate_multi_market_oos.urllib.request.urlopen",
                   return_value=FakeResponse(json.dumps(vendor))) as urlopen:
            result = cross_provider_check(yahoo, symbol="VTI")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["overlapping_return_observations"], 129)
        self.assertGreater(result["pearson_daily_return_correlation"], 0.999)
        self.assertIn("api_token=demo", urlopen.call_args.args[0].full_url)
        self.assertNotIn("api_token", result["source_url"])

    def test_core_simulation_does_not_require_provider_credentials(self):
        prices = synthetic_history(observations=80)
        with patch.dict(os.environ, {}, clear=True):
            with patch("scripts.evaluate_multi_market_oos.urllib.request.urlopen",
                       side_effect=AssertionError("core simulation must not fetch external data")):
                result = simulate_price_paths(prices, steps=5, paths=128, seed=3,
                                              return_paths=False)
        self.assertEqual(result["summary"]["path_count"], 128)
    def test_provider_denial_is_not_claimed_as_completed(self):
        with patch("scripts.evaluate_multi_market_oos.urllib.request.urlopen",
                   return_value=FakeResponse("not-json")):
            result = cross_provider_check([("2024-01-01", 100.0)], symbol="VTI")
        self.assertEqual(result["status"], "invalid_response")


class BenchmarkSmokeTests(unittest.TestCase):
    def test_streamed_benchmark_smoke_case_reports_requested_paths(self):
        prices = synthetic_history(observations=100)
        result = run_case(prices, steps=5, paths=256, seed=9, chunk_size=64)
        self.assertEqual(result["summary"]["path_count"], 256)
        self.assertEqual(result["summary"]["storage_mode"], "streamed_summary")
        self.assertGreater(result["elapsed_seconds"], 0)
        self.assertFalse(result["numerically_saturated"])


if __name__ == "__main__":
    unittest.main()