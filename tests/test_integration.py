import unittest
from unittest.mock import AsyncMock, patch

from tracker.integration import track_alerted_token


class IntegrationBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_tracker_result_is_returned(self):
        expected = {"status": "qualified", "reason": "both checks passed"}
        with patch("tracker.integration.evaluate_and_record", new=AsyncMock(return_value=expected)):
            result = await track_alerted_token({"address": "MintBridge", "symbol": "BRG"})
        self.assertEqual(result, expected)

    async def test_100th_qualified_token_exports_and_sends_results(self):
        from pathlib import Path

        class FakeDatabase:
            path = Path("/tmp/tracker-test")
            def count(self):
                return 100
            def list_tokens(self):
                return [
                    {"address": f"Mint{i}", "symbol": f"T{i}", "initial_mc": 100,
                     "peak_mc": 200 if i == 1 else 100, "current_mc": 150}
                    for i in range(100)
                ]

        with patch("tracker.integration.TrackerDatabase", return_value=FakeDatabase()), \
             patch("tracker.integration.evaluate_and_record", new=AsyncMock(return_value={"status": "qualified"})), \
             patch("tracker.integration.send_progress_notification", new=AsyncMock(return_value=True)) as send_text, \
             patch("tracker.integration.export_results", return_value=Path("/tmp/results.csv")) as export, \
             patch("tracker.integration.send_completion_export", new=AsyncMock(return_value=True)) as send_csv:
            result = await track_alerted_token({"address": "Mint99", "symbol": "T99"})

        self.assertEqual(result["status"], "qualified")
        send_text.assert_awaited_once()
        export.assert_called_once()
        send_csv.assert_awaited_once_with(Path("/tmp/results.csv"))

    async def test_tracker_exception_is_contained(self):
        with patch("tracker.integration.evaluate_and_record", new=AsyncMock(side_effect=RuntimeError("db down"))):
            result = await track_alerted_token({"address": "MintBridge", "symbol": "BRG"})
        self.assertEqual(result["status"], "tracker_error")


if __name__ == "__main__":
    unittest.main()
