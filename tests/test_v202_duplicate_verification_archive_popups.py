from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class Window:
    def __init__(self, state="normal", *, context=False):
        self._state = state
        self._shower_context_menu = context
        self.focused = self.grabbed = None

    def winfo_toplevel(self):
        return self

    def winfo_exists(self):
        return True

    def state(self):
        return self._state

    def grab_current(self):
        return self.grabbed

    def focus_displayof(self):
        return self.focused


class DuplicateVerificationArchivePopupTests(unittest.TestCase):
    def app(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        app.status_var = mock.Mock()
        app.operation_active = mock.Mock(return_value=False)
        app.refresh_local_orders = mock.Mock()
        app.open_order_review = mock.Mock()
        app.start_duplicate_source_cleanup = mock.Mock(return_value=True)
        app.show_themed_notice = mock.Mock()
        app.run_managed_task = mock.Mock(return_value=True)
        return app

    def test_hidden_focused_grabbed_and_explicit_owners_fall_back_to_root(self):
        for state in ("withdrawn", "iconic"):
            with self.subTest(state=state):
                app = self.app()
                root, hidden = Window(), Window(state)
                root.focused = root.grabbed = hidden
                app.root = root
                app._last_active_page_window = hidden
                self.assertIs(app.resolve_popup_owner(hidden), root)

    def test_context_menu_cannot_own_confirmation_even_before_hidden(self):
        app = self.app()
        root, menu, review = Window(), Window(context=True), Window()
        root.focused = root.grabbed = menu
        app.root = root
        app._last_active_page_window = review
        self.assertIs(app.resolve_popup_owner(menu), review)

    def test_visible_modal_and_explicit_review_owners_remain_valid(self):
        app = self.app()
        root, modal, review = Window(), Window(), Window()
        root.grabbed = modal
        app.root = root
        self.assertIs(app.resolve_popup_owner(root), modal)
        self.assertIs(app.resolve_popup_owner(review), review)

    def test_duplicate_choice_can_retain_different_aw_with_same_job(self):
        app = self.app()
        duplicate = shower_batch.ProcessOrder("900001", "90000001 JOB", "QA")
        original = shower_batch.ProcessOrder("900002", duplicate.job_name, "QA")
        source = Path("Original.pdf")
        removed = [Path("Copy.pdf")]
        self.assertTrue(app.apply_ambiguous_pdf_choice(duplicate, {
            "action": "remove_duplicates", "order": original, "path": source,
            "remove": removed, "retire": [duplicate],
        }, reopen_review=True))
        app.start_duplicate_source_cleanup.assert_called_once_with(
            original, removed, keep=source, reopen_review=True, retire_orders=[duplicate],
        )

    def test_duplicate_choice_cannot_target_unrelated_job_or_invalid_order(self):
        app = self.app()
        duplicate = shower_batch.ProcessOrder("900001", "90000001 JOB", "QA")
        for original in (shower_batch.ProcessOrder("900002", "90000002 OTHER", "QA"), None):
            with self.subTest(original=original):
                self.assertFalse(app.apply_ambiguous_pdf_choice(duplicate, {
                    "action": "remove_duplicates", "order": original,
                    "path": Path("Original.pdf"), "remove": [Path("Copy.pdf")],
                }))
        app.start_duplicate_source_cleanup.assert_not_called()

    def test_verified_dialog_protects_original_and_has_separate_confirmation(self):
        source = inspect.getsource(gui.ShowerProgrammerApp.show_intentional_duplicate_dialog)
        for text in (
            'values=["Remove Duplicates", "Allow Intentional Duplicate"]',
            "if not verified_var.get():", 'confirm_text="Allow Duplicate"',
            'confirm_text="Remove Duplicates"', "path != selected", "value=False",
            'text="Open"', '"order": keeper',
        ):
            self.assertIn(text, source)

    def test_batch_completion_refresh_waits_for_notice_close(self):
        with workspace_temporary_directory(prefix="v202") as raw:
            app = self.app()
            folder = Path(raw)
            order = shower_batch.ProcessOrder("900001", "90000001 JOB", "QA")
            app.folder_var = app.process_list_var = app.output_dir_var = SimpleNamespace(get=lambda: str(folder))
            app.process_batches = {"batch": {"name": "Batch 8671.xls", "all_orders": [order]}}
            app.load_processing_history_for_output = mock.Mock()
            with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
                app.archive_sent_batch_inputs("batch")
            app.load_processing_history_for_output.assert_not_called()
            app.run_managed_task.call_args.kwargs["on_done"](([folder / "archive.xls"], [], True))
            app.refresh_local_orders.assert_not_called()
            app.root.after.assert_not_called()
            app.show_themed_notice.call_args.kwargs["on_close"]()
            app.refresh_local_orders.assert_called_once_with(lock_controls=False)

    def test_batch_with_invalid_receipts_does_not_schedule_refresh(self):
        with workspace_temporary_directory(prefix="v202") as raw:
            app = self.app()
            app.folder_var = app.process_list_var = app.output_dir_var = SimpleNamespace(get=lambda: raw)
            app.process_batches = {"batch": {"all_orders": [shower_batch.ProcessOrder("900001", "90000001 JOB", "QA")]}}
            with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
                app.archive_sent_batch_inputs("batch")
            app.run_managed_task.call_args.kwargs["on_done"](([], ["No current receipt"], False))
            self.assertNotIn("on_close", app.show_themed_notice.call_args.kwargs)
            app.root.after.assert_not_called()
            app.refresh_local_orders.assert_not_called()

    def test_standalone_archive_skips_prior_pdf_matching_but_send_keeps_it(self):
        for reuse in (False, True):
            with self.subTest(reuse=reuse), workspace_temporary_directory(prefix="v202") as raw:
                folder = Path(raw)
                orders, lists = folder / "Orders", folder / "Process List"
                orders.mkdir()
                lists.mkdir()
                app = self.app()
                archived = orders / app.dated_archive_folder_name()
                archived.mkdir()
                (archived / "Original.pdf").write_bytes(b"archived input")
                batch = lists / "Batch 8671.xls"
                batch.write_bytes(b"completed list")
                app.matching_order_files = mock.Mock(return_value=[])
                order = shower_batch.ProcessOrder("900001", "90000001 JOB", "QA")
                stages = mock.Mock()
                moved, warnings = app.archive_sent_input_files_for_orders(
                    [order], orders, lists, include_process_lists=False,
                    completed_process_batches=[{"orders": [order], "files": [batch]}],
                    reuse_prior_archive_sources=reuse, stage_callback=stages,
                )
                self.assertFalse(batch.exists())
                self.assertEqual([path.name for path in moved], [batch.name])
                self.assertEqual(warnings, [])
                prior_calls = [call for call in app.matching_order_files.call_args_list if call.args[0] == archived]
                self.assertEqual(bool(prior_calls), reuse)
                self.assertTrue((archived / "Original.pdf").exists())
                stages.assert_any_call("Archiving completed process-list files...")

    def test_notice_close_continuation_is_once_only_and_ignores_child_destruction(self):
        source = inspect.getsource(gui.ShowerProgrammerApp.show_themed_notice)
        self.assertIn("event.widget is not dialog", source)
        self.assertIn("if notified:", source)
        self.assertIn('dialog.bind("<Destroy>", notify_closed, add="+")', source)
        self.assertIn("self.root.after(75, on_close)", source)
        self.assertIn("self.resolve_popup_owner", source)

    def test_version_202_metadata(self):
        version = json.loads((ROOT / "Backend" / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 202)
        self.assertIn("VERSION_2_02_VERIFIED_DUPLICATES_SENT_BATCH_POPUPS", (ROOT / "Backend" / "shower_v4_features.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
