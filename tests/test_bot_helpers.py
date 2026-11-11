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


class ScannerTrackerEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_telegram_alert_flows_through_durable_queue_and_qualification(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        import tracker.integration as integration
        from tracker.pipeline import evaluate_and_record

        narrative = [{
            "source": "Project website",
            "url": "https://example.org/about",
            "summary": "A community-led project building open tools for creators and digital culture.",
            "observed_at": "2026-11-10T10:00:00Z",
        }]
        attention = [{
            "source": "Reddit public search",
            "url": "https://reddit.com/r/example/post",
            "summary": "Independent authors discussed the project with measurable engagement.",
            "distinct_authors": 2,
            "post_count": 2,
            "engagement": 7,
            "observed_at": "2026-11-10T10:01:00Z",
        }]

        async def passing_collector(**_kwargs):
            return {"narrative_evidence": narrative, "attention_evidence": attention}

        async def real_pipeline_with_test_evidence(token, database):
            return await evaluate_and_record(
                token, database=database, evidence_collector=passing_collector
            )

        pair = {
            "chainId": "solana",
            "baseToken": {"address": "MintEndToEnd", "name": "Example", "symbol": "EX"},
            "marketCap": 50000,
            "liquidity": {"usd": 10000},
            "volume": {"h24": 10000, "m5": 5000},
            "txns": {"h24": {"buys": 30, "sells": 10}, "m5": {"buys": 8, "sells": 2}},
            "priceChange": {"m5": 15},
            "url": "https://dexscreener.com/solana/MintEndToEnd",
        }

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "tracker.db"
            address = "MintEndToEnd"
            bot.alerted.discard(address)
            bot.candidates[address] = 1
            with patch.dict(os.environ, {"TRACKER_DB_PATH": str(db_path)}), \
                 patch.object(bot, "check_security", new=AsyncMock(return_value={})), \
                 patch.object(bot, "check_lp_status", new=AsyncMock(return_value="BURNED")), \
                 patch.object(bot, "check_sell_route", new=AsyncMock(return_value="OK")), \
                 patch.object(bot, "security_summary", return_value="Security checked"), \
                 patch.object(bot, "lp_status_text", return_value="LP checked"), \
                 patch.object(bot, "sell_route_text", return_value="Sell route checked"), \
                 patch.object(bot, "tg", new=AsyncMock(return_value=None)) as telegram, \
                 patch("tracker.integration.evaluate_and_record", side_effect=real_pipeline_with_test_evidence), \
                 patch("tracker.integration.send_progress_notification", new=AsyncMock(return_value=True)):
                sent = await bot.evaluate_pair(object(), pair)
                self.assertTrue(sent)
                telegram.assert_awaited_once()
                await integration.drain_tracking_tasks(timeout_seconds=2)

            db = TrackerDatabase(db_path)
            self.assertEqual(db.count(), 1)
            recorded = db.list_tokens()[0]
            self.assertEqual(recorded["address"], address)
            self.assertEqual(recorded["initial_mc"], 50000)
            self.assertEqual(db.pending_candidate_count(), 0)
            self.assertIn(address, bot.alerted)
            self.assertNotIn(address, bot.candidates)

    async def test_failed_scanner_telegram_alert_never_enters_tracker_queue(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase

        pair = {
            "chainId": "solana",
            "baseToken": {"address": "MintTelegramFail", "name": "Example", "symbol": "EX"},
            "marketCap": 50000,
            "liquidity": {"usd": 10000},
            "volume": {"h24": 10000, "m5": 5000},
            "txns": {"h24": {"buys": 30, "sells": 10}, "m5": {"buys": 8, "sells": 2}},
            "priceChange": {"m5": 15},
        }
        address = "MintTelegramFail"
        bot.alerted.discard(address)
        bot.candidates[address] = 1

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "tracker.db"
            with patch.dict(os.environ, {"TRACKER_DB_PATH": str(db_path)}), \
                 patch.object(bot, "check_security", new=AsyncMock(return_value={})), \
                 patch.object(bot, "check_lp_status", new=AsyncMock(return_value="BURNED")), \
                 patch.object(bot, "check_sell_route", new=AsyncMock(return_value="OK")), \
                 patch.object(bot, "security_summary", return_value="Security checked"), \
                 patch.object(bot, "lp_status_text", return_value="LP checked"), \
                 patch.object(bot, "sell_route_text", return_value="Sell route checked"), \
                 patch.object(bot, "tg", new=AsyncMock(side_effect=RuntimeError("Telegram unavailable"))), \
                 patch.object(bot, "schedule_tracking") as schedule:
                with self.assertRaisesRegex(RuntimeError, "Telegram unavailable"):
                    await bot.evaluate_pair(object(), pair)

            schedule.assert_not_called()
            self.assertNotIn(address, bot.alerted)
            self.assertIn(address, bot.candidates)
            self.assertEqual(TrackerDatabase(db_path).pending_candidate_count(), 0)
