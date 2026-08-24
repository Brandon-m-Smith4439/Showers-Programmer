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


class JoinedKickOosAndRefreshTests(unittest.TestCase):
    def test_two_run_kick_guides_share_the_actual_transition(self) -> None:
        shared = (39.5, 28.5)
        left = (0.0, 28.0)
        right = (79.5, 28.375)
        mapped_shared = (500.0, 100.0)
        entries = [
            (shared, left, *mapped_shared, 80.0, 106.0),
            (right, shared, 920.0, 101.5, *mapped_shared),
        ]

        paths = ShowerProgrammerApp.dxf_oos_guide_paths(entries)

        left_path = paths[(shared, left)]
        right_path = paths[(right, shared)]
        self.assertEqual(left_path[0], mapped_shared)
        self.assertEqual(right_path[0], mapped_shared)
        self.assertLess(left_path[1][0], mapped_shared[0])
        self.assertGreater(right_path[1][0], mapped_shared[0])
        self.assertGreater(left_path[1][1], mapped_shared[1])
        self.assertGreater(right_path[1][1], mapped_shared[1])

    def test_unconnected_oos_guide_keeps_existing_direction(self) -> None:
        start = (0.0, 80.0)
        end = (60.0, 79.875)
        mapped_start = (80.0, 100.0)
        mapped_end = (900.0, 102.0)

        path = ShowerProgrammerApp.dxf_oos_guide_paths(
            [(start, end, *mapped_start, *mapped_end)]
        )[(start, end)]

        self.assertEqual(path[0], mapped_start)
        self.assertEqual(path[2], mapped_end)
        self.assertEqual(
            path[1],
            ShowerProgrammerApp.dxf_exaggerated_oos_guide_endpoint(mapped_start, mapped_end),
        )

    def test_three_run_chain_is_not_reinterpreted_as_a_two_run_kick(self) -> None:
        first = ((0.0, 80.0), (20.0, 79.875), 80.0, 100.0, 300.0, 102.0)
        second = ((20.0, 79.875), (40.0, 80.0), 300.0, 102.0, 520.0, 100.0)
        third = ((40.0, 80.0), (60.0, 79.875), 520.0, 100.0, 740.0, 102.0)

        paths = ShowerProgrammerApp.dxf_oos_guide_paths([first, second, third])

        self.assertEqual(paths[(first[0], first[1])][0], (first[2], first[3]))
        self.assertEqual(paths[(second[0], second[1])][0], (second[2], second[3]))
        self.assertEqual(paths[(third[0], third[1])][0], (third[2], third[3]))

    def test_refresh_rechecks_complex_oos_and_updates_visible_issue_state(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = source.index("        def refresh_dxf_preview() -> None:")
        end = source.index("        def rotate_dxf_and_process", start)
        refresh = source[start:end]
        self.assertIn("complex_cache.clear()", refresh)
        self.assertIn("issues = self.visible_order_issues(", refresh)
        self.assertIn("Manual DXF review cleared automatically", refresh)
        self.assertIn("Four OOS runs remain", refresh)

    def test_version_145_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["version"], "Version 1.45")
        self.assertEqual(version["version_number"], 145)
        self.assertEqual(version["marker"], "VERSION_1_45_JOINED_KICK_OOS_REFRESH")
        feature_source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn(version["marker"], feature_source)


if __name__ == "__main__":
    unittest.main()
