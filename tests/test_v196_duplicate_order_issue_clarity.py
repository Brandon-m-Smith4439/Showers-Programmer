from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui

JOB = "90479383 OCTOPLEX BLOCK 19 UNIT 135 4365"


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_sketch(path: Path) -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 720, JOB)
    document.showPage()
    document.drawString(72, 720, '30" x 72"')
    document.drawString(72, 690, "Marks: P1")
    document.showPage()
    document.save()


def make_order() -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw_order="239591", job_name=JOB, customer="BFS East Greenville SC MW")
    order.items[1] = shower_batch.ProcessItem(item=1, width_text="30", height_text="72")
    return order


class Version196DuplicateOrderIssueClarityTests(unittest.TestCase):
    def test_trailing_source_reference_comes_from_end_of_pdf_name(self) -> None:
        path = Path("Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf")
        self.assertEqual(programmer.trailing_pdf_reference(path), "43659060")

    def test_same_job_different_po_references_report_possible_duplicate_entry(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43658876.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf"
            write_sketch(first)
            write_sketch(second)

            with self.assertRaises(programmer.AmbiguousPdfError) as raised:
                shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config={})

            message = str(raised.exception)
            self.assertIn("Possible duplicate order entry", message)
            self.assertIn("Job Nr 90479383", message)
            self.assertIn("2 sketches", message)
            self.assertIn("different PO/reference numbers", message)
            self.assertIn("43658876", message)
            self.assertIn("43659060", message)
            self.assertLess(len(message), 230)

    def test_orders_grid_uses_compact_duplicate_entry_summary(self) -> None:
        long_issue = (
            "Possible duplicate order entry: Job Nr 90479383 matches 2 sketches with different "
            "PO/reference numbers (43658876, 43659060). Verify A&W order 239591 before processing."
        )
        concise = gui.ShowerProgrammerApp.concise_issue_text(long_issue)
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        if version["version_number"] == 196:
            self.assertEqual(
                concise,
                "Possible duplicate entry: Job 90479383 has 2 sketches with different PO/reference numbers; verify A&W 239591",
            )
        else:
            self.assertEqual(
                concise,
                "DUPLICATE ORDER WARNING: Job 90479383 • A&W 239591 • verify duplicate source/order before processing",
            )
        self.assertNotIn("43658876", concise)

    def test_generic_ambiguity_stays_neutral_when_trailing_references_do_not_differ(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK A.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK B.pdf"
            write_sketch(first)
            write_sketch(second)

            with self.assertRaises(programmer.AmbiguousPdfError) as raised:
                shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config={})

            message = str(raised.exception)
            self.assertIn("Source sketch needs verification", message)
            self.assertNotIn("Possible duplicate order entry", message)

    def test_dialog_copy_warns_about_po_correction_double_production(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        normalized = " ".join(source.replace('"', "").split())
        self.assertIn("Possible duplicate order entry detected", normalized)
        self.assertIn("resent after a PO correction", normalized)
        self.assertIn("produce the same glass twice", normalized)

    def test_version_196_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 196)
        if version["version_number"] == 196:
            self.assertEqual(version["marker"], "VERSION_1_96_DUPLICATE_ORDER_ISSUE_CLARITY")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_96_DUPLICATE_ORDER_ISSUE_CLARITY", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "duplicate_order_entry_detection_message",
            "compact_shared_job_issue_summary",
            "po_reference_collision_explanation",
            "version_1_96_duplicate_order_issue_clarity",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
