from __future__ import annotations

import inspect
import queue
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer_gui as gui


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class Version095BackgroundResponsivenessTests(unittest.TestCase):
    def test_quarantine_reports_progress_for_large_local_cleanup(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Input"
            recovery = temp / "Recovery"
            source.mkdir()
            files = []
            for index in range(3):
                path = source / f"900001_{index}.dxf"
                path.write_text(str(index), encoding="utf-8")
                files.append(path)
            progress: list[tuple[int, int, str]] = []

            moved, warnings, bundle_id = gui.ShowerProgrammerApp.quarantine_paths(
                recovery,
                files,
                [source],
                ["900001"],
                progress_callback=lambda done, total, path: progress.append((done, total, path.name)),
            )

            self.assertEqual(warnings, [])
            self.assertIsNotNone(bundle_id)
            self.assertEqual(len(moved), 3)
            self.assertEqual([item[0] for item in progress], [1, 2, 3])
            self.assertTrue(all(item[1] == 3 for item in progress))

    def test_delete_entry_point_only_schedules_background_discovery(self) -> None:
        entry_source = inspect.getsource(gui.ShowerProgrammerApp.delete_selected_local_order_inputs)
        worker_source = inspect.getsource(gui.ShowerProgrammerApp.delete_order_inputs)
        self.assertIn("delete_order_inputs", entry_source)
        self.assertIn("worker_prepare_local_order_delete", worker_source)
        self.assertIn("run_managed_task", worker_source)
        combined = entry_source + worker_source
        self.assertNotIn("threading.Thread", combined)
        self.assertNotIn("matching_order_files(", combined)
        self.assertNotIn("delete_import_paths_bounded(", combined)

    def test_archive_settings_initial_refresh_is_deferred_and_threaded(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        self.assertIn("run_managed_task", source)
        self.assertIn("load_archive_settings_inventory", source)
        self.assertIn("task_context=task", source)
        self.assertNotIn('threading.Thread(target=worker, name="shower-settings-archive-load"', source)
        self.assertNotIn("self.archived_order_inventory(", source)

    def test_other_settings_history_tabs_defer_their_initial_disk_load(self) -> None:
        recovery_source = inspect.getsource(gui.ShowerProgrammerApp.build_recovery_settings_tab)
        history_source = inspect.getsource(gui.ShowerProgrammerApp.build_action_history_settings_tab)
        self.assertIn("dialog.after(250, refresh)", recovery_source)
        self.assertIn("def activate_action_history()", history_source)
        self.assertIn("parent.after_idle(refresh_history)", history_source)

    def test_archive_inventory_enrichment_is_ui_free_and_reuses_one_active_file_list(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        order = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
        entry = {"archive_name": "8.13.2026", "order": order}
        with writable_test_directory() as temp:
            active = temp / "12345678 TEST_1.dxf"
            active.write_text("0\nEOF\n", encoding="ascii")
            with (
                mock.patch.object(app, "archived_order_inventory", return_value=([entry], [])),
                mock.patch.object(
                    app,
                    "load_processing_history_for_output",
                    return_value={"orders": {"900001": {"sent_at": "2026-08-13 09:30:00"}}},
                ),
                mock.patch.object(app, "matching_order_files", return_value=[active]) as matcher,
            ):
                inventory, warnings = app.load_archive_settings_inventory(temp, temp, temp)

            self.assertEqual(warnings, [])
            self.assertTrue(inventory[0]["_active_copy"])
            self.assertEqual(inventory[0]["_sent_summary"], "Sent 08/13/26")
            self.assertEqual(inventory[0]["_sent_at"], "2026-08-13 09:30:00")
            candidate_files = matcher.call_args.kwargs["candidate_files"]
            self.assertEqual(candidate_files, [active])

    def test_confirmed_local_cleanup_worker_runs_without_tk_variable_access(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.worker_queue = queue.Queue()
        app.process_batches = {}
        with writable_test_directory() as temp:
            app.runtime_root = temp
            order_folder = temp / "Input" / "Orders"
            process_root = temp / "Input" / "Process List"
            output_dir = temp / "Output"
            order_folder.mkdir(parents=True)
            process_root.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            source = order_folder / "12345678 TEST JOB_1.dxf"
            source.write_text("0\nEOF\n", encoding="ascii")
            order = shower_batch.ProcessOrder("900006", "12345678 TEST JOB", "Customer")
            order.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')

            result = app.worker_delete_local_order_inputs(
                {
                    "orders": [order],
                    "files": [source],
                    "network_files": [],
                    "local_order_folder": order_folder,
                    "process_list_root": process_root,
                    "output_dir": output_dir,
                    "include_network": False,
                }
            )

            self.assertFalse(result.get("incomplete", False))
            self.assertEqual([order.aw_order for order in result.get("successfully_deleted_orders", [])], ["900006"])
            self.assertFalse(source.exists())
            history = gui.ShowerProgrammerApp.load_processing_history_for_output(output_dir)
            self.assertIn("900006", history["orders"])

    def test_deleted_order_receipt_can_be_written_without_tk_variables(self) -> None:
        with writable_test_directory() as temp:
            order = shower_batch.ProcessOrder("900005", "12345679 DELETE TEST", "Customer")
            order.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')

            gui.ShowerProgrammerApp.mark_orders_deleted_for_output([order], temp)

            history = gui.ShowerProgrammerApp.load_processing_history_for_output(temp)
            entry = history["orders"]["900005"]
            self.assertTrue(entry["deleted_at"])
            self.assertEqual(
                entry["deleted_process_signature"],
                gui.ShowerProgrammerApp.sent_process_signature(order),
            )

    def test_scan_status_language_matches_current_sync_workflow(self) -> None:
        scan_source = inspect.getsource(gui.ShowerProgrammerApp.worker_scan_orders)
        self.assertIn("Loading programming rules and saved overrides", scan_source)
        self.assertIn("Comparing shared process lists with the local Process List folder", scan_source)
        self.assertIn("Synchronizing visible shared order files into local Input", scan_source)
        self.assertIn("Cleaning validated shared inputs for completed or already-sent orders", scan_source)
        self.assertNotIn("Checking shared process lists", scan_source)


if __name__ == "__main__":
    unittest.main()
