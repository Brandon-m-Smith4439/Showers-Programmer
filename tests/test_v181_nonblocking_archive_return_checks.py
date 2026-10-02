from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class NonblockingArchiveReturnAndChecksTests(unittest.TestCase):
    def test_restore_records_exact_active_file_pairs_and_return_uses_them_without_rescan(self) -> None:
        with workspace_temporary_directory() as temp_text:
            temp = Path(temp_text)
            order_dir = temp / "Input" / "Orders"
            process_dir = temp / "Input" / "Process List"
            archive_dir = order_dir / "Archive 2026-09-22"
            process_archive_dir = process_dir / "Archive 2026-09-22"
            for directory in (order_dir, process_dir, archive_dir, process_archive_dir):
                directory.mkdir(parents=True, exist_ok=True)

            order = shower_batch.ProcessOrder("239337", "90000001 TEST", "CUSTOMER")
            archived_pdf = archive_dir / "239337.pdf"
            archived_dxf = archive_dir / "AW_239337_01.dxf"
            archived_process = process_archive_dir / "Batch 6200.xlsx"
            archived_pdf.write_bytes(b"pdf-source")
            archived_dxf.write_bytes(b"dxf-source")
            archived_process.write_bytes(b"process-source")
            entry = {
                "order": order,
                "archive_name": "Archive 2026-09-22",
                "order_archive_dir": archive_dir,
                "order_files": [archived_pdf, archived_dxf],
                "process_list_files": [archived_process],
            }

            restored, process_files, warnings = gui.ShowerProgrammerApp.copy_archived_batch_for_testing(
                [entry], order_dir, process_dir
            )
            self.assertEqual(warnings, [])
            self.assertEqual(len(restored), 2)
            self.assertEqual(len(process_files), 1)
            self.assertTrue(entry.get("_restored_active_order_file_pairs"))
            self.assertTrue(entry.get("_restored_active_process_file_pairs"))

            original = gui.ShowerProgrammerApp.matching_order_files
            with mock.patch.object(
                gui.ShowerProgrammerApp,
                "matching_order_files",
                side_effect=AssertionError("exact restored return should not rescan Input"),
            ):
                returned, return_warnings = gui.ShowerProgrammerApp.return_archived_batch_to_archive(
                    [entry], order_dir, process_dir
                )
            self.assertEqual(return_warnings, [])
            self.assertTrue(returned)
            self.assertFalse((order_dir / archived_pdf.name).exists())
            self.assertFalse((order_dir / archived_dxf.name).exists())
            self.assertFalse((process_dir / archived_process.name).exists())
            self.assertEqual(archived_pdf.read_bytes(), b"pdf-source")
            self.assertEqual(archived_dxf.read_bytes(), b"dxf-source")
            self.assertEqual(archived_process.read_bytes(), b"process-source")
            self.assertIsNotNone(original)

    def test_archive_return_and_followup_refresh_do_not_disable_every_control(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.return_restored_batch_inputs)
        self.assertIn("lock_controls=False", source)
        self.assertIn("self.refresh_local_orders(lock_controls=False)", source)
        activity = inspect.getsource(gui.ShowerProgrammerApp.start_background_activity)
        self.assertIn("if self.background_controls_locked:", activity)
        self.assertIn("self.set_controls_enabled(False)", activity)

    def test_checked_state_has_dedicated_first_data_column(self) -> None:
        display = gui.ShowerProgrammerApp.ORDER_TREE_DISPLAY_COLUMNS
        self.assertEqual(display[0], "review")
        self.assertEqual(display[1], "order")
        self.assertIn(gui.ShowerProgrammerApp.order_tree_check_text("Order checked"), {"✓", "☑", "[✓]"})
        self.assertIn(gui.ShowerProgrammerApp.order_tree_check_text(""), {"□", "☐", "[ ]"})
        self.assertTrue(gui.ShowerProgrammerApp.order_tree_value_is_checked("✓"))
        self.assertTrue(gui.ShowerProgrammerApp.order_tree_value_is_checked("☑"))
        self.assertFalse(gui.ShowerProgrammerApp.order_tree_value_is_checked("☐"))
        source = inspect.getsource(gui.ShowerProgrammerApp.build_ui)
        self.assertIn('self.tree.column("#0", width=', source)
        self.assertIn('self.tree.column(col, width=', source)
        toggle = inspect.getsource(gui.ShowerProgrammerApp.toggle_order_checked_from_tree_checkbox)
        self.assertIn('self.tree.identify_column(event.x) != "#1"', toggle)

    def test_version_181_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 181)
        self.assertIn("VERSION_1_81_NONBLOCKING_ARCHIVE_RETURN_CHECKS", (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_81_NONBLOCKING_ARCHIVE_RETURN_CHECKS", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "exact_restored_file_manifest",
            "nonblocking_archive_return_controls",
            "nonblocking_post_return_refresh",
            "dedicated_order_check_column",
            "version_1_81_nonblocking_archive_return_checks",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
