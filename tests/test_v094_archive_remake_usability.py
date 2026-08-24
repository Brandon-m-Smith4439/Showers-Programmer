from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, *pages: str) -> None:
        self.pages = [FakePage(text) for text in pages]


def write_process_list(path: Path, order: shower_batch.ProcessOrder) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for item_number, item in sorted(order.items.items()):
        row = [""] * 22
        row[2] = item.width_text
        row[3] = item.height_text
        row[6] = f"{order.aw_order}-{item_number}"
        row[7] = " | ".join(item.processing)
        row[8] = item.delivery_date
        row[10] = item.customer or order.customer
        row[13] = order.job_name
        row[21] = " | ".join(item.machine_hints)
        sheet.append(row)
    workbook.save(path)
    workbook.close()


def sample_order() -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder("237500", "89590000 TEST ARCHIVE", "TEST CUSTOMER")
    order.items[1] = shower_batch.ProcessItem(
        1,
        width_text='30"',
        height_text='80"',
        delivery_date="08/14/2026",
        customer="TEST CUSTOMER",
        processing=["Flat Polish", "2 HINGES GEN037"],
        machine_hints=["DENVER 1"],
    )
    return order


class Version094UsabilityTests(unittest.TestCase):
    def test_location_remake_detection_handles_aw_joined_and_multiline_fields(self) -> None:
        reader = FakeReader(
            "Project #: SAMPLE\nMASTERLocation:\nDOOR REMAKE ONLY\nMarks: P2",
            "Project #: SAMPLE  Location: REMAKE PANEL  Marks: P2",
        )
        self.assertTrue(shower_batch.pdf_location_indicates_remake(reader))
        values = shower_batch.pdf_location_values(reader)
        self.assertTrue(any("REMAKE" in value.upper() for value in values))

    def test_location_remake_detection_still_ignores_unrelated_remake_notes(self) -> None:
        reader = FakeReader("Project #: SAMPLE\nLocation:\nMASTER\nMarks: P2\nNote: REMAKE hardware only")
        self.assertFalse(shower_batch.pdf_location_indicates_remake(reader))

    def test_location_value_stops_before_measurement_footer_without_colon(self) -> None:
        reader = FakeReader(
            "Project #: SAMPLE Location: MASTER Measurements are in inches "
            "Customer note: REMAKE hardware only"
        )
        self.assertEqual(shower_batch.pdf_location_values(reader), ["MASTER"])
        self.assertFalse(shower_batch.pdf_location_indicates_remake(reader))

    def test_remake_uses_diamon_fixed_large_glass_anchor(self) -> None:
        panel = programmer.Panel(1, 1, "P1", 50.0, 80.0, "DENVER 2")
        piece_bbox = (120.0, 150.0, 500.0, 550.0)
        pdf_cfg = {
            "diamon_fusion_font_size": 55,
            "diamon_fusion_edge_gap": 4,
            "remake": {"font_size": 40},
        }
        remake_x, remake_y, remake_font, remake_rect = programmer.choose_remake_banner_position(
            612.0,
            792.0,
            pdf_cfg,
            piece_bbox,
            (0.0, 600.0, 612.0, 600.0),
            panel,
            "REMAKE",
        )
        df_x, df_y, df_font, _df_rect = programmer.choose_diamon_banner_position(
            612.0,
            792.0,
            pdf_cfg,
            piece_bbox,
            (0.0, 600.0, 612.0, 600.0),
            "DIAMON FUSION",
            55.0,
            [],
            [],
            panel,
        )
        self.assertEqual(remake_font, 55.0)
        self.assertEqual(remake_x, df_x)
        self.assertEqual(remake_y, df_y)
        self.assertGreaterEqual(remake_rect[1], piece_bbox[3] + 4.0 - 0.01)

    def test_overview_text_size_changes_without_piece_override(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        stored = {
            "overview_text_boxes": {
                "237500": [{"id": "overview-a", "text": "TEST", "x": 100.0, "y": 200.0, "font_size": 21.0}]
            },
            "item_overrides": {"237500": {"1": {"machine": "DENVER 1"}}},
        }
        app.load_manual_overrides = lambda: stored
        app.save_manual_overrides = lambda data: None

        size = app.resize_overview_text_box("237500", "overview-a", 21.0, 1)

        self.assertEqual(size, 25.0)
        self.assertEqual(stored["overview_text_boxes"]["237500"][0]["font_size"], 25.0)
        self.assertEqual(stored["item_overrides"]["237500"]["1"]["machine"], "DENVER 1")

    def test_archive_inventory_restore_and_return_preserve_original_archive(self) -> None:
        order = sample_order()
        with workspace_temporary_directory() as temp_name:
            root = Path(temp_name)
            order_root = root / "Input" / "Orders"
            process_root = root / "Input" / "Process List"
            order_archive = order_root / "8.12.26"
            process_archive = process_root / "8.12.26"
            order_archive.mkdir(parents=True)
            process_archive.mkdir(parents=True)

            archived_pdf = order_archive / f"Glass Order TEST_{order.job_name}.pdf"
            archived_dxf = order_archive / f"{order.job_name}_1.dxf"
            archived_pdf.write_bytes(b"archived pdf placeholder")
            archived_dxf.write_text("0\nEOF\n", encoding="ascii")
            archived_process = process_archive / "Batch 9000.xlsx"
            write_process_list(archived_process, order)

            inventory, warnings = gui.ShowerProgrammerApp.archived_order_inventory(order_root, process_root)
            self.assertEqual(warnings, [])
            self.assertEqual(len(inventory), 1)
            entry = inventory[0]
            self.assertEqual(entry["order"].aw_order, order.aw_order)

            restored, test_process, restore_warnings = gui.ShowerProgrammerApp.copy_archived_order_for_testing(
                entry,
                order_root,
                process_root,
            )
            self.assertEqual(restore_warnings, [])
            self.assertEqual({path.name for path in restored}, {archived_pdf.name, archived_dxf.name})
            self.assertIsNotNone(test_process)
            self.assertTrue(test_process.exists())
            self.assertTrue(archived_pdf.exists())
            self.assertTrue(archived_dxf.exists())
            self.assertTrue(archived_process.exists())

            returned, return_warnings = gui.ShowerProgrammerApp.return_archived_order_to_archive(
                entry,
                order_root,
                process_root,
            )
            self.assertEqual(return_warnings, [])
            self.assertTrue(returned)
            self.assertFalse((order_root / archived_pdf.name).exists())
            self.assertFalse((order_root / archived_dxf.name).exists())
            self.assertFalse(test_process.exists())
            self.assertTrue(archived_pdf.exists())
            self.assertTrue(archived_dxf.exists())
            self.assertTrue(archived_process.exists())

    def test_raked_geometry_can_match_sketch_edge_length_when_aw_matches_dxf_bounds(self) -> None:
        # Overall DXF bounds match the A+W process dimensions, while the PDF
        # sketch can legitimately label the 28-inch bottom edge and the true
        # length of the strongly raked left edge.
        expected = (28.40625, 94.1875)
        left_dx = math.sqrt(94.3125**2 - 94.1875**2)
        with workspace_temporary_directory() as temp_name:
            path = Path(temp_name) / "raked.dxf"
            segments = (
                ((0.0, 0.0), (28.0, 0.0)),
                ((28.0, 0.0), (28.40625, 94.1875)),
                ((28.40625, 94.1875), (left_dx, 94.1875)),
                ((left_dx, 94.1875), (0.0, 0.0)),
            )
            pairs = [("0", "SECTION"), ("2", "ENTITIES")]
            for start, end in segments:
                pairs.extend(
                    [
                        ("0", "LINE"), ("8", "0"),
                        ("10", f"{start[0]:.8f}"), ("20", f"{start[1]:.8f}"),
                        ("11", f"{end[0]:.8f}"), ("21", f"{end[1]:.8f}"),
                    ]
                )
            pairs.extend([("0", "ENDSEC"), ("0", "EOF")])
            path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")

            profile = shower_batch._dxf_oos_profile(path, expected)
            self.assertIsNotNone(profile)
            self.assertTrue(shower_batch._pdf_dimensions_match_oos_profile((28.0, 94.3125), profile or {}))

    def test_geometry_reconciliation_never_reuses_a_strictly_matched_sketch_piece(self) -> None:
        order = shower_batch.ProcessOrder("237501", "89590001 UNIQUE MATCH", "TEST CUSTOMER")
        order.items[1] = shower_batch.ProcessItem(1, width_text="30", height_text="80")
        order.items[2] = shower_batch.ProcessItem(2, width_text="28.40625", height_text="94.1875")
        actual = [(1, 30.0, 80.0), (2, 10.0, 10.0)]
        profile = {
            "overall_width": 28.40625,
            "overall_height": 94.1875,
            "edge_width": 30.0,
            "edge_height": 80.0,
            "width_candidates": [30.0],
            "height_candidates": [80.0],
            "skew_shift": 0.5,
        }
        with mock.patch.object(
            shower_batch,
            "_find_oos_dxf_evidence",
            return_value=(Path("proof.dxf"), profile),
        ):
            self.assertFalse(
                shower_batch.reconcile_out_of_square_dimension_match(order, actual, Path("orders"))
            )

    def test_dimension_mismatch_message_is_sectioned_for_readability(self) -> None:
        order = sample_order()
        message = shower_batch.dimension_mismatch_message(
            order,
            Path("Glass Order TEST.pdf"),
            [(1, 29.0, 80.0)],
        )
        self.assertIn("PROCESS LIST\n", message)
        self.assertIn("SKETCH\n", message)
        self.assertIn("WHAT THE PROGRAMMER CHECKED\n", message)
        self.assertIn("NEXT STEP\n", message)


if __name__ == "__main__":
    unittest.main()
