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


class StablePaintHandoffTests(unittest.TestCase):
    def test_shared_presenter_keeps_veil_through_visible_event_loop_turns(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        self.assertIn("WindowPresentationVeil(window, background=self.APP_BG)", source)
        self.assertIn("def post_reveal_paint_pass", source)
        self.assertIn("window.attributes(\"-alpha\", 1.0)", source)
        self.assertIn("cover.lift()", source)
        self.assertIn("post_reveal_passes", source)

    def test_startup_transfers_external_shield_to_in_root_cover(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.finish_startup_presentation)
        self.assertIn("root_cover = WindowLoadingCover(", source)
        self.assertIn("def finish_handoff", source)
        self.assertLess(source.index("shield.destroy()"), source.index("root_cover.destroy()", source.index("shield.destroy()")))

    def test_review_waits_for_real_first_preview_frames(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn('"first_sketch_frame_ready": False', source)
        self.assertIn('"first_dxf_frame_ready": False', source)
        self.assertIn("preview_ready = bool(state.get(\"first_sketch_frame_ready\"))", source)
        self.assertIn("presentation_cover=review_cover", source)
        self.assertIn("release_presentation_cover=False", source)

    def test_settings_keeps_loading_cover_inside_final_window_until_presented(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn("settings_cover = WindowLoadingCover(", source)
        self.assertIn("presentation_cover=settings_cover", source)
        self.assertIn("post_reveal_passes=4", source)

    def test_version_175_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 175)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_75_STABLE_PAINT_HANDOFF", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "post_map_presentation_veil",
            "startup_internal_cover_handoff",
            "review_first_content_frame_gate",
            "settings_target_window_cover",
            "version_1_75_stable_paint_handoff",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
