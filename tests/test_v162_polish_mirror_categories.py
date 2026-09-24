from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui


def edgework_reader(labels: tuple[str, ...] = ()) -> PdfReader:
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(612, 792))
    left, bottom, right, top = 150.0, 170.0, 440.0, 620.0
    pdf.line(left, bottom, right, bottom)
    pdf.line(right, bottom, right, top)
    pdf.line(right, top, left, top)
    pdf.line(left, top, left, bottom)
    pdf.setFont("Helvetica", 10)
    positions = (
        ((left + right) / 2, bottom + 12),
        ((left + right) / 2, top - 18),
        (left + 8, (bottom + top) / 2),
        (right - 24, (bottom + top) / 2),
    )
    for label, (x, y) in zip(labels, positions):
        pdf.drawString(x, y, label)
    pdf.save()
    stream.seek(0)
    return PdfReader(stream)


class EdgePolishPresenceTests(unittest.TestCase):
    @staticmethod
    def panel(text: str = "") -> programmer.Panel:
        return programmer.Panel(1, 0, text, 42.0, 80.0, "DENVER 2")

    def test_programmed_piece_without_polish_warns(self) -> None:
        panel = self.panel()

        programmer.validate_edge_polish_presence(edgework_reader(), panel)

        self.assertEqual(panel.warnings, ["No Polish was detected on any of the edges."])

    def test_any_spatial_fp_or_se_prevents_warning(self) -> None:
        for label in ("FP", "FP-S", "SE"):
            with self.subTest(label=label):
                panel = self.panel()
                programmer.validate_edge_polish_presence(edgework_reader((label,)), panel)
                self.assertEqual(panel.warnings, [])

    def test_page_summary_is_conservative_fallback(self) -> None:
        panel = self.panel("Flat Polish 2 Long 2 Short As Shown")

        programmer.validate_edge_polish_presence(edgework_reader(), panel)

        self.assertEqual(panel.warnings, [])

    def test_label_only_piece_does_not_warn(self) -> None:
        panel = self.panel()
        panel.machine = ""
        panel.label_only = True
        panel.skip_dxf = True

        programmer.validate_edge_polish_presence(edgework_reader(), panel)

        self.assertEqual(panel.warnings, [])


class MirrorCategoryTests(unittest.TestCase):
    config = {"rules": {"mirror_keywords": ["MIRROR"]}}

    @staticmethod
    def order(aw_order: str, machine: str) -> shower_batch.ProcessOrder:
        order = shower_batch.ProcessOrder(aw_order, "12345678 MIRROR JOB", "Customer")
        order.items[1] = shower_batch.ProcessItem(
            item=1,
            processing=["Flat Polish side(s) 1/2/3/4"],
            machine_hints=[machine],
        )
        return order

    def test_mirror_categories_distinguish_cnc_from_sketch_only(self) -> None:
        self.assertEqual(
            shower_batch.mirror_fabrication_category(self.order("900001", "Waterjet"), self.config),
            "Mirror - With Fabrication",
        )
        self.assertEqual(
            shower_batch.mirror_fabrication_category(self.order("900002", "Packing / Shipping"), self.config),
            "Mirror - Without Fabrication",
        )
        self.assertFalse(
            gui.ShowerProgrammerApp.process_order_requires_program_dxf(
                self.order("900002", "Packing / Shipping"),
                self.config,
            )
        )

    def test_batch_label_reports_both_mirror_categories(self) -> None:
        batch = {
            "name": "Batch 7000.xls",
            "orders": [
                self.order("900001", "Waterjet"),
                self.order("900002", "Packing / Shipping"),
            ],
            "mirror_categories": {
                "Mirror - With Fabrication": ["900001"],
                "Mirror - Without Fabrication": ["900002"],
            },
        }

        label = gui.ShowerProgrammerApp.batch_tree_label(batch)

        self.assertIn("Mirror fab 1", label)
        self.assertIn("Mirror no fab 1", label)


if __name__ == "__main__":
    unittest.main()
