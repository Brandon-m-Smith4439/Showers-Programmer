from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class RebuildRegressionReliabilityTests(unittest.TestCase):
    def test_retained_release_tests_do_not_pin_historical_current_version(self) -> None:
        for name, floor in (
            ("test_v169_full_surface_presentation.py", 169),
            ("test_v171_popup_ownership_archive_test.py", 171),
        ):
            source = (ROOT / "tests" / name).read_text(encoding="utf-8")
            self.assertNotIn(f'assertEqual(version["version_number"], {floor})', source)
            self.assertIn(f'assertGreaterEqual(version["version_number"], {floor})', source)
            self.assertNotIn(f'assertEqual(version["marker"], "VERSION_1_{floor % 100:02d}', source)

    def test_retained_review_polling_test_tracks_current_responsive_contract(self) -> None:
        source = (ROOT / "tests" / "test_v163_snappy_review_startup.py").read_text(encoding="utf-8")
        self.assertNotIn('self.assertIn("next_delay = 25", source)', source)
        self.assertIn('self.assertIn("next_delay = 1", source)', source)
        self.assertIn('self.assertIn("next_delay = 10", source)', source)
        self.assertIn('self.assertIn("next_delay = 20", source)', source)
        self.assertIn('self.assertIn("next_delay = 90", source)', source)

    def test_version_172_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 172)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_72_REBUILD_REGRESSION_RELIABILITY", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "cumulative_release_test_compatibility",
            "retained_release_version_floor",
            "version_1_72_rebuild_regression_reliability",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
