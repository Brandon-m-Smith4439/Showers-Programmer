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


def write_sketch(path: Path, marker: str = "A") -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 720, JOB)
    document.drawString(72, 700, f"Source marker: {marker}")
    document.showPage()
    document.drawString(72, 720, '30" x 72"')
    document.drawString(72, 690, "Marks: P1")
    document.showPage()
    document.save()


def make_order() -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw_order="239591", job_name=JOB, customer="BFS East Greenville SC MW")
    order.items[1] = shower_batch.ProcessItem(item=1, width_text="30", height_text="72")
    return order


class Version197DuplicateOrderSafetyGuardTests(unittest.TestCase):
    def test_different_po_reference_collision_cannot_be_bypassed_by_saved_mapping(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43658876.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf"
            write_sketch(first, "original")
            write_sketch(second, "resent")
            config = {
                "pdf_order_mappings": {
                    "239591": {
                        "filename": second.name,
                        "job_number": "90479383",
                    }
                }
            }

            self.assertIsNone(
                shower_batch.mapped_process_order_pdf(folder, make_order(), config, candidate_pdfs=[first, second])
            )
            with self.assertRaises(programmer.AmbiguousPdfError) as raised:
                shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config=config)

            error = raised.exception
            self.assertFalse(error.assignment_allowed)
            self.assertEqual(error.collision_kind, "conflicting_reference")
            self.assertIn("Correct or remove the unintended duplicate order", str(error))

    def test_blocking_duplicate_collision_is_not_dimension_disambiguated(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43658876.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf"
            write_sketch(first, "original")
            write_sketch(second, "resent")

            with self.assertRaises(programmer.AmbiguousPdfError) as raised:
                shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config={})

            self.assertFalse(raised.exception.assignment_allowed)
            self.assertEqual(raised.exception.collision_kind, "conflicting_reference")

    def test_copy_suffix_and_spacing_variants_are_blocking_duplicate_imports(self) -> None:
        variants = (
            "Glass Order 90479383 SAMPLE (1).pdf",
            "Glass Order 90479383 SAMPLE 1.pdf",
            "Glass Order 90479383 SAMPLE_1.pdf",
            "Glass Order 90479383 SAMPLE - Copy.pdf",
            "Glass Order 90479383 SAMPLE .pdf",
            "Glass Order 90479383 SAMPLE1.pdf",
        )
        with writable_test_directory() as folder:
            canonical = folder / "Glass Order 90479383 SAMPLE.pdf"
            write_sketch(canonical, "canonical")
            for index, name in enumerate(variants, start=1):
                duplicate = folder / name
                write_sketch(duplicate, f"variant-{index}")
                collision = programmer.classify_pdf_duplicate_collision([canonical, duplicate])
                self.assertIsNotNone(collision, name)
                assert collision is not None
                self.assertEqual(collision.kind, "copy_name_variant", name)

    def test_copy_named_same_dimension_sketch_cannot_be_forced_by_assignment(self) -> None:
        with writable_test_directory() as folder:
            canonical = folder / "Glass Order 90479383 SAMPLE.pdf"
            duplicate = folder / "Glass Order 90479383 SAMPLE (1).pdf"
            write_sketch(canonical, "canonical")
            write_sketch(duplicate, "resent-copy")
            config = {
                "pdf_order_mappings": {
                    "239591": {
                        "filename": duplicate.name,
                        "job_number": "90479383",
                    }
                }
            }

            self.assertIsNone(
                shower_batch.mapped_process_order_pdf(folder, make_order(), config, candidate_pdfs=[canonical, duplicate])
            )
            with self.assertRaises(programmer.AmbiguousPdfError) as raised:
                shower_batch.preview_process_order_pdf(folder, make_order(), [canonical, duplicate], config=config)
            self.assertFalse(raised.exception.assignment_allowed)
            self.assertEqual(raised.exception.collision_kind, "copy_name_variant")

    def test_byte_identical_same_job_sketches_are_blocking_even_with_unrelated_names(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 LEFT.pdf"
            second = folder / "Glass Order 90479383 RIGHT.pdf"
            payload = b"same source sketch bytes"
            first.write_bytes(payload)
            second.write_bytes(payload)

            collision = programmer.classify_pdf_duplicate_collision([first, second])
            self.assertIsNotNone(collision)
            assert collision is not None
            self.assertEqual(collision.kind, "identical_content")

    def test_duplicate_import_name_grouping_catches_windows_copy_variants(self) -> None:
        with writable_test_directory() as folder:
            canonical = folder / "Glass Order 90479383 SAMPLE.pdf"
            variants = [
                folder / "Glass Order 90479383 SAMPLE_1.pdf",
                folder / "Glass Order 90479383 SAMPLE (1).pdf",
                folder / "Glass Order 90479383 SAMPLE 1.pdf",
                folder / "Glass Order 90479383 SAMPLE .pdf",
                folder / "Glass Order 90479383 SAMPLE1.pdf",
            ]
            for path in [canonical, *variants]:
                path.write_bytes(b"identical")

            groups = gui.ShowerProgrammerApp.import_duplicate_groups([canonical, *variants])
            self.assertEqual(len(groups), 1)
            duplicate_names = {path.name for path in groups[0]["duplicates"]}
            self.assertEqual(duplicate_names, {path.name for path in variants})

    def test_natural_dxf_item_suffix_is_not_a_copy_without_a_base_file(self) -> None:
        with writable_test_directory() as folder:
            item_one = folder / "90479383 SAMPLE_1.dxf"
            item_two = folder / "90479383 SAMPLE_2.dxf"
            item_one.write_bytes(b"one")
            item_two.write_bytes(b"two")
            self.assertEqual(gui.ShowerProgrammerApp.import_duplicate_name_groups([item_one, item_two]), [])

    def test_legitimate_same_job_ambiguity_still_allows_assignment(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 LEFT PANEL.pdf"
            second = folder / "Glass Order 90479383 RIGHT PANEL.pdf"
            write_sketch(first, "left")
            write_sketch(second, "right")
            collision = programmer.classify_pdf_duplicate_collision([first, second])
            self.assertIsNone(collision)

            config = {
                "pdf_order_mappings": {
                    "239591": {
                        "filename": second.name,
                        "job_number": "90479383",
                    }
                }
            }
            resolved = shower_batch.preview_process_order_pdf(folder, make_order(), [first, second], config=config)
            self.assertEqual(resolved, second.resolve())

    def test_gui_disables_source_assignment_for_duplicate_safety_condition(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn("DUPLICATE PRODUCTION WARNING", source)
        self.assertIn("Only the separate, explicit intentional-duplicate authorization", (BACKEND / "shower_batch.py").read_text(encoding="utf-8"))

    def test_version_197_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 197)
        if version["version_number"] == 197:
            self.assertEqual(version["marker"], "VERSION_1_97_DUPLICATE_ORDER_SAFETY_GUARD")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_97_DUPLICATE_ORDER_SAFETY_GUARD", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "duplicate_source_assignment_guard",
            "copy_variant_import_detection",
            "exact_content_duplicate_source_guard",
            "blocking_duplicate_dimension_fallback",
            "version_1_97_duplicate_order_safety_guard",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
