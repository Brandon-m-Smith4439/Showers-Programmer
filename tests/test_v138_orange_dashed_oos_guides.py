from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shower_programmer_gui import ShowerProgrammerApp


class OrangeDashedOosGuideTests(unittest.TestCase):
    def test_release_metadata_tracks_version_138(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 138)

    def test_horizontal_guide_uses_actual_minor_axis_direction(self) -> None:
        start = (20.0, 100.0)
        actual_end = (420.0, 102.0)

        guide_end = ShowerProgrammerApp.dxf_exaggerated_oos_guide_endpoint(start, actual_end)

        self.assertGreater(actual_end[1] - start[1], 0.0)
        self.assertGreater(guide_end[1] - start[1], 0.0)

    def test_vertical_guide_uses_actual_minor_axis_direction(self) -> None:
        start = (300.0, 40.0)
        actual_end = (298.0, 500.0)

        guide_end = ShowerProgrammerApp.dxf_exaggerated_oos_guide_endpoint(start, actual_end)

        self.assertLess(actual_end[0] - start[0], 0.0)
        self.assertLess(guide_end[0] - start[0], 0.0)

    def test_direction_guide_uses_restored_long_dash_pattern(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        marker = 'tags=("dxf_oos_direction_guide",)'
        marker_index = source.index(marker)
        guide_call = source[max(0, marker_index - 240) : marker_index]
        self.assertIn("fill=self.WARNING", guide_call)
        self.assertIn("dash=", guide_call)


if __name__ == "__main__":
    unittest.main()
