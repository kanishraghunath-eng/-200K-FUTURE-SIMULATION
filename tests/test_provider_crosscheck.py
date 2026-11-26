import csv
import io
import math
import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from scripts.evaluate_multi_market_oos import cross_provider_check
from engine.monte_carlo import simulate_price_paths


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class StooqProviderTests(unittest.TestCase):
    def test_missing_key_is_reported_without_network_request(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("scripts.evaluate_multi_market_oos.urllib.request.urlopen") as urlopen:
                result = cross_provider_check([("2024-01-01", 100.0)])
        self.assertEqual(result["status"], "api_key_required")
        urlopen.assert_not_called()

    def test_authenticated_csv_produces_matched_return_diagnostic(self):
        start = date(2024, 1, 1)
        yahoo_rows = []
        stooq_lines = ["Date,Open,High,Low,Close,Volume"]
        for i in range(130):
            day = (start + timedelta(days=i)).isoformat()
            yahoo_price = 100.0 * math.exp(0.001 * i + 0.0002 * math.sin(i))
            stooq_price = 50.0 * math.exp(0.001 * i + 0.0002 * math.sin(i))
            yahoo_rows.append((day, yahoo_price))
            stooq_lines.append(f"{day},0,0,0,{stooq_price:.10f},1000")
        body = "\n".join(stooq_lines) + "\n"
        with patch.dict(os.environ, {"STOOQ_API_KEY": "test-key"}):
            with patch("scripts.evaluate_multi_market_oos.urllib.request.urlopen",
                       return_value=FakeResponse(body)) as urlopen:
                result = cross_provider_check(yahoo_rows)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["overlapping_return_observations"], 129)
        self.assertGreater(result["pearson_daily_return_correlation"], 0.999)
        request_url = urlopen.call_args.args[0].full_url
        self.assertIn("apikey=test-key", request_url)
        self.assertNotIn("test-key", result["source_url"])

    def test_core_simulation_runs_without_stooq_key_or_network(self):
        prices = [100.0 * math.exp(0.001 * i + 0.002 * math.sin(i)) for i in range(40)]
        with patch.dict(os.environ, {}, clear=True):
            with patch("scripts.evaluate_multi_market_oos.urllib.request.urlopen",
                       side_effect=AssertionError("core simulation must not access Stooq")):
                result = simulate_price_paths(
                    prices, steps=5, paths=64, seed=11, return_paths=False
                )
        self.assertEqual(result["summary"]["path_count"], 64)
        self.assertEqual(result["summary"]["storage_mode"], "streamed_summary")
        self.assertEqual(result["metadata"]["paths"], 64)

    def test_non_csv_api_key_challenge_is_not_misreported_as_zero_overlap(self):
        with patch.dict(os.environ, {"STOOQ_API_KEY": "bad-key"}):
            with patch("scripts.evaluate_multi_market_oos.urllib.request.urlopen",
                       return_value=FakeResponse("Get your API key")):
                result = cross_provider_check([("2024-01-01", 100.0)])
        self.assertEqual(result["status"], "api_key_rejected")
        self.assertNotIn("bad-key", str(result))


if __name__ == "__main__":
    unittest.main()
