from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer as programmer


CONFIG = {
    "rules": {
        "mirror_keywords": ["MIRROR"],
        "denver_min_inches": 6.125,
        "waterjet_fit_limit_inches": 75,
        "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
        "hinge_label_keywords": ["GEN037", "V1E037", "AV1E037", "JRG037", "GEN180"],
        "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
        "denver_fabrication_keywords": ["HOLE", "SLOT"],
        "waterjet_keywords": ["NOTCH", "RADIUS"],
        "weak_waterjet_keywords": ["IRREGULAR SHAPE"],
        "label_only_allow_keywords": ["RAKED EDGE"],
    }
}


class MirrorWaterjetTests(unittest.TestCase):
    def panel(self, text: str, machine: str = "") -> programmer.Panel:
        return programmer.Panel(1, 1, text, 42.0, 83.0, machine)

    def test_quarter_inch_mirror_annealed_always_uses_waterjet(self) -> None:
        panel = programmer.classify_panel(
            self.panel('1/4" Mirror Clear Annealed\nFlat Polish 2 Long 2 Short'),
            CONFIG,
            "900001",
        )

        self.assertEqual(panel.machine, "WJ")
        self.assertFalse(panel.label_only)
        self.assertFalse(panel.skip_dxf)
        self.assertIn("mirror glass type always uses WJ", panel.reasons)

    def test_mirror_overrides_process_list_denver_hint(self) -> None:
        panel = self.panel('1/4" Mirror Clear Annealed', "DENVER 2")
        order = shower_batch.ProcessOrder("900001", "12345678 TEST")
        item = shower_batch.ProcessItem(1, width_text='42"', height_text='83"')
        item.machine_hints.append("DENVER 2")
        order.items[1] = item

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "WJ")
        self.assertFalse(panel.label_only)
        self.assertFalse(panel.skip_dxf)
        self.assertIn("mirror glass type always uses WJ", panel.reasons)

    def test_process_list_mirror_glass_forces_waterjet_when_pdf_is_plain(self) -> None:
        panel = self.panel('1/4" Clear Annealed', "")
        order = shower_batch.ProcessOrder("900001", "12345678 TEST")
        item = shower_batch.ProcessItem(1, width_text='42"', height_text='83"')
        item.processing.append('1/4" Mirror Annealed')
        order.items[1] = item

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "WJ")
        self.assertFalse(panel.label_only)
        self.assertFalse(panel.skip_dxf)

    def test_radius_cutout_overrides_conflicting_denver_process_route(self) -> None:
        panel = self.panel('3/8" Clear Tempered\n1/2 Radius', "WJ")
        order = shower_batch.ProcessOrder("900010", "12345680 RADIUS PANEL")
        item = shower_batch.ProcessItem(1, width_text='33-1/2"', height_text='80"')
        item.machine_hints.append("Denver 2 (CNC)")
        order.items[1] = item

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "WJ")
        self.assertIn("WJ-only radius/notch fabrication overrides process-list Denver routing", panel.reasons)

    def test_double_notch_is_strong_waterjet_fabrication(self) -> None:
        panel = self.panel('3/8" Clear Tempered', "")
        order = shower_batch.ProcessOrder("900011", "12345681 DOUBLE NOTCH PANEL")
        item = shower_batch.ProcessItem(1, width_text='33-1/2"', height_text='80"')
        item.processing.append("Double Notch")
        item.machine_hints.append("Denver 2 (CNC)")
        order.items[1] = item

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "WJ")

    def test_new_hinge_codes_remain_denver_even_when_radius_text_is_present(self) -> None:
        for code in ("JRG037", "GEN180"):
            with self.subTest(code=code):
                panel = programmer.classify_panel(
                    self.panel(f'3/8" Clear Tempered\n{code}\nRadius'),
                    CONFIG,
                    "900012",
                )
                order = shower_batch.ProcessOrder("900012", "12345682 HINGE DOOR")
                item = shower_batch.ProcessItem(1, width_text='28"', height_text='79-1/2"')
                item.machine_hints.append("Denver 1 (CNC)")
                order.items[1] = item

                shower_batch.apply_process_hints([panel], order, CONFIG)

                self.assertEqual(panel.machine, "DENVER 1")
                self.assertTrue(programmer.has_hinge_label_text(code, CONFIG))

    def test_project_name_mirror_does_not_change_clear_glass(self) -> None:
        panel = programmer.classify_panel(
            self.panel('Project #:\nMIRROR LAKE\n1/4" Clear Annealed\nFlat Polish 2 Long 2 Short'),
            CONFIG,
            "900002",
        )

        self.assertEqual(panel.machine, "")
        self.assertTrue(panel.label_only)
        self.assertTrue(panel.skip_dxf)

    @staticmethod
    def process_row(
        order_item: str,
        job_name: str,
        machine: str,
        processing: str = "Flat Polish side(s) 1/2/3/4",
    ) -> list[str]:
        row = [""] * 22
        row[2] = '42"'
        row[3] = '83"'
        row[6] = order_item
        row[7] = processing
        row[10] = "Customer"
        row[13] = job_name
        row[21] = machine
        return row

    def test_mirror_batch_keeps_only_waterjet_section_orders(self) -> None:
        rows = [
            ['1/4" Mirror'],
            self.process_row("900001-1", "12345678 MIRROR JOB", "Waterjet"),
            self.process_row("900002-1", "12345679 PACKING ONLY", "Packing / Shipping"),
            self.process_row(
                "900001-1",
                "12345678 MIRROR JOB",
                "Packing / Shipping",
                "INTERNAL CUTOUT MACRO",
            ),
        ]

        orders = shower_batch.load_process_orders_from_rows(rows)

        self.assertEqual([order.aw_order for order in orders], ["900001"])
        self.assertEqual(
            orders[0].items[1].machine_hints,
            ["Waterjet", "Packing / Shipping"],
        )

    def test_customer_job_named_mirror_does_not_scope_a_clear_glass_batch(self) -> None:
        rows = [
            ['3/8" Clear Annealed'],
            self.process_row("900001-1", "12345678 MIRROR LAKE", "Waterjet"),
            self.process_row("900002-1", "12345679 STANDARD JOB", "Denver 1 (CNC)"),
        ]

        orders = shower_batch.load_process_orders_from_rows(rows)

        self.assertEqual([order.aw_order for order in orders], ["900001", "900002"])

    def test_mixed_material_batch_is_not_treated_as_mirror_only(self) -> None:
        rows = [
            ['1/4" Mirror'],
            ['3/8" Clear Annealed'],
            self.process_row("900001-1", "12345678 MIRROR JOB", "Waterjet"),
            self.process_row("900002-1", "12345679 SHOWER JOB", "Denver 2 (CNC)"),
        ]

        orders = shower_batch.load_process_orders_from_rows(rows)

        self.assertEqual([order.aw_order for order in orders], ["900001", "900002"])


if __name__ == "__main__":
    unittest.main()
