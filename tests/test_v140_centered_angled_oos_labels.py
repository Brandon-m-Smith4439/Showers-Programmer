from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shower_programmer_gui import ShowerProgrammerApp


class CenteredAngledOosLabelTests(unittest.TestCase):
    def test_release_history_retains_version_140(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("## [Version 1.40]", changelog)
        self.assertIn("VERSION_1_40_CENTERED_ANGLED_OOS_LABELS", features)

    def test_label_anchor_is_middle_of_dashed_guide(self) -> None:
        self.assertEqual(
            ShowerProgrammerApp.dxf_oos_label_anchor((0.0, 0.0), (100.0, 10.0)),
            (50.0, 5.0),
        )

    def test_label_angle_follows_guide_and_stays_upright(self) -> None:
        forward = ShowerProgrammerApp.dxf_oos_label_angle((0.0, 0.0), (100.0, 10.0))
        reverse = ShowerProgrammerApp.dxf_oos_label_angle((100.0, 10.0), (0.0, 0.0))
        vertical = ShowerProgrammerApp.dxf_oos_label_angle((0.0, 0.0), (10.0, 100.0))
        self.assertAlmostEqual(forward, -5.71, places=2)
        self.assertAlmostEqual(reverse, -5.71, places=2)
        self.assertAlmostEqual(vertical, -84.29, places=2)
        self.assertTrue(all(-90.0 <= value <= 90.0 for value in (forward, reverse, vertical)))

    def test_label_search_starts_inside_and_has_collision_fallbacks(self) -> None:
        connected, inward_distances, shifts = ShowerProgrammerApp.dxf_oos_label_search_parameters(
            (0.0, 0.0),
            (100.0, 1.0),
            100.0,
        )
        self.assertFalse(connected)
        self.assertEqual(inward_distances[0], 18.0)
        self.assertGreaterEqual(len(inward_distances), 6)
        self.assertIn(0.0, shifts)
        self.assertTrue(any(value > 0.0 for value in shifts))
        self.assertTrue(any(value < 0.0 for value in shifts))

    def test_preview_uses_centered_anchor_and_guide_angle(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn("self.dxf_oos_label_anchor(guide_start, guide_end)", source)
        self.assertIn("self.dxf_oos_label_angle(guide_start, guide_end)", source)


if __name__ == "__main__":
    unittest.main()
