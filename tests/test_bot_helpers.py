"""Focused tests for scanner-side DexScreener response handling."""
import os
import unittest
from unittest.mock import patch

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
