from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


class Version199IssueAutofitResendWarningTests(unittest.TestCase):
    def make_order(self, aw: str = "239591") -> shower_batch.ProcessOrder:
        order = shower_batch.ProcessOrder(
            aw_order=aw,
            job_name="90479383 OCTOPLEX BLOCK 19 UNIT 135 4365",
            customer="BFS East Greenville SC MW",
        )
        order.items[1] = shower_batch.ProcessItem(item=1, width_text="30", height_text="72")
        return order

    def test_duplicate_family_issues_use_one_consistent_orders_column_message(self) -> None:
        variants = [
            "Duplicate import detected: Job Nr 90479383 has 2 identical source sketches. Remove/correct the repeated import before processing A&W order 239591.",
            "Possible duplicate import: Job Nr 90479383 has 2 source sketches whose names differ only by a copy suffix or spacing. Verify the repeated import before processing A&W order 239591.",
            "Possible duplicate order entry: Job Nr 90479383 matches 2 sketches with different PO/reference numbers (43658876, 43659060). Correct or remove the unintended duplicate order before processing A&W order 239591.",
            "Possible duplicate order entry: Job Nr 90479383 matches 2 sketches with different PO/reference numbers (43658876, 43659060). Verify A&W order 239591 before processing.",
            "Multiple PDFs match A&W order 239591 / Job Nr 90479383. Keep only the intended local PDF or rename it to include the A&W order or Job Nr: A.pdf B.pdf",
        ]
        rendered = {gui.ShowerProgrammerApp.concise_issue_text(value) for value in variants}
        self.assertEqual(
            rendered,
            {"DUPLICATE ORDER WARNING: Job 90479383 • A&W 239591 • verify duplicate source/order before processing"},
        )

    def test_duplicate_equivalent_issue_messages_are_deduplicated_in_summary(self) -> None:
        issues = [
            "Duplicate import detected: Job Nr 90479383 has 2 identical source sketches. Remove/correct the repeated import before processing A&W order 239591.",
            "Possible duplicate import: Job Nr 90479383 has 2 source sketches whose names differ only by a copy suffix or spacing. Verify the repeated import before processing A&W order 239591.",
        ]
        summary = gui.ShowerProgrammerApp.issue_summary(issues)
        self.assertEqual(
            summary,
            "DUPLICATE ORDER WARNING: Job 90479383 • A&W 239591 • verify duplicate source/order before processing",
        )

    def test_issues_autofit_uses_full_measured_width_while_other_columns_keep_caps(self) -> None:
        self.assertEqual(gui.ShowerProgrammerApp.orders_tree_autofit_target("issues", 220, 1487), 1487)
        self.assertEqual(gui.ShowerProgrammerApp.orders_tree_autofit_target("job", 120, 1487), 300)
        self.assertEqual(gui.ShowerProgrammerApp.orders_tree_autofit_target("customer", 110, 80), 110)

    def test_current_signature_sent_detection_distinguishes_resend_from_changed_revision(self) -> None:
        order = self.make_order()
        signature = gui.ShowerProgrammerApp.sent_process_signature(order)
        history = {
            "orders": {
                "239591": {
                    "sent_at": "2026-10-02 07:45:00",
                    "sent_process_signature": signature,
                }
            }
        }
        self.assertTrue(gui.ShowerProgrammerApp.order_is_currently_sent_in_history(order, history))

        changed = self.make_order()
        changed.items[2] = shower_batch.ProcessItem(item=2, width_text="24", height_text="60")
        self.assertFalse(gui.ShowerProgrammerApp.order_is_currently_sent_in_history(changed, history))

    def test_send_review_contains_red_already_sent_warning_and_explicit_send_again_confirmation(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn('"ALREADY SENT WARNING"', source)
        self.assertIn('confirm_text="Send Again"', source)
        self.assertIn('"ALREADY SENT"', source)
        self.assertIn('already_sent_aw_orders', source)
        self.assertIn('Sending again can create duplicate production', source)

    def test_version_199_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 199)
        if version["version_number"] == 199:
            self.assertEqual(version["marker"], "VERSION_1_99_ISSUE_AUTOFIT_RESEND_WARNING")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_99_ISSUE_AUTOFIT_RESEND_WARNING", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "consistent_duplicate_issue_message",
            "full_issue_column_autofit",
            "already_sent_send_warning",
            "current_signature_resend_detection",
            "version_1_99_issue_autofit_resend_warning",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
