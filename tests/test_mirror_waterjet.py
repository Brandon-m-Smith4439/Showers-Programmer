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
        "hinge_label_keywords": ["GEN037", "V1E037", "AV1E037"],
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

    def test_project_name_mirror_does_not_change_clear_glass(self) -> None:
        panel = programmer.classify_panel(
            self.panel('Project #:\nMIRROR LAKE\n1/4" Clear Annealed\nFlat Polish 2 Long 2 Short'),
            CONFIG,
            "900002",
        )

        self.assertEqual(panel.machine, "")
        self.assertTrue(panel.label_only)
        self.assertTrue(panel.skip_dxf)


if __name__ == "__main__":
    unittest.main()
