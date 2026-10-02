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

JOB = "90479383 OCTOPLEX BLOCK 19 UNIT 135 4365"


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_sketch(path: Path, width: str = "30", height: str = "72") -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 720, JOB)
    document.showPage()
    document.drawString(72, 720, f'{width}" x {height}"')
    document.drawString(72, 690, "Marks: P1")
    document.showPage()
    document.save()


def make_order(aw_order: str = "239591") -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw_order=aw_order, job_name=JOB, customer="BFS East Greenville SC MW")
    order.items[1] = shower_batch.ProcessItem(item=1, width_text="30", height_text="72")
    return order


class Version195SharedJobPdfAssignmentTests(unittest.TestCase):
    def test_same_job_distinct_pdfs_are_ambiguous_without_assignment(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43658876.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf"
            write_sketch(first)
            write_sketch(second)

            with self.assertRaises(programmer.AmbiguousPdfError) as raised:
                shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config={})

            message = str(raised.exception)
            self.assertIn("Possible duplicate order entry", message)
            self.assertIn("different PO/reference numbers", message)
            self.assertEqual(set(raised.exception.candidates), {first, second})

    def test_explicit_aw_order_assignment_resolves_legitimate_same_job_ambiguity(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX LEFT PANEL.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX RIGHT PANEL.pdf"
            write_sketch(first)
            write_sketch(second)
            config = {
                "pdf_order_mappings": {
                    "239591": {
                        "filename": second.name,
                        "job_number": "90479383",
                    }
                }
            }

            preview = shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config=config)
            opened, _reader = shower_batch.open_process_order_pdf(folder, make_order(), config=config)

            self.assertEqual(preview, second.resolve())
            self.assertEqual(opened, second.resolve())

    def test_mapping_for_reused_aw_number_is_ignored_when_job_identity_changed(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43658876.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf"
            write_sketch(first)
            write_sketch(second)
            config = {
                "pdf_order_mappings": {
                    "239591": {
                        "filename": second.name,
                        "job_number": "99999999",
                    }
                }
            }

            self.assertIsNone(shower_batch.configured_pdf_order_mapping(make_order(), config))
            with self.assertRaises(programmer.AmbiguousPdfError):
                shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config=config)

    def test_manual_override_merge_keeps_pdf_assignment_separate_from_programming(self) -> None:
        merged = programmer.merge_item_overrides(
            {"rules": {"denver_min_inches": 6.125}},
            {
                "pdf_order_mappings": {
                    "239591": {
                        "filename": "Glass Order 90479383 example.pdf",
                        "job_number": "90479383",
                    }
                }
            },
        )
        self.assertEqual(
            merged["pdf_order_mappings"]["239591"]["filename"],
            "Glass Order 90479383 example.pdf",
        )
        self.assertEqual(merged.get("item_overrides"), {})

    def test_gui_exposes_non_destructive_source_pdf_assignment(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn('"Assign Source PDF"', source)
        self.assertIn('"Change Source PDF"', source)
        self.assertIn("pdf_order_mappings", source)
        self.assertIn("no pdf is", source.casefold())
        self.assertIn("renamed, deleted, or changed on the shared input", source)

    def test_version_195_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 195)
        if version["version_number"] == 195:
            self.assertEqual(version["marker"], "VERSION_1_95_SHARED_JOB_PDF_ASSIGNMENT")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_95_SHARED_JOB_PDF_ASSIGNMENT", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "shared_job_pdf_identity_detection",
            "persistent_aw_pdf_assignment",
            "non_destructive_source_pdf_resolution",
            "mapped_pdf_dimension_validation",
            "version_1_95_shared_job_pdf_assignment",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
