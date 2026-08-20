from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch


CONFIG = {
    "rules": {
        "mirror_keywords": ["MIRROR"],
        "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
        "denver_fabrication_keywords": ["HOLE", "SLOT"],
        "waterjet_keywords": ["HOLE", "NOTCH", "RADIUS"],
        "weak_waterjet_keywords": ["IRREGULAR SHAPE"],
        "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
    }
}


class Page:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class Reader:
    def __init__(self, pages: list[str]) -> None:
        self.pages = [Page(text) for text in pages]


def mirror_page(width: str, height: str, extra: str = "") -> str:
    return f'1/4" Mirror Clear Annealed\n{width}" x {height}"\nFlat Polish 2 Long 2 Short\n{extra}'


class MirrorPageDxfMatchTests(unittest.TestCase):
    def mirror_order(self, width: str = '19-1/4', height: str = '81-11/16') -> shower_batch.ProcessOrder:
        item = shower_batch.ProcessItem(
            item=4,
            width_text=f'{width}"',
            height_text=f'{height}"',
            # Mirror-only process-list filtering can retain the Waterjet row
            # without retaining the separate material-description row.
            processing=["2'' Hole x 1"],
            machine_hints=["Waterjet", "Packing / Shipping"],
        )
        return shower_batch.ProcessOrder("900126", "SANITIZED MIRROR JOB", "CUSTOMER", {4: item})

    def test_item_four_uses_fourth_mirror_page_by_dimensions(self) -> None:
        reader = Reader([
            "GLASS ORDER\nTotal of 6 Panel(s) in this Order",
            mirror_page("23", "48"),
            mirror_page("30-1/2", "48"),
            mirror_page("17-5/8", "56-1/2"),
            mirror_page("19-1/4", "81-11/16", "All holes have 2 inch diameter"),
            mirror_page("48", "67-9/16"),
            mirror_page("73", "67-3/16"),
        ])
        panels = []
        shower_batch.attach_unlabeled_process_pages(reader, panels, self.mirror_order(), CONFIG)
        self.assertEqual([(panel.item, panel.page_index) for panel in panels], [(4, 4)])
        self.assertTrue(any("mirror page matched by process-list dimensions" in reason for reason in panels[0].reasons))

    def test_item_four_uses_overview_sequence_when_dimensions_are_unavailable(self) -> None:
        order = self.mirror_order("", "")
        reader = Reader([
            "GLASS ORDER\nTotal of 4 Panel(s) in this Order",
            mirror_page("10", "20"),
            mirror_page("11", "21"),
            mirror_page("12", "22"),
            mirror_page("13", "23", "CUTOUT"),
        ])
        panels = []
        shower_batch.attach_unlabeled_process_pages(reader, panels, order, CONFIG)
        self.assertEqual([(panel.item, panel.page_index) for panel in panels], [(4, 4)])
        self.assertTrue(any("mirror page matched by overview/item sequence" in reason for reason in panels[0].reasons))

    def test_non_mirror_unlabeled_mapping_keeps_existing_page_order(self) -> None:
        item = shower_batch.ProcessItem(4, width_text='19"', height_text='80"')
        order = shower_batch.ProcessOrder("900127", "SANITIZED GLASS JOB", "CUSTOMER", {4: item})
        reader = Reader(["GLASS ORDER", '3/8" Clear Tempered\n19" x 80"'])
        panels = []
        shower_batch.attach_unlabeled_process_pages(reader, panels, order, CONFIG)
        self.assertEqual([(panel.item, panel.page_index) for panel in panels], [(4, 1)])


if __name__ == "__main__":
    unittest.main()
