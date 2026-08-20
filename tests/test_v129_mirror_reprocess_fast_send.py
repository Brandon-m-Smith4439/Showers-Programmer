from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
from shower_programmer_gui import ShowerProgrammerApp


class MirrorWaterjetReprocessTests(unittest.TestCase):
    def landscape_mirror(self, corner: str) -> programmer.Panel:
        panel = programmer.Panel(
            item=1,
            page_index=1,
            text="1/4 Mirror Clear Annealed",
            width=58.0,
            height=42.0,
            machine="WJ",
            indicator_corner=corner,
            mirror_glass=True,
        )
        return panel

    def test_landscape_mirror_bottom_left_keeps_source_orientation(self) -> None:
        panel = self.landscape_mirror("bottom_left")
        programmer.apply_manual_wj_rotation_for_indicator(panel, {})
        self.assertEqual(panel.rotation_degrees, 0.0)

    def test_landscape_mirror_top_right_flips_180_degrees(self) -> None:
        panel = self.landscape_mirror("top_right")
        programmer.apply_manual_wj_rotation_for_indicator(panel, {})
        self.assertEqual(panel.rotation_degrees, 180.0)

    def test_saved_manual_corner_overrides_stale_rotation_during_reprocess(self) -> None:
        panel = self.landscape_mirror("bottom_left")
        config = {
            "item_overrides": {
                "237695": {
                    "1": {
                        "indicator_corner": "top_right",
                        "manual_indicator_corner": True,
                        "rotation_degrees": 0.0,
                    }
                }
            }
        }
        programmer.apply_override(panel, config, "237695")
        self.assertEqual(panel.indicator_corner, "top_right")
        self.assertEqual(panel.rotation_degrees, 180.0)


class ExactSendCleanupTests(unittest.TestCase):
    def test_exact_handoff_skips_shared_folder_enumeration(self) -> None:
        base = ROOT / "tests" / "_verification" / f"v129-send-cleanup-{uuid.uuid4().hex[:8]}"
        shared = base / "Showers Programmer Input"
        shared.mkdir(parents=True)
        order_pdf = shared / "Glass Order 90000001 SAMPLE JOB.pdf"
        order_dxf = shared / "90000001 SAMPLE JOB_1.dxf"
        process_list = shared / "Batch 7000.xls"
        unrelated = shared / "Glass Order 99999999 KEEP ME.pdf"
        for path in (order_pdf, order_dxf, process_list, unrelated):
            path.write_bytes(path.name.encode("ascii"))

        order = shower_batch.ProcessOrder(
            aw_order="240001",
            job_name="90000001 SAMPLE JOB",
            items={1: shower_batch.ProcessItem(item=1)},
        )
        plans = [
            {
                "files": [base / "local" / process_list.name],
                "orders": [order],
            }
        ]
        validated = {order.aw_order: {order_pdf.name, order_dxf.name}}

        with mock.patch.object(ShowerProgrammerApp, "EDI_IMPORT_ORDERS_DIR", shared), mock.patch.object(
            ShowerProgrammerApp,
            "index_import_source_folder_bounded",
            side_effect=AssertionError("exact cleanup must not enumerate the shared folder"),
        ):
            exact_sources = ShowerProgrammerApp.exact_network_cleanup_sources(validated, plans)
            deleted, warnings = ShowerProgrammerApp.clear_import_staging_folder(
                [order],
                completed_process_batches=plans,
                source_files=exact_sources,
                validated_order_sources_by_aw=validated,
                delete_timeout_seconds=3.0,
            )

        self.assertEqual({path.name for path in deleted}, {order_pdf.name, order_dxf.name, process_list.name})
        self.assertFalse(warnings)
        self.assertTrue(unrelated.exists())
        self.assertFalse(order_pdf.exists())
        self.assertFalse(order_dxf.exists())
        self.assertFalse(process_list.exists())
        self.assertEqual(ShowerProgrammerApp._last_network_cleanup_remaining, [])

    def test_send_summary_reports_stage_timing(self) -> None:
        details = ShowerProgrammerApp.send_complete_details(
            [Path("240001.pdf")],
            [],
            [],
            [],
            stage_timings={
                "output_copy_seconds": 0.25,
                "local_archive_seconds": 0.5,
                "network_cleanup_seconds": 1.25,
                "integrity_seconds": 0.1,
                "total_seconds": 2.1,
            },
        )
        self.assertIn("copy 0.2s", details)
        self.assertIn("network cleanup 1.2s", details)
        self.assertIn("total 2.1s", details)


if __name__ == "__main__":
    unittest.main()
