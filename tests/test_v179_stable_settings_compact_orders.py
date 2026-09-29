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


class StableSettingsCompactOrdersTests(unittest.TestCase):
    def test_settings_tabs_build_inside_hosts_below_persistent_covers(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn("tab_content_hosts: dict[str, ctk.CTkFrame]", source)
        self.assertIn('host = ctk.CTkFrame(tab_parent, fg_color="transparent", corner_radius=0)', source)
        self.assertIn('WindowLoadingCover(\n                parent,', source)
        self.assertIn('self.build_configuration_settings_tab(tab_content_hosts["Configuration"], dialog)', source)
        self.assertIn('async_initial_tabs = {"System Health", "Archives", "Action History"}', source)

    def test_configuration_sections_build_inside_hosts_under_local_cover(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_configuration_settings_tab)
        self.assertIn("configuration_tab_hosts: dict[str, ctk.CTkFrame]", source)
        self.assertIn("tab = configuration_tab_hosts[section]", source)
        self.assertIn("self.build_hinge_settings_tab(configuration_tab_hosts[hinge_tab_name], dialog)", source)
        self.assertIn("cover.lift()", source)
        self.assertIn("dialog.after_idle(cover.lift)", source)

    def test_orders_keep_compact_checked_control_and_issues_column(self) -> None:
        display = gui.ShowerProgrammerApp.ORDER_TREE_DISPLAY_COLUMNS
        self.assertIn("review", display)
        self.assertIn("order", display)
        self.assertIn("issues", display)
        self.assertIn(gui.ShowerProgrammerApp.order_tree_check_text("Order checked"), {"☑", "✓", "[✓]"})
        self.assertIn(gui.ShowerProgrammerApp.order_tree_check_text(""), {"☐", "□", "[ ]"})

        source = inspect.getsource(gui.ShowerProgrammerApp.build_ui)
        self.assertIn('self.tree.bind("<Button-1>", self.toggle_order_checked_from_tree_checkbox', source)
        self.assertIn('"issues": 350', source)

    def test_header_grips_and_padding_are_compact(self) -> None:
        self.assertEqual(gui.ShowerProgrammerApp.order_tree_heading_text("Status"), "⋮Status⋮")
        source = inspect.getsource(gui.ShowerProgrammerApp.configure_styles)
        self.assertIn('"Orders.Treeview.Heading"', source)
        self.assertRegex(source, r"padding=\((?:0|2), 10\)")

    def test_version_179_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 179)
        self.assertIn("VERSION_1_79_STABLE_SETTINGS_COMPACT_ORDERS", (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_79_STABLE_SETTINGS_COMPACT_ORDERS", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "stable_settings_overlay_hosts",
            "stable_configuration_overlay_hosts",
            "compact_orders_columns",
            "direct_order_check_gutter",
            "early_issues_column",
            "compact_header_grips",
            "version_1_79_stable_settings_compact_orders",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
