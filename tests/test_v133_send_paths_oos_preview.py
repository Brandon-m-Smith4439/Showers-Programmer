from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shower_programmer_gui import ShowerProgrammerApp


class SendPathsAndOosPreviewTests(unittest.TestCase):
    def test_release_metadata_tracks_version_133(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 133)

    def test_send_unique_paths_preserves_order_and_removes_duplicates(self) -> None:
        first = ROOT / "Output" / "237716.pdf"
        second = ROOT / "Output" / "23771602.dxf"

        result = ShowerProgrammerApp.unique_paths([first, first, second, first])

        self.assertEqual(result, [first, second])

    def test_connected_short_return_is_included_in_oos_preview(self) -> None:
        segments = [
            ((0.0, 0.0), (28.0, 0.125)),
            ((28.0, 0.125), (28.125, 7.125)),
            ((28.125, 7.125), (28.0, 79.5)),
            ((28.0, 79.5), (0.0, 79.5)),
            ((0.0, 79.5), (0.0, 0.0)),
        ]

        highlighted = ShowerProgrammerApp.out_of_square_preview_segments(segments, 79.5)

        self.assertIn(segments[0], highlighted)
        self.assertIn(segments[1], highlighted)
        self.assertIn(segments[2], highlighted)
        self.assertEqual(
            ShowerProgrammerApp.out_of_square_segment_label(*segments[1]),
            '1/8" OOS',
        )

    def test_rotated_connected_return_is_still_detected(self) -> None:
        source = [
            ((0.0, 0.0), (28.0, 0.125)),
            ((28.0, 0.125), (28.125, 7.125)),
            ((28.125, 7.125), (28.0, 79.5)),
            ((28.0, 79.5), (0.0, 79.5)),
            ((0.0, 79.5), (0.0, 0.0)),
        ]

        def rotate(point: tuple[float, float]) -> tuple[float, float]:
            x, y = point
            angle = math.radians(90)
            return (
                round(x * math.cos(angle) - y * math.sin(angle), 9),
                round(x * math.sin(angle) + y * math.cos(angle), 9),
            )

        segments = [(rotate(start), rotate(end)) for start, end in source]
        highlighted = ShowerProgrammerApp.out_of_square_preview_segments(segments, 79.5)

        self.assertIn(segments[1], highlighted)

    def test_isolated_short_angled_cutout_remains_excluded(self) -> None:
        outline = [
            ((0.0, 0.0), (28.0, 0.125)),
            ((28.0, 0.125), (28.0, 79.5)),
            ((28.0, 79.5), (0.0, 79.5)),
            ((0.0, 79.5), (0.0, 0.0)),
        ]
        isolated_cutout = ((10.0, 40.0), (10.125, 45.0))
        segments = [*outline, isolated_cutout]

        highlighted = ShowerProgrammerApp.out_of_square_preview_segments(segments, 79.5)

        self.assertNotIn(isolated_cutout, highlighted)


if __name__ == "__main__":
    unittest.main()
