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


class OrangeReversedOosGuideTests(unittest.TestCase):
    def test_release_metadata_tracks_version_137(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 137)

    def test_horizontal_guide_remains_exaggerated(self) -> None:
        start = (20.0, 100.0)
        actual_end = (420.0, 102.0)

        guide_end = ShowerProgrammerApp.dxf_exaggerated_oos_guide_endpoint(start, actual_end)

        self.assertGreater(abs(guide_end[1] - start[1]), abs(actual_end[1] - start[1]))

    def test_vertical_guide_remains_exaggerated(self) -> None:
        start = (300.0, 40.0)
        actual_end = (298.0, 500.0)

        guide_end = ShowerProgrammerApp.dxf_exaggerated_oos_guide_endpoint(start, actual_end)

        self.assertGreater(abs(guide_end[0] - start[0]), abs(actual_end[0] - start[0]))

    def test_old_orange_endpoint_ticks_are_removed(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertNotIn('tags=("dxf_oos_endpoint",)', source)
        self.assertIn('tags=("dxf_oos_direction_guide",)', source)


if __name__ == "__main__":
    unittest.main()
