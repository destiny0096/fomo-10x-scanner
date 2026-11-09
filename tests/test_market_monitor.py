import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tracker.market_monitor import _market_cap, fetch_market_caps, market_cap_monitor


class MarketCapParsingTests(unittest.IsolatedAsyncioTestCase):
    def test_uses_reported_market_cap(self):
        self.assertEqual(_market_cap({"marketCap": 125000}), 125000.0)

    def test_does_not_substitute_fdv_for_market_cap(self):
        self.assertIsNone(_market_cap({"fdv": 900000}))

    async def test_fetch_uses_solana_base_token_reported_market_cap(self):
        class Response:
            status = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None
            async def json(self, content_type=None):
                return {"pairs": [
                    {"chainId": "solana", "baseToken": {"address": "MintA"},
                     "marketCap": 50000, "liquidity": {"usd": 1000}},
                    {"chainId": "ethereum", "baseToken": {"address": "MintA"},
                     "marketCap": 999999, "liquidity": {"usd": 999999}},
                    {"chainId": "solana", "baseToken": {"address": "MintB"},
                     "fdv": 80000, "liquidity": {"usd": 500}},
                    {"chainId": "solana", "baseToken": {"address": "MintA"},
                     "marketCap": 60000, "liquidity": {"usd": 2000}},
                    None,
                ]}

        class Session:
            def get(self, url):
                self.url = url
                return Response()

        session = Session()
        values = await fetch_market_caps(session, ["MintA", "MintB"])
        self.assertEqual(values, {"MintA": 60000.0})
        self.assertIn("MintA,MintB", session.url)

    def test_rejects_missing_zero_and_invalid_values(self):
        for pair in ({}, {"marketCap": 0}, {"marketCap": "unknown"}, {"marketCap": "nan"}, {"marketCap": "inf"}):
            with self.subTest(pair=pair):
                self.assertIsNone(_market_cap(pair))


class MonitorIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_initialization_failure_is_contained(self):
        with patch("tracker.market_monitor.TrackerDatabase", side_effect=OSError("disk unavailable")):
            await market_cap_monitor(interval_seconds=60)

    async def test_scheduled_backup_runs_on_startup(self):
        class FakeDatabase:
            def count(self):
                return 0
            def list_tokens(self):
                return []

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None

        with patch.dict(os.environ, {"TRACKER_BACKUP_INTERVAL_SECONDS": "60"}), \
             patch("tracker.market_monitor.aiohttp.ClientSession", return_value=FakeSession()), \
             patch("tracker.backup.create_backup") as create_backup, \
             patch("tracker.market_monitor.asyncio.to_thread", new=AsyncMock(return_value=Path("/tmp/backup.db"))) as to_thread, \
             patch("tracker.market_monitor.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await market_cap_monitor(database=FakeDatabase(), interval_seconds=60)

        to_thread.assert_awaited_once_with(create_backup)

    async def test_negative_backup_interval_is_also_disabled(self):
        class FakeDatabase:
            def count(self):
                return 0
            def list_tokens(self):
                return []

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None

        with patch.dict(os.environ, {"TRACKER_BACKUP_INTERVAL_SECONDS": "-1"}), \
             patch("tracker.market_monitor.aiohttp.ClientSession", return_value=FakeSession()), \
             patch("tracker.backup.create_backup") as create_backup, \
             patch("tracker.market_monitor.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await market_cap_monitor(database=FakeDatabase(), interval_seconds=60)

        create_backup.assert_not_called()

    async def test_scheduled_backups_can_be_disabled(self):
        class FakeDatabase:
            def count(self):
                return 0
            def list_tokens(self):
                return []

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None

        with patch.dict(os.environ, {"TRACKER_BACKUP_INTERVAL_SECONDS": "0"}), \
             patch("tracker.market_monitor.aiohttp.ClientSession", return_value=FakeSession()), \
             patch("tracker.backup.create_backup") as create_backup, \
             patch("tracker.market_monitor.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await market_cap_monitor(database=FakeDatabase(), interval_seconds=60)

        create_backup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
