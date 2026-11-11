import unittest
from unittest.mock import AsyncMock, patch

from tracker.integration import (drain_tracking_tasks, track_alerted_token, process_pending_candidates, schedule_tracking, _background_tasks)


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
            def claim_completion_export(self):
                return True
            def finish_completion_export(self, *, sent):
                self.export_sent = sent
            def pending_completion_export_count(self):
                return 1
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
            def claim_completion_export(self):
                return True
            def finish_completion_export(self, *, sent):
                self.export_sent = sent
            def pending_completion_export_count(self):
                return 1
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


    async def test_final_csv_failure_remains_queued_and_retries(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        from tracker.integration import deliver_pending_completion_export

        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "tracker.db")
            for index in range(100):
                status = db.add_qualified(
                    {"address": f"ExportMint{index}", "symbol": f"E{index}", "market_cap": 100},
                    "2026-11-11T10:00:00Z",
                )
                self.assertEqual(status, "added")

            with patch("tracker.integration.export_results", return_value=Path(directory) / "results.csv"), \
                 patch("tracker.integration.send_completion_export", new=AsyncMock(return_value=False)):
                self.assertFalse(await deliver_pending_completion_export(db))
            self.assertEqual(db.pending_completion_export_count(), 1)

            with patch("tracker.integration.export_results", return_value=Path(directory) / "results.csv"), \
                 patch("tracker.integration.send_completion_export", new=AsyncMock(return_value=True)) as send:
                self.assertTrue(await deliver_pending_completion_export(db))
            send.assert_awaited_once()
            self.assertEqual(db.pending_completion_export_count(), 0)

    async def test_completion_export_claim_is_recoverable_after_restart(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tracker.db"
            db = TrackerDatabase(path)
            for index in range(100):
                db.add_qualified(
                    {"address": f"RestartExport{index}", "market_cap": 100},
                    "2026-11-11T10:00:00Z",
                )
            self.assertTrue(db.claim_completion_export())
            restarted = TrackerDatabase(path)
            self.assertEqual(restarted.pending_completion_export_count(), 1)
            self.assertFalse(restarted.claim_completion_export())
            with restarted._connect() as connection:
                connection.execute(
                    "UPDATE completion_export_queue SET claimed_at='2000-01-01T00:00:00+00:00' WHERE id=1"
                )
            self.assertTrue(restarted.claim_completion_export())

    async def test_pending_milestone_delivery_marks_sent_only_after_success(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase

        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            token = {"address": "OutboxMint", "symbol": "OUT", "market_cap": 100}
            db.add_qualified(token, "2026-11-10T10:00:00Z")
            with patch("tracker.integration.send_progress_notification", new=AsyncMock(return_value=False)) as send:
                delivered = await __import__("tracker.integration", fromlist=["deliver_pending_notifications"]).deliver_pending_notifications(db)
            self.assertEqual(delivered, 0)
            self.assertEqual(db.pending_notification_count(), 1)
            with patch("tracker.integration.send_progress_notification", new=AsyncMock(return_value=True)) as send:
                delivered = await __import__("tracker.integration", fromlist=["deliver_pending_notifications"]).deliver_pending_notifications(db)
            self.assertEqual(delivered, 1)
            self.assertEqual(db.pending_notification_count(), 0)

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

    async def test_tracker_cancellation_is_not_swallowed_as_tracker_error(self):
        cancelled = AsyncMock(side_effect=__import__("asyncio").CancelledError())
        with patch("tracker.integration.evaluate_and_record", new=cancelled):
            with self.assertRaises(__import__("asyncio").CancelledError):
                await track_alerted_token({"address": "MintCancelled", "symbol": "CXL"})
        cancelled.assert_awaited_once()


    async def test_durable_worker_completes_queued_candidate(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            db.enqueue_candidate({"address": "WorkerMint", "symbol": "WRK", "market_cap": 100})
            with patch("tracker.integration.TrackerDatabase", return_value=db), patch("tracker.integration.track_alerted_token", new=AsyncMock(return_value={"status": "rejected"})) as track:
                processed = await process_pending_candidates()
            self.assertEqual(processed, 1)
            track.assert_awaited_once()
            self.assertEqual(db.pending_candidate_count(), 0)

    async def test_transient_worker_failure_requeues_candidate(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            db.enqueue_candidate({"address": "RetryMint", "market_cap": 100})
            with patch("tracker.integration.TrackerDatabase", return_value=db), patch("tracker.integration.track_alerted_token", new=AsyncMock(return_value={"status": "evidence_error", "reason": "source offline"})):
                processed = await process_pending_candidates()
            self.assertEqual(processed, 0)
            self.assertEqual(db.pending_candidate_count(), 1)
            self.assertEqual(db.claim_next_candidate()["address"], "RetryMint")


    async def test_worker_releases_claim_when_shutdown_cancels_evaluation(self):
        import asyncio
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            db.enqueue_candidate({"address": "CancelQueueMint", "market_cap": 100})
            started = asyncio.Event()
            async def blocked(_token):
                started.set()
                await asyncio.Event().wait()
            with patch("tracker.integration.TrackerDatabase", return_value=db), patch("tracker.integration.track_alerted_token", side_effect=blocked):
                worker = asyncio.create_task(process_pending_candidates())
                await started.wait()
                worker.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await worker
            self.assertEqual(db.pending_candidate_count(), 1)
            self.assertEqual(db.claim_next_candidate()["address"], "CancelQueueMint")


    async def test_startup_resume_wakes_worker_for_pending_candidates(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        from tracker.integration import resume_pending_tracking
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            db.enqueue_candidate({"address": "ResumeMint", "market_cap": 100})
            with patch("tracker.integration.TrackerDatabase", return_value=db), patch("tracker.integration._start_candidate_worker", return_value=True) as start:
                self.assertTrue(resume_pending_tracking())
            start.assert_called_once()

    async def test_schedule_persists_before_waking_worker(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            with patch("tracker.integration.TrackerDatabase", return_value=db), patch("tracker.integration._start_candidate_worker", return_value=True) as start:
                self.assertTrue(schedule_tracking({"address": "ScheduledMint", "symbol": "SCH", "market_cap": 100}))
            self.assertEqual(db.pending_candidate_count(), 1)
            start.assert_called_once()

    async def test_queue_database_failure_uses_volatile_fallback(self):
        def accept_coroutine(coroutine):
            coroutine.close()
            return unittest.mock.Mock()

        with patch("tracker.integration.TrackerDatabase", side_effect=OSError("disk offline")), patch("tracker.integration.asyncio.create_task", side_effect=accept_coroutine) as create_task:
            self.assertTrue(schedule_tracking({"address": "FallbackMint"}))
            create_task.assert_called_once()

    async def test_schedule_failure_is_contained_and_coroutine_is_closed(self):
        from tracker.integration import schedule_tracking
        with patch("tracker.integration.TrackerDatabase", side_effect=OSError("disk offline")), patch("tracker.integration.asyncio.create_task", side_effect=RuntimeError("loop closing")):
            self.assertFalse(schedule_tracking({"address": "MintNoLoop"}))

    async def test_tracker_database_constructor_failure_is_contained(self):
        with patch("tracker.integration.TrackerDatabase", side_effect=OSError("disk unavailable")):
            result = await track_alerted_token({"address": "MintDisk", "symbol": "DSK"})
        self.assertEqual(result["status"], "tracker_error")

    async def test_tracker_exception_is_contained(self):
        with patch("tracker.integration.evaluate_and_record", new=AsyncMock(side_effect=RuntimeError("db down"))):
            result = await track_alerted_token({"address": "MintBridge", "symbol": "BRG"})
        self.assertEqual(result["status"], "tracker_error")


if __name__ == "__main__":
    unittest.main()


class CandidateRecoveryJourneyTests(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_candidate_succeeds_on_later_worker_attempt(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase

        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "tracker.db")
            db.enqueue_candidate({"address": "RetryThenPass", "symbol": "RTP", "market_cap": 12000})
            outcomes = [
                {"status": "evidence_error", "reason": "public source temporarily unavailable"},
                {"status": "rejected", "reason": "evidence did not pass both gates"},
            ]
            async def next_outcome(_token):
                return outcomes.pop(0)

            with patch("tracker.integration.TrackerDatabase", return_value=db), \
                 patch("tracker.integration.track_alerted_token", side_effect=next_outcome) as track:
                self.assertEqual(await process_pending_candidates(), 0)
                self.assertEqual(db.pending_candidate_count(), 1)
                self.assertEqual(await process_pending_candidates(), 1)

            self.assertEqual(track.await_count, 2)
            self.assertEqual(db.pending_candidate_count(), 0)

    async def test_startup_resume_processes_candidate_from_reopened_database(self):
        import tempfile
        from pathlib import Path
        from tracker.database import TrackerDatabase
        from tracker.integration import resume_pending_tracking

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tracker.db"
            first_process_db = TrackerDatabase(path)
            first_process_db.enqueue_candidate({
                "address": "RestartJourney", "symbol": "RST", "market_cap": 15000
            })
            # Reopen the same SQLite file as a fresh application process would.
            restarted_process_db = TrackerDatabase(path)
            with patch("tracker.integration.TrackerDatabase", return_value=restarted_process_db), \
                 patch("tracker.integration.track_alerted_token", new=AsyncMock(return_value={"status": "rejected"})) as track:
                self.assertTrue(resume_pending_tracking())
                await drain_tracking_tasks(timeout_seconds=2)

            track.assert_awaited_once()
            self.assertEqual(restarted_process_db.pending_candidate_count(), 0)
