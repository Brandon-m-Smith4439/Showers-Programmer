from __future__ import annotations

import queue
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_programmer_gui as gui
import shower_review_service
import shower_state
import shower_tasks
from shower_temp import workspace_temporary_directory


class Version200FreezeRecoveryTests(unittest.TestCase):
    def app_stub(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        app.worker_queue = queue.Queue()
        app.task_manager = shower_tasks.BackgroundTaskManager(lambda kind, payload: app.worker_queue.put((kind, payload)))
        app._managed_task_pending_ids = set()
        app._managed_task_pending_since = {}
        app._managed_task_requeued_ids = set()
        app._managed_task_handlers = {}
        app._worker_queue_dispatching = False
        app._worker_queue_last_drain_at = time.monotonic()
        app.pending_review_open_aw = ""
        app.is_busy = False
        app.finish_background_activity = mock.Mock()
        app.record_performance = mock.Mock()
        app.record_action = mock.Mock()
        app.handle_worker_queue_dispatch_failure = mock.Mock()
        app.status_var = mock.Mock()
        app.progress = mock.Mock()
        app.record_activity_progress = mock.Mock()
        app.show_structured_error = mock.Mock()
        return app

    def wait_for(self, condition):
        deadline = time.monotonic() + 3
        while not condition():
            if time.monotonic() >= deadline:
                self.fail("Background task did not settle within three seconds")
            time.sleep(0.005)

    def test_dropped_terminal_callback_is_retained_and_recovered_exactly_once(self):
        app = self.app_stub()
        completed = threading.Event()

        def broken_publisher(kind, payload):
            if kind != "task_progress":
                completed.set()
                raise RuntimeError("dropped callback")

        app.task_manager = shower_tasks.BackgroundTaskManager(broken_publisher)
        snapshot = app.task_manager.start("Fixture", lambda task: 42, message="fixture")
        self.assertTrue(completed.wait(3))
        task_id = snapshot.task_id
        done = mock.Mock()
        app._managed_task_pending_ids.add(task_id)
        app._managed_task_pending_since[task_id] = time.monotonic() - 5
        app._managed_task_handlers[task_id] = {"done": done}
        app.recover_worker_queue_liveness()
        retained = app.task_manager.terminal_event(task_id)
        self.assertIsNotNone(retained)
        app.worker_queue.put(retained)
        app.drain_worker_queue()
        done.assert_called_once_with(42)
        app.finish_background_activity.assert_called_once()
        self.assertFalse(app._managed_task_pending_ids)
        self.assertIsNone(app.task_manager.terminal_event(task_id))
        app.handle_worker_queue_dispatch_failure.assert_not_called()

    def test_failed_thread_start_does_not_strand_manager(self):
        manager = shower_tasks.BackgroundTaskManager(lambda *_args: None)
        with mock.patch.object(threading.Thread, "start", side_effect=RuntimeError("no thread")):
            with self.assertRaisesRegex(RuntimeError, "no thread"):
                manager.start("Fixture", lambda task: None, message="fixture")
        self.assertIsNone(manager.active)
        snapshot = manager.start("Retry", lambda task: "ok", message="retry")
        self.wait_for(lambda: manager.terminal_event(snapshot.task_id) is not None)
        self.assertEqual(manager.terminal_event(snapshot.task_id)[1]["result"], "ok")

    def test_hundred_sequential_tasks_have_bounded_retained_outcomes(self):
        manager = shower_tasks.BackgroundTaskManager(lambda *_args: None)
        completed_ids = []
        for index in range(100):
            snapshot = manager.start("Fixture", lambda task, index=index: index, message="fixture")
            self.wait_for(lambda: manager.terminal_event(snapshot.task_id) is not None)
            self.assertEqual(manager.terminal_event(snapshot.task_id)[1]["result"], index)
            completed_ids.append(snapshot.task_id)
        self.assertLessEqual(len(manager._terminal_events), 32)
        self.assertIsNone(manager.terminal_event(completed_ids[0]))
        self.assertIsNone(manager.active)

    def test_worker_system_exit_releases_manager_and_delivers_error(self):
        manager = shower_tasks.BackgroundTaskManager(lambda *_args: None)

        def worker(task):
            raise SystemExit("fixture exit")

        snapshot = manager.start("Fixture", worker, message="fixture")
        self.wait_for(lambda: manager.terminal_event(snapshot.task_id) is not None)
        kind, data = manager.terminal_event(snapshot.task_id)
        self.assertEqual(kind, "task_error")
        self.assertIsInstance(data["error"], SystemExit)
        self.assertIsNone(manager.active)

    def test_cancelled_task_has_recoverable_terminal_event(self):
        manager = shower_tasks.BackgroundTaskManager(lambda *_args: None)
        entered = threading.Event()
        release = threading.Event()

        def worker(task):
            entered.set()
            release.wait(3)
            task.check_cancelled()

        snapshot = manager.start("Fixture", worker, message="fixture")
        try:
            self.assertTrue(entered.wait(3))
            self.assertTrue(manager.cancel())
        finally:
            release.set()
        self.wait_for(lambda: manager.terminal_event(snapshot.task_id) is not None)
        self.assertEqual(manager.terminal_event(snapshot.task_id)[0], "task_cancelled")

    def test_heartbeat_rearms_after_detail_update_failure(self):
        app = self.app_stub()
        app.recover_worker_queue_liveness = mock.Mock()
        app.recover_invisible_modal_grab = mock.Mock()
        app.update_activity_detail = mock.Mock(side_effect=ValueError("fixture"))
        app.refresh_activity_heartbeat()
        app.root.after.assert_called_once_with(1000, app.refresh_activity_heartbeat)
        app.handle_worker_queue_dispatch_failure.assert_called_once()

    def test_heartbeat_does_not_reenter_nested_modal_queue_dispatch(self):
        app = self.app_stub()
        app._worker_queue_dispatching = True
        app._worker_queue_last_drain_at = time.monotonic() - 10
        app.drain_worker_queue = mock.Mock()
        app.recover_worker_queue_liveness()
        app.drain_worker_queue.assert_not_called()

    def test_stalled_queue_poll_restarts(self):
        app = self.app_stub()
        app._worker_queue_last_drain_at = time.monotonic() - 10
        app.drain_worker_queue = mock.Mock()
        app.recover_worker_queue_liveness()
        app.drain_worker_queue.assert_called_once()

    def test_only_abandoned_withdrawn_dialog_grab_is_released(self):
        app = self.app_stub()
        window = SimpleNamespace(state=lambda: "withdrawn", _shower_present_pending=True)
        grabber = mock.Mock()
        grabber.winfo_toplevel.return_value = window
        app.root.grab_current.return_value = grabber
        app.recover_invisible_modal_grab()
        grabber.grab_release.assert_not_called()
        window._shower_present_pending = False
        app.recover_invisible_modal_grab()
        grabber.grab_release.assert_called_once()
        grabber.grab_release.reset_mock()
        window.state = lambda: "normal"
        app.recover_invisible_modal_grab()
        grabber.grab_release.assert_not_called()

    def test_queue_handles_ten_thousand_events_in_bounded_ticks(self):
        app = self.app_stub()
        seen = []
        for index in range(10000):
            app.worker_queue.put(("ui_callback", lambda index=index: seen.append(index)))
        ticks = 0
        started = time.monotonic()
        while not app.worker_queue.empty():
            before = len(seen)
            app.drain_worker_queue()
            self.assertLessEqual(len(seen) - before, app.WORKER_QUEUE_DRAIN_MAX_EVENTS)
            ticks += 1
        elapsed = time.monotonic() - started
        self.assertEqual(seen, list(range(10000)))
        self.assertGreaterEqual(ticks, 834)
        self.assertLess(elapsed, 5)
        self.assertFalse(app._worker_queue_dispatching)
        app.handle_worker_queue_dispatch_failure.assert_not_called()

    def test_queue_fault_does_not_drop_following_callback(self):
        app = self.app_stub()
        done = mock.Mock()

        def broken():
            raise ValueError("fixture callback")

        app.worker_queue.put(("ui_callback", broken))
        app.worker_queue.put(("ui_callback", done))
        app.drain_worker_queue()
        app.drain_worker_queue()
        done.assert_called_once()
        app.handle_worker_queue_dispatch_failure.assert_called_once()

    def test_stale_progress_does_not_overwrite_newer_task(self):
        app = self.app_stub()
        app._managed_task_pending_ids.add("new")
        app.worker_queue.put(("task_progress", {"task_id": "old", "current": 1, "total": 1, "message": "old"}))
        app.drain_worker_queue()
        app.status_var.set.assert_not_called()
        app.progress.configure.assert_not_called()

    def test_known_runtime_root_does_not_repeat_writability_probes(self):
        app = self.app_stub()
        app.runtime_root = Path("runtime")
        app.preferred_runtime_root = mock.Mock(side_effect=AssertionError("Unnecessary runtime probe"))
        self.assertEqual(app.internal_orders_dir(), Path("runtime/Input/Orders"))
        self.assertEqual(app.internal_process_list_dir(), Path("runtime/Input/Process List"))
        self.assertEqual(app.internal_output_dir(), Path("runtime/Output"))
        app.preferred_runtime_root.assert_not_called()

    def test_prefetch_old_generation_cannot_pop_new_same_key_request(self):
        service = shower_review_service.ReviewContextPrefetcher(max_workers=2)
        old_entered, old_release, new_entered, new_release = (threading.Event() for _ in range(4))
        old_done, new_done = mock.Mock(), mock.Mock()

        def load_old():
            old_entered.set()
            old_release.wait(3)
            return "old"

        def load_new():
            new_entered.set()
            new_release.wait(3)
            return "new"

        try:
            service.request("same", load_old, old_done)
            self.assertTrue(old_entered.wait(3))
            old_future = service._pending["same"][0]
            service.cancel_pending()
            service.request("same", load_new, new_done)
            self.assertTrue(new_entered.wait(3))
            old_release.set()
            old_future.result(timeout=3)
            self.wait_for(lambda: old_future.done())
            self.assertEqual(service.pending_count, 1)
            old_done.assert_not_called()
            new_done.assert_not_called()
            new_release.set()
            self.wait_for(lambda: new_done.called)
            new_done.assert_called_once_with("new", None)
        finally:
            old_release.set()
            new_release.set()
            service.shutdown()

    def test_bad_prefetch_subscriber_does_not_swallow_review(self):
        service = shower_review_service.ReviewContextPrefetcher()
        release = threading.Event()
        done = threading.Event()
        received = []

        def loader():
            release.wait(3)
            return "review"

        def broken(value, error):
            raise ValueError("fixture")

        def good(value, error):
            received.append((value, error))
            done.set()

        try:
            service.request("same", loader, broken)
            self.assertFalse(service.request("same", loader, good))
            release.set()
            self.assertTrue(done.wait(3))
            self.assertEqual(received, [("review", None)])
        finally:
            release.set()
            service.shutdown()

    def test_optional_telemetry_does_not_wait_for_production_database_writer(self):
        with workspace_temporary_directory() as temp:
            store = shower_state.StateStore.for_output(Path(temp))
            connection = store.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                started = time.monotonic()
                store.record_performance("fixture", "locked", 1)
                store.record_error("fixture", "locked", "fixture")
                self.assertLess(time.monotonic() - started, 0.5)
            finally:
                connection.rollback()
                connection.close()
            store.record_performance("fixture", "unlocked", 1)
            self.assertEqual(len(store.recent_performance()), 1)

    def test_output_discovery_prunes_artifact_subtrees(self):
        with workspace_temporary_directory() as temp:
            output = Path(temp)
            batch = output / "Runs" / "10.02.26" / "6626"
            (batch / "Sketches" / "unrelated").mkdir(parents=True)
            (batch / "Programs" / "unrelated").mkdir(parents=True)
            manual = output / "Runs" / "10.02.26" / "Manual" / "1"
            (manual / "Reports").mkdir(parents=True)
            (batch / "Sketches" / "unrelated" / "manifest.json").write_text("{}")
            roots = gui.ShowerProgrammerApp.output_search_roots(output)
            self.assertEqual(set(roots), {output, batch, manual})

    def test_conflict_check_discovers_roots_once_for_all_orders(self):
        app = self.app_stub()
        app.output_search_roots = mock.Mock(return_value=[])
        orders = [SimpleNamespace(aw_order=str(index)) for index in range(1000)]
        self.assertEqual(app.existing_output_conflicts(orders, Path("output"), False, False), [])
        app.output_search_roots.assert_called_once()

    def test_scan_metadata_uses_new_model_and_one_history_snapshot(self):
        app = self.app_stub()
        app.order_by_aw = {"1": SimpleNamespace(signature="stale")}
        history = {"orders": {"1": {"sent_at": "2026-10-02T10:00:00", "sent_process_signature": "current", "last_processed": "2026-10-02", "status": "OK"}}}
        app.load_processing_history_for_output = mock.Mock(return_value=history)
        app.manual_overrides_for_output = mock.Mock(return_value={})
        app.visible_order_issues = mock.Mock(return_value=[])
        app.processed_summary_for_order = mock.Mock(return_value="Yes")
        app.review_status_from_overrides = mock.Mock(return_value="Order checked")
        app.sent_process_signature = lambda order: order.signature
        previews = [SimpleNamespace(aw_order="1", status="READY", issues=[])]
        rows = app.prepare_scan_row_metadata([SimpleNamespace(aw_order="1", signature="current")], previews, Path("output"))
        self.assertEqual(rows["1"]["sent"], "Sent 10/02/26")
        self.assertEqual(rows["1"]["status"], "OK")
        self.assertEqual(rows["1"]["review"], "Order checked")
        app.load_processing_history_for_output.assert_called_once()
        app.manual_overrides_for_output.assert_called_once()
        app.processed_summary_for_order.assert_called_once_with("1", output_dir=Path("output"), history_data=history)

    def test_review_pdf_builder_runs_as_managed_work_and_keeps_source_untouched(self):
        app = self.app_stub()
        app.block_recent_external_page_launch = mock.Mock(return_value=False)
        app.last_run_folder = None
        app.selected_or_visible_aw_orders = mock.Mock(return_value=["1", "2"])
        app.config_with_manual_overrides = mock.Mock(return_value={})
        app.sketch_review_page_indices = mock.Mock(return_value=[0])
        app.run_managed_task = mock.Mock(return_value=True)
        with workspace_temporary_directory() as temp:
            output = Path(temp)
            paths = []
            for index in range(2):
                path = output / f"{index + 1}.pdf"
                writer = gui.PdfWriter()
                writer.add_blank_page(width=100, height=200)
                with path.open("wb") as handle:
                    writer.write(handle)
                writer.close()
                paths.append(path)
            original = [path.read_bytes() for path in paths]
            app.output_dir_var = SimpleNamespace(get=lambda: str(output))
            app.folder_var = SimpleNamespace(get=lambda: str(output))
            app.generated_sketch_paths_for_orders = mock.Mock(return_value=paths)
            app.review_sketches()
            app.generated_sketch_paths_for_orders.assert_not_called()
            args, kwargs = app.run_managed_task.call_args
            self.assertEqual(args[0], "Build Sketch Review")
            task = shower_tasks.TaskContext(shower_tasks.TaskSnapshot("fixture", "PDF", "fixture"), threading.Event(), lambda snapshot: None)
            review, _folder = args[1](task)
            self.assertEqual(len(gui.PdfReader(review).pages), 2)
            self.assertEqual([path.read_bytes() for path in paths], original)


if __name__ == "__main__":
    unittest.main()
