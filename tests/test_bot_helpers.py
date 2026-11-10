"""Focused tests for scanner-side DexScreener response handling."""
import os
import unittest
from unittest.mock import AsyncMock, patch

# bot.py reads Telegram configuration during import. Supply harmless placeholders;
# these tests never make Telegram or network requests.
with patch.dict(os.environ, {
    "TELEGRAM_BOT_TOKEN": "test-token",
    "TELEGRAM_CHAT_ID": "test-chat",
}):
    import bot


class BestSolanaPairsTests(unittest.TestCase):
    def test_ignores_malformed_entries_without_aborting_batch(self):
        pairs = [
            None,
            "not-a-pair",
            [],
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


if __name__ == "__main__":
    unittest.main()


class ScannerTrackerIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracker_schedule_failure_does_not_undo_successful_scanner_alert(self):
        pair = {
            "chainId": "solana",
            "baseToken": {"address": "MintTrackerDown", "name": "Example", "symbol": "EX"},
            "marketCap": 50000,
            "liquidity": {"usd": 10000},
            "volume": {"h24": 10000, "m5": 5000},
            "txns": {"h24": {"buys": 30, "sells": 10}, "m5": {"buys": 8, "sells": 2}},
            "priceChange": {"m5": 15},
            "url": "https://dexscreener.com/solana/MintTrackerDown",
        }
        address = "MintTrackerDown"
        bot.alerted.discard(address)
        bot.candidates[address] = 1

        with patch.object(bot, "check_security", new=AsyncMock(return_value={})), \
             patch.object(bot, "check_lp_status", new=AsyncMock(return_value="BURNED")), \
             patch.object(bot, "check_sell_route", new=AsyncMock(return_value="OK")), \
             patch.object(bot, "security_summary", return_value="Security checked"), \
             patch.object(bot, "lp_status_text", return_value="LP checked"), \
             patch.object(bot, "sell_route_text", return_value="Sell route checked"), \
             patch.object(bot, "tg", new=AsyncMock(return_value=None)) as telegram, \
             patch.object(bot, "schedule_tracking", side_effect=RuntimeError("tracker unavailable")):
            sent = await bot.evaluate_pair(object(), pair)

        self.assertTrue(sent)
        telegram.assert_awaited_once()
        self.assertIn(address, bot.alerted)
        self.assertNotIn(address, bot.candidates)
