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


class SnappyReviewStartupTests(unittest.TestCase):
    def test_pdfium_is_lazy_loaded(self) -> None:
        module_source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        startup_prefix = module_source.split("def get_pdfium()", 1)[0]
        self.assertNotIn("import pypdfium2", startup_prefix)
        self.assertIn("import pypdfium2 as loaded_pdfium", inspect.getsource(gui.get_pdfium))

    def test_cached_review_context_is_handed_directly_to_window_builder(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn("prepared_context: dict[str, Any] | None = None", source)
        self.assertIn("prepared_context = self.cached_order_review_context", source)
        self.assertIn("context = prepared_context or self.cached_order_review_context", source)
        self.assertIn("review_host_cover = WindowLoadingCover(", source)

    def test_loading_panel_is_delayed_until_preparation_is_actually_slow(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.schedule_review_opening_feedback)
        self.assertIn("self.root.after(140, show_if_still_waiting)", source)
        self.assertIn("if self.pending_review_open_aw != aw_order", source)

    def test_single_order_selection_prefetches_review_context(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.on_orders_tree_selection)
        self.assertIn("self.start_review_cache_warmup(selected_orders)", source)
        self.assertIn("len(selected_orders) == 1", source)

    def test_review_completion_uses_fast_adaptive_queue_polling(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.drain_worker_queue)
        self.assertIn("if not self.worker_queue.empty():", source)
        self.assertIn("next_delay = 1", source)
        self.assertIn("if self.pending_review_open_aw:", source)
        self.assertIn("next_delay = 10", source)
        self.assertIn("next_delay = 20", source)
        self.assertIn("next_delay = 90", source)

    def test_first_review_raster_never_renders_synchronously_on_tk_thread(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.editor_page_image)
        self.assertNotIn("self.render_pdfium_single_page_to_file", source)
        self.assertIn("priority_page_index=page_index", source)
        self.assertIn('state.setdefault("raster_source_cache", {})', source)

    def test_priority_page_notifies_before_full_cache_warm(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.start_async_review_raster_render)
        priority_render = source.index("priority_ready = self.render_pdfium_single_page_to_file")
        priority_notify = source.index("notify_redraw()", priority_render)
        full_warm = source.index("self.ensure_review_pdf_raster_cache", priority_notify)
        self.assertLess(priority_render, priority_notify)
        self.assertLess(priority_notify, full_warm)

    def test_startup_housekeeping_is_deferred_off_tk_thread(self) -> None:
        init_source = inspect.getsource(gui.ShowerProgrammerApp.__init__)
        maintenance_source = inspect.getsource(gui.ShowerProgrammerApp.start_deferred_startup_housekeeping)
        self.assertIn("self.root.after(180, self.start_deferred_startup_housekeeping)", init_source)
        self.assertNotIn("self.root.after(250, self.archive_old_action_history)", init_source)
        self.assertNotIn("self.state_store.migrate_processing_history", init_source)
        self.assertIn("self.state_store.migrate_processing_history", maintenance_source)
        self.assertIn("threading.Thread(", maintenance_source)
        self.assertIn("daemon=True", maintenance_source)

    def test_startup_recovery_discovery_runs_off_tk_thread(self) -> None:
        init_source = inspect.getsource(gui.ShowerProgrammerApp.__init__)
        async_source = inspect.getsource(gui.ShowerProgrammerApp.start_startup_recovery_check_async)
        apply_source = inspect.getsource(gui.ShowerProgrammerApp.apply_startup_recovery_results)
        self.assertIn("self.root.after(650, self.start_startup_recovery_check_async)", init_source)
        self.assertIn("shower_reliability.startup_recovery_issues", async_source)
        self.assertIn("threading.Thread(", async_source)
        self.assertIn("self.root.after(0, apply_results)", async_source)
        self.assertIn("messagebox._show", apply_source)

    def test_version_163_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_63_SNAPPY_REVIEW_STARTUP"
        self.assertGreaterEqual(version["version_number"], 163)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self.assertIn("version_1_63_snappy_review_startup", flags)
        self.assertIn("async_priority_review_raster", flags)


if __name__ == "__main__":
    unittest.main()
