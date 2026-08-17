from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
import shower_programmer_gui as gui


class Version117AdaptiveDxfRotationDisplayTests(unittest.TestCase):
    def test_rotation_display_strips_unneeded_decimals_and_keeps_up_to_six(self) -> None:
        cases = {
            90.0: "90",
            89.85: "89.85",
            89.850011: "89.850011",
            -90.154436: "-90.154436",
            12.3456789: "12.345679",
            12.3400001: "12.34",
            -0.0000004: "0",
            -0.0000006: "-0.000001",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(gui.ShowerProgrammerApp.format_degrees(value), expected)

    def test_panel_rotation_summary_uses_adaptive_display_only(self) -> None:
        panel = programmer.Panel(1, 1, "", 15.75, 46.375, "DENVER 2")
        panel.rotation_degrees = -90.0
        panel.angle_correction_degrees = -0.154436
        self.assertEqual(gui.ShowerProgrammerApp.panel_rotation_summary(panel), "-90.154436 deg")

        panel.rotation_degrees = 90.0
        panel.angle_correction_degrees = 0.0
        self.assertEqual(gui.ShowerProgrammerApp.panel_rotation_summary(panel), "90 deg")

    def test_programming_evidence_contract_remains_compact(self) -> None:
        panel = {
            "machine": "DENVER 1",
            "glass_type": '3/8" Clear Tempered',
            "dimensions": "34 x 80 in",
            "process_hint": "DENVER 1",
            "source_dxf": "90000101.dxf",
            "indicator": "bottom_left",
            "rotation": 90.0,
            "angle_correction": 0.125,
            "hinge_side": "left",
            "hinges_up": False,
            "manual_override": False,
            "reasons": ["hinge side left; hinges down"],
        }
        text = gui.ShowerProgrammerApp.format_programming_evidence_panel(panel)
        self.assertIn("DXF rotation: 90 deg", text)
        self.assertIn("Out-of-square correction: +0.12 deg", text)
        self.assertNotIn("DXF rotation: 90.000000 deg", text)


if __name__ == "__main__":
    unittest.main()
