from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer


CONFIG = {
    "rules": {
        "waterjet_tall_rotation_by_indicator": {
            "top_left": 90,
            "bottom_right": -90,
            "top_right": -90,
            "bottom_left": 90,
        }
    }
}


class MirrorWaterjetIndicatorAlignmentTests(unittest.TestCase):
    def panel(self, width: float, height: float) -> programmer.Panel:
        panel = programmer.Panel(1, 1, '1/4" Mirror Clear Annealed', width, height, "WJ")
        panel.source_dxf = Path("matched-source.dxf")
        panel.indicator_corner = "top_right"
        panel.rotation_degrees = 0.0
        return panel

    def test_live_landscape_mirror_dimensions_align_zero_degree_to_bottom_left(self) -> None:
        live_dimensions = ((58.375, 42.0), (58.75, 42.0), (58.0, 42.0), (53.875, 44.0625))
        with mock.patch.object(
            programmer,
            "dxf_square_corners",
            return_value={"top_left", "top_right", "bottom_left", "bottom_right"},
        ), mock.patch.object(programmer, "dxf_outline_dimensions", side_effect=lambda _path: current):
            for current in live_dimensions:
                panel = self.panel(*current)
                programmer.adjust_wj_indicator_corner(panel)
                programmer.adjust_wj_rotation_for_indicator(panel, CONFIG)
                self.assertEqual(panel.indicator_corner, "bottom_left")
                self.assertEqual(panel.rotation_degrees, 0.0)

    def test_landscape_uses_top_right_only_when_bottom_left_is_not_square(self) -> None:
        panel = self.panel(58.0, 42.0)
        with mock.patch.object(programmer, "dxf_square_corners", return_value={"top_right"}), mock.patch.object(
            programmer,
            "dxf_outline_dimensions",
            return_value=(58.0, 42.0),
        ):
            programmer.adjust_wj_indicator_corner(panel)
        self.assertEqual(panel.indicator_corner, "top_right")

    def test_landscape_without_reliable_outline_still_uses_zero_degree_corner(self) -> None:
        panel = self.panel(53.875, 44.0625)
        with mock.patch.object(programmer, "dxf_square_corners", return_value=set()), mock.patch.object(
            programmer,
            "dxf_outline_dimensions",
            return_value=(53.875, 44.0625),
        ):
            programmer.adjust_wj_indicator_corner(panel)
        self.assertEqual(panel.indicator_corner, "bottom_left")

    def test_portrait_waterjet_keeps_top_left_quarter_turn(self) -> None:
        panel = self.panel(42.0, 58.0)
        with mock.patch.object(programmer, "dxf_square_corners", return_value={"top_left", "bottom_right"}), mock.patch.object(
            programmer,
            "dxf_outline_dimensions",
            return_value=(42.0, 58.0),
        ):
            programmer.adjust_wj_indicator_corner(panel)
            programmer.adjust_wj_rotation_for_indicator(panel, CONFIG)
        self.assertEqual(panel.indicator_corner, "top_left")
        self.assertEqual(panel.rotation_degrees, 90.0)

    def test_manual_waterjet_marker_still_bypasses_automatic_corner_selection(self) -> None:
        panel = self.panel(58.0, 42.0)
        panel.manual_indicator_override = True
        with mock.patch.object(programmer, "apply_manual_wj_rotation_for_indicator") as apply_manual:
            programmer.adjust_indicator_for_source_dxf(panel, CONFIG)
        apply_manual.assert_called_once_with(panel, CONFIG)
        self.assertEqual(panel.indicator_corner, "top_right")


if __name__ == "__main__":
    unittest.main()
