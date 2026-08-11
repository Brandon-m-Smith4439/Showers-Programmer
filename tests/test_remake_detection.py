from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer as programmer


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, *pages: str) -> None:
        self.pages = [FakePage(text) for text in pages]


class PdfLocationRemakeTests(unittest.TestCase):
    def test_location_remake_is_detected(self) -> None:
        reader = FakeReader(
            "Project #: SAMPLE\nLocation: DOOR REMAKE ONLY\nMarks: P2\nMeasurements are in inches"
        )
        self.assertEqual(shower_batch.pdf_location_values(reader), ["DOOR REMAKE ONLY"])
        self.assertTrue(shower_batch.pdf_location_indicates_remake(reader))

    def test_location_remake_is_detected_when_header_fields_share_a_line(self) -> None:
        reader = FakeReader("Project #: SAMPLE  Location: panel remake only  Marks: P1")
        self.assertEqual(shower_batch.pdf_location_values(reader), ["panel remake only"])
        self.assertTrue(shower_batch.pdf_location_indicates_remake(reader))

    def test_remake_elsewhere_does_not_trigger_location_detection(self) -> None:
        reader = FakeReader(
            "Project #: SAMPLE\nLocation: MASTER\nMarks: P1\nCustomer note: REMAKE hardware only"
        )
        self.assertEqual(shower_batch.pdf_location_values(reader), ["MASTER"])
        self.assertFalse(shower_batch.pdf_location_indicates_remake(reader))

    def test_plain_location_is_not_a_remake(self) -> None:
        reader = FakeReader("Location: SECOND FLOOR\nMarks: P3")
        self.assertFalse(shower_batch.pdf_location_indicates_remake(reader))

    def test_prepare_job_uses_existing_remake_selection_for_location_remake(self) -> None:
        reader = FakeReader("Location: DOOR REMAKE ONLY\nMarks: P1")
        process_order = shower_batch.ProcessOrder("900001", "1000 SAMPLE", "CUSTOMER")
        process_order.items[1] = shower_batch.ProcessItem(1)
        panels = [
            programmer.Panel(1, 0, "P1", 30.0, 80.0, "DENVER 1"),
            programmer.Panel(2, 1, "P2", 30.0, 80.0, "DENVER 1"),
        ]
        no_op_targets = (
            "attach_unlabeled_process_pages",
            "attach_unmarked_process_pages",
            "reconcile_process_list_item_gaps",
            "reconcile_missing_items_from_extra_sketch_pages",
            "apply_process_hints",
            "apply_process_list_scope",
        )
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(shower_batch, "open_process_order_pdf", return_value=(Path("source.pdf"), reader)))
            stack.enter_context(mock.patch.object(programmer, "analyze_panels", return_value=panels))
            stack.enter_context(mock.patch.object(shower_batch, "match_process_items_to_sketch_pages", return_value={}))
            stack.enter_context(mock.patch.object(programmer, "refine_panel_orientations"))
            stack.enter_context(mock.patch.object(programmer, "apply_override"))
            stack.enter_context(mock.patch.object(programmer, "assign_dxf_paths"))
            stack.enter_context(mock.patch.object(shower_batch, "collect_issues", return_value=[]))
            for name in no_op_targets:
                stack.enter_context(mock.patch.object(shower_batch, name))
            job, _, _ = shower_batch.prepare_job(
                Path("orders"),
                Path("sketches"),
                Path("programs"),
                Path("reports"),
                {},
                process_order,
            )
        self.assertEqual(job.remake_items, {1})
        self.assertTrue(panels[0].remake)
        self.assertTrue(panels[1].remake_excluded)
        self.assertTrue(panels[1].skip_dxf)


if __name__ == "__main__":
    unittest.main()
