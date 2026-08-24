from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui
import shower_regressions
from shower_temp import workspace_temporary_directory


class Version120ProfessionalHardeningTests(unittest.TestCase):
    def make_order(self, aw: str, job: str, width: str = "24", height: str = "72") -> shower_batch.ProcessOrder:
        order = shower_batch.ProcessOrder(aw, job, "SANITIZED")
        order.items[1] = shower_batch.ProcessItem(
            1,
            width_text=width,
            height_text=height,
            delivery_date="8/17/2026",
            customer="SANITIZED",
            processing=["FLAT POLISH"],
            machine_hints=["DENVER 2"],
        )
        return order

    def test_direct_legacy_xls_fixture_skips_excel(self) -> None:
        fixture = PROJECT_ROOT / "tests" / "known_orders" / "legacy_process_list_sample.xls"
        messages: list[str] = []
        with mock.patch.object(shower_batch, "convert_legacy_xls_to_xlsx", side_effect=AssertionError("Excel fallback should not run")):
            orders = shower_batch.load_process_orders_from_legacy_xls(
                fixture,
                lambda _stage, _path, message: messages.append(message),
            )
        self.assertEqual([order.aw_order for order in orders], ["700001", "700002"])
        self.assertTrue(any("Excel conversion skipped" in message for message in messages))

    def test_archive_revision_inspector_reports_deltas_and_sources(self) -> None:
        with workspace_temporary_directory() as raw:
            root = Path(raw)
            old_dir = root / "08.10.26" / "Orders"
            new_dir = root / "08.17.26" / "Orders"
            old_dir.mkdir(parents=True)
            new_dir.mkdir(parents=True)
            old_pdf = old_dir / "700101.pdf"
            new_dxf = new_dir / "700102.dxf"
            old_pdf.write_bytes(b"pdf")
            new_dxf.write_text("0\nEOF\n", encoding="ascii")
            first = self.make_order("700101", "90000001 ALPHA")
            changed = self.make_order("700101", "90000001 ALPHA", width="25")
            second = self.make_order("700102", "90000002 BETA")
            raw_entries = [
                {"order": first, "archive_name": "08.10.26", "archive_date": gui.datetime(2026, 8, 10), "batch_name": "Batch 9900.xlsx", "batch_key": "old", "process_list_files": [root / "old.xlsx"], "order_archive_dir": old_dir, "order_files": [old_pdf]},
                {"order": changed, "archive_name": "08.17.26", "archive_date": gui.datetime(2026, 8, 17), "batch_name": "Batch 9900.xlsx", "batch_key": "new", "process_list_files": [root / "new.xlsx"], "order_archive_dir": new_dir, "order_files": []},
                {"order": second, "archive_name": "08.17.26", "archive_date": gui.datetime(2026, 8, 17), "batch_name": "Batch 9900.xlsx", "batch_key": "new", "process_list_files": [root / "new.xlsx"], "order_archive_dir": new_dir, "order_files": [new_dxf]},
            ]
            groups = gui.ShowerProgrammerApp.consolidate_archive_batch_entries(raw_entries)
            text = gui.ShowerProgrammerApp.archive_revision_inspector_text(groups[0])
        self.assertIn("2 revision(s)", text)
        self.assertIn("added 700102", text)
        self.assertIn("changed 700101", text)
        self.assertIn("Resolved archived file sources", text)

    def test_system_health_check_has_expected_core_checks(self) -> None:
        with workspace_temporary_directory() as raw:
            root = Path(raw)
            with mock.patch.object(gui.ShowerProgrammerApp, "probe_network_path", return_value={"reachable": True, "elapsed_ms": 2}), mock.patch.object(gui.ShowerProgrammerApp, "excel_fallback_probe", return_value=("WARN", "fallback optional")):
                results = gui.ShowerProgrammerApp.run_system_health_checks(
                    local_orders=root / "Input" / "Orders",
                    local_process_lists=root / "Input" / "Process List",
                    network_input=root / "Network",
                    production_sketches=root / "Sketches",
                    output_dir=root / "Output",
                )
        names = {result["name"] for result in results}
        self.assertTrue({"Local Input", "Network Input", "Production Sketches", "SQLite", "Legacy XLS", "Archive Access", "Scan Cache"}.issubset(names))

    def test_system_health_check_closes_sqlite_connection(self) -> None:
        class FakeCursor:
            @staticmethod
            def fetchone() -> tuple[str]:
                return ("ok",)

        class FakeConnection:
            def __init__(self) -> None:
                self.closed = False

            @staticmethod
            def execute(_sql: str) -> FakeCursor:
                return FakeCursor()

            def close(self) -> None:
                self.closed = True

        connection = FakeConnection()
        with workspace_temporary_directory() as raw:
            root = Path(raw)
            with (
                mock.patch.object(gui.sqlite3, "connect", return_value=connection),
                mock.patch.object(gui.ShowerProgrammerApp, "probe_network_path", return_value={"reachable": True, "elapsed_ms": 1}),
                mock.patch.object(gui.ShowerProgrammerApp, "excel_fallback_probe", return_value=("WARN", "fallback optional")),
            ):
                results = gui.ShowerProgrammerApp.run_system_health_checks(
                    local_orders=root / "Input" / "Orders",
                    local_process_lists=root / "Input" / "Process List",
                    network_input=root / "Network",
                    production_sketches=root / "Sketches",
                    output_dir=root / "Output",
                )
        self.assertTrue(connection.closed)
        sqlite_result = next(result for result in results if result["name"] == "SQLite")
        self.assertEqual(sqlite_result["status"], "PASS")

    def test_known_order_regression_library_runs(self) -> None:
        results = shower_regressions.run_known_order_library(PROJECT_ROOT, shower_batch)
        self.assertEqual(results[0]["id"], "KINSDALE_OOS_001")
        self.assertEqual(results[0]["match_basis"], "sketch_dxf_envelope")

    def test_scan_stage_performance_summary_is_compact(self) -> None:
        text = gui.ShowerProgrammerApp.format_scan_stage_timings({
            "Network index": 0.8,
            "Process-list parse": 14.2,
            "PDF/DXF preview": 0.5,
            "Total": 15.7,
        })
        self.assertIn("Network index 0.80s", text)
        self.assertIn("Process-list parse 14.20s", text)
        self.assertIn("Total 15.70s", text)

    def test_test_mode_provenance_manifest_records_revision_source(self) -> None:
        with workspace_temporary_directory() as raw:
            root = Path(raw)
            source = root / "archive" / "700101.pdf"
            source.parent.mkdir()
            source.write_bytes(b"pdf")
            restored = root / "workspace" / "Input" / "Orders" / source.name
            restored.parent.mkdir(parents=True)
            restored.write_bytes(source.read_bytes())
            process = root / "workspace" / "Input" / "Process List" / "Batch.xlsx"
            process.parent.mkdir(parents=True)
            process.write_bytes(b"xlsx")
            order = self.make_order("700101", "90000001 ALPHA")
            entry = {
                "order": order,
                "order_files": [source],
                "_archive_batch_revision_count": 3,
                "_archive_order_revision_sources": [{"archive_name": "08.10.26", "batch_name": "Batch 9900.xlsx", "order_files": [source]}],
            }
            target = gui.ShowerProgrammerApp.write_test_mode_provenance_manifest(root / "workspace", [entry], [restored], [process], batch_name="Batch 9900.xlsx")
            payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["orders"][0]["revision_count"], 3)
        self.assertEqual(payload["orders"][0]["files"][0]["source_archive"], "08.10.26")

    def test_rebuild_script_runs_pre_release_smoke_test(self) -> None:
        rebuild = (PROJECT_ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        required_flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self.assertIn("tests\\release_smoke_test.py", rebuild)
        self.assertIn("Running non-destructive pre-release smoke test", rebuild)
        self.assertIn("version_1_20_professional_hardening", required_flags)

    def test_archive_tab_exposes_revision_details_control(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn('"Revision Details"', source)
        self.assertIn("archive_revision_inspector_text(target)", source)
        self.assertIn('revision_inspector_frame.grid_remove()', source)


if __name__ == "__main__":
    unittest.main()
