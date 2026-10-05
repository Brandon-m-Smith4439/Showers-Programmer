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
import shower_v4_features


class NativeWindowOwnershipTests(unittest.TestCase):
    def test_shared_child_shell_avoids_ctk_toplevel(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.create_hidden_toplevel)
        shell = inspect.getsource(gui.FlashFreeToplevel)
        self.assertIn("FlashFreeToplevel(owner, background=self.APP_BG)", source)
        self.assertNotIn("ctk.CTkToplevel(", source)
        self.assertIn("super().__init__(master, background=background)", shell)
        self.assertIn("self.withdraw()", shell)
        self.assertIn('self.attributes("-alpha", 0.0)', shell)
        self.assertIn('kwargs["background"] = kwargs.pop("fg_color")', shell)

    def test_owner_contract_uses_tk_transient_without_win32_reparent(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        owner_source = inspect.getsource(gui.ShowerProgrammerApp.bind_native_window_owner)
        self.assertIn("self.bind_native_window_owner(window, transient_owner)", source)
        self.assertIn("window.transient(owner_window)", owner_source)
        self.assertNotIn("GWLP_HWNDPARENT", owner_source)
        self.assertNotIn("SetWindowLongPtr", owner_source)
        self.assertIn("self.stabilize_window_foreground(window, transient_owner)", source)


    def test_review_native_maximize_happens_only_after_workspace_is_built(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        start = source.index("dialog = self.create_hidden_toplevel(self.root)")
        cover = source.index("review_cover = WindowLoadingCover(", start)
        first_ctk = source.index("header = ctk.CTkFrame(review_content", cover)
        present = source.index("self.present_window_without_flash(", first_ctk)
        self.assertIn("self.prime_hidden_maximized_geometry(dialog, self.root)", source[start:cover])
        self.assertLess(cover, first_ctk)
        self.assertLess(first_ctk, present)
        self.assertIn("maximize=True", source[present:])


    def test_review_foreground_is_stabilized_after_loading_shield_teardown(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        reveal = source.split("def review_is_in_front() -> None:", 1)[1]
        self.assertIn("review_host_cover.destroy()", reveal)
        self.assertIn("foreground_checks", reveal)
        self.assertIn("self.window_is_foreground(dialog)", reveal)
        self.assertIn("retries_ms=(0, 45, 140)", reveal)


    def test_root_stays_withdrawn_until_startup_shield_exists(self) -> None:
        source = inspect.getsource(gui.main)
        guard = source.index("ShowerProgrammerApp.install_first_map_guard(root)")
        withdraw = source.index("root.withdraw()", guard)
        shield = source.index("startup_shield = StartupShield(")
        self.assertLess(guard, withdraw)
        self.assertLess(withdraw, shield)
        before_shield = source[:shield]
        self.assertNotIn("ShowerProgrammerApp.maximize_window(root)", before_shield)

    def test_windows_caption_is_themed_while_window_is_still_transparent(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        mapping = source.split("def map_finished_surface() -> None:", 1)[1].split("def settle_pass", 1)[0]
        self.assertIn("self.apply_native_window_chrome(window)", mapping)
        self.assertIn("mapped_paint_pass()", mapping)
        visible = source.split("def finish_visible() -> None:", 1)[1].split("def mapped_paint_pass", 1)[0]
        self.assertIn('window.attributes("-alpha", 1.0)', visible)
        chrome = inspect.getsource(gui.ShowerProgrammerApp.apply_native_window_chrome)
        self.assertIn("DwmSetWindowAttribute", chrome)
        self.assertIn("DWMWA_CAPTION_COLOR", chrome)
        self.assertIn("DWMWA_TEXT_COLOR", chrome)


    def test_context_menus_tooltips_and_conflict_dialogs_use_shared_hidden_shells(self) -> None:
        context = inspect.getsource(gui.ShowerProgrammerApp.show_themed_context_menu)
        tooltip = inspect.getsource(gui.ShowerProgrammerApp.attach_tooltip)
        conflict = inspect.getsource(shower_v4_features.show_send_conflict_dialog)
        self.assertIn("self.create_hidden_toplevel(popup_owner)", context)
        self.assertIn("self.create_hidden_native_toplevel(tooltip_owner", tooltip)
        self.assertIn("app.create_hidden_toplevel(parent)", conflict)
        self.assertNotIn("ctk.CTkToplevel(parent)", conflict)

    def test_existing_page_activation_uses_native_owner_not_topmost_focus_force_loop(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.bring_page_window_to_front)
        self.assertIn("if page_owner is not self.root", source)
        self.assertIn("self.bind_native_window_owner(window, page_owner)", source)
        self.assertIn("self.root if window is self.root else self.resolve_popup_owner", source)
        self.assertIn("self.another_modal_owns_input(window)", source)
        self.assertIn("self.stabilize_window_foreground", source)
        self.assertNotIn('attributes("-topmost", True)', source)
        self.assertNotIn("focus_force", source)

    def test_version_167_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_67_NATIVE_WINDOW_OWNERSHIP"
        self.assertGreaterEqual(version["version_number"], 167)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "native_owned_child_windows",
            "flash_free_native_toplevel_shell",
            "unmapped_maximized_layout",
            "dwm_prethemed_window_chrome",
            "withdrawn_root_bootstrap",
            "review_native_owner_foreground",
            "version_1_67_native_window_ownership",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
