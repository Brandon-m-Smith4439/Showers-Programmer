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


class MirrorSectionCheckPolishTests(unittest.TestCase):
    def test_mirror_dividers_use_viewport_spanning_half_height_overlay(self) -> None:
        cls = gui.ShowerProgrammerApp
        self.assertEqual(cls.ORDER_TREE_ROW_HEIGHT, 38)
        self.assertEqual(cls.MIRROR_SECTION_BAND_HEIGHT, 19)
        source = inspect.getsource(cls.refresh_mirror_section_overlays)
        self.assertIn("self.tree.winfo_width()", source)
        self.assertIn("label.place(x=2", source)
        self.assertIn("width=max(1, tree_width - 4)", source)
        self.assertIn("band_height", source)
        self.assertNotIn('self.ORDER_TREE_INDEX["order"]', source)

    def test_mirror_divider_text_is_not_stored_in_a_tree_column(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.insert_mirror_section_dividers)
        self.assertIn('values=tuple("" for _column in self.ORDER_TREE_COLUMNS)', source)
        self.assertIn("self.ensure_mirror_section_overlay(row_id, category)", source)
        self.assertNotIn("self.mirror_section_label(category) if column == \"order\"", source)
        self.assertTrue(hasattr(gui.ShowerProgrammerApp, "MIRROR_SECTION_BAND_HEIGHT"))

    def test_mirror_bands_use_offset_header_palette_and_category_text_colors(self) -> None:
        palette = inspect.getsource(gui.ShowerProgrammerApp.apply_ui_mode_palette)
        self.assertIn('self.MIRROR_SECTION_BG = "#2b3a50"', palette)
        self.assertIn('self.MIRROR_SECTION_BG = "#e7eef8"', palette)
        ensure = inspect.getsource(gui.ShowerProgrammerApp.ensure_mirror_section_overlay)
        self.assertIn("bg=self.MIRROR_SECTION_BG", ensure)
        self.assertIn('self.WARNING if category == "Mirror - With Fabrication" else self.ACCENT_DARK', ensure)

    def test_order_check_indicator_is_font_stable_and_unambiguous(self) -> None:
        self.assertEqual(gui.ShowerProgrammerApp.order_tree_check_text("Order checked"), "[✓]")
        self.assertEqual(gui.ShowerProgrammerApp.order_tree_check_text(""), "[ ]")
        self.assertTrue(gui.ShowerProgrammerApp.order_tree_value_is_checked("[✓]"))
        self.assertFalse(gui.ShowerProgrammerApp.order_tree_value_is_checked("[ ]"))
        self.assertEqual(gui.ShowerProgrammerApp.ORDER_TREE_DISPLAY_COLUMNS[0], "review")

    def test_version_184_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 184)
        self.assertIn("VERSION_1_84_MIRROR_SECTION_CHECK_POLISH", (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "spanning_mirror_section_bands",
            "half_height_mirror_section_bands",
            "clear_order_checkboxes",
            "version_1_84_mirror_section_check_polish",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
