import unittest
from unittest.mock import patch

from tracker.market_monitor import _market_cap, market_cap_monitor


class MarketCapParsingTests(unittest.TestCase):
    def test_uses_reported_market_cap(self):
        self.assertEqual(_market_cap({"marketCap": 125000}), 125000.0)

    def test_does_not_substitute_fdv_for_market_cap(self):
        self.assertIsNone(_market_cap({"fdv": 900000}))

    def test_rejects_missing_zero_and_invalid_values(self):
        for pair in ({}, {"marketCap": 0}, {"marketCap": "unknown"}, {"marketCap": "nan"}, {"marketCap": "inf"}):
            with self.subTest(pair=pair):
                self.assertIsNone(_market_cap(pair))


if __name__ == "__main__":
    unittest.main()


class MonitorIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_initialization_failure_is_contained(self):
        with patch("tracker.market_monitor.TrackerDatabase", side_effect=OSError("disk unavailable")):
            await market_cap_monitor(interval_seconds=60)
