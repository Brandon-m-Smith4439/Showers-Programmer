from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui


def make_order(aw: str, width: str = "24", height: str = "72") -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw, f"JOB {aw}", "Customer")
    order.items[1] = shower_batch.ProcessItem(
        item=1,
        width_text=width,
        height_text=height,
        delivery_date="8/17/2026",
        customer="Customer",
        processing=["DENVER 2"],
        machine_hints=["DENVER 2"],
    )
    return order


class _Task:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def progress(self, current: int, total: int, message: str) -> None:
        self.messages.append(message)

    def check_cancelled(self) -> None:
        return None


class Version115ArchiveXlsDxfPolishTests(unittest.TestCase):
    def test_dxf_reference_values_are_concise_and_rotation_uses_current_adaptive_format(self) -> None:
        self.assertEqual(gui.ShowerProgrammerApp.dxf_units_text("in", 1.0), "inches")
        self.assertEqual(gui.ShowerProgrammerApp.dxf_units_text("mm", 1.0 / 25.4), "millimeters")
        self.assertEqual(gui.ShowerProgrammerApp.format_degrees(-90.154436), "-90.154436")
        panel = programmer.Panel(1, 1, "", 15.75, 46.375, "DENVER 2")
        panel.rotation_degrees = -90.0
        panel.angle_correction_degrees = -0.154436
        summary = gui.ShowerProgrammerApp.panel_rotation_summary(panel)
        self.assertNotIn("DXF rotation:", summary)
        self.assertEqual(summary, "-90.154436 deg")

    def test_programming_evidence_keeps_compact_rotation_format(self) -> None:
        panel = {
            "machine": "DENVER 1",
            "glass_type": '3/8" Clear Tempered',
            "dimensions": "34 x 80 in",
            "process_hint": "DENVER 1",
            "source_dxf": "90000101.dxf",
            "indicator": "bottom_left",
            "rotation": 90.0,
            "angle_correction": 0.125,
            "hinge_side": "left",
            "hinges_up": False,
            "manual_override": False,
            "reasons": ["hinge side left; hinges down"],
        }
        text = gui.ShowerProgrammerApp.format_programming_evidence_panel(panel)
        self.assertIn("DXF rotation: 90 deg", text)
        self.assertIn("Out-of-square correction: +0.12 deg", text)
        self.assertNotIn("DXF rotation: 90.0000 deg", text)

    def test_legacy_xls_cache_reuses_content_after_timestamp_only_change(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            source = temp / "Batch 6337.xls"
            target = temp / "Batch 6337.xlsx"
            source.write_bytes(b"legacy-process-list")
            target.write_bytes(b"converted")
            sidecar = shower_batch.converted_xlsx_source_hash_path(target)
            digest = shower_batch.shower_cache.file_sha256(source)
            sidecar.write_text(digest, encoding="ascii")
            older = source.stat().st_mtime - 10
            os.utime(target, (older, older))
            with mock.patch.object(
                shower_batch,
                "converted_xlsx_path",
                return_value=target,
            ), mock.patch.object(
                shower_batch.shower_cache,
                "cached_file_sha256",
                return_value=digest,
            ), mock.patch.object(shower_batch.subprocess, "run") as run:
                resolved = shower_batch.convert_legacy_xls_to_xlsx(source)
            self.assertEqual(resolved, target)
            run.assert_not_called()

    def test_excel_conversion_script_disables_slow_interactive_work(self) -> None:
        script = shower_batch.legacy_xls_excel_conversion_script("C:/Batch 6337.xls", "C:/Batch 6337.xlsx")
        self.assertIn("AskToUpdateLinks = $false", script)
        self.assertIn("EnableEvents = $false", script)
        self.assertIn("ScreenUpdating = $false", script)
        self.assertIn("AutomationSecurity = 3", script)
        self.assertIn("Workbooks.Open($Source, 0, $true)", script)
        self.assertIn("CheckCompatibility = $false", script)

    def test_five_archive_revisions_force_one_synthetic_process_list(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            base = datetime(2026, 8, 17)
            entries: list[dict[str, object]] = []
            # Five revisions of one logical batch. Newer revisions keep prior
            # orders and add one more, which mirrors the production update case.
            for revision in range(5):
                archive_dir = temp / f"archive-{revision}"
                archive_dir.mkdir()
                process = archive_dir / ("Batch 6338.xls" if revision == 4 else "Batch 6338.xlsx")
                process.write_bytes(b"process")
                stamp = base - timedelta(days=4 - revision)
                os.utime(process, (stamp.timestamp(), stamp.timestamp()))
                for order_number in range(1, revision + 2):
                    entries.append(
                        {
                            "archive_name": stamp.strftime("%-m.%-d.%y") if os.name != "nt" else stamp.strftime("%#m.%#d.%y"),
                            "archive_date": stamp,
                            "batch_name": process.name,
                            "batch_key": f"rev-{revision}",
                            "process_list_files": [process],
                            "order_archive_dir": archive_dir,
                            "order_files": [],
                            "order": make_order(str(633800 + order_number)),
                        }
                    )
            groups = gui.ShowerProgrammerApp.consolidate_archive_batch_entries(entries)
            self.assertEqual(len(groups), 1)
            group = groups[0]
            self.assertEqual(group["revision_count"], 5)
            self.assertTrue(group["needs_synthetic_process_list"])
            children = group["children"]
            self.assertEqual(len(children), 5)
            self.assertTrue(all(child.get("_archive_batch_needs_synthetic_process_list") for child in children))

            orders_dir = temp / "test" / "Input" / "Orders"
            process_dir = temp / "test" / "Input" / "Process List"
            task = _Task()
            with mock.patch.object(gui.ShowerProgrammerApp, "matching_order_files", return_value=[]):
                restored, process_files, warnings = gui.ShowerProgrammerApp.copy_archived_batch_for_testing(
                    children,
                    orders_dir,
                    process_dir,
                    task_context=task,
                )
            self.assertEqual(restored, [])
            self.assertEqual(warnings, [])
            self.assertEqual(len(process_files), 1)
            self.assertEqual(process_files[0].suffix.lower(), ".xlsx")
            self.assertTrue(process_files[0].name.startswith("Archive Test Batch"))
            self.assertFalse(any(path.suffix.lower() == ".xls" for path in process_dir.iterdir()))
            parsed = shower_batch.load_process_orders_from_workbook(process_files[0])
            self.assertEqual([order.aw_order for order in parsed], ["633801", "633802", "633803", "633804", "633805"])
            self.assertTrue(any("5 archive revisions" in message for message in task.messages))


if __name__ == "__main__":
    unittest.main()
