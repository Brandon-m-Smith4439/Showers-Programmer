from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_configuration


class Version122ConfigurationWorkspaceTests(unittest.TestCase):
    @staticmethod
    def sample_config() -> dict:
        return {
            "_notes": {"rules": "not editable"},
            "pdf": {
                "_notes": {"indicator_size": "Marker size."},
                "label_font_size": 21,
                "label_color_rgb": [0, 120, 212],
                "label_position": {"x_ratio": 0.5, "default_y_ratio": 0.5},
                "indicator_size": 18,
                "waterjet_indicator_size": 30,
                "waterjet_indicator_line_width": 8,
                "waterjet_indicator_length_ratio": 2.5,
                "hinge_side_band_ratio": 0.28,
                "hinge_side_min_delta": 8,
                "remake": {"font_size": 55},
            },
            "dxf": {
                "waterjet_output_scale": 25.4,
                "waterjet_insunits": 4,
                "waterjet_measurement": 1,
                "default_output_scale": 1,
                "default_insunits": 1,
                "default_measurement": 0,
            },
            "rules": {
                "denver_min_inches": 6.125,
                "waterjet_fit_limit_inches": 75,
                "waterjet_fp_min_count": 6,
                "auto_angle_direction": 1,
                "auto_dxf_angle_min_degrees": 0.02,
                "auto_dxf_angle_max_degrees": 1.0,
                "auto_dxf_fps_cut_min_segment_ratio": 0.12,
                "auto_dxf_fps_cut_min_coverage_ratio": 0.45,
                "hinge_label_keywords": ["PPH", "GEN037"],
                "hinge_label_orientations": {"PPH": "up", "GEN037": "down"},
                "waterjet_tall_rotation_by_indicator": {
                    "top_left": 90,
                    "bottom_left": 90,
                    "top_right": -90,
                    "bottom_right": -90,
                },
                "waterjet_keywords": ["NOTCH", "RADIUS"],
                "mirror_keywords": ["MIRROR"],
            },
            "item_overrides": {},
            "future_section": {"new_setting": "preserved"},
        }

    def test_every_non_note_setting_is_exposed_and_unknown_settings_survive(self) -> None:
        fields = shower_configuration.configuration_fields(self.sample_config())
        paths = {field.path for field in fields}
        self.assertIn("pdf.indicator_size", paths)
        self.assertIn("rules.hinge_label_orientations", paths)
        self.assertIn("item_overrides", paths)
        self.assertIn("future_section.new_setting", paths)
        self.assertFalse(any("_notes" in path for path in paths))

    def test_fields_are_grouped_into_operator_friendly_sections(self) -> None:
        fields = {field.path: field for field in shower_configuration.configuration_fields(self.sample_config())}
        self.assertEqual(fields["pdf.indicator_size"].section, "Indicators")
        self.assertEqual(fields["dxf.waterjet_output_scale"].section, "DXF Output")
        self.assertEqual(fields["rules.waterjet_keywords"].section, "Detection Rules")
        self.assertEqual(fields["rules.denver_min_inches"].section, "Machine Routing")
        self.assertEqual(fields["rules.auto_dxf_angle_min_degrees"].section, "Orientation & Geometry")
        self.assertEqual(fields["pdf.remake.font_size"].section, "REMAKE & Overrides")
        self.assertEqual(fields["future_section.new_setting"].section, "Advanced")

    def test_editor_coercion_handles_numbers_lists_booleans_and_json_maps(self) -> None:
        value, issue = shower_configuration.parse_editor_value("6.25", 6.125)
        self.assertEqual(value, 6.25)
        self.assertIsNone(issue)
        value, issue = shower_configuration.parse_editor_value("PPH\nGEN037", ["PPH"])
        self.assertEqual(value, ["PPH", "GEN037"])
        self.assertIsNone(issue)
        value, issue = shower_configuration.parse_editor_value("false", True)
        self.assertFalse(value)
        self.assertIsNone(issue)
        value, issue = shower_configuration.parse_editor_value('{"PPH": "up"}', {"PPH": "down"})
        self.assertEqual(value, {"PPH": "up"})
        self.assertIsNone(issue)

    def test_failed_type_coercion_is_advisory_and_preserves_operator_text(self) -> None:
        value, issue = shower_configuration.parse_editor_value("shop decision", 6.125)
        self.assertEqual(value, "shop decision")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.severity, "ERROR")

    def test_validation_reports_bad_values_without_mutating_them(self) -> None:
        config = self.sample_config()
        config["rules"]["denver_min_inches"] = -1
        config["pdf"]["label_color_rgb"] = [0, 400, 0]
        before = json.dumps(config, sort_keys=True)
        issues = shower_configuration.validate_configuration(config)
        self.assertTrue(any(issue.path == "rules.denver_min_inches" for issue in issues))
        self.assertTrue(any(issue.path == "pdf.label_color_rgb" for issue in issues))
        self.assertEqual(json.dumps(config, sort_keys=True), before)

    def test_invalid_configuration_can_still_be_saved_exactly_as_requested(self) -> None:
        config = self.sample_config()
        config["rules"]["denver_min_inches"] = "intentional override"
        self.assertTrue(shower_configuration.validate_configuration(config))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "shower_programmer_config.json"
            shower_configuration.atomic_write_configuration(target, config)
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["rules"]["denver_min_inches"], "intentional override")

    def test_presave_backup_is_created_and_original_bytes_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "shower_programmer_config.json"
            original = b'{"rules":{"denver_min_inches":6.125}}\n'
            target.write_bytes(original)
            backup_dir = Path(raw) / "Output" / "Configuration Backups"
            backup = shower_configuration.backup_configuration(target, backup_dir=backup_dir)
            self.assertIsNotNone(backup)
            self.assertEqual(Path(backup).parent, backup_dir)
            self.assertEqual(Path(backup).read_bytes(), original)

    def test_gui_and_rebuild_script_expose_configuration_workspace(self) -> None:
        gui_source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        rebuild = (PROJECT_ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        required_flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        feature_source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn('"Configuration": lambda: self.build_configuration_settings_tab', gui_source)
        self.assertIn("Save these values anyway?", gui_source)
        self.assertIn("shower_configuration.validate_configuration", gui_source)
        self.assertIn("SOURCE_CONFIGURATION=Backend\\shower_configuration.py", rebuild)
        self.assertIn("SOURCE_REQUIRED_FLAGS=Backend\\release_required_flags.txt", rebuild)
        self.assertNotIn("%REQUIRED_FLAGS%", rebuild)
        self.assertIn("version_1_22_configuration_workspace", required_flags)
        self.assertIn("version_1_22_configuration_workspace", feature_source)

    def test_rebuild_flag_manifest_is_unique_and_cmd_safe(self) -> None:
        rebuild = (PROJECT_ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        manifest_lines = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8").splitlines()
        flags = [
            flag.strip()
            for line in manifest_lines
            if line.strip() and not line.lstrip().startswith("#")
            for flag in line.split(",")
            if flag.strip()
        ]
        self.assertEqual(len(flags), len(set(flags)))
        self.assertGreater(len(flags), 200)
        self.assertNotIn('set "REQUIRED_FLAGS=', rebuild)
        self.assertLess(max(map(len, rebuild.splitlines())), 8191)


if __name__ == "__main__":
    unittest.main()
