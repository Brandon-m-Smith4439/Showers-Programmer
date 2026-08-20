#!/usr/bin/env python3
"""Configuration editing, grouping, coercion, and validation for Shower Programmer.

The GUI intentionally treats validation as advisory: operators may save a value
that fails validation after acknowledging the warning.  This module therefore
never mutates or silently repairs a configuration while validating it.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ConfigurationIssue:
    severity: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class ConfigurationField:
    path: str
    section: str
    label: str
    description: str
    value: Any
    value_type: str


SECTION_ORDER = (
    "Labels & PDF",
    "Indicators",
    "DXF Output",
    "Machine Routing",
    "Detection Rules",
    "Orientation & Geometry",
    "REMAKE & Overrides",
    "Advanced",
)

# Dicts in this set are edited as a complete JSON object rather than recursively
# expanded.  They are intentionally dynamic maps whose keys are themselves shop
# configuration (hinge codes, indicator corners, or exact order overrides).
OPAQUE_DICT_PATHS = {
    "rules.hinge_label_orientations",
    "rules.waterjet_tall_rotation_by_indicator",
    "item_overrides",
}


_FIELD_LABELS = {
    "pdf.label_x_ratio": "Legacy label X ratio",
    "pdf.label_y_ratio": "Legacy label Y ratio",
    "pdf.label_font_size": "Order label font size",
    "pdf.label_color_rgb": "Label / marker RGB",
    "pdf.diamon_fusion_font_size": "DIAMON FUSION font size",
    "pdf.diamon_fusion_min_font_size": "DIAMON FUSION minimum font size",
    "pdf.diamon_fusion_edge_gap": "DIAMON FUSION edge gap",
    "pdf.diamon_fusion_y_ratio": "DIAMON FUSION legacy Y control",
    "pdf.diamon_fusion_above_remake_gap": "Gap above REMAKE",
    "pdf.indicator_size": "Denver indicator size",
    "pdf.waterjet_indicator_size": "Water Jet indicator size",
    "pdf.waterjet_indicator_line_width": "Water Jet line width",
    "pdf.waterjet_indicator_length_ratio": "Water Jet marker length ratio",
    "pdf.indicator_offset": "Indicator edge offset",
    "pdf.hinge_side_band_ratio": "Hinge-side detection band",
    "pdf.hinge_side_min_delta": "Hinge-side confidence delta",
    "pdf.avoid_corner_text_with_indicator": "Avoid source text with indicators",
    "pdf.corner_text_avoidance_max_shift": "Maximum text-avoidance shift",
    "dxf.waterjet_output_scale": "Water Jet output scale",
    "dxf.waterjet_insunits": "Water Jet INSUNITS",
    "dxf.waterjet_measurement": "Water Jet MEASUREMENT",
    "dxf.default_output_scale": "Denver/default output scale",
    "dxf.default_insunits": "Denver/default INSUNITS",
    "dxf.default_measurement": "Denver/default MEASUREMENT",
    "rules.denver_min_inches": "Denver minimum edge",
    "rules.waterjet_fit_limit_inches": "Water Jet fit limit",
    "rules.waterjet_fp_min_count": "Plain FP labels required for WJ",
    "rules.auto_angle_correction": "Enable automatic angle correction",
    "rules.auto_angle_direction": "Automatic angle direction",
    "rules.auto_dxf_angle_correction": "Use DXF angle correction",
    "rules.auto_dxf_angle_min_degrees": "Minimum DXF correction",
    "rules.auto_dxf_angle_max_degrees": "Maximum DXF correction",
    "rules.auto_dxf_hinge_side_detection": "Use DXF hinge-side detection",
    "rules.auto_dxf_fps_cut_min_segment_ratio": "FP-S minimum cut segment ratio",
    "rules.auto_dxf_fps_cut_min_coverage_ratio": "FP-S minimum side coverage",
    "rules.waterjet_tall_rotation_by_indicator": "Tall WJ rotation by marker",
    "rules.hinge_label_orientations": "Hinge-code default orientations",
    "item_overrides": "Exact order overrides",
}


_FIELD_DESCRIPTIONS = {
    "rules.denver_min_inches": "If any required glass edge is below this size, the piece cannot use Denver and routes to Water Jet.",
    "rules.waterjet_fit_limit_inches": "Maximum configured Water Jet envelope dimension used by fit/oversize checks.",
    "rules.auto_angle_direction": "Direction multiplier used by the legacy automatic angle-correction path. Usually 1 or -1.",
    "dxf.waterjet_output_scale": "Program-only scale applied to Water Jet DXFs. 25.4 converts inch geometry to millimeters.",
    "rules.hinge_label_orientations": "JSON map of configured hinge labels to their default 'up' or 'down' orientation.",
    "rules.waterjet_tall_rotation_by_indicator": "JSON map from marker corner to the rotation used for tall Water Jet pieces.",
    "item_overrides": "Advanced JSON map for exact one-off order corrections. Keep this empty unless an exact order needs a deliberate exception.",
}


def humanize_key(key: str) -> str:
    text = str(key or "").replace("_", " ").strip()
    if not text:
        return "Configuration"
    replacements = {"dxf": "DXF", "pdf": "PDF", "wj": "WJ", "rgb": "RGB", "fps": "FP-S", "insunits": "INSUNITS"}
    words = []
    for word in text.split():
        replacement = replacements.get(word.casefold())
        words.append(replacement if replacement else word.capitalize())
    return " ".join(words)


def value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    if value is None:
        return "null"
    return "string"


def section_for_path(path: str) -> str:
    lowered = path.casefold()
    if path == "item_overrides" or lowered.startswith("pdf.remake"):
        return "REMAKE & Overrides"
    if lowered.startswith("pdf.indicator") or lowered.startswith("pdf.waterjet_indicator") or lowered.startswith("pdf.hinge_side") or "corner_text" in lowered:
        return "Indicators"
    if lowered.startswith("pdf.indicator_nudge"):
        return "Indicators"
    if lowered.startswith("dxf."):
        return "DXF Output"
    if lowered.startswith("pdf."):
        return "Labels & PDF"
    if lowered.startswith("rules."):
        key = lowered.rsplit(".", 1)[-1]
        if "keyword" in key or "hinge_label" in key and "orientation" not in key:
            return "Detection Rules"
        if any(token in key for token in ("angle", "orientation", "rotation", "segment_ratio", "coverage_ratio", "hinge_side")):
            return "Orientation & Geometry"
        if any(token in key for token in ("denver", "waterjet", "mirror", "fit_limit")):
            return "Machine Routing"
        return "Detection Rules"
    return "Advanced"


def _description_for(config: dict[str, Any], path: str) -> str:
    if path in _FIELD_DESCRIPTIONS:
        return _FIELD_DESCRIPTIONS[path]
    parts = path.split(".")
    node: Any = config
    for index, part in enumerate(parts):
        if not isinstance(node, dict):
            break
        notes = node.get("_notes")
        if index == len(parts) - 1 and isinstance(notes, dict):
            note = notes.get(part)
            if isinstance(note, str) and note.strip():
                return note.strip()
        node = node.get(part)
    return "Editable application configuration value. Changes are validated when you save."


def configuration_fields(config: dict[str, Any]) -> list[ConfigurationField]:
    """Return every editable non-note configuration leaf in presentation order."""
    fields: list[ConfigurationField] = []

    def walk(node: Any, prefix: str) -> None:
        if prefix in OPAQUE_DICT_PATHS:
            fields.append(
                ConfigurationField(
                    path=prefix,
                    section=section_for_path(prefix),
                    label=_FIELD_LABELS.get(prefix, humanize_key(prefix.rsplit(".", 1)[-1])),
                    description=_description_for(config, prefix),
                    value=copy.deepcopy(node),
                    value_type=value_type(node),
                )
            )
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "_notes":
                    continue
                child = f"{prefix}.{key}" if prefix else str(key)
                walk(value, child)
            return
        if not prefix:
            return
        fields.append(
            ConfigurationField(
                path=prefix,
                section=section_for_path(prefix),
                label=_FIELD_LABELS.get(prefix, humanize_key(prefix.rsplit(".", 1)[-1])),
                description=_description_for(config, prefix),
                value=copy.deepcopy(node),
                value_type=value_type(node),
            )
        )

    walk(config, "")
    order = {name: index for index, name in enumerate(SECTION_ORDER)}
    fields.sort(key=lambda field: (order.get(field.section, 999), field.path.casefold()))
    return fields


def get_path(config: dict[str, Any], path: str, default: Any = None) -> Any:
    node: Any = config
    for part in str(path).split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_path(config: dict[str, Any], path: str, value: Any) -> None:
    parts = str(path).split(".")
    node: dict[str, Any] = config
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def format_editor_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return "\n".join(str(item) for item in value)
        return json.dumps(value, indent=2, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    if value is None:
        return "null"
    return str(value)


def _parse_scalar_token(token: str, template_items: list[Any]) -> Any:
    stripped = token.strip()
    if not template_items:
        return stripped
    sample = next((item for item in template_items if item is not None), "")
    if isinstance(sample, bool):
        lower = stripped.casefold()
        if lower in {"true", "yes", "1", "on"}:
            return True
        if lower in {"false", "no", "0", "off"}:
            return False
        raise ValueError(f"'{stripped}' is not a boolean")
    if isinstance(sample, int) and not isinstance(sample, bool):
        return int(stripped)
    if isinstance(sample, float):
        value = float(stripped)
        if not math.isfinite(value):
            raise ValueError("number must be finite")
        return value
    return stripped


def parse_editor_value(text: str, template: Any) -> tuple[Any, ConfigurationIssue | None]:
    """Coerce text using the existing value type; preserve raw text if coercion fails."""
    raw = str(text)
    try:
        if isinstance(template, bool):
            lower = raw.strip().casefold()
            if lower in {"true", "yes", "1", "on"}:
                return True, None
            if lower in {"false", "no", "0", "off"}:
                return False, None
            raise ValueError("expected true/false")
        if isinstance(template, int) and not isinstance(template, bool):
            return int(raw.strip()), None
        if isinstance(template, float):
            number = float(raw.strip())
            if not math.isfinite(number):
                raise ValueError("number must be finite")
            return number, None
        if isinstance(template, list):
            stripped = raw.strip()
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("expected a JSON list")
                return parsed, None
            tokens = [token.strip() for token in re.split(r"[\r\n,;]+", raw) if token.strip()]
            return [_parse_scalar_token(token, template) for token in tokens], None
        if isinstance(template, dict):
            parsed = json.loads(raw or "{}")
            if not isinstance(parsed, dict):
                raise ValueError("expected a JSON object")
            return parsed, None
        if template is None:
            stripped = raw.strip()
            if stripped.casefold() == "null":
                return None, None
            return raw, None
        return raw, None
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        # Advisory validation means an operator may intentionally save a type that
        # differs from the previous configuration.  Keep the raw text and surface
        # a high-visibility error instead of silently discarding their edit.
        return raw, ConfigurationIssue("ERROR", "", f"Could not parse as {value_type(template)}: {exc}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_configuration(config: dict[str, Any]) -> list[ConfigurationIssue]:
    issues: list[ConfigurationIssue] = []

    def error(path: str, message: str) -> None:
        issues.append(ConfigurationIssue("ERROR", path, message))

    def warn(path: str, message: str) -> None:
        issues.append(ConfigurationIssue("WARNING", path, message))

    if not isinstance(config, dict):
        return [ConfigurationIssue("ERROR", "configuration", "The root configuration must be a JSON object.")]

    for section in ("pdf", "dxf", "rules", "item_overrides"):
        if not isinstance(config.get(section), dict):
            error(section, f"'{section}' should be a JSON object.")

    numeric_positive = (
        "pdf.label_font_size",
        "pdf.diamon_fusion_font_size",
        "pdf.diamon_fusion_min_font_size",
        "pdf.indicator_size",
        "pdf.waterjet_indicator_size",
        "pdf.waterjet_indicator_line_width",
        "pdf.waterjet_indicator_length_ratio",
        "pdf.hinge_side_min_delta",
        "dxf.waterjet_output_scale",
        "dxf.default_output_scale",
        "rules.denver_min_inches",
        "rules.waterjet_fit_limit_inches",
        "rules.auto_dxf_angle_max_degrees",
    )
    for path in numeric_positive:
        value = get_path(config, path)
        if not _is_number(value):
            error(path, "Expected a finite numeric value.")
        elif float(value) <= 0:
            error(path, "Value should be greater than zero.")

    for path in (
        "pdf.label_x_ratio",
        "pdf.label_y_ratio",
        "pdf.label_position.x_ratio",
        "pdf.label_position.default_y_ratio",
        "pdf.label_position.denver_y_ratio",
        "pdf.label_position.waterjet_y_ratio",
    ):
        value = get_path(config, path)
        if not _is_number(value):
            error(path, "Expected a ratio between 0 and 1.")
        elif not 0 <= float(value) <= 1:
            warn(path, "This placement ratio is normally between 0 and 1.")

    for path in ("pdf.hinge_side_band_ratio", "rules.auto_dxf_fps_cut_min_segment_ratio", "rules.auto_dxf_fps_cut_min_coverage_ratio"):
        value = get_path(config, path)
        if not _is_number(value):
            error(path, "Expected a ratio between 0 and 1.")
        elif not 0 <= float(value) <= 1:
            error(path, "Ratio should be between 0 and 1.")

    minimum_angle = get_path(config, "rules.auto_dxf_angle_min_degrees")
    maximum_angle = get_path(config, "rules.auto_dxf_angle_max_degrees")
    if not _is_number(minimum_angle):
        error("rules.auto_dxf_angle_min_degrees", "Expected a finite numeric value.")
    elif float(minimum_angle) < 0:
        error("rules.auto_dxf_angle_min_degrees", "Minimum angle cannot be negative.")
    if _is_number(minimum_angle) and _is_number(maximum_angle) and float(minimum_angle) > float(maximum_angle):
        error("rules.auto_dxf_angle_min_degrees", "Minimum DXF correction is greater than the configured maximum.")

    denver_min = get_path(config, "rules.denver_min_inches")
    wj_limit = get_path(config, "rules.waterjet_fit_limit_inches")
    if _is_number(denver_min) and _is_number(wj_limit) and float(denver_min) >= float(wj_limit):
        warn("rules.waterjet_fit_limit_inches", "Water Jet fit limit is not greater than the Denver minimum edge.")

    direction = get_path(config, "rules.auto_angle_direction")
    if direction not in (-1, 1):
        warn("rules.auto_angle_direction", "Automatic angle direction is normally 1 or -1.")

    fp_count = get_path(config, "rules.waterjet_fp_min_count")
    if not isinstance(fp_count, int) or isinstance(fp_count, bool) or fp_count < 1:
        error("rules.waterjet_fp_min_count", "Plain FP count should be a positive whole number.")

    rgb = get_path(config, "pdf.label_color_rgb")
    if not isinstance(rgb, list) or len(rgb) != 3 or any(not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 255 for channel in rgb):
        error("pdf.label_color_rgb", "RGB color must contain exactly three whole numbers from 0 through 255.")

    for path in (
        "rules.mirror_keywords",
        "rules.door_keywords",
        "rules.hinge_label_keywords",
        "rules.door_cut_in_keywords",
        "rules.denver_fabrication_keywords",
        "rules.weak_waterjet_keywords",
        "rules.waterjet_keywords",
        "rules.fabrication_keywords",
        "rules.label_only_allow_keywords",
    ):
        value = get_path(config, path)
        if value is None:
            continue
        if not isinstance(value, list):
            error(path, "Expected a list of case-insensitive text keywords.")
            continue
        if any(not isinstance(item, str) or not item.strip() for item in value):
            error(path, "Keyword lists should contain non-empty text values only.")
        duplicates = sorted({item.strip().casefold() for item in value if isinstance(item, str) and item.strip() and sum(1 for other in value if isinstance(other, str) and other.strip().casefold() == item.strip().casefold()) > 1})
        if duplicates:
            warn(path, f"Duplicate keyword(s): {', '.join(duplicates)}")

    hinge_codes = get_path(config, "rules.hinge_label_keywords", [])
    hinge_map = get_path(config, "rules.hinge_label_orientations", {})
    if not isinstance(hinge_map, dict):
        error("rules.hinge_label_orientations", "Expected a JSON object mapping hinge codes to 'up' or 'down'.")
    else:
        invalid = [str(code) for code, orientation in hinge_map.items() if str(orientation).strip().casefold() not in {"up", "down"}]
        if invalid:
            error("rules.hinge_label_orientations", f"Orientation must be 'up' or 'down' for: {', '.join(invalid)}")
        if isinstance(hinge_codes, list):
            configured_codes = {str(code).strip().casefold() for code in hinge_map}
            missing = [
                str(code)
                for code in hinge_codes
                if str(code).strip().casefold() not in configured_codes
            ]
            if missing:
                warn("rules.hinge_label_orientations", f"No default orientation is configured for: {', '.join(missing)}")

    rotation_map = get_path(config, "rules.waterjet_tall_rotation_by_indicator", {})
    expected_corners = {"top_left", "top_right", "bottom_left", "bottom_right"}
    if not isinstance(rotation_map, dict):
        error("rules.waterjet_tall_rotation_by_indicator", "Expected a JSON object keyed by the four marker corners.")
    else:
        missing = sorted(expected_corners.difference(rotation_map))
        if missing:
            warn("rules.waterjet_tall_rotation_by_indicator", f"Missing corner mapping(s): {', '.join(missing)}")
        for corner, rotation in rotation_map.items():
            if not _is_number(rotation):
                error(f"rules.waterjet_tall_rotation_by_indicator.{corner}", "Rotation should be numeric degrees.")
            elif abs(float(rotation)) > 360:
                warn(f"rules.waterjet_tall_rotation_by_indicator.{corner}", "Rotation is outside the usual -360 to 360 degree range.")

    for path in ("dxf.waterjet_insunits", "dxf.waterjet_measurement", "dxf.default_insunits", "dxf.default_measurement"):
        value = get_path(config, path)
        if not isinstance(value, int) or isinstance(value, bool):
            error(path, "DXF unit header values should be whole numbers.")

    overrides = get_path(config, "item_overrides")
    if not isinstance(overrides, dict):
        error("item_overrides", "Exact order overrides must remain a JSON object.")

    return issues


def issues_summary(issues: Iterable[ConfigurationIssue]) -> tuple[int, int]:
    issue_list = list(issues)
    errors = sum(1 for issue in issue_list if issue.severity.upper() == "ERROR")
    warnings = sum(1 for issue in issue_list if issue.severity.upper() == "WARNING")
    return errors, warnings



def backup_configuration(path: Path, *, backup_dir: Path | None = None, keep: int = 20) -> Path | None:
    """Create a compact pre-save backup in a persistent operator-data folder."""
    source = Path(path)
    if not source.is_file():
        return None
    target_dir = Path(backup_dir) if backup_dir is not None else source.parent / "Configuration Backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = target_dir / f"{source.stem}-before-edit-{stamp}{source.suffix}"
    target.write_bytes(source.read_bytes())
    backups = sorted(
        target_dir.glob(f"{source.stem}-before-edit-*{source.suffix}"),
        key=lambda candidate: candidate.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in backups[max(1, int(keep)) :]:
        try:
            stale.unlink()
        except OSError:
            pass
    return target

def atomic_write_configuration(path: Path, config: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
