from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_configuration
import shower_programmer_gui as gui


class ConfigurationOrdersPolishTests(unittest.TestCase):
    def test_compact_popups_use_atomic_reveal_and_borderless_cards(self) -> None:
        presenter = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        message_box = inspect.getsource(gui._ProgramMessageBox._show)
        confirmation = inspect.getsource(gui.ShowerProgrammerApp.ask_themed_confirmation)
        notice = inspect.getsource(gui.ShowerProgrammerApp.show_themed_notice)
        text_prompt = inspect.getsource(gui.ShowerProgrammerApp.ask_themed_text)

        self.assertIn("atomic_reveal: bool | None = None", presenter)
        self.assertIn("use_atomic_reveal", presenter)
        self.assertIn('window.attributes("-alpha", 1.0)', presenter)
        for source in (message_box, confirmation, notice, text_prompt):
            self.assertIn("overrideredirect(True)", source)

    def test_configuration_internal_tabs_build_lazily_under_local_cover(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_configuration_settings_tab)
        self.assertIn("configuration_tab_covers: dict[str, WindowLoadingCover]", source)
        self.assertIn("WindowLoadingCover(\n                inner.tab(name)", source)
        self.assertIn("stop = min(index + 3, len(section_fields))", source)
        self.assertIn("if selected != section:", source)
        self.assertIn("dialog.after(1, build_next_batch)", source)
        self.assertIn("query = search_var.get().strip().casefold()", source)
        self.assertIn("card.grid_remove()", source)

    def test_deprecated_configuration_values_are_removed_from_release_defaults(self) -> None:
        shipped = json.loads((BACKEND / "shower_programmer_config.json").read_text(encoding="utf-8"))
        self.assertEqual(shower_configuration.default_configuration(), shipped)
        self.assertEqual(shower_configuration.validate_configuration(shipped), [])

        legacy = copy.deepcopy(shipped)
        legacy.setdefault("pdf", {})["label_x_ratio"] = 0.25
        legacy["pdf"]["label_y_ratio"] = 0.75
        legacy["pdf"]["diamon_fusion_min_font_size"] = 20
        legacy["pdf"]["diamon_fusion_y_ratio"] = 0.9
        legacy.setdefault("rules", {})["auto_angle_direction"] = "clockwise"
        visible_paths = {field.path for field in shower_configuration.configuration_fields(legacy)}
        for path in shower_configuration.DEPRECATED_CONFIGURATION_PATHS:
            self.assertNotIn(path, visible_paths)
            self.assertIsNone(shower_configuration.get_path(shower_configuration.prune_deprecated_configuration(legacy), path))

    def test_reset_to_defaults_is_backed_up_and_immutable(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_configuration_settings_tab)
        self.assertIn('text="Reset to Defaults"', source)
        self.assertIn("shower_configuration.default_configuration()", source)
        self.assertIn("shower_configuration.backup_configuration", source)
        self.assertIn("shower_configuration.atomic_write_configuration", source)

        first = shower_configuration.default_configuration()
        first["rules"]["denver_min_inches"] = 999
        second = shower_configuration.default_configuration()
        self.assertNotEqual(first["rules"]["denver_min_inches"], second["rules"]["denver_min_inches"])
        self.assertEqual(second["rules"]["denver_min_inches"], 6.125)

    def test_orders_grid_is_horizontally_scrollable_and_batch_metadata_moves_to_items(self) -> None:
        build_source = inspect.getsource(gui.ShowerProgrammerApp.build_ui)
        install_source = inspect.getsource(gui.ShowerProgrammerApp.install_process_batches)
        self.assertIn("orient=tk.HORIZONTAL, command=self.tree.xview", build_source)
        self.assertIn('self.tree.bind("<Shift-MouseWheel>"', build_source)
        self.assertIn("stretch=False", build_source)
        self.assertIn('summary if column == "items"', install_source)

        batch = {
            "name": "Batch 7000.xls",
            "orders": [object(), object()],
            "mirror_categories": {
                "Mirror - With Fabrication": ["900001"],
                "Mirror - Without Fabrication": ["900002"],
            },
        }
        self.assertEqual(gui.ShowerProgrammerApp.batch_tree_label(batch), "Batch 7000.xls")
        summary = gui.ShowerProgrammerApp.batch_tree_summary(batch)
        self.assertEqual(summary, "2 orders")
        self.assertEqual(
            gui.ShowerProgrammerApp.mirror_section_label("Mirror - With Fabrication"),
            "MIRROR • WITH FABRICATION",
        )
        self.assertEqual(
            gui.ShowerProgrammerApp.mirror_section_label("Mirror - Without Fabrication"),
            "MIRROR • WITHOUT FABRICATION",
        )

    def test_version_178_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 178)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_78_CONFIGURATION_ORDERS_POLISH", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "atomic_popup_reveal",
            "modern_borderless_compact_prompts",
            "lazy_configuration_inner_tabs",
            "switchable_configuration_section_loading",
            "curated_active_configuration",
            "canonical_configuration_defaults",
            "reset_configuration_defaults",
            "horizontal_orders_grid",
            "batch_metadata_items_column",
            "version_1_78_configuration_orders_polish",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
