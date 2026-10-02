from __future__ import annotations

import inspect
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class DuplicateCleanupSentArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_temporary_directory(prefix="v201")
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.local = self.root / "Orders"
        self.shared = self.root / "Configured Import"
        self.output = self.root / "Output"
        self.process = self.root / "Process List"
        for path in (self.local, self.shared, self.output, self.process):
            path.mkdir()
        self.kept = self.local / "90000001 Original.pdf"
        self.copy = self.local / "90000001 Original - Copy.pdf"
        self.kept.write_bytes(b"original")
        self.copy.write_bytes(b"duplicate")
        self.network_copy = self.shared / self.copy.name
        self.network_copy.write_bytes(self.copy.read_bytes())
        self.groups = [{"canonical": self.kept, "duplicates": [self.copy]}]
        self.order = shower_batch.ProcessOrder("900001", "90000001 QA", "QA")

    def cleanup(self, selected=None, groups=None, **kwargs):
        return gui.ShowerProgrammerApp.cleanup_duplicate_sources(
            self.local, self.shared, self.root / "Recovery",
            [self.copy] if selected is None else selected,
            self.groups if groups is None else groups, self.order.aw_order, **kwargs,
        )

    def app(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        app.runtime_root = self.root
        app.folder_var = SimpleNamespace(get=lambda: str(self.local))
        app.import_source_var = SimpleNamespace(get=lambda: str(self.shared))
        app.output_dir_var = SimpleNamespace(get=lambda: str(self.output))
        app.process_list_var = SimpleNamespace(get=lambda: str(self.process))
        app.operation_active = mock.Mock(return_value=False)
        app.status_var = mock.Mock()
        app.run_managed_task = mock.Mock(return_value=True)
        app.pending_import_duplicate_groups = {}
        app.clear_review_context_cache = mock.Mock()
        app.clear_duplicate_order_authorization = mock.Mock()
        app.save_pdf_order_mapping = mock.Mock()
        app.record_action = mock.Mock()
        app.show_themed_notice = mock.Mock()
        app.refresh_local_orders = mock.Mock()
        app.reconcile_active_orders_after_send = mock.Mock()
        return app

    def task(self):
        return SimpleNamespace(progress=mock.Mock(), check_cancelled=mock.Mock())

    def test_only_selected_files_removed_original_dxf_and_lists_preserved(self):
        dxf = self.local / "90000001_1.dxf"
        dxf.write_bytes(b"program geometry")
        batch = self.process / "Batch 9999.xlsx"
        batch.write_bytes(b"process list")
        result = self.cleanup()
        self.assertEqual(result["removed"], [self.copy])
        self.assertFalse(self.copy.exists())
        self.assertFalse(self.network_copy.exists())
        self.assertEqual(self.kept.read_bytes(), b"original")
        self.assertEqual(dxf.read_bytes(), b"program geometry")
        self.assertEqual(batch.read_bytes(), b"process list")
        self.assertEqual(result["warnings"], [])
        bundles = gui.ShowerProgrammerApp.quarantine_bundles(self.root / "Recovery")
        self.assertEqual(len(bundles), 1)
        recovered, warnings = gui.ShowerProgrammerApp.restore_quarantine_bundle(
            self.root / "Recovery", result["bundle"],
        )
        self.assertEqual(warnings, [])
        self.assertEqual(self.copy.read_bytes(), b"duplicate")

    def test_operator_can_keep_copy_and_remove_suggested_original(self):
        (self.shared / self.kept.name).write_bytes(self.kept.read_bytes())
        result = self.cleanup([self.kept])
        self.assertEqual(result["removed"], [self.kept])
        self.assertEqual(self.copy.read_bytes(), b"duplicate")
        self.assertTrue(self.network_copy.exists())

    def test_cannot_delete_both_sources(self):
        with self.assertRaisesRegex(ValueError, "Keep at least one"):
            self.cleanup([self.kept, self.copy])
        self.assertTrue(self.kept.exists())
        self.assertTrue(self.copy.exists())

    def test_cannot_delete_unlisted_or_external_sources(self):
        outsider = self.root / "Other.pdf"
        outsider.write_bytes(b"unrelated")
        for selected, groups in (([outsider], self.groups), ([outsider], [{"canonical": self.kept, "duplicates": [outsider]}])):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.cleanup(selected, groups)
        self.assertEqual(outsider.read_bytes(), b"unrelated")

    def test_changed_shared_file_is_preserved_and_warning_visible(self):
        self.network_copy.write_bytes(b"new revision, not the selected duplicate")
        result = self.cleanup()
        self.assertTrue(self.network_copy.exists())
        self.assertIn("changed", " ".join(result["warnings"]))

    def test_locked_local_file_does_not_delete_shared_copy(self):
        with mock.patch.object(gui.shutil, "move", side_effect=PermissionError("locked")):
            result = self.cleanup()
        self.assertEqual(result["removed"], [])
        self.assertTrue(self.copy.exists())
        self.assertTrue(self.network_copy.exists())
        self.assertTrue(result["warnings"])

    def test_slow_shared_check_times_out_without_late_deletion(self):
        original_hash = gui.ShowerProgrammerApp.sha256_file
        release = threading.Event()
        finished = threading.Event()

        def slow_hash(path):
            if path == self.network_copy:
                release.wait(2)
                finished.set()
            return original_hash(path)

        with mock.patch.object(gui.ShowerProgrammerApp, "sha256_file", side_effect=slow_hash):
            started = time.monotonic()
            result = self.cleanup(timeout_seconds=0.1)
            self.assertLess(time.monotonic() - started, 1)
            self.assertIn("timed out", " ".join(result["warnings"]))
            release.set()
            self.assertTrue(finished.wait(2))
            time.sleep(0.05)
        self.assertTrue(self.network_copy.exists())

    def test_worker_capacity_exhaustion_returns_warning(self):
        with mock.patch.object(gui.ShowerProgrammerApp, "start_bounded_network_thread", return_value=False):
            result = self.cleanup()
        self.assertIn("busy", " ".join(result["warnings"]))
        self.assertTrue(self.network_copy.exists())

    def test_start_returns_before_file_io_and_honors_configured_import_folder(self):
        app = self.app()
        app.cleanup_duplicate_sources = mock.Mock(return_value={"removed": [self.copy], "warnings": []})
        app.start_duplicate_source_cleanup(self.order, [self.copy], keep=self.kept)
        app.cleanup_duplicate_sources.assert_not_called()
        worker = app.run_managed_task.call_args.args[1]
        worker(self.task())
        self.assertEqual(app.cleanup_duplicate_sources.call_args.args[1], self.shared)
        self.assertTrue(app.run_managed_task.call_args.kwargs["cancellable"] is False)

    def test_assignment_to_another_order_blocks_removal(self):
        app = self.app()
        app.load_manual_overrides_for_output = mock.Mock(return_value={"pdf_order_mappings": {"900002": {"filename": self.copy.name}}})
        app.start_duplicate_source_cleanup(self.order, [self.copy], keep=self.kept)
        with self.assertRaisesRegex(ValueError, "assigned to A&W 900002"):
            app.run_managed_task.call_args.args[1](self.task())
        self.assertTrue(self.copy.exists())

    def test_explicit_duplicate_entry_retired_original_kept(self):
        app = self.app()
        duplicate_order = shower_batch.ProcessOrder("900002", self.order.job_name, "QA")
        app.start_duplicate_source_cleanup(self.order, [self.copy], keep=self.kept, retire_orders=[duplicate_order])
        args, kwargs = app.run_managed_task.call_args
        payload = args[1](self.task())
        history = app.load_processing_history_for_output(self.output)
        self.assertNotIn(self.order.aw_order, history["orders"])
        self.assertEqual(history["orders"]["900002"]["deleted_scope"], "duplicate")
        self.assertTrue(app.order_is_terminal_in_history(duplicate_order, history))
        kwargs["on_done"](payload)
        app.reconcile_active_orders_after_send.assert_called_once_with([duplicate_order])
        app.save_pdf_order_mapping.assert_called_once_with(self.order, self.kept)
        app.refresh_local_orders.assert_not_called()
        self.assertTrue(self.kept.exists())

    def test_discarded_duplicate_not_reactivated_by_shared_pdf_or_batch(self):
        app = self.app()
        app.mark_orders_deleted_for_output([self.order], self.output, {self.order.aw_order: "duplicate"})
        batch = {"orders": [self.order], "all_orders": [self.order], "path": self.process / "Batch 9999.xlsx"}
        with mock.patch.object(gui.ShowerProgrammerApp, "missing_order_input_requirements", return_value={self.order.aw_order: {"pdf": True}}):
            self.assertEqual(app.reactivate_deleted_orders_available_in_shared_input([batch], {"files": [self.network_copy]}, self.local, self.output), [])
        self.assertEqual(app.reactivate_reimported_process_list_orders([batch], [batch["path"]], self.output), [])

    def test_archive_receipt_checks_run_only_in_worker_and_refresh_after_notice(self):
        app = self.app()
        app.load_processing_history_for_output = mock.Mock(return_value={"orders": {}})
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            app.archive_sent_order_inputs([self.order])
        app.load_processing_history_for_output.assert_not_called()
        worker = app.run_managed_task.call_args.args[1]
        result = worker(self.task())
        app.load_processing_history_for_output.assert_called_once()
        self.assertIn("No current sent receipt", result[1][0])
        order = []
        app.show_themed_notice.side_effect = lambda *_a, **_k: order.append("notice")
        app.root.after.side_effect = lambda *_a: order.append("schedule")
        app.run_managed_task.call_args.kwargs["on_done"](result)
        self.assertEqual(order, ["notice"])
        app.refresh_local_orders.assert_not_called()
        app.show_themed_notice.call_args.kwargs["on_close"]()
        app.refresh_local_orders.assert_called_once_with(lock_controls=False)

    def test_selected_sent_archive_moves_inputs_retains_incomplete_process_list(self):
        app = self.app()
        app.archive_manual_process_orders_for_output = mock.Mock(return_value=[])
        app.file_matches_process_orders = mock.Mock(return_value=False)
        app.matching_order_files = mock.Mock(return_value=[self.kept])
        batch = self.process / "Batch 9999.xlsx"
        batch.write_bytes(b"active incomplete batch")
        app.save_processing_history_for_output(self.output, {"orders": {self.order.aw_order: {"sent_at": "2026-10-02", "sent_process_signature": app.sent_process_signature(self.order)}}})
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            app.archive_sent_order_inputs([self.order])
        files, warnings = app.run_managed_task.call_args.args[1](self.task())
        self.assertEqual(warnings, [])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), b"original")
        self.assertFalse(self.kept.exists())
        self.assertTrue(batch.exists())
        self.assertTrue(self.copy.exists())

    def test_archive_rejects_concurrent_task_without_opening_dialog(self):
        app = self.app()
        app.operation_active.return_value = True
        with mock.patch.object(gui.messagebox, "askyesno") as dialog:
            app.archive_sent_order_inputs([self.order])
            app.archive_sent_batch_inputs("batch")
        dialog.assert_not_called()
        app.run_managed_task.assert_not_called()

    def test_archive_and_duplicate_ui_do_not_start_shared_scan_on_completion(self):
        for method in (gui.ShowerProgrammerApp.archive_sent_order_inputs, gui.ShowerProgrammerApp.archive_sent_batch_inputs, gui.ShowerProgrammerApp.start_duplicate_source_cleanup):
            source = inspect.getsource(method)
            self.assertNotIn("self.scan_orders", source)
            self.assertIn("lock_controls=False", source)


if __name__ == "__main__":
    unittest.main()
