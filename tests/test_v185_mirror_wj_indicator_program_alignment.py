from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer


class MirrorWaterjetIndicatorProgramAlignmentTests(unittest.TestCase):
    def panel(self, *, mirror: bool = True, width: float = 48.625, height: float = 40.0) -> programmer.Panel:
        panel = programmer.Panel(
            item=1,
            page_index=1,
            text='1/4" Mirror Clear Annealed' if mirror else '3/8" Clear Tempered',
            width=width,
            height=height,
            machine="WJ",
            indicator_corner="bottom_left",
            rotation_degrees=0.0,
            mirror_glass=mirror,
        )
        panel.source_dxf = Path("239465-source.dxf")
        return panel

    def test_239465_style_raked_landscape_mirror_flips_program_with_top_right_marker(self) -> None:
        panel = self.panel()
        # The raked left edge makes the normal bottom-left WJ marker unsuitable,
        # while the top-right corner remains square and is selected automatically.
        with mock.patch.object(programmer, "dxf_square_corners", return_value={"top_right", "bottom_right"}), mock.patch.object(
            programmer,
            "dxf_outline_dimensions",
            return_value=(48.625, 40.0),
        ):
            programmer.adjust_wj_indicator_corner(panel)
            programmer.adjust_wj_rotation_for_indicator(panel, {})

        self.assertEqual(panel.indicator_corner, "top_right")
        self.assertEqual(panel.rotation_degrees, 180.0)
        self.assertIn(
            "Landscape mirror WJ top-right marker uses 180 deg program orientation",
            panel.reasons,
        )

    def test_normal_landscape_mirror_bottom_left_remains_zero_degrees(self) -> None:
        panel = self.panel()
        with mock.patch.object(
            programmer,
            "dxf_square_corners",
            return_value={"top_left", "top_right", "bottom_left", "bottom_right"},
        ), mock.patch.object(programmer, "dxf_outline_dimensions", return_value=(48.625, 40.0)):
            programmer.adjust_wj_indicator_corner(panel)
            programmer.adjust_wj_rotation_for_indicator(panel, {})

        self.assertEqual(panel.indicator_corner, "bottom_left")
        self.assertEqual(panel.rotation_degrees, 0.0)

    def test_nonmirror_landscape_waterjet_behavior_is_unchanged(self) -> None:
        panel = self.panel(mirror=False)
        panel.indicator_corner = "top_right"
        panel.rotation_degrees = 0.0
        with mock.patch.object(programmer, "dxf_outline_dimensions", return_value=(48.625, 40.0)):
            programmer.adjust_wj_rotation_for_indicator(panel, {})

        self.assertEqual(panel.rotation_degrees, 0.0)

    def test_portrait_mirror_waterjet_behavior_is_unchanged(self) -> None:
        panel = self.panel(width=40.0, height=48.625)
        panel.indicator_corner = "top_left"
        with mock.patch.object(programmer, "dxf_outline_dimensions", return_value=(40.0, 48.625)):
            programmer.adjust_wj_rotation_for_indicator(panel, {})

        self.assertEqual(panel.rotation_degrees, 90.0)

    def test_version_185_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 185)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_85_MIRROR_WJ_INDICATOR_PROGRAM_ALIGNMENT", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "mirror_wj_auto_corner_program_alignment",
            "mirror_wj_top_right_180_orientation",
            "version_1_85_mirror_wj_indicator_program_alignment",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
