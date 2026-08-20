from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
import shower_reliability


class MirrorAnchorTests(unittest.TestCase):
    def test_mirror_bottom_left_uses_detected_outline_height(self) -> None:
        panel = programmer.Panel(1, 1, '1/4" Mirror Clear Annealed', 58.0, 42.0, "WJ")
        panel.mirror_glass = True
        panel.indicator_corner = "bottom_left"
        bbox = (120.0, 210.0, 470.0, 520.0)
        config = {
            "waterjet_indicator_size": 30,
            "waterjet_indicator_length_ratio": 1.6,
            "indicator_nudge": {
                "waterjet_outline_x": 0,
                "waterjet_outline_y": 25,
                "waterjet_corner_x": {"bottom_left": -18},
            },
        }

        geometry = programmer.indicator_marker_geometry(
            "WJ",
            "bottom_left",
            bbox,
            612.0,
            792.0,
            config,
            precise_edges=True,
            panel=panel,
        )

        self.assertIsNotNone(geometry)
        self.assertEqual((geometry or {})["point"], (102.0, 210.0))

    def test_regular_waterjet_keeps_existing_outline_nudge(self) -> None:
        panel = programmer.Panel(1, 1, '3/8" Clear Tempered', 58.0, 42.0, "WJ")
        panel.indicator_corner = "bottom_left"
        geometry = programmer.indicator_marker_geometry(
            "WJ",
            "bottom_left",
            (120.0, 210.0, 470.0, 520.0),
            612.0,
            792.0,
            {
                "waterjet_indicator_size": 30,
                "indicator_nudge": {"waterjet_outline_y": 25},
            },
            precise_edges=True,
            panel=panel,
        )
        self.assertEqual((geometry or {})["point"], (120.0, 235.0))


class SendRollbackTrackerTests(unittest.TestCase):
    workspace = ROOT / "tests" / "_verification" / "v128-send-rollback"

    def setUp(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def test_cancel_removes_new_file_created_by_transaction(self) -> None:
        target = self.workspace / "shop" / "237670.pdf"
        source = self.workspace / "source.pdf"
        source.write_bytes(b"new sketch")
        tracker = shower_reliability.SendRollbackTracker(self.workspace, "send-new")
        entry = tracker.prepare_target(target)
        tracker.copy_atomically(source, target)
        tracker.record_copy(entry)

        rolled_back, warnings = tracker.rollback()

        self.assertEqual(warnings, [])
        self.assertIn(target, rolled_back)
        self.assertFalse(target.exists())

    def test_cancel_restores_file_replaced_by_transaction(self) -> None:
        target = self.workspace / "shop" / "237670.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"previous production sketch")
        source = self.workspace / "source.pdf"
        source.write_bytes(b"replacement sketch")
        tracker = shower_reliability.SendRollbackTracker(self.workspace, "send-replace")
        entry = tracker.prepare_target(target)
        tracker.copy_atomically(source, target)
        tracker.record_copy(entry)

        rolled_back, warnings = tracker.rollback()

        self.assertEqual(warnings, [])
        self.assertIn(target, rolled_back)
        self.assertEqual(target.read_bytes(), b"previous production sketch")

    def test_cancel_preserves_file_changed_after_send_copy(self) -> None:
        target = self.workspace / "shop" / "237670.pdf"
        source = self.workspace / "source.pdf"
        source.write_bytes(b"sent sketch")
        tracker = shower_reliability.SendRollbackTracker(self.workspace, "send-external-change")
        entry = tracker.prepare_target(target)
        tracker.copy_atomically(source, target)
        tracker.record_copy(entry)
        target.write_bytes(b"newer external edit")

        rolled_back, warnings = tracker.rollback()

        self.assertEqual(rolled_back, [])
        self.assertEqual(target.read_bytes(), b"newer external edit")
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
