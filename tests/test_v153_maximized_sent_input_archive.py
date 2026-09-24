from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


class MaximizedSentInputArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sent = shower_batch.ProcessOrder("238159", "89911400 123 HUNTS")
        self.unsent = shower_batch.ProcessOrder("238158", "89909114 3239 SUNNYBROOK")
        self.app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        self.app.process_batches = {
            "batch-6469": {"all_orders": [self.sent, self.unsent]},
        }
        self.app.order_batch_ids = {"238159": ["batch-6469"]}
        self.app.sent_process_signature = mock.Mock(side_effect=lambda order: f"sig-{order.aw_order}")
        self.history = {
            "orders": {
                "238159": {
                    "sent_at": "2026-09-22 08:00:00",
                    "sent_process_signature": "sig-238159",
                },
                "238158": {},
            }
        }
        self.app.load_processing_history = mock.Mock(return_value=self.history)

    def test_sent_order_inputs_are_archivable_inside_incomplete_batch(self) -> None:
        sent_orders = self.app.sent_orders_for_input_archive_context(None, [self.sent], self.history)

        self.assertEqual([order.aw_order for order in sent_orders], ["238159"])
        self.assertIsNone(self.app.archivable_batch_id_for_context(None, [self.sent]))

    def test_batch_context_archives_only_currently_sent_orders(self) -> None:
        sent_orders = self.app.sent_orders_for_input_archive_context("batch-6469", [], self.history)

        self.assertEqual([order.aw_order for order in sent_orders], ["238159"])

    def test_order_archive_does_not_request_process_list_retirement(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.archive_sent_order_inputs)

        self.assertIn("include_process_lists=False", source)
        self.assertIn("completed_process_batches=[]", source)

    def test_main_window_uses_native_maximize_before_reveal(self) -> None:
        maximize_source = inspect.getsource(gui.ShowerProgrammerApp.maximize_window)
        presentation_source = inspect.getsource(gui.ShowerProgrammerApp.force_main_window_maximized)

        self.assertIn("GetAncestor", maximize_source)
        self.assertLess(maximize_source.index("ShowWindow"), maximize_source.index('window.state("zoomed")'))
        self.assertNotIn("self.root.after(220, settle_and_reveal)", presentation_source)
        self.assertNotIn("self.root.update()", presentation_source)
        self.assertLess(
            presentation_source.index("self.maximize_window(self.root)"),
            presentation_source.index('self.root.attributes("-alpha", 1.0)'),
        )

    def test_version_153_release_marker_is_preserved(self) -> None:
        marker = "VERSION_1_53_MAXIMIZED_SENT_INPUT_ARCHIVE"

        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
