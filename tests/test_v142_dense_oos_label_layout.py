from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shower_programmer_gui import ShowerProgrammerApp


class DenseOosLabelLayoutTests(unittest.TestCase):
    def test_font_fallback_is_only_enabled_for_multiple_runs(self) -> None:
        self.assertEqual(ShowerProgrammerApp.dxf_oos_label_font_sizes(1), (9,))
        self.assertEqual(ShowerProgrammerApp.dxf_oos_label_font_sizes(4), (9, 8))
        self.assertEqual(ShowerProgrammerApp.dxf_oos_label_font_sizes(8), (9, 8, 7))

    def test_short_dense_runs_receive_absolute_annotation_lanes(self) -> None:
        offsets = ShowerProgrammerApp.dxf_oos_tangent_offsets(8, 12.0, (0.0, 0.2, -0.2))
        self.assertIn(0.0, offsets)
        self.assertIn(24.0, offsets)
        self.assertIn(-24.0, offsets)
        self.assertIn(230.0, offsets)
        self.assertEqual(len(offsets), len(set(offsets)))

    def test_glass_outline_segment_intersection_is_detected(self) -> None:
        rect = (20.0, 20.0, 60.0, 40.0)
        self.assertTrue(
            ShowerProgrammerApp.preview_rect_intersects_segment(rect, (0.0, 0.0), (80.0, 60.0), 2.0)
        )
        self.assertFalse(
            ShowerProgrammerApp.preview_rect_intersects_segment(rect, (0.0, 5.0), (80.0, 5.0), 2.0)
        )

    def test_overlap_area_scores_partial_text_collisions(self) -> None:
        self.assertEqual(
            ShowerProgrammerApp.preview_rect_overlap_area((0.0, 0.0, 20.0, 20.0), (10.0, 5.0, 30.0, 15.0)),
            100.0,
        )
        self.assertEqual(
            ShowerProgrammerApp.preview_rect_overlap_area((0.0, 0.0, 5.0, 5.0), (10.0, 10.0, 15.0, 15.0)),
            0.0,
        )

    def test_displaced_label_leader_starts_beyond_text(self) -> None:
        endpoints = ShowerProgrammerApp.dxf_oos_leader_endpoints(
            (0.0, 0.0, 40.0, 20.0),
            (20.0, 10.0),
            (100.0, 10.0),
        )
        self.assertGreater(endpoints[0], 40.0)
        self.assertEqual(endpoints[1], 10.0)
        self.assertEqual(endpoints[2:], (100.0, 10.0))

    def test_version_142_release_history_is_retained(self) -> None:
        feature_source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_42_DENSE_OOS_LABEL_LAYOUT", feature_source)
        self.assertIn("## [Version 1.42]", changelog)


if __name__ == "__main__":
    unittest.main()
