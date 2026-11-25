"""Tests for scanner alert delivery independent of public social evidence."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

with patch.dict(os.environ, {
    "TELEGRAM_BOT_TOKEN": "test-token",
    "TELEGRAM_CHAT_ID": "test-chat",
}):
    import bot

from tracker.database import TrackerDatabase
from tracker.pipeline import evaluate_and_record
import tracker.integration as integration


def make_pair(address="MintNoSocial", market_cap=50000):
    pair = {
        "chainId": "solana",
        "baseToken": {"address": address, "name": "Example", "symbol": "EX"},
        "marketCap": market_cap,
        "liquidity": {"usd": 10000},
        "volume": {"h24": 10000, "m5": 5000},
        "txns": {"h24": {"buys": 30, "sells": 10}, "m5": {"buys": 8, "sells": 2}},
        "priceChange": {"m5": 15},
        "url": f"https://dexscreener.com/solana/{address}",
    }
    return pair


class BestSolanaPairsTests(unittest.TestCase):
    def test_ignores_malformed_entries_without_aborting_batch(self):
        pairs = [
            None, "not-a-pair", [],
            {"chainId": "solana", "baseToken": None, "liquidity": {"usd": 50}},
            {"chainId": "solana", "baseToken": {"address": "MintA"}, "liquidity": {"usd": "bad"}},
            {"chainId": "solana", "baseToken": {"address": "MintA"}, "liquidity": {"usd": 100}},
            {"chainId": "ethereum", "baseToken": {"address": "MintB"}, "liquidity": {"usd": 9999}},
            {"chainId": "solana", "baseToken": {"address": "MintA"}, "liquidity": {"usd": 200}},
        ]
        result = bot.best_solana_pairs(pairs)
        self.assertEqual(set(result), {"MintA"})
        self.assertEqual(result["MintA"]["liquidity"]["usd"], 200)

    def test_unexpected_top_level_response_returns_empty_mapping(self):
        self.assertEqual(bot.best_solana_pairs({"pairs": []}), {})


class ScannerTrackerEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot.alerted.clear()
        bot.candidates.clear()

    async def test_alert_is_sent_without_reddit_or_website_evidence_and_tracked(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "tracker.db"
            pair = make_pair()
            with patch.dict(os.environ, {"TRACKER_DB_PATH": str(db_path)}), \
                 patch.object(bot, "check_security", new=AsyncMock(return_value={})), \
                 patch.object(bot, "check_lp_status", new=AsyncMock(return_value="BURNED")), \
                 patch.object(bot, "check_sell_route", new=AsyncMock(return_value="OK")), \
                 patch.object(bot, "security_summary", return_value="Security checked"), \
                 patch.object(bot, "lp_status_text", return_value="LP checked"), \
                 patch.object(bot, "sell_route_text", return_value="Sell route checked"), \
                 patch.object(bot, "tg", new=AsyncMock(return_value=None)) as telegram, \
                 patch("tracker.integration.send_progress_notification", new=AsyncMock(return_value=True)):
                bot.candidates[pair["baseToken"]["address"]] = 1
                sent = await bot.evaluate_pair(object(), pair)
                self.assertTrue(sent)
                telegram.assert_awaited_once()
                await integration.drain_tracking_tasks(timeout_seconds=2)

            db = TrackerDatabase(db_path)
            self.assertEqual(db.count(), 1)
            self.assertEqual(db.list_tokens()[0]["address"], "MintNoSocial")
            self.assertEqual(db.list_tokens()[0]["initial_mc"], 50000)
            self.assertEqual(db.pending_candidate_count(), 0)

    async def test_scanner_alert_still_sends_if_tracker_storage_is_unavailable(self):
        pair = make_pair("MintTrackerDown")
        with patch.object(bot, "check_security", new=AsyncMock(return_value={})), \
             patch.object(bot, "check_lp_status", new=AsyncMock(return_value="BURNED")), \
             patch.object(bot, "check_sell_route", new=AsyncMock(return_value="OK")), \
             patch.object(bot, "security_summary", return_value="Security checked"), \
             patch.object(bot, "lp_status_text", return_value="LP checked"), \
             patch.object(bot, "sell_route_text", return_value="Sell route checked"), \
             patch.object(bot, "TrackerDatabase", side_effect=OSError("disk unavailable")), \
             patch.object(bot, "tg", new=AsyncMock(return_value=None)) as telegram, \
             patch.object(bot, "schedule_tracking", return_value=False):
            sent = await bot.evaluate_pair(object(), pair)
        self.assertTrue(sent)
        telegram.assert_awaited_once()

    async def test_failed_telegram_delivery_does_not_enter_tracker(self):
        pair = make_pair("MintTelegramFail")
        with patch.object(bot, "check_security", new=AsyncMock(return_value={})), \
             patch.object(bot, "check_lp_status", new=AsyncMock(return_value="BURNED")), \
             patch.object(bot, "check_sell_route", new=AsyncMock(return_value="OK")), \
             patch.object(bot, "tg", new=AsyncMock(side_effect=RuntimeError("Telegram unavailable"))), \
             patch.object(bot, "schedule_tracking") as schedule:
            with self.assertRaisesRegex(RuntimeError, "Telegram unavailable"):
                await bot.evaluate_pair(object(), pair)
        schedule.assert_not_called()

    async def test_fdv_fallback_can_alert_but_missing_reported_market_cap_is_not_tracked(self):
        pair = make_pair("MintFdvOnly", market_cap=None)
        pair.pop("marketCap")
        pair["fdv"] = 50000
        with patch.object(bot, "check_security", new=AsyncMock(return_value={})), \
             patch.object(bot, "check_lp_status", new=AsyncMock(return_value="BURNED")), \
             patch.object(bot, "check_sell_route", new=AsyncMock(return_value="OK")), \
             patch.object(bot, "security_summary", return_value="Security checked"), \
             patch.object(bot, "lp_status_text", return_value="LP checked"), \
             patch.object(bot, "sell_route_text", return_value="Sell route checked"), \
             patch.object(bot, "TrackerDatabase") as database, \
             patch.object(bot, "tg", new=AsyncMock(return_value=None)) as telegram, \
             patch.object(bot, "schedule_tracking", return_value=True) as schedule:
            database.return_value.prepare_alert.return_value = "pending"
            sent = await bot.evaluate_pair(object(), pair)
        self.assertTrue(sent)
        telegram.assert_awaited_once()
        self.assertIsNone(schedule.call_args.args[0]["market_cap"])


if __name__ == "__main__":
    unittest.main()
