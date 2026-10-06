from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
import shower_programmer as programmer
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class Tree:
    def __init__(self):
        self.widths = {name: 160 for name in gui.ShowerProgrammerApp.ORDER_TREE_COLUMNS}

    def column(self, name, option=None, **values):
        if values:
            self.widths[name] = values["width"]
        if option == "width":
            return self.widths[name]
        return 38 if option == "minwidth" else {"width": self.widths[name], "minwidth": 38}


class Canvas:
    def __init__(self):
        self.text = []

    def delete(self, *_args):
        self.text.clear()

    def winfo_width(self):
        return 560

    def winfo_height(self):
        return 500

    def create_rectangle(self, *_args, **_kwargs):
        pass

    def create_text(self, *_args, **kwargs):
        self.text.append(kwargs.get("text", ""))


class ReviewWorkflowTests(unittest.TestCase):
    def test_size_locked_preview_never_reads_or_draws_dxf(self):
        app = object.__new__(gui.ShowerProgrammerApp)
        for name in ("PREVIEW_CARD_BG", "TEXT", "MUTED", "ACCENT_DARK", "DANGER"):
            setattr(app, name, "#123456")
        canvas = Canvas()
        panel = programmer.Panel(1, 1, "Mirror", 118, 76, machine="WJ", waterjet_size_blocked=True)
        with mock.patch.object(app, "order_review_dxf_preview_data", side_effect=AssertionError("locked DXF read")):
            app.draw_order_review_dxf(canvas, Path("missing.dxf"), panel)
        self.assertTrue(any("bypass" in text.lower() for text in canvas.text), canvas.text)
        self.assertFalse(any("No DXF" in text for text in canvas.text))

    def test_size_lock_is_per_piece_not_global(self):
        app = gui.ShowerProgrammerApp
        self.assertTrue(app.review_dxf_size_locked(programmer.Panel(1, 1, "", 118, 76, machine="WJ", waterjet_size_blocked=True)))
        self.assertFalse(app.review_dxf_size_locked(programmer.Panel(2, 2, "", 30, 80, machine="WJ")))
        self.assertFalse(app.review_dxf_size_locked(programmer.Panel(3, 3, "", 30, 80, machine="DENVER 2")))

    def test_release_wrapper_preserves_machine_and_locked_gate(self):
        import shower_batch
        import shower_v4_features as v4
        v4.install(programmer, shower_batch, gui)
        app = object.__new__(gui.ShowerProgrammerApp)
        for name in ("PREVIEW_CARD_BG", "TEXT", "MUTED", "ACCENT_DARK", "DANGER"):
            setattr(app, name, "#123456")
        panel = programmer.Panel(1, 1, "Mirror", 118, 76, machine="WJ", waterjet_size_blocked=True)
        canvas = Canvas()
        with mock.patch.object(app, "order_review_dxf_preview_data", side_effect=AssertionError("locked DXF read")):
            app.draw_order_review_dxf(canvas, Path("missing.dxf"), panel, {})
        self.assertTrue(any("DXF LOCKED" in text for text in canvas.text))
        self.assertEqual(panel.machine, "WJ")

    def test_column_widths_round_trip_and_theme_save_preserves_other_preferences(self):
        with workspace_temporary_directory(prefix="columns") as raw:
            path = Path(raw) / "ui.json"
            app = object.__new__(gui.ShowerProgrammerApp)
            app.ui_settings = {"future_preference": "keep"}
            app.dark_mode_var = SimpleNamespace(get=lambda: True)
            app.tree = Tree()
            app.tree.widths.update(job=274, issues=431)
            with mock.patch.object(app, "preferred_ui_settings_path", return_value=path):
                app.save_ui_settings()
                saved = json.loads(path.read_text())
                self.assertEqual(saved["orders_column_widths"]["job"], 274)
                self.assertEqual(saved["future_preference"], "keep")
                app.ui_settings = app.load_ui_settings()
                app.tree = Tree()
                app.restore_orders_column_widths()
                self.assertEqual(app.tree.widths["job"], 274)
                self.assertEqual(app.tree.widths["issues"], 431)

    def test_invalid_saved_widths_do_not_break_table_or_restore_unknown_columns(self):
        app = object.__new__(gui.ShowerProgrammerApp)
        app.tree = Tree()
        app.ui_settings = {"orders_column_widths": {"job": -100, "issues": "oops", "bogus": 500, "customer": 242}}
        app.restore_orders_column_widths()
        self.assertEqual(app.tree.widths["job"], 160)
        self.assertEqual(app.tree.widths["issues"], 160)
        self.assertNotIn("bogus", app.tree.widths)
        self.assertEqual(app.tree.widths["customer"], 242)

    def test_proposed_geometry_and_radius_centers_rotate_together_without_changing_units_or_cache(self):
        data = {"segments": [((0., 0.), (80., 0.)), ((80., 0.), (80., 30.))],
                "internal_radius_samples": [(78., 2., 0.375)], "internal_radii": [0.375],
                "unit_label": "mm", "inches_per_unit": 1 / 25.4}
        original = copy.deepcopy(data)
        rotated = gui.ShowerProgrammerApp.rotate_dxf_reference_data(data, 90)
        self.assertAlmostEqual(rotated["segments"][0][1][0], 0)
        self.assertAlmostEqual(rotated["segments"][0][1][1], 80)
        self.assertAlmostEqual(rotated["internal_radius_samples"][0][0], -2)
        self.assertAlmostEqual(rotated["internal_radius_samples"][0][1], 78)
        self.assertEqual(rotated["internal_radius_samples"][0][2], .375)
        self.assertEqual(rotated["inches_per_unit"], 1 / 25.4)
        self.assertEqual(data, original)

    def test_proposed_indicator_uses_existing_programming_rules_without_mutating_panel(self):
        panel = programmer.Panel(1, 1, "Panel", machine="DENVER 2", width=86, height=53,
                                 indicator_corner="bottom_right", rotation_degrees=0)
        config = {"rules": {"auto_dxf_angle_correction": False}}
        proposed = gui.ShowerProgrammerApp.dxf_reference_panel_for_position(panel, {"raw_indicator_corner": "top_left"}, config)
        self.assertEqual(proposed.rotation_degrees, 180)
        self.assertEqual(panel.rotation_degrees, 0)
        self.assertEqual(panel.indicator_corner, "bottom_right")

    def test_multiple_issues_are_counted_numbered_and_deduplicated(self):
        summary = gui.ShowerProgrammerApp.issue_summary(["P1: missing source DXF", "P1: missing source DXF", "Sketch paper size: too small", "P2: manual review", "Missing process list"])
        self.assertIn("4 issues", summary)
        self.assertIn("[1]", summary)
        self.assertIn("[2]", summary)
        self.assertIn("+1 more", summary)
        self.assertEqual(gui.ShowerProgrammerApp.issue_summary(["P1: missing source DXF"]), "P1: missing DXF")

    def test_pending_reference_uses_edited_output_and_verified_rotation_without_writing_files(self):
        with workspace_temporary_directory(prefix="reference") as raw:
            root = Path(raw)
            source, output = root / "source.dxf", root / "90000101.dxf"
            source.write_bytes(b"source")
            output.write_bytes(b"operator edited cutouts")
            history = programmer.shower_dxf_history.history_dir(output) / "state.json"
            history.parent.mkdir(parents=True)
            history.write_text(json.dumps({"schema": 1, "output_name": output.name, "rotation": 90}))
            panel = programmer.Panel(1, 1, "Panel", 86, 53, machine="DENVER 2", rotation_degrees=90,
                                     source_dxf=source, output_dxf=output)
            data = {"segments": [((0., 0.), (80., 0.))], "internal_radius_samples": [(78., 2., .375)]}
            state = {"positions": {(1, "indicator"): {"raw_indicator_corner": "top_left"}},
                     "dxf_reference_config": {"rules": {"auto_dxf_angle_correction": False}}}
            app = object.__new__(gui.ShowerProgrammerApp)
            preview, proposed, note = app.dxf_reference_view(output, panel, data, state)
            self.assertEqual(proposed.rotation_degrees, 180)
            self.assertAlmostEqual(preview["segments"][0][1][0], 0)
            self.assertAlmostEqual(preview["segments"][0][1][1], 80)
            self.assertIn("PENDING", note)
            self.assertEqual(output.read_bytes(), b"operator edited cutouts")
            self.assertEqual(source.read_bytes(), b"source")

    def test_unknown_legacy_orientation_keeps_actual_output_unchanged(self):
        with workspace_temporary_directory(prefix="reference") as raw:
            root = Path(raw)
            source, output = root / "source.dxf", root / "90000101.dxf"
            panel = programmer.Panel(1, 1, "Panel", 86, 53, machine="DENVER 2", rotation_degrees=90,
                                     source_dxf=source, output_dxf=output)
            data = {"segments": [((0., 0.), (80., 0.))], "internal_radius_samples": []}
            state = {"positions": {(1, "indicator"): {"raw_indicator_corner": "top_left"}},
                     "dxf_reference_config": {"rules": {"auto_dxf_angle_correction": False}}}
            app = object.__new__(gui.ShowerProgrammerApp)
            preview, proposed, note = app.dxf_reference_view(output, panel, data, state)
            self.assertIs(preview, data)
            self.assertEqual(proposed.rotation_degrees, 90)
            self.assertIn("no verified rotation history", note)


if __name__ == "__main__":
    unittest.main()
