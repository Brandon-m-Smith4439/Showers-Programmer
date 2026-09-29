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


class FlashFreeWindowMappingTests(unittest.TestCase):
    def test_hidden_children_use_flash_free_native_shell(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.create_hidden_toplevel)
        shell_source = inspect.getsource(gui.FlashFreeToplevel)
        self.assertIn("FlashFreeToplevel(owner, background=self.APP_BG)", source)
        self.assertIn("self.withdraw()", shell_source)
        self.assertIn('self.attributes("-alpha", 0.0)', shell_source)
        self.assertIn("_shower_never_mapped_unstyled", source)
        self.assertIn("self.install_first_map_guard(window)", source)

    def test_shared_presenter_maps_only_after_hidden_layout_is_complete(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        self.assertIn("window.withdraw()", source)
        self.assertIn("window.update_idletasks()", source)
        self.assertIn("window.deiconify()", source)
        self.assertIn('window.attributes("-alpha", 1.0)', source)
        self.assertLess(source.index("window.withdraw()"), source.index("window.update_idletasks()"))
        self.assertLess(source.index("window.update_idletasks()"), source.index('window.attributes("-alpha", 1.0)'))
        stage = inspect.getsource(gui.ShowerProgrammerApp.stage_window_behind_owner)
        self.assertIn("window.withdraw()", stage)
        self.assertNotIn("HWND_BOTTOM", stage)
        self.assertIn("self.release_first_map_guard(window)", source)
        self.assertIn("self.stabilize_window_foreground", source)
        self.assertNotIn("focus_force", source)

    def test_startup_root_stays_transparent_until_branded_shield_is_present(self) -> None:
        source = inspect.getsource(gui.main)
        start = source.index('root.attributes("-alpha", 0.0)')
        shield = source.index("startup_shield = StartupShield(")
        finish = source.index("app.finish_startup_presentation(startup_shield)")
        visible_between = source.find('root.attributes("-alpha", 1.0)', start, shield)
        self.assertEqual(visible_between, -1)
        self.assertLess(shield, finish)

    def test_startup_shield_is_withdrawn_and_painted_before_map(self) -> None:
        source = inspect.getsource(gui.StartupShield)
        self.assertIn("self.window.withdraw()", source)
        self.assertIn('self.window.attributes("-alpha", 0.0)', source)
        self.assertIn("self._present_fully_painted()", source)
        present = source.split("def _present_fully_painted", 1)[1]
        self.assertLess(present.index("self.window.deiconify()"), present.index('self.window.attributes("-alpha", 1.0)'))
        self.assertIn("self.window.update_idletasks()", present)

    def test_review_reasserts_foreground_after_loading_shield_is_removed(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        host = source.index("review_host_cover = WindowLoadingCover(")
        present = source.index("self.present_window_without_flash(", host)
        self.assertLess(host, present)
        self.assertIn("maximize=True", source[present:])
        reveal = source.split("def review_is_in_front() -> None:", 1)[1]
        self.assertIn("foreground_checks", reveal)
        self.assertIn("self.window_is_foreground(dialog)", reveal)
        self.assertLess(reveal.index("self.activate_window_above_owner(dialog, self.root)"), reveal.index("review_host_cover.destroy()"))
        self.assertIn("retries_ms=(0, 45, 140)", reveal)


    def test_ctk_delayed_deiconify_is_guarded_until_intentional_present(self) -> None:
        install = inspect.getsource(gui.ShowerProgrammerApp.install_first_map_guard)
        release = inspect.getsource(gui.ShowerProgrammerApp.release_first_map_guard)
        self.assertIn("_shower_first_map_allowed", install)
        self.assertIn("guarded_deiconify", install)
        self.assertIn("return None", install)
        self.assertIn("window.deiconify = original_deiconify", release)

    def test_modal_grab_is_deferred_until_window_is_viewable(self) -> None:
        presenter = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        manual = inspect.getsource(gui.ShowerProgrammerApp.open_manual_program_dialog)
        self.assertIn("_shower_grab_on_present", presenter)
        self.assertIn("window.grab_set()", presenter)
        self.assertIn('setattr(dialog, "_shower_grab_on_present", True)', manual)
        self.assertNotIn("dialog.grab_set()", manual)

    def test_version_166_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_66_FLASH_FREE_WINDOW_MAPPING"
        self.assertGreaterEqual(version["version_number"], 166)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "withdraw_before_first_map",
            "transparent_painted_window_reveal",
            "review_foreground_reassertion",
            "global_flash_free_child_presentation",
            "ctk_first_map_guard",
            "version_1_66_flash_free_window_mapping",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
