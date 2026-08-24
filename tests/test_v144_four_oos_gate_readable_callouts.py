from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
from shower_programmer_gui import ShowerProgrammerApp


class FourOosGateAndReadableCalloutTests(unittest.TestCase):
    def test_gate_starts_at_four_runs_on_one_side(self) -> None:
        three = [
            ((0.0, 80.0), (20.0, 79.875)),
            ((20.0, 79.875), (40.0, 79.75)),
            ((40.0, 79.75), (60.0, 79.625)),
            ((60.0, 79.625), (60.0, 0.0)),
            ((60.0, 0.0), (0.0, 0.0)),
            ((0.0, 0.0), (0.0, 80.0)),
        ]
        four = [three[0], three[1], three[2], ((60.0, 79.625), (80.0, 79.5))]
        four.extend([((80.0, 79.5), (80.0, 0.0)), ((80.0, 0.0), (0.0, 0.0)), ((0.0, 0.0), (0.0, 80.0))])

        self.assertFalse(programmer.dxf_complex_oos_review_from_segments(three)["requires_manual_review"])
        details = programmer.dxf_complex_oos_review_from_segments(four)
        self.assertTrue(details["requires_manual_review"])
        self.assertEqual(details["side_counts"].get("top"), 4)

    def test_fp_s_warning_alone_does_not_create_four_oos_gate(self) -> None:
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.manual_overrides_for_output = lambda _output: {}
        app.current_complex_oos_candidate_items = lambda *_args, **_kwargs: ({1}, {})
        app.current_complex_oos_review = lambda *_args, **_kwargs: {
            "requires_manual_review": False,
            "signature": {"path": "panel.dxf", "size": 10, "modified_ns": 1},
        }
        issues = ["P1: FP-S cut-in/cut-out detected; manual DXF review required."]

        self.assertEqual(
            app.unresolved_manual_dxf_review_items("237774", issues, output_dir=ROOT),
            [],
        )
        self.assertEqual(app.visible_order_issues("237774", issues, output_dir=ROOT), issues)

    def test_stale_complex_warning_auto_resolves_when_geometry_is_no_longer_complex(self) -> None:
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.manual_overrides_for_output = lambda _output: {}
        app.current_complex_oos_candidate_items = lambda *_args, **_kwargs: ({1}, {})
        app.current_complex_oos_review = lambda *_args, **_kwargs: {
            "requires_manual_review": False,
            "signature": {"path": "panel.dxf", "size": 20, "modified_ns": 2},
        }
        issue = "P1: Complex OOS geometry detected (4 OOS runs on top edge); manual DXF review required."

        self.assertEqual(
            app.unresolved_manual_dxf_review_items("237774", [issue], output_dir=ROOT),
            [],
        )
        self.assertEqual(app.visible_order_issues("237774", [issue], output_dir=ROOT), [])

    def test_near_label_needs_no_arrow_and_far_label_stops_short_of_guide(self) -> None:
        bounds = (40.0, 30.0, 80.0, 50.0)
        near = ShowerProgrammerApp.dxf_oos_callout_leader(
            bounds,
            (60.0, 40.0),
            (20.0, 60.0),
            (100.0, 60.0),
        )
        far = ShowerProgrammerApp.dxf_oos_callout_leader(
            (40.0, 0.0, 80.0, 20.0),
            (60.0, 10.0),
            (20.0, 80.0),
            (100.0, 80.0),
        )

        self.assertIsNone(near)
        self.assertIsNotNone(far)
        assert far is not None
        self.assertLess(far[3], 80.0)
        self.assertGreaterEqual(80.0 - far[3], 6.0)

    def test_order_237774_has_two_distinct_oos_runs_and_no_manual_gate(self) -> None:
        path = ROOT / "Shower Programmer" / "Output" / "Runs" / "8.21.26" / "Batch_6398" / "Programs" / "23777401.dxf"
        if not path.exists():
            self.skipTest("Archived 237774.1 DXF is not available in this checkout")
        details = programmer.dxf_complex_oos_review_details(path)
        labels = {
            ShowerProgrammerApp.out_of_square_segment_label(start, end, 1.0)
            for start, end in details["highlighted_segments"]
        }

        self.assertFalse(details["requires_manual_review"])
        self.assertEqual(details["side_counts"].get("top"), 2)
        self.assertEqual(labels, {'1/8" OOS', '1/2" OOS'})

    def test_version_144_release_history_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 144)
        feature_source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_44_FOUR_OOS_GATE_READABLE_CALLOUTS", feature_source)


if __name__ == "__main__":
    unittest.main()
