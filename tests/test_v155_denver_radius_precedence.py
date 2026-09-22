from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer


CONFIG = {
    "rules": {
        "denver_min_inches": 6.125,
        "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
        "hinge_label_keywords": ["GEN037", "V1E037", "AV1E037"],
        "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
        "denver_fabrication_keywords": ["SCU", "SCU4", "SLOT", "MACRO", "HOLE"],
        "waterjet_keywords": ["NOTCH", "1/2 RADIUS", "RADIUS"],
        "weak_waterjet_keywords": ["IRREGULAR SHAPE"],
        "label_only_allow_keywords": ["RAKED EDGE"],
    }
}


class DenverRadiusPrecedenceTests(unittest.TestCase):
    def test_239169_scu4_radius_stays_on_explicit_denver_one_route(self) -> None:
        panel = programmer.Panel(
            3,
            2,
            '3/8" Clear Tempered\n17-13/16" x 80"\n1/2 Radius',
            17.8125,
            80.0,
            "",
        )
        programmer.classify_panel(panel, CONFIG, "239169")
        order = shower_batch.ProcessOrder("239169", "88652260.2 CADIA VILLAGE 17", "Customer")
        order.items[2] = shower_batch.ProcessItem(
            2,
            width_text='17"13/16',
            height_text='80"',
            processing=["Flat Polish side(s) 1/2/3/4", "0 Notched Corners", "SCU4 Slot MACRO"],
            machine_hints=["Denver 2 (CNC)", "Denver 1 (CNC)", "Packing / Shipping"],
        )

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "DENVER 1")
        self.assertIn(
            "Denver-specific fabrication keeps radius/notch work on DENVER 1",
            panel.reasons,
        )

    def test_true_radius_without_denver_fabrication_remains_waterjet(self) -> None:
        panel = programmer.Panel(
            1,
            1,
            '3/8" Clear Tempered\n33-1/2" x 80"\n1/2 Radius',
            33.5,
            80.0,
            "",
        )
        programmer.classify_panel(panel, CONFIG, "900010")
        order = shower_batch.ProcessOrder("900010", "12345680 RADIUS PANEL", "Customer")
        order.items[1] = shower_batch.ProcessItem(
            1,
            width_text='33-1/2"',
            height_text='80"',
            processing=["1/2 Radius"],
            machine_hints=["Denver 2 (CNC)"],
        )

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "WJ")

    def test_waterjet_scu4_radius_remains_waterjet(self) -> None:
        panel = programmer.Panel(
            1,
            1,
            '3/8" Clear Tempered\n42" x 42"\nSCU4 Slot\n1/2 Radius',
            42.0,
            42.0,
            "",
        )
        programmer.classify_panel(panel, CONFIG, "900011")
        order = shower_batch.ProcessOrder("900011", "12345681 WATERJET SCU4", "Customer")
        order.items[1] = shower_batch.ProcessItem(
            1,
            width_text='42"',
            height_text='42"',
            processing=["SCU4 Slot MACRO", "1/2 Radius"],
            machine_hints=["Waterjet", "Tempering Furnace"],
        )

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "WJ")

    def test_version_155_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))

        self.assertEqual(version["version"], "Version 1.55")
        self.assertEqual(version["version_number"], 155)
        self.assertEqual(version["marker"], "VERSION_1_55_DENVER_RADIUS_PRECEDENCE")


if __name__ == "__main__":
    unittest.main()
