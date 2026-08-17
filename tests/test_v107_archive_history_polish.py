from __future__ import annotations

import inspect
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

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


def order(aw_order: str, job: str) -> shower_batch.ProcessOrder:
    return shower_batch.ProcessOrder(aw_order=aw_order, job_name=job)


class Version107ArchiveHistoryPolishTests(unittest.TestCase):
    def test_action_history_diagnostics_are_collapsed_by_default_with_buttons_inside(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_action_history_settings_tab)
        self.assertIn('diagnostics_expanded = tk.BooleanVar(value=False)', source)
        self.assertIn('text="▶ Diagnostics"', source)
        self.assertIn('diagnostics_container.grid_forget()', source)
        self.assertIn('progress_actions = ctk.CTkFrame(diagnostics_container', source)
        self.assertIn('"Retry Load"', source)
        self.assertIn('"Open History Folder"', source)
        self.assertIn('"Copy Diagnostics"', source)
        self.assertIn('set_history_diagnostics_expanded(True)', source)

    def test_archive_batch_number_prefers_batch_token_and_has_numeric_fallback(self) -> None:
        self.assertEqual(gui.ShowerProgrammerApp.archive_batch_number("Batch 6144.xlsx"), "6144")
        self.assertEqual(gui.ShowerProgrammerApp.archive_batch_number("Process List 7821 updated.xlsx"), "7821")
        self.assertEqual(gui.ShowerProgrammerApp.archive_batch_group_key("Batch 06144.xlsx"), "batch:6144")

    def test_archive_revisions_collapse_to_one_batch_and_newest_duplicate_order_wins(self) -> None:
        with writable_test_directory() as temp:
            older_process = temp / "Batch 6144.xlsx"
            newer_process = temp / "Batch 6144 updated.xlsx"
            older_process.write_text("old", encoding="utf-8")
            newer_process.write_text("new", encoding="utf-8")
            older_entries = [
                {
                    "archive_name": "8.10.26",
                    "archive_date": datetime(2026, 8, 10),
                    "batch_name": older_process.name,
                    "batch_key": "old-key",
                    "process_list_files": [older_process],
                    "order_files": [],
                    "order": order("237001", "OLD JOB"),
                },
                {
                    "archive_name": "8.10.26",
                    "archive_date": datetime(2026, 8, 10),
                    "batch_name": older_process.name,
                    "batch_key": "old-key",
                    "process_list_files": [older_process],
                    "order_files": [],
                    "order": order("237002", "SECOND JOB"),
                },
            ]
            newer_entries = [
                {
                    "archive_name": "8.14.26",
                    "archive_date": datetime(2026, 8, 14),
                    "batch_name": newer_process.name,
                    "batch_key": "new-key",
                    "process_list_files": [newer_process],
                    "order_files": [],
                    "order": order("237001", "UPDATED JOB"),
                },
                {
                    "archive_name": "8.14.26",
                    "archive_date": datetime(2026, 8, 14),
                    "batch_name": newer_process.name,
                    "batch_key": "new-key",
                    "process_list_files": [newer_process],
                    "order_files": [],
                    "order": order("237003", "NEW JOB"),
                },
            ]

            groups = gui.ShowerProgrammerApp.consolidate_archive_batch_entries([*older_entries, *newer_entries])

            self.assertEqual(len(groups), 1)
            group = groups[0]
            self.assertEqual(group["display_name"], "Batch 6144")
            self.assertEqual(group["revision_count"], 2)
            self.assertEqual(group["archive_name"], "8.14.26")
            children = group["children"]
            by_aw = {child["order"].aw_order: child for child in children}
            self.assertEqual(set(by_aw), {"237001", "237002", "237003"})
            self.assertEqual(by_aw["237001"]["order"].job_name, "UPDATED JOB")
            self.assertTrue(group["needs_synthetic_process_list"])
            self.assertEqual(by_aw["237001"]["_archive_batch_authoritative_process_files"], [newer_process])

    def test_archive_revision_with_complete_newest_batch_retains_authoritative_metadata(self) -> None:
        with writable_test_directory() as temp:
            older_process = temp / "Batch 7000.xlsx"
            newer_process = temp / "Batch 7000 revised.xlsx"
            older_process.write_text("old", encoding="utf-8")
            newer_process.write_text("new", encoding="utf-8")
            entries = [
                {
                    "archive_name": "8.13.26",
                    "archive_date": datetime(2026, 8, 13),
                    "batch_name": older_process.name,
                    "batch_key": "old",
                    "process_list_files": [older_process],
                    "order_files": [],
                    "order": order("237100", "FIRST"),
                },
                {
                    "archive_name": "8.14.26",
                    "archive_date": datetime(2026, 8, 14),
                    "batch_name": newer_process.name,
                    "batch_key": "new",
                    "process_list_files": [newer_process],
                    "order_files": [],
                    "order": order("237100", "FIRST UPDATED"),
                },
                {
                    "archive_name": "8.14.26",
                    "archive_date": datetime(2026, 8, 14),
                    "batch_name": newer_process.name,
                    "batch_key": "new",
                    "process_list_files": [newer_process],
                    "order_files": [],
                    "order": order("237101", "SECOND"),
                },
            ]
            # Add the second order to the older revision too, making the newest
            # revision a complete superset/authoritative representation.
            entries.append(
                {
                    "archive_name": "8.13.26",
                    "archive_date": datetime(2026, 8, 13),
                    "batch_name": older_process.name,
                    "batch_key": "old",
                    "process_list_files": [older_process],
                    "order_files": [],
                    "order": order("237101", "SECOND OLD"),
                }
            )

            group = gui.ShowerProgrammerApp.consolidate_archive_batch_entries(entries)[0]
            # Version 1.15 deliberately uses one synthetic XLSX for every
            # multi-revision batch, even when the newest revision is complete.
            self.assertTrue(group["needs_synthetic_process_list"])
            for child in group["children"]:
                self.assertEqual(child["_archive_batch_authoritative_process_files"], [newer_process])
                self.assertTrue(child["_archive_batch_needs_synthetic_process_list"])

    def test_consolidated_batch_restore_uses_one_synthetic_process_list_when_revisions_differ(self) -> None:
        with writable_test_directory() as temp:
            older_process = temp / "archive-old" / "Batch 8100.xlsx"
            newer_process = temp / "archive-new" / "Batch 8100.xlsx"
            older_process.parent.mkdir(parents=True)
            newer_process.parent.mkdir(parents=True)
            older_process.write_text("old", encoding="utf-8")
            newer_process.write_text("new", encoding="utf-8")
            entries = [
                {
                    "archive_name": "8.14.26",
                    "archive_date": datetime(2026, 8, 14),
                    "batch_name": newer_process.name,
                    "batch_key": "new",
                    "process_list_files": [newer_process],
                    "order_files": [],
                    "order": order("238100", "NEW ONLY"),
                },
                {
                    "archive_name": "8.13.26",
                    "archive_date": datetime(2026, 8, 13),
                    "batch_name": older_process.name,
                    "batch_key": "old",
                    "process_list_files": [older_process],
                    "order_files": [],
                    "order": order("238099", "OLDER ORDER"),
                },
            ]
            group = gui.ShowerProgrammerApp.consolidate_archive_batch_entries(entries)[0]
            self.assertTrue(group["needs_synthetic_process_list"])
            restored, process_lists, warnings = gui.ShowerProgrammerApp.copy_archived_batch_for_testing(
                group["action_children"],
                temp / "active-orders",
                temp / "active-process",
            )
            self.assertEqual(restored, [])
            self.assertEqual(warnings, [])
            self.assertEqual(len(process_lists), 1)
            self.assertTrue(process_lists[0].name.startswith("Archive Test Batch "))
            self.assertNotEqual(process_lists[0].name, older_process.name)
            self.assertNotEqual(process_lists[0].name, newer_process.name)

    def test_archive_render_uses_consolidated_batch_groups(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        self.assertIn("consolidate_archive_batch_entries", source)
        self.assertIn('revision_count', source)
        self.assertIn('display_name', source)


if __name__ == "__main__":
    unittest.main()
