import unittest
from unittest.mock import AsyncMock

from tracker.market_monitor import _market_cap, fetch_market_caps


class MarketCapMonitorTests(unittest.IsolatedAsyncioTestCase):
    def test_market_cap_prefers_market_cap_then_fdv(self):
        self.assertEqual(_market_cap({"marketCap": 25000, "fdv": 30000}), 25000)
        self.assertEqual(_market_cap({"fdv": 30000}), 30000)
        self.assertEqual(_market_cap({"marketCap": 0, "fdv": None}), 0)
        self.assertEqual(_market_cap({"marketCap": "bad"}), 0)

    async def test_fetch_uses_solana_base_token_market_cap(self):
        class Response:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return None
            async def json(self, content_type=None):
                return {"pairs": [
                    {"chainId": "solana", "baseToken": {"address": "MintA"},
                     "marketCap": 50000, "liquidity": {"usd": 1000}},
                    {"chainId": "ethereum", "baseToken": {"address": "MintA"},
                     "marketCap": 999999, "liquidity": {"usd": 999999}},
                    {"chainId": "solana", "baseToken": {"address": "MintB"},
                     "marketCap": 80000, "liquidity": {"usd": 500}},
                ]}
        class Session:
            def get(self, url):
                self.url = url
                return Response()
        session = Session()
        values = await fetch_market_caps(session, ["MintA", "MintB"])
        self.assertEqual(values, {"MintA": 50000, "MintB": 80000})
        self.assertIn("MintA,MintB", session.url)


if __name__ == "__main__":
    unittest.main()
