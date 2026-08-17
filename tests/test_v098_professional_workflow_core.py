from __future__ import annotations

import inspect
import shutil
import sys
import threading
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_errors
import shower_programmer_gui as gui
import shower_state
import shower_tasks
import shower_v4_features


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = str(value)


class CancelAfterFirstProgress:
    def __init__(self) -> None:
        self.calls = 0

    def progress(self, _current: int, _total: int, _message: str) -> None:
        self.calls += 1
        if self.calls >= 2:
            raise shower_tasks.TaskCancelled("cancelled for regression test")

    def check_cancelled(self) -> None:
        return None


class Version098ProfessionalWorkflowCoreTests(unittest.TestCase):
    def test_sqlite_lifecycle_transitions_are_authoritative_and_idempotent(self) -> None:
        with writable_test_directory() as temp:
            store = shower_state.StateStore.for_output(temp)
            store.transition_order(
                "900001",
                shower_state.LifecycleState.ACTIVE,
                reason="Initial scan",
                job_name="12345678 TEST",
                in_input=True,
            )
            store.transition_order(
                "900001",
                shower_state.LifecycleState.ACTIVE,
                job_name="12345678 TEST",
                in_input=True,
            )
            store.transition_order(
                "900001",
                shower_state.LifecycleState.PROCESSED,
                reason="Programming complete",
                in_input=True,
            )

            state = store.order_state("900001")
            events = list(reversed(store.lifecycle_events("900001")))
            self.assertEqual(state["lifecycle_state"], shower_state.LifecycleState.PROCESSED)
            self.assertEqual([event["to_state"] for event in events], ["ACTIVE", "PROCESSED"])
            self.assertTrue(Path(temp, shower_state.DATABASE_NAME).exists())

    def test_lifecycle_model_covers_bad_day_operational_states(self) -> None:
        derive = shower_state.StateStore.derive_lifecycle_state
        scenarios = {
            "active": (dict(has_process_list=True, in_input=True), "ACTIVE"),
            "ready": (dict(has_process_list=True, in_input=True, status="READY"), "READY"),
            "issue": (dict(has_process_list=True, in_input=True, status="ISSUES"), "ISSUES"),
            "processed": (dict(has_process_list=True, in_input=True, status="OK"), "PROCESSED"),
            "sent": (dict(has_process_list=True, in_input=False, sent_at="2026-08-13"), "SENT"),
            "deleted": (dict(has_process_list=True, in_input=False, deleted_at="2026-08-13"), "DELETED_LOCAL"),
            "archived": (dict(has_process_list=True, in_input=False, archived=True), "ARCHIVED"),
            "testing": (dict(has_process_list=True, in_input=True, test_mode=True), "TESTING"),
            "orphan": (dict(has_process_list=False, in_input=True), "ORPHANED_INPUT"),
        }
        for name, (arguments, expected) in scenarios.items():
            with self.subTest(name=name):
                self.assertEqual(derive(**arguments), expected)

    def test_batch_identity_is_stable_for_same_logical_file_and_revisions_are_distinct(self) -> None:
        with writable_test_directory() as temp:
            xls = temp / "Batch 7000.xls"
            xlsx = temp / "Batch 7000.xlsx"
            xls.write_bytes(b"same batch bytes")
            xlsx.write_bytes(b"same batch bytes")

            first = shower_state.StateStore.batch_identity(xls)
            companion = shower_state.StateStore.batch_identity(xlsx)
            self.assertEqual(first.normalized_name, "batch 7000")
            self.assertEqual(first.key, companion.key)

            xlsx.write_bytes(b"new revision bytes")
            revised = shower_state.StateStore.batch_identity(xlsx)
            self.assertNotEqual(first.key, revised.key)
            self.assertNotEqual(first.content_hash, revised.content_hash)

    def test_background_task_manager_reports_progress_and_cancels_safely(self) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        event_ready = threading.Event()

        def emit(kind: str, payload: dict[str, object]) -> None:
            events.append((kind, payload))
            if kind in {"task_cancelled", "task_done", "task_error"}:
                event_ready.set()

        manager = shower_tasks.BackgroundTaskManager(emit)

        def worker(task: shower_tasks.TaskContext) -> None:
            for step in range(100):
                task.progress(step, 100, f"Step {step}")
                time.sleep(0.005)

        manager.start("Cancelable Test", worker, message="Starting", total=100, cancellable=True)
        deadline = time.time() + 2.0
        while not any(kind == "task_progress" and int(payload.get("current", 0)) > 0 for kind, payload in events):
            self.assertLess(time.time(), deadline)
            time.sleep(0.005)
        self.assertTrue(manager.cancel())
        self.assertTrue(event_ready.wait(2.0))
        self.assertTrue(any(kind == "task_cancelled" for kind, _payload in events))
        self.assertFalse(any(kind == "task_error" for kind, _payload in events))

    def test_structured_errors_use_codes_without_coupling_tests_to_popup_wording(self) -> None:
        mismatch = shower_errors.classify_exception(RuntimeError("Piece dimensions do not match the process list"))
        locked = shower_errors.classify_exception(PermissionError("file is locked"))
        timeout = shower_errors.classify_exception(RuntimeError("network operation timed out"))

        self.assertEqual(mismatch.code, shower_errors.ErrorCode.DIMENSION_MISMATCH)
        self.assertEqual(locked.code, shower_errors.ErrorCode.FILE_LOCKED)
        self.assertEqual(timeout.code, shower_errors.ErrorCode.NETWORK_TIMEOUT)
        self.assertIsInstance(mismatch, RuntimeError)

    def test_performance_instrumentation_persists_stage_timings(self) -> None:
        with writable_test_directory() as temp:
            store = shower_state.StateStore.for_output(temp)
            with store.measure("Scan Orders", "Synthetic stage", {"orders": 20}):
                time.sleep(0.002)
            samples = store.recent_performance()
            self.assertTrue(samples)
            self.assertEqual(samples[0]["operation"], "Scan Orders")
            self.assertEqual(samples[0]["stage"], "Synthetic stage")
            self.assertGreaterEqual(float(samples[0]["elapsed_ms"]), 0.0)

    def test_sqlite_archive_index_reuses_unchanged_date_without_reparsing_process_list(self) -> None:
        with writable_test_directory() as temp:
            order_root = temp / "Orders"
            process_root = temp / "Process List"
            archive_name = "8.13.2026"
            order_archive = order_root / archive_name
            process_archive = process_root / archive_name
            order_archive.mkdir(parents=True)
            process_archive.mkdir(parents=True)
            process_file = process_archive / "Batch 7000.xlsx"
            process_file.write_bytes(b"archive process list revision")
            dxf = order_archive / "12345678 TEST JOB_1.dxf"
            dxf.write_text("0\nEOF\n", encoding="ascii")
            order = shower_batch.ProcessOrder("900001", "12345678 TEST JOB", "Customer")
            order.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')
            store = shower_state.StateStore.for_output(temp / "Output")

            with mock.patch.object(shower_batch, "load_process_orders_from_file", return_value=[order]) as loader:
                first, first_warnings = gui.ShowerProgrammerApp.archived_order_inventory(
                    order_root,
                    process_root,
                    state_store=store,
                )
            self.assertEqual(first_warnings, [])
            self.assertEqual(loader.call_count, 1)
            self.assertEqual([entry["order"].aw_order for entry in first], ["900001"])

            with mock.patch.object(
                shower_batch,
                "load_process_orders_from_file",
                side_effect=AssertionError("unchanged archive date should be served from SQLite"),
            ):
                second, second_warnings = gui.ShowerProgrammerApp.archived_order_inventory(
                    order_root,
                    process_root,
                    state_store=store,
                )
            self.assertEqual(second_warnings, [])
            self.assertEqual([entry["order"].aw_order for entry in second], ["900001"])
            self.assertTrue(second[0]["_sqlite_indexed"])

    def test_archive_indexing_honors_cancellation_between_archive_dates(self) -> None:
        with writable_test_directory() as temp:
            order_root = temp / "Orders"
            process_root = temp / "Process List"
            for archive_name in ("8.12.2026", "8.13.2026"):
                (order_root / archive_name).mkdir(parents=True)
                (process_root / archive_name).mkdir(parents=True)
            context = CancelAfterFirstProgress()
            with self.assertRaises(shower_tasks.TaskCancelled):
                gui.ShowerProgrammerApp.archived_order_inventory(
                    order_root,
                    process_root,
                    task_context=context,
                )

    def test_test_mode_uses_isolated_workspace_and_marks_lifecycle_testing(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        with writable_test_directory() as temp:
            production_orders = temp / "Input" / "Orders"
            production_process = temp / "Input" / "Process List"
            production_output = temp / "Output"
            for folder in (production_orders, production_process, production_output):
                folder.mkdir(parents=True)
            app.runtime_root = temp
            app.folder_var = FakeVar(str(production_orders))
            app.process_list_var = FakeVar(str(production_process))
            app.output_dir_var = FakeVar(str(production_output))
            app.status_var = FakeVar()
            app.test_mode_workspace = None
            app._production_paths_before_test = None
            app.copy_archived_order_for_testing = lambda _entry, order_dir, process_dir: (
                [order_dir / "12345678 TEST_1.dxf"],
                process_dir / "Archive Test 900001.xlsx",
                [],
            )
            order = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
            order.items[1] = shower_batch.ProcessItem(1)

            workspace, warnings = app.enter_test_mode({"order": order})

            self.assertEqual(warnings, [])
            self.assertTrue(str(workspace).startswith(str(temp / "Test Workspace")))
            self.assertNotEqual(Path(app.folder_var.get()), production_orders)
            self.assertIn("Test Workspace", app.output_dir_var.get())
            state = app.state_store.order_state("900001")
            self.assertEqual(state["lifecycle_state"], shower_state.LifecycleState.TESTING)
            self.assertEqual(state["test_mode"], 1)

    def test_test_mode_blocks_all_production_send_entry_points(self) -> None:
        for method_name in ("send_sketches_to_shop", "send_programs_to_shop", "send_all_to_shop"):
            source = inspect.getsource(getattr(gui.ShowerProgrammerApp, method_name))
            with self.subTest(method=method_name):
                self.assertIn("test_mode_workspace", source)
                self.assertIn("Production sending is disabled", source)

    def test_failure_dialog_can_create_one_click_order_diagnostics(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.show_structured_error)
        diagnostic_source = inspect.getsource(gui.ShowerProgrammerApp.create_diagnostic_package_for_order)
        self.assertIn("Create Diagnostic Package", source)
        self.assertIn("self.selected_orders()", source)
        self.assertIn("error_context=structured", source)
        self.assertIn('"lifecycle"', diagnostic_source)
        self.assertIn('"recent_performance"', diagnostic_source)
        self.assertIn('"structured_error"', diagnostic_source)

    def test_batch_merge_is_core_behavior_not_a_release_monkey_patch(self) -> None:
        first = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
        first.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')
        second = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
        second.items[2] = shower_batch.ProcessItem(2, width_text='24"', height_text='80"')

        merged = shower_batch.unique_orders_from_batches([{"orders": [first]}, {"orders": [second]}])
        install_source = inspect.getsource(shower_v4_features.install)

        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0].items), {1, 2})
        self.assertNotIn("shower_batch.load_process_orders =", install_source)
        self.assertNotIn("gui.ShowerProgrammerApp.unique_orders_from_batches =", install_source)

    def test_archive_index_replacement_is_idempotent(self) -> None:
        with writable_test_directory() as temp:
            process_dir = temp / "Process" / "8.13.2026"
            order_dir = temp / "Orders" / "8.13.2026"
            process_dir.mkdir(parents=True)
            order_dir.mkdir(parents=True)
            record = shower_state.ArchiveRecord(
                archive_name="8.13.2026",
                archive_date="2026-08-13",
                batch_key="batch-key",
                batch_name="Batch 7000.xlsx",
                aw_order="900001",
                job_name="12345678 TEST",
                customer="Customer",
                process_list_path=str(process_dir / "Batch 7000.xlsx"),
                order_archive_dir=str(order_dir),
                order_files=(str(order_dir / "12345678 TEST_1.dxf"),),
            )
            store = shower_state.StateStore.for_output(temp / "Output")
            store.replace_archive_folder("8.13.2026", process_dir, order_dir, [record])
            store.replace_archive_folder("8.13.2026", process_dir, order_dir, [record])
            rows = store.archive_records(["8.13.2026"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].aw_order, "900001")


if __name__ == "__main__":
    unittest.main()
