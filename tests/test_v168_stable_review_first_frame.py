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


class StableReviewFirstFrameTests(unittest.TestCase):
    def test_review_host_cover_precedes_workspace_and_native_presentation(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        host_cover = source.index("review_host_cover = WindowLoadingCover(")
        cover = source.index("review_cover = WindowLoadingCover(", host_cover)
        header = source.index("header = ctk.CTkFrame(review_content", cover)
        workspace = source.index("workspace = ctk.CTkFrame(review_content", header)
        present = source.index("self.present_window_without_flash(", workspace)
        self.assertLess(host_cover, cover)
        self.assertLess(cover, header)
        self.assertLess(header, workspace)
        self.assertLess(workspace, present)
        self.assertIn("maximize=True", source[present:])


    def test_real_review_content_is_built_under_one_host_below_cover(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn("review_content = tk.Frame(dialog", source)
        self.assertIn("header = ctk.CTkFrame(review_content", source)
        self.assertIn("workspace = ctk.CTkFrame(review_content", source)
        cover = inspect.getsource(gui.WindowLoadingCover)
        self.assertIn("self.frame.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)", cover)
        self.assertIn("self.frame.lift()", cover)

    def test_cover_is_removed_only_after_first_redraw_and_settle(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        presentation = source.split("def present_review_window() -> None:", 1)[1]
        settle = presentation.index("dialog.update_idletasks()")
        redraw = presentation.index("redraw()", settle)
        destroy = presentation.index("review_cover.destroy()", redraw)
        self.assertLess(settle, redraw)
        self.assertLess(redraw, destroy)
        self.assertIn("reveal_after_stable_paint", presentation)
        self.assertIn("dialog.after(18", presentation)

    def test_review_context_prefetch_warms_dxf_geometry(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.prepare_order_review_context)
        self.assertIn("dxf_preview_cache", source)
        self.assertIn("self.order_review_dxf_preview_data(preview_path", source)
        self.assertIn('"dxf_preview_cache": dxf_preview_cache', source)
        self.assertIn('"initial_overview": initial_overview', source)
        review = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn('state.pop("initial_overview", None)', review)
        self.assertIn('dict(context.get("dxf_preview_cache", {}))', review)

    def test_child_window_icon_reuses_cached_photo(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.set_window_icon)
        self.assertIn("_shower_programmer_shared_icon", source)
        self.assertIn("if window is not getattr(self, \"root\", None):", source)
        self.assertEqual(source.count("tk.PhotoImage("), 1)

    def test_review_stable_first_frame_is_measured(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn('"Review Order",', source)
        self.assertIn('"Stable first frame",', source)
        reveal = source.split("def reveal_after_stable_paint(pass_index: int = 0) -> None:", 1)[1]
        self.assertLess(reveal.index("review_cover.destroy()"), reveal.index("self.record_performance("))
        self.assertIn("dialog.after(", reveal)
        self.assertIn("self.record_action(", reveal)


    def test_version_168_release_marker_is_current(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_68_STABLE_REVIEW_FIRST_FRAME"
        self.assertGreaterEqual(version["version_number"], 168)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "in_window_review_loading_cover",
            "background_dxf_preview_warmup",
            "background_review_overview_warmup",
            "cached_child_window_icon",
            "stable_review_first_frame_timing",
            "version_1_68_stable_review_first_frame",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
