from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class ResponsiveBatchProcessingTests(unittest.TestCase):
    def test_worker_queue_drain_is_time_budgeted_and_yields_to_tk(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.drain_worker_queue)
        self.assertIn("WORKER_QUEUE_DRAIN_MAX_EVENTS", source)
        self.assertIn("WORKER_QUEUE_DRAIN_BUDGET_SECONDS", source)
        self.assertIn("drained_events += 1", source)
        self.assertIn("if not self.worker_queue.empty():", source)
        self.assertIn("next_delay = 1", source)

    def test_processing_worker_announces_each_order_before_starting_child_process(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.worker_run_batch)
        announce = source.index('"order_started"')
        submit = source.index("executor.submit(shower_batch.process_one_order_isolated")
        self.assertLess(announce, submit)
        self.assertIn("future.result(timeout=self.ORDER_FUTURE_POLL_SECONDS)", source)

    def test_cancel_waits_for_current_order_then_stops_before_next(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.worker_run_batch)
        self.assertIn('"order_cancel_pending"', source)
        self.assertIn("if task_context is not None and task_context.cancelled:", source)
        self.assertIn('"batch_cancelled_partial"', source)
        self.assertIn("self.update_processing_history(run, output_dir", source)
        self.assertIn("raise shower_tasks.TaskCancelled", source)

    def test_destructive_cleanup_is_scoped_to_current_order(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.worker_run_batch)
        self.assertIn("self.clear_existing_outputs_for_orders([order]", source)
        self.assertIn("self.remove_order_sketch_files([order]", source)
        self.assertIn("self.remove_order_program_files([order]", source)
        self.assertNotIn("self.clear_existing_outputs_for_orders(orders,", source)

    def test_cancel_button_is_reenabled_after_other_controls_are_locked(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.start_background_activity)
        disabled = source.index("self.set_controls_enabled(False)")
        enabled_cancel = source.index("self.cancel_task_button.configure(state=tk.NORMAL)")
        self.assertLess(disabled, enabled_cancel)

    def test_live_result_path_avoids_per_order_history_disk_reads(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.apply_live_processing_result)
        self.assertNotIn("load_processing_history", source)
        self.assertNotIn("history_for_order", source)
        self.assertNotIn("load_manual_overrides", source)
        self.assertIn('"Processed {completed}/{total} • finalizing"', source)

    def test_batch_done_does_not_reinsert_every_result(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.drain_worker_queue)
        done = source[source.index('elif kind == "done":'):source.index('elif kind == "error":')]
        self.assertIn("self.finalize_live_processing_rows", done)
        self.assertNotIn("self.insert_or_update_result(result)", done)

    def test_version_170_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 170)
        self.assertIn("VERSION_1_70_RESPONSIVE_BATCH_PROCESSING", (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "responsive_processing_queue",
            "visible_order_processing_cursor",
            "safe_between_order_cancellation",
            "incremental_batch_finalization",
            "enabled_processing_cancel_button",
            "version_1_70_responsive_batch_processing",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
