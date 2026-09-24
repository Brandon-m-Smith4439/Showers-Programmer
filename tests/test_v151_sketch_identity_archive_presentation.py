from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui


class SketchIdentityArchivePresentationTests(unittest.TestCase):
    def test_sketch_page_keeps_p3_but_displays_mapped_aw_item_two(self) -> None:
        panel = programmer.Panel(3, 2, '28" x 77" FP', 28.0, 77.0, "DENVER 2")
        panel.aw_item = 2
        job = programmer.Job(
            Path("input.pdf"),
            "239018",
            "JOB 1",
            [panel],
            Path("out.pdf"),
            Path("report.txt"),
        )

        self.assertEqual(panel.item, 3)
        self.assertEqual(gui.ShowerProgrammerApp.panel_order_label(job, panel), "239018.2")

    def test_remaining_child_order_can_resolve_completed_batch_archive(self) -> None:
        sent = shower_batch.ProcessOrder("239018", "JOB 1")
        deleted = shower_batch.ProcessOrder("239019", "JOB 2")
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.process_batches = {"batch-1": {"all_orders": [sent, deleted]}}
        app.order_batch_ids = {"239018": ["batch-1"]}
        app.load_processing_history = mock.Mock(return_value={"orders": {}})
        app.sent_process_signature = mock.Mock(return_value="current")
        app.order_is_terminal_in_history = mock.Mock(return_value=True)
        app.history_entry_from_data = mock.Mock(
            side_effect=lambda _history, aw: (
                {"sent_at": "2026-09-22T08:00:00", "sent_process_signature": "current"}
                if aw == "239018"
                else {"deleted_at": "2026-09-22T08:01:00", "deleted_process_signature": "current"}
            )
        )

        result = app.archivable_batch_id_for_context(None, [sent])

        self.assertEqual(result, "batch-1")

    def test_manual_customer_is_optional(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_manual_program_dialog)

        self.assertIn('add_field(4, "Customer (optional)", customer_var)', source)
        self.assertNotIn("if not customer_var.get().strip()", source)

    def test_windows_are_presented_after_layout_is_ready(self) -> None:
        main_source = inspect.getsource(gui.main)
        presentation_source = inspect.getsource(gui.ShowerProgrammerApp.force_main_window_maximized)

        self.assertIn("SetCurrentProcessExplicitAppUserModelID", main_source)
        self.assertIn('root.attributes("-alpha", 0.0)', main_source)
        self.assertNotIn("self.root.withdraw()", presentation_source)
        self.assertIn('self.root.attributes("-alpha", 1.0)', presentation_source)
        self.assertNotIn("for delay in", presentation_source)

    def test_version_151_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 151)
        self.assertIn(
            "VERSION_1_51_SKETCH_IDENTITY_ARCHIVE_PRESENTATION",
            (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
