from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"


class LongDashOosGuideTests(unittest.TestCase):
    def test_release_metadata_includes_version_139(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 139)

    def test_oos_guide_and_connector_use_long_dash_patterns(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        guide_marker = 'tags=("dxf_oos_direction_guide",)'
        connector_marker = 'tags=("dxf_oos_offset_leg",)'
        guide_index = source.index(guide_marker)
        connector_index = source.index(connector_marker)
        self.assertIn("dash=(14, 7)", source[guide_index - 240 : guide_index])
        self.assertIn("dash=(10, 6)", source[connector_index - 240 : connector_index])


if __name__ == "__main__":
    unittest.main()
