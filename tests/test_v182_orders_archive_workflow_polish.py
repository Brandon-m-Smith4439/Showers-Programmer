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


class OrdersArchiveWorkflowPolishTests(unittest.TestCase):
    def test_orders_layout_has_check_first_and_issues_last(self) -> None:
        display = gui.ShowerProgrammerApp.ORDER_TREE_DISPLAY_COLUMNS
        self.assertEqual(display[0], "review")
        self.assertEqual(display[1], "order")
        self.assertEqual(display[-1], "issues")
        self.assertIn(gui.ShowerProgrammerApp.order_tree_check_text("Order checked"), {"☑", "[✓]"})
        self.assertIn(gui.ShowerProgrammerApp.order_tree_check_text(""), {"☐", "[ ]"})
        source = inspect.getsource(gui.ShowerProgrammerApp.build_ui)
        self.assertIn('self.tree.column("#0", width=16, minwidth=14', source)
        self.assertRegex(source, r'self\.tree\.column\(col, width=(?:40|42), minwidth=(?:38|40), anchor=tk\.CENTER, stretch=False\)')
        self.assertNotIn('text=f"Order {result.aw_order}"', inspect.getsource(gui.ShowerProgrammerApp.apply_live_processing_result))

    def test_batch_status_is_blank_and_mirror_categories_have_dividers(self) -> None:
        install = inspect.getsource(gui.ShowerProgrammerApp.install_process_batches)
        self.assertNotIn('"BATCH" if column == "status"', install)
        self.assertIn("self.insert_mirror_section_dividers(parent_id, batch)", install)
        self.assertEqual(
            gui.ShowerProgrammerApp.mirror_section_label("Mirror - With Fabrication"),
            "MIRROR • WITH FABRICATION",
        )
        self.assertEqual(
            gui.ShowerProgrammerApp.mirror_section_label("Mirror - Without Fabrication"),
            "MIRROR • WITHOUT FABRICATION",
        )
        summary = gui.ShowerProgrammerApp.batch_tree_summary({"orders": [1, 2]}, 2)
        self.assertEqual(summary, "2 orders")

    def test_double_click_separator_routes_to_autofit(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_ui)
        self.assertIn('self.tree.bind("<Double-1>", self.on_orders_tree_double_click)', source)
        handler = inspect.getsource(gui.ShowerProgrammerApp.on_orders_tree_double_click)
        self.assertIn('region == "separator"', handler)
        self.assertIn("self.autofit_orders_tree_column(column)", handler)
        self.assertTrue(callable(getattr(gui.ShowerProgrammerApp, "autofit_orders_tree_column", None)))

    def test_remake_processed_text_has_red_marker(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.processed_summary_for_order)
        self.assertIn('"🔴 REMAKE • "', source)
        finalize = inspect.getsource(gui.ShowerProgrammerApp.finalize_live_processing_rows)
        self.assertIn('"🔴 REMAKE • "', finalize)

    def test_archive_return_soft_task_does_not_mark_entire_app_busy(self) -> None:
        run_source = inspect.getsource(gui.ShowerProgrammerApp.run_managed_task)
        self.assertIn("mark_busy: bool = True", run_source)
        self.assertIn("mark_busy=mark_busy", run_source)
        activity = inspect.getsource(gui.ShowerProgrammerApp.start_background_activity)
        self.assertIn("self.is_busy = bool(mark_busy)", activity)
        returned = inspect.getsource(gui.ShowerProgrammerApp.return_restored_batch_inputs)
        self.assertIn("lock_controls=False", returned)
        self.assertIn("mark_busy=False", returned)
        refresh = inspect.getsource(gui.ShowerProgrammerApp.refresh_local_orders)
        self.assertIn("mark_busy=lock_controls", refresh)
        detail = inspect.getsource(gui.ShowerProgrammerApp.update_activity_detail)
        self.assertIn('active_task = getattr(getattr(self, "task_manager", None), "active", None)', detail)

    def test_unchanged_exact_restore_return_avoids_hashing(self) -> None:
        with workspace_temporary_directory() as temp_text:
            root = Path(temp_text)
            archive = root / "archive.pdf"
            active = root / "active.pdf"
            archive.write_bytes(b"same")
            gui.ShowerProgrammerApp.copy_file_atomically(archive, active)
            with mock.patch.object(
                gui.ShowerProgrammerApp,
                "sha256_file",
                side_effect=AssertionError("untouched copy should use stat fast path"),
            ):
                result = gui.ShowerProgrammerApp.return_exact_restored_file_pair(active, archive, root)
            self.assertEqual(result, archive)
            self.assertFalse(active.exists())
            self.assertTrue(archive.exists())

    def test_version_182_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 182)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_82_ORDERS_ARCHIVE_WORKFLOW_POLISH", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "orders_check_column_alignment",
            "issues_rightmost_column",
            "orders_separator_autofit",
            "mirror_fabrication_section_dividers",
            "remake_process_red_indicator",
            "archive_return_soft_busy_progress",
            "version_1_82_orders_archive_workflow_polish",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
