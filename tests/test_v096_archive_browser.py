from __future__ import annotations

import inspect
import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest import mock

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_process_list(path: Path, aw_order: str, job: str, customer: str = "Customer") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    row = [""] * 22
    row[2] = '30"'
    row[3] = '80"'
    row[6] = f"{aw_order}-1"
    row[10] = customer
    row[13] = job
    row[21] = "DENVER 1"
    sheet.append(row)
    workbook.save(path)
    workbook.close()


class Version096ArchiveBrowserTests(unittest.TestCase):
    def test_date_filter_defaults_to_seven_days_and_supports_single_date(self) -> None:
        today = datetime(2026, 8, 13)
        start, finish = gui.ShowerProgrammerApp.normalize_archive_date_filter("", "", today=today)
        self.assertEqual(start, datetime(2026, 8, 7))
        self.assertEqual(finish, today)

        single_from = gui.ShowerProgrammerApp.normalize_archive_date_filter("8/10/2026", "", today=today)
        single_to = gui.ShowerProgrammerApp.normalize_archive_date_filter("", "8.10.26", today=today)
        self.assertEqual(single_from, (datetime(2026, 8, 10), datetime(2026, 8, 10)))
        self.assertEqual(single_to, (datetime(2026, 8, 10), datetime(2026, 8, 10)))

    def test_archive_directory_scan_respects_requested_date_window(self) -> None:
        with writable_test_directory() as temp:
            for name in ("8.13.26", "8.7.26", "8.6.26", "7.31.26"):
                (temp / name).mkdir()
            selected = gui.ShowerProgrammerApp.archive_date_directories(
                temp,
                date_from=datetime(2026, 8, 7),
                date_to=datetime(2026, 8, 13),
            )
            self.assertEqual([path.name for path in selected], ["8.13.26", "8.7.26"])

    def test_order_inventory_is_batch_scoped_and_does_not_open_pdfs_during_browse(self) -> None:
        with writable_test_directory() as temp:
            orders_root = temp / "Orders"
            process_root = temp / "Process List"
            recent_order_dir = orders_root / "8.13.26"
            recent_process_dir = process_root / "8.13.26"
            old_process_dir = process_root / "8.1.26"
            recent_order_dir.mkdir(parents=True)
            recent_process_dir.mkdir(parents=True)
            old_process_dir.mkdir(parents=True)
            write_process_list(recent_process_dir / "Batch 8200.xlsx", "900001", "12345678 TEST")
            write_process_list(old_process_dir / "Batch OLD.xlsx", "900002", "87654321 OLD")
            (recent_order_dir / "Glass Order 12345678 TEST.pdf").write_bytes(b"not opened during browsing")
            (recent_order_dir / "12345678 TEST_1.dxf").write_text("0\nEOF\n", encoding="ascii")

            with mock.patch.object(
                programmer,
                "extract_first_page_text",
                side_effect=AssertionError("Archive browsing should not open PDF text"),
            ):
                inventory, warnings = gui.ShowerProgrammerApp.archived_order_inventory(
                    orders_root,
                    process_root,
                    date_from=datetime(2026, 8, 7),
                    date_to=datetime(2026, 8, 13),
                )

            self.assertEqual(warnings, [])
            self.assertEqual(len(inventory), 1)
            self.assertEqual(inventory[0]["archive_name"], "8.13.26")
            self.assertEqual(inventory[0]["batch_name"], "Batch 8200.xlsx")
            self.assertEqual(inventory[0]["order"].aw_order, "900001")
            self.assertTrue(inventory[0]["_fast_file_mapping"])

    def test_run_inventory_is_date_filtered_and_history_is_grouped_into_run(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        with writable_test_directory() as temp:
            output = temp / "Output"
            current_run = output / "Runs" / "8.13.26" / "Batch 8200"
            old_run = output / "Runs" / "8.1.26" / "Batch OLD"
            for run in (current_run, old_run):
                (run / "Sketches").mkdir(parents=True)
                (run / "Programs").mkdir()
                (run / "Reports").mkdir()
                (run / "manifest.json").write_text(
                    json.dumps({"created": "2026-08-13 09:00:00"}),
                    encoding="utf-8",
                )
            (current_run / "Sketches" / "900001.pdf").write_bytes(b"pdf")
            (current_run / "Programs" / "90000101.dxf").write_text("0\nEOF\n", encoding="ascii")
            history = {
                "orders": {
                    "900001": {
                        "run_folder": str(current_run),
                        "last_processed": "2026-08-13 09:00:00",
                        "status": "OK",
                        "output_pdf": str(current_run / "Sketches" / "900001.pdf"),
                    }
                }
            }
            with mock.patch.object(app, "load_processing_history_for_output", return_value=history):
                runs, warnings = app.load_archive_run_settings_inventory(
                    output,
                    date_from=datetime(2026, 8, 7),
                    date_to=datetime(2026, 8, 13),
                )

            self.assertEqual(warnings, [])
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["batch_name"], "Batch 8200")
            self.assertEqual(runs[0]["sketch_count"], 1)
            self.assertEqual(runs[0]["program_count"], 1)
            self.assertEqual(runs[0]["orders"][0]["aw_order"], "900001")

    def test_archive_settings_source_contains_grouping_sorting_modes_and_incremental_loading(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        self.assertIn('show="tree headings"', source)
        self.assertIn('open=auto_open', source)
        self.assertIn('sort_column = "archive"', source)
        self.assertIn('sort_descending = True', source)
        self.assertIn('"Orders / Sketch Archives", "Processing Runs"', source)
        self.assertIn('"Load 7 More Days"', source)
        self.assertIn('normalize_archive_date_filter', source)
        self.assertIn('load_archive_run_settings_inventory', source)


if __name__ == "__main__":
    unittest.main()
