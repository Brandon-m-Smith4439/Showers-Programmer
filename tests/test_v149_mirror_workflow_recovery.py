from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui


class MirrorWorkflowRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = ROOT / "tmp" / "tests" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    def test_letter_suffix_job_accepts_trailing_sentence_period(self) -> None:
        value = "90239127M. My Shower Door. PO 88058"
        self.assertEqual(programmer.extract_job_number(value), "90239127M")
        self.assertTrue(programmer.text_contains_job_number(value, "90239127M"))
        self.assertEqual(
            programmer.job_from_filename("Glass Order PO 88058_90239127M. My Shower Door. PO 88058.pdf"),
            "90239127M My Shower Door. PO 88058",
        )
        self.assertFalse(programmer.text_contains_job_number("90239127M.2 Other revision", "90239127M"))

    def test_mirror_waterjet_section_heading_routes_only_fabricated_item(self) -> None:
        rows = [
            ['1/4" Mirror'],
            ["Kodiak (Polisher)  (2000)"],
            ["", "", '52"11/16', '118"3/16', "", "", "239009-1", "Flat Polish", "9/25/2026", "", "MY SHOWER DOOR", "", "", "90239127M. My Shower Door. PO 88058"],
            ["Waterjet  (2200)"],
            ["", "", '52"11/16', '118"3/16', "", "", "239009-2", "INTERNAL CUTOUT MACRO", "9/25/2026", "", "MY SHOWER DOOR", "", "", "90239127M. My Shower Door. PO 88058"],
        ]

        orders = shower_batch.load_process_orders_from_rows(rows)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].aw_order, "239009")
        self.assertEqual(orders[0].item_numbers, [2])
        self.assertEqual(orders[0].items[2].desired_machine(), "WJ")

    def test_mirror_waterjet_uses_filtered_dxf_sequence_when_exact_item_is_absent(self) -> None:
        order = shower_batch.ProcessOrder("239009", "90239127M My Shower Door", "Customer")
        order.items[2] = shower_batch.ProcessItem(item=2, machine_hints=["WJ"])
        panel = programmer.Panel(
            item=2,
            page_index=2,
            text='1/4" Mirror Clear Annealed',
            width=52.6875,
            height=118.1875,
            machine="WJ",
            mirror_glass=True,
        )
        sequence_dxf = self.temp / "90239127M My Shower Door_1.dxf"
        sequence_dxf.write_text("DXF", encoding="ascii")

        def find_source(_folder, _job, candidate_panel, aw_order=None):
            del aw_order
            return sequence_dxf if (candidate_panel.source_item or candidate_panel.item) == 1 else None

        with mock.patch.object(programmer, "find_source_dxf", side_effect=find_source), mock.patch.object(
            programmer, "dxf_dimensions_match_panel", return_value=True
        ):
            shower_batch.apply_mirror_dxf_sequence_hints([panel], order, self.temp)

        self.assertEqual(panel.source_item, 1)
        self.assertTrue(any("mirror Waterjet DXF sequence P1" in reason for reason in panel.reasons))

    def test_manual_process_orders_round_trip(self) -> None:
        order = shower_batch.ProcessOrder("239009", "90239127M My Shower Door", "MY SHOWER DOOR")
        order.items[2] = shower_batch.ProcessItem(
            item=2,
            width_text="52.6875",
            height_text="118.1875",
            processing=["MANUAL PROGRAMMING"],
            machine_hints=["WJ"],
        )

        gui.ShowerProgrammerApp.save_manual_process_orders_for_output(self.temp, [order])
        loaded = gui.ShowerProgrammerApp.load_manual_process_orders_for_output(self.temp)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].aw_order, "239009")
        self.assertEqual(loaded[0].items[2].desired_machine(), "WJ")
        self.assertTrue(getattr(loaded[0], "manual_process_order", False))

    def test_startup_recovery_notice_state_persists_fingerprint_and_history(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.action_history_dir = lambda: self.temp
        issues = [
            {
                "type": "send",
                "severity": "WARN",
                "title": "Interrupted Send transaction",
                "detail": "Stopped during archive.",
                "path": "journal.json",
            }
        ]
        fingerprint = app.startup_recovery_fingerprint(issues)
        state = {"active_fingerprint": fingerprint, "history": [{"status": "WARNING"}]}

        app.save_startup_recovery_notice_state(state)
        loaded = app.load_startup_recovery_notice_state()

        self.assertEqual(loaded["active_fingerprint"], fingerprint)
        self.assertEqual(len(loaded["history"]), 1)

    def test_unchanged_startup_recovery_warning_is_only_shown_once(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.runtime_root = self.temp
        app.output_dir_var = mock.Mock(get=lambda: str(self.temp / "Output"))
        app.root = mock.Mock()
        app.action_history_dir = lambda: self.temp / "History"
        app.record_action = mock.Mock()
        app.open_settings = mock.Mock()
        warning = {
            "type": "send",
            "severity": "WARN",
            "title": "Interrupted Send transaction",
            "detail": "Stopped during archive.",
            "path": "journal.json",
        }

        with mock.patch.object(gui.shower_reliability, "startup_recovery_issues", return_value=[warning]), mock.patch.object(
            gui.messagebox, "_show", return_value="later"
        ) as show:
            app.run_startup_recovery_check()
            app.run_startup_recovery_check()

        self.assertEqual(show.call_count, 1)
        self.assertEqual(app.record_action.call_count, 1)

    def test_cleanup_discovers_authoritative_and_cached_order_files(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.queue_scan_progress = lambda *_args, **_kwargs: None
        orders_dir = self.temp / "Input" / "Orders"
        cache_dir = self.temp / "Input" / ".Network PDF Cache"
        process_dir = self.temp / "Input" / "Process List"
        output_dir = self.temp / "Output"
        for folder in (orders_dir, cache_dir, process_dir, output_dir):
            folder.mkdir(parents=True, exist_ok=True)
        local_pdf = orders_dir / "90239127M My Shower Door.pdf"
        cached_pdf = cache_dir / "Glass Order PO 88058_90239127M. My Shower Door. PO 88058.pdf"
        local_pdf.write_bytes(b"not parsed because the filename is authoritative")
        cached_pdf.write_bytes(b"not parsed because the filename is authoritative")
        order = shower_batch.ProcessOrder("239009", "90239127M. My Shower Door. PO 88058", "Customer")

        result = app.worker_prepare_local_order_delete(
            [order],
            orders_dir,
            process_dir,
            output_dir,
            None,
            False,
        )

        self.assertEqual(set(result["files"]), {local_pdf, cached_pdf})
        self.assertEqual(set(result["local_allowed_roots"]), {orders_dir, cache_dir})

    def test_existing_network_pdf_cache_can_repair_missing_local_pdf(self) -> None:
        orders_dir = self.temp / "Input" / "Orders"
        cache_dir = self.temp / "Input" / ".Network PDF Cache"
        orders_dir.mkdir(parents=True)
        cache_dir.mkdir(parents=True)
        cached_pdf = cache_dir / "Glass Order PO 88058_90239127M. My Shower Door. PO 88058.pdf"
        cached_pdf.write_bytes(b"cached source")
        order = shower_batch.ProcessOrder("239009", "90239127M. My Shower Door. PO 88058", "Customer")

        summary = gui.ShowerProgrammerApp.copy_edi_orders_for_process_orders(
            orders_dir,
            [order],
            import_snapshot={"source": str(self.temp / "Shared"), "order_files": [], "hardware_files": []},
            missing_requirements={"239009": {"pdf": True, "dxf_items": []}},
        )

        promoted = orders_dir / cached_pdf.name
        self.assertTrue(promoted.is_file())
        self.assertIn(promoted, summary["copied"])

    def test_version_149_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 149)
        source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_49_MIRROR_MANUAL_WORKFLOW", source)


if __name__ == "__main__":
    unittest.main()
