import unittest

from tracker.market_monitor import _market_cap


class MarketCapParsingTests(unittest.TestCase):
    def test_uses_reported_market_cap(self):
        self.assertEqual(_market_cap({"marketCap": 125000}), 125000.0)

    def test_does_not_substitute_fdv_for_market_cap(self):
        self.assertIsNone(_market_cap({"fdv": 900000}))

    def test_rejects_missing_zero_and_invalid_values(self):
        for pair in ({}, {"marketCap": 0}, {"marketCap": "unknown"}):
            with self.subTest(pair=pair):
                self.assertIsNone(_market_cap(pair))


if __name__ == "__main__":
    unittest.main()
