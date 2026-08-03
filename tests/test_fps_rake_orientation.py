from __future__ import annotations

import math
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_programmer as programmer


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_raked_door_dxf(path: Path, *, short_cut_transition: bool = False) -> None:
    pairs = [
        ("0", "SECTION"),
        ("2", "HEADER"),
        ("9", "$INSUNITS"),
        ("70", "1"),
        ("0", "ENDSEC"),
        ("0", "SECTION"),
        ("2", "ENTITIES"),
    ]
    lines = [
        ((0.0, 0.0), (28.0, 0.0)),
        ((28.0, 0.0), (27.75, 83.5)),
        ((27.75, 83.5), (0.0, 83.5)),
        ((0.0, 83.5), (0.0, 0.0)),
    ]
    if short_cut_transition:
        lines.extend(
            [
                ((27.9617769, 9.2499893), (27.75, 60.5)),
                ((27.75, 60.5), (27.75, 74.25)),
            ]
        )
    for start, end in lines:
        pairs.extend(
            [
                ("0", "LINE"),
                ("10", f"{start[0]:g}"),
                ("20", f"{start[1]:g}"),
                ("11", f"{end[0]:g}"),
                ("21", f"{end[1]:g}"),
            ]
        )
    pairs.extend([("0", "ENDSEC"), ("0", "EOF")])
    path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")


class FpsRakeOrientationTests(unittest.TestCase):
    def test_full_height_fps_hinge_rake_flattens_cnc_bottom(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "source.dxf"
            output = temp / "output.dxf"
            write_raked_door_dxf(source)

            panel = programmer.Panel(2, 2, "FP-S AGEN037 AGEN037", 28.0, 83.5, "DENVER 1")
            panel.process_text = "DENVER 1"
            panel.hinge_side = "right"
            panel.hinges_up = False
            panel.rotation_degrees = -90.0
            panel.source_dxf = source
            panel.output_dxf = output
            config = {
                "rules": {
                    "auto_angle_correction": True,
                    "auto_dxf_angle_correction": True,
                    "auto_dxf_angle_min_degrees": 0.02,
                    "auto_dxf_angle_max_degrees": 1.0,
                    "auto_dxf_angle_min_side_ratio": 0.20,
                },
                "dxf": {"default_output_scale": 1.0},
            }

            self.assertTrue(programmer.has_fps_edgework(panel))
            self.assertFalse(programmer.needs_manual_review_for_fps_cut(panel, config))
            self.assertFalse(programmer.needs_manual_review_for_fps_dxf_cut(panel, config))

            programmer.apply_dxf_angle_correction(panel, config)
            expected = -math.degrees(math.atan2(0.25, 83.5))
            self.assertAlmostEqual(panel.angle_correction_degrees, expected, places=6)
            self.assertTrue(any("FP-S raked right edge detected" in reason for reason in panel.reasons))

            programmer.write_panel_dxf(panel, force=True, config=config)
            bottom = max(
                programmer.dxf_side_segments(output, "bottom"),
                key=lambda segment: math.dist(segment[0], segment[1]),
            )
            self.assertAlmostEqual(bottom[0][1], bottom[1][1], places=6)
            self.assertGreater(math.dist(bottom[0], bottom[1]), 83.49)

    def test_short_fps_cut_transition_puts_hinges_up(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "source.dxf"
            output = temp / "output.dxf"
            write_raked_door_dxf(source, short_cut_transition=True)

            panel = programmer.Panel(2, 2, "FP-S AGEN037 AGEN037", 28.0, 83.5, "DENVER 1")
            panel.process_text = "DENVER 1"
            panel.hinge_side = "right"
            panel.hinges_up = False
            panel.rotation_degrees = -90.0
            panel.indicator_corner = "top_right"
            panel.source_dxf = source
            panel.output_dxf = output
            config = {
                "rules": {
                    "auto_angle_correction": True,
                    "auto_dxf_angle_correction": True,
                    "auto_dxf_angle_min_degrees": 0.02,
                    "auto_dxf_angle_max_degrees": 1.0,
                    "auto_dxf_angle_min_side_ratio": 0.20,
                    "auto_dxf_fps_cut_min_segment_ratio": 0.12,
                    "auto_dxf_fps_cut_min_coverage_ratio": 0.45,
                },
                "dxf": {"default_output_scale": 1.0},
            }

            self.assertFalse(programmer.dxf_hinge_side_has_cut_in(source, "right", config))
            self.assertTrue(programmer.dxf_side_has_short_cut_transition(source, "right", config))
            programmer.adjust_denver_door_hinge_side_from_dxf(panel, config)
            programmer.apply_dxf_manual_review_warning(panel, config)
            programmer.apply_dxf_angle_correction(panel, config)

            self.assertTrue(panel.hinges_up)
            self.assertEqual(panel.rotation_degrees, 90.0)
            self.assertEqual(panel.indicator_corner, "bottom_left")
            self.assertEqual(panel.angle_correction_degrees, 0.0)
            self.assertTrue(any("hinges up from DXF FP-S cut transition" in reason for reason in panel.reasons))
            self.assertTrue(any("manual DXF review required" in warning for warning in panel.warnings))

            programmer.write_panel_dxf(panel, force=True, config=config)
            bottom = max(
                programmer.dxf_side_segments(output, "bottom"),
                key=lambda segment: math.dist(segment[0], segment[1]),
            )
            self.assertAlmostEqual(bottom[0][1], bottom[1][1], places=6)
            self.assertGreater(math.dist(bottom[0], bottom[1]), 83.49)


if __name__ == "__main__":
    unittest.main()
