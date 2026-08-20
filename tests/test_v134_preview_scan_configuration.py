from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_configuration
from shower_programmer_gui import ShowerProgrammerApp


class PreviewScanConfigurationTests(unittest.TestCase):
    def test_release_metadata_tracks_version_134(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["version"], "Version 1.34")
        self.assertEqual(version["version_number"], 134)
        self.assertEqual(version["marker"], "VERSION_1_34_PREVIEW_SCAN_CONFIGURATION")

    def test_connected_return_label_search_starts_beyond_hinge_fabrication(self) -> None:
        connected_return = ((79.375, 28.0), (72.375, 28.125))

        is_return, inward_distances, segment_shifts = ShowerProgrammerApp.dxf_oos_label_search_parameters(
            *connected_return,
            79.5,
        )

        self.assertTrue(is_return)
        self.assertGreaterEqual(inward_distances[0], 38.0)
        self.assertIn(0.40, segment_shifts)

    def test_scan_io_workers_are_bounded_at_eight(self) -> None:
        self.assertEqual(ShowerProgrammerApp.scan_io_worker_count(0), 1)
        self.assertEqual(ShowerProgrammerApp.scan_io_worker_count(3), 3)
        self.assertEqual(ShowerProgrammerApp.scan_io_worker_count(40), 8)

    def test_missing_hinge_orientations_are_added_without_overwriting_choices(self) -> None:
        original = {
            "rules": {
                "hinge_label_keywords": ["GEN037", "PPH", "COL037"],
                "hinge_label_orientations": {"GEN037": "up"},
            }
        }
        snapshot = copy.deepcopy(original)

        upgraded, changed = ShowerProgrammerApp.configuration_with_hinge_orientation_defaults(original)

        self.assertTrue(changed)
        self.assertEqual(original, snapshot)
        self.assertEqual(
            upgraded["rules"]["hinge_label_orientations"],
            {"GEN037": "up", "PPH": "up", "COL037": "down"},
        )
        self.assertFalse(
            any(
                issue.path == "rules.hinge_label_orientations"
                for issue in shower_configuration.validate_configuration(upgraded)
            )
        )

    def test_hinge_orientation_validation_matches_codes_case_insensitively(self) -> None:
        config = {
            "pdf": {},
            "dxf": {},
            "rules": {
                "hinge_label_keywords": ["GEN037"],
                "hinge_label_orientations": {"gen037": "down"},
            },
            "item_overrides": {},
        }

        issues = shower_configuration.validate_configuration(config)

        self.assertFalse(
            any(
                issue.path == "rules.hinge_label_orientations"
                and "No default orientation" in issue.message
                for issue in issues
            )
        )


if __name__ == "__main__":
    unittest.main()
