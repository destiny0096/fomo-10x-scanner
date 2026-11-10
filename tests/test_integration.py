import unittest
from unittest.mock import AsyncMock, patch

from tracker.integration import drain_tracking_tasks, track_alerted_token, _background_tasks


class IntegrationBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_tracker_result_is_returned(self):
        expected = {"status": "qualified", "reason": "both checks passed"}
        with patch("tracker.integration.deliver_pending_notifications", new=AsyncMock(return_value=0)), patch("tracker.integration.evaluate_and_record", new=AsyncMock(return_value=expected)):
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
             patch("tracker.integration.deliver_pending_notifications", new=AsyncMock(return_value=0)) as deliver, \
             patch("tracker.integration.export_results", return_value=Path("/tmp/results.csv")) as export, \
             patch("tracker.integration.send_completion_export", new=AsyncMock(return_value=True)) as send_csv:
            result = await track_alerted_token({"address": "Mint99", "symbol": "T99"})

        self.assertEqual(result["status"], "qualified")
        deliver.assert_awaited_once_with(unittest.mock.ANY)
        export.assert_called_once()
        send_csv.assert_awaited_once_with(Path("/tmp/results.csv"))

    async def test_final_export_cannot_overwrite_live_database(self):
        from pathlib import Path

        class FakeDatabase:
            path = Path("/tmp/tracker_results.csv")
            def count(self):
                return 100
            def list_tokens(self):
                return []

        with patch.dict("os.environ", {"TRACKER_EXPORT_PATH": "/tmp/tracker_results.csv"}), \
             patch("tracker.integration.TrackerDatabase", return_value=FakeDatabase()), \
             patch("tracker.integration.evaluate_and_record", new=AsyncMock(return_value={"status": "qualified"})), \
             patch("tracker.integration.deliver_pending_notifications", new=AsyncMock(return_value=1)), \
             patch("tracker.integration.export_results") as export, \
             patch("tracker.integration.send_completion_export", new=AsyncMock(return_value=True)) as send_csv:
            result = await track_alerted_token({"address": "Mint100", "symbol": "T100"})

        self.assertEqual(result["status"], "qualified")
        export.assert_not_called()
        send_csv.assert_not_awaited()

    async def test_drain_waits_for_background_tracker_tasks(self):
        import asyncio
        started = asyncio.Event()
        finish = asyncio.Event()

        async def work():
            started.set()
            await finish.wait()

        task = asyncio.create_task(work())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        await started.wait()
        waiter = asyncio.create_task(drain_tracking_tasks(timeout_seconds=1))
        await asyncio.sleep(0)
        self.assertFalse(waiter.done())
        finish.set()
        await waiter
        self.assertTrue(task.done())
        self.assertNotIn(task, _background_tasks)

    async def test_drain_cancels_task_after_timeout(self):
        import asyncio
        started = asyncio.Event()

        async def work():
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(work())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        await started.wait()
        await drain_tracking_tasks(timeout_seconds=0.01)
        self.assertTrue(task.cancelled())
        self.assertNotIn(task, _background_tasks)

    async def test_tracker_exception_is_contained(self):
        with patch("tracker.integration.evaluate_and_record", new=AsyncMock(side_effect=RuntimeError("db down"))):
            result = await track_alerted_token({"address": "MintBridge", "symbol": "BRG"})
        self.assertEqual(result["status"], "tracker_error")


if __name__ == "__main__":
    unittest.main()
