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


class ManualDxfReviewAndOosCalloutTests(unittest.TestCase):
    def test_manual_review_issue_extracts_piece(self) -> None:
        self.assertEqual(
            ShowerProgrammerApp.manual_dxf_review_item_from_issue(
                "P2: Complex OOS geometry detected; manual DXF review required."
            ),
            2,
        )
        self.assertEqual(
            ShowerProgrammerApp.manual_dxf_review_item_from_issue("P3: FP-S cut; review DXF"),
            3,
        )
        self.assertIsNone(ShowerProgrammerApp.manual_dxf_review_item_from_issue("P1: missing DXF"))

    def test_resolution_only_matches_the_exact_dxf_signature(self) -> None:
        signature = {"path": "program.dxf", "size": 20, "modified_ns": 100}
        data = {
            "item_overrides": {
                "237999": {
                    "2": {
                        ShowerProgrammerApp.MANUAL_DXF_REVIEW_RESOLUTION_KEY: {
                            "signature": signature,
                        }
                    }
                }
            }
        }
        self.assertTrue(
            ShowerProgrammerApp.manual_dxf_review_is_resolved_in_overrides(
                data, "237999", 2, signature
            )
        )
        changed = dict(signature, modified_ns=101)
        self.assertFalse(
            ShowerProgrammerApp.manual_dxf_review_is_resolved_in_overrides(
                data, "237999", 2, changed
            )
        )

    def test_visible_issues_hide_only_matching_resolved_review(self) -> None:
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        signature = {"path": "program.dxf", "size": 20, "modified_ns": 100}
        data = {
            "item_overrides": {
                "237999": {
                    "2": {
                        app.MANUAL_DXF_REVIEW_RESOLUTION_KEY: {"signature": signature}
                    }
                }
            }
        }
        app.manual_overrides_for_output = lambda _output: data
        app.current_complex_oos_candidate_items = lambda *_args, **_kwargs: ({2}, {})
        app.current_complex_oos_review = lambda *_args, **_kwargs: {
            "requires_manual_review": True,
            "signature": signature,
        }
        issues = [
            "P2: Complex OOS geometry detected; manual DXF review required.",
            "P2: source item P3",
        ]
        self.assertEqual(
            app.visible_order_issues("237999", issues, output_dir=ROOT),
            ["P2: source item P3"],
        )
        app.current_complex_oos_review = lambda *_args, **_kwargs: {
            "requires_manual_review": True,
            "signature": dict(signature, size=21),
        }
        self.assertEqual(app.visible_order_issues("237999", issues, output_dir=ROOT), issues)

    def test_oos_search_includes_matching_exterior_lanes(self) -> None:
        self.assertEqual(
            ShowerProgrammerApp.dxf_oos_normal_offsets((18.0, 26.0, 42.0)),
            (18.0, 26.0, 42.0, -18.0, -26.0, -42.0),
        )

    def test_source_contains_main_send_gate_and_arrow_rendering(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn("self.order_result_sources[str(result.aw_order)] = source_result", source)
        self.assertIn("manual_dxf_blocked = bool(unresolved_dxf_items)", source)
        self.assertIn("Resolve Manual DXF Review", source)
        self.assertIn("arrow=tk.LAST", source)
        self.assertIn("outside_penalty = 14.0 if not inside_outline else 0.0", source)

    def test_version_143_release_history_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 143)
        feature_source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_43_MANUAL_DXF_REVIEW_OOS_CALLOUTS", feature_source)


if __name__ == "__main__":
    unittest.main()
