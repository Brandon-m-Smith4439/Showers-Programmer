from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


CONFIG = {
    "rules": {
        "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
        "hinge_label_keywords": ["GEN037", "V1E037", "COL037"],
        "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
        "denver_fabrication_keywords": ["K CUT", "K-CUT"],
    }
}


class NoFabricationSendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        self.app.output_was_skipped_for_order = lambda _aw, _kind: False
        self.app.tree_issue_text_for_order = lambda _aw: ""

    @staticmethod
    def order_with_item(
        processing: list[str],
        machine_hints: list[str],
        aw_order: str = "900001",
    ) -> shower_batch.ProcessOrder:
        item = shower_batch.ProcessItem(
            item=1,
            width_text='4-1/4"',
            height_text='73-3/4"',
            processing=list(processing),
            machine_hints=list(machine_hints),
        )
        return shower_batch.ProcessOrder(aw_order, "SANITIZED ADD-ON", "CUSTOMER", {1: item})

    def test_flat_polish_tempering_and_packing_does_not_require_program(self) -> None:
        order = self.order_with_item(
            ['Flat Polish side(s) 1/2/3/4', '3/8" Clear Tempered'],
            ["Tempering Furnace", "Packing / Shipping"],
        )
        self.assertFalse(self.app.process_order_requires_program_dxf(order, CONFIG))
        warnings = self.app.send_plan_warnings_for_order(
            order,
            include_sketches=True,
            include_programs=True,
            sketch_paths=[Path("900001.pdf")],
            dxf_paths=[],
            program_required=False,
        )
        self.assertNotIn("Missing generated program DXF.", warnings)
        sent = self.app.successfully_sent_orders(
            [order],
            [Path("900001.pdf")],
            [],
            [Path("900001.pdf")],
            include_sketches=True,
            include_programs=True,
            program_required_by_aw={"900001": False},
        )
        self.assertEqual([value.aw_order for value in sent], ["900001"])

    def test_cnc_routes_and_fabrication_still_require_program(self) -> None:
        explicit = self.order_with_item(['3/8" Clear Tempered'], ["Denver 2 (CNC)"])
        inferred = self.order_with_item(['0\'\' 1/2 Hole x 1'], ["Packing / Shipping"], "900002")
        unknown = shower_batch.ProcessOrder("900003", "UNKNOWN PROCESS DATA")
        for order in (explicit, inferred, unknown):
            with self.subTest(order=order.aw_order):
                self.assertTrue(self.app.process_order_requires_program_dxf(order, CONFIG))

    def test_hinge_detection_is_nested_under_configuration(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        top_level_builders = source.split("tab_builders = {", 1)[1].split("for tab_name in tab_builders", 1)[0]
        self.assertNotIn('"Hinge Detection": lambda:', top_level_builders)
        self.assertIn('hinge_tab_name = "Hinge Detection"', source)
        self.assertIn('self.open_settings("Configuration")', source)
        self.assertIn('select_tab("Hinge Detection")', source)


if __name__ == "__main__":
    unittest.main()
