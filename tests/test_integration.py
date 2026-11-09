import unittest
from unittest.mock import AsyncMock, patch

from tracker.integration import track_alerted_token


class IntegrationBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_tracker_result_is_returned(self):
        expected = {"status": "qualified", "reason": "both checks passed"}
        with patch("tracker.integration.evaluate_and_record", new=AsyncMock(return_value=expected)):
            result = await track_alerted_token({"address": "MintBridge", "symbol": "BRG"})
        self.assertEqual(result, expected)

    async def test_tracker_exception_is_contained(self):
        with patch("tracker.integration.evaluate_and_record", new=AsyncMock(side_effect=RuntimeError("db down"))):
            result = await track_alerted_token({"address": "MintBridge", "symbol": "BRG"})
        self.assertEqual(result["status"], "tracker_error")


if __name__ == "__main__":
    unittest.main()
