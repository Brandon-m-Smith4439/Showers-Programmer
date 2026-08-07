from __future__ import annotations

import sys
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer


JOB = "89420398.4 2089 HOLBROOK"


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def process_order(aw_order: str, dimensions: list[tuple[int, str, str]]) -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw_order=aw_order, job_name=JOB)
    for item_number, width, height in dimensions:
        order.items[item_number] = shower_batch.ProcessItem(
            item=item_number,
            width_text=width,
            height_text=height,
        )
    return order


def write_sketch(path: Path, dimensions: list[tuple[str, str]]) -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 720, JOB)
    document.showPage()
    for item_number, (width, height) in enumerate(dimensions, start=1):
        document.drawString(72, 720, f'{width}" x {height}"')
        document.drawString(72, 690, f"Marks: P{item_number}")
        document.showPage()
    document.save()


class DuplicateJobNumberTests(unittest.TestCase):
    def test_ambiguous_pdf_error_exposes_candidates_for_gui_resolution(self) -> None:
        with writable_test_directory() as folder:
            first = folder / f"Glass Order ALPHA_{JOB}.pdf"
            second = folder / f"Glass Order BETA_{JOB}.pdf"
            first.write_bytes(b"placeholder one")
            second.write_bytes(b"placeholder two")
            with mock.patch.object(
                programmer,
                "extract_first_page_text",
                return_value=f"Job Nr {JOB}",
            ):
                with self.assertRaises(programmer.AmbiguousPdfError) as raised:
                    programmer.find_pdf(folder, JOB, "237008")
            self.assertEqual(set(raised.exception.candidates), {first, second})
            self.assertEqual(raised.exception.aw_order, "237008")

    def test_process_list_keeps_same_job_as_separate_aw_orders(self) -> None:
        rows: list[list[str]] = []
        for aw_item, width, height in (
            ("237008-1", "31-7/8", "112-5/16"),
            ("237008-2", "31-7/8", "112-3/16"),
            ("237009-1", "32", "12"),
        ):
            row = [""] * 22
            row[2] = width
            row[3] = height
            row[6] = aw_item
            row[13] = JOB
            rows.append(row)

        orders = shower_batch.load_process_orders_from_rows(rows)

        self.assertEqual([order.aw_order for order in orders], ["237008", "237009"])
        self.assertEqual(orders[0].item_numbers, [1, 2])
        self.assertEqual(orders[1].item_numbers, [1])

    def test_dimensions_select_distinct_pdfs_for_same_job_number(self) -> None:
        with writable_test_directory() as folder:
            doors = folder / f"Glass Order COPPER_{JOB}.pdf"
            panel = folder / f"Glass Order COPPER_{JOB}_1.pdf"
            write_sketch(doors, [("31-7/8", "112-5/16"), ("31-7/8", "112-3/16")])
            write_sketch(panel, [("32", "12")])

            doors_path, _doors_reader = shower_batch.open_process_order_pdf(
                folder,
                process_order("237008", [(1, "31-7/8", "112-5/16"), (2, "31-7/8", "112-3/16")]),
            )
            panel_path, _panel_reader = shower_batch.open_process_order_pdf(
                folder,
                process_order("237009", [(1, "32", "12")]),
            )

            self.assertEqual(doors_path, doors.resolve())
            self.assertEqual(panel_path, panel.resolve())

    def test_missing_second_sketch_is_reported_instead_of_reusing_wrong_pdf(self) -> None:
        with writable_test_directory() as folder:
            doors = folder / f"Glass Order COPPER_{JOB}.pdf"
            write_sketch(doors, [("31-7/8", "112-5/16"), ("31-7/8", "112-3/16")])

            with self.assertRaisesRegex(RuntimeError, r"A&W 237009 does not match.*32 x 12"):
                shower_batch.open_process_order_pdf(
                    folder,
                    process_order("237009", [(1, "32", "12")]),
                )


if __name__ == "__main__":
    unittest.main()
