#!/usr/bin/env python3
"""Automate first-pass shower sketch programming.

This script marks glass order PDFs with A&W item labels, machine labels, and
orientation indicators, then writes adjusted DXF files for pieces that need
machine programming.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import math
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


DEFAULT_CONFIG_NAME = "shower_programmer_config.json"
TEMPLATE_PAGE_MARKERS = ("TEMPLATES FOR GLASS", "TEMPLATE A:", "TEMPLATE B:")
LABEL_FONT = "Helvetica-Bold"
PDF_MATRIX_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
PdfMatrix = tuple[float, float, float, float, float, float]


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def project_root() -> Path:
    directory = script_dir()
    return directory.parent if directory.name.lower() == "backend" else directory


def default_input_dir() -> Path:
    candidate = project_root() / "Input"
    return candidate if candidate.exists() else project_root()


def default_orders_dir() -> Path:
    candidate = default_input_dir() / "Orders"
    return candidate if candidate.exists() else default_input_dir()


def default_process_list_path() -> Path:
    process_list_dir = default_input_dir() / "Process List"
    if process_list_dir.exists():
        return process_list_dir
    candidate = default_input_dir() / "Process List Per Machine.xlsx"
    if candidate.exists():
        return candidate
    return default_input_dir() / "Process List Per Machine.xlsx"


def default_output_dir() -> Path:
    return project_root() / "Output"


def pdf_matrix_from_values(values: Iterable[Any]) -> PdfMatrix:
    items = list(values)
    if len(items) < 6:
        return PDF_MATRIX_IDENTITY
    return tuple(float(value) for value in items[:6])  # type: ignore[return-value]


def multiply_pdf_matrices(left: PdfMatrix, right: PdfMatrix) -> PdfMatrix:
    a1, b1, c1, d1, e1, f1 = left
    a2, b2, c2, d2, e2, f2 = right
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def transform_pdf_point(matrix: PdfMatrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def text_origin_from_matrices(cm: Iterable[Any], tm: Iterable[Any]) -> tuple[float, float]:
    ctm = pdf_matrix_from_values(cm)
    text_matrix = pdf_matrix_from_values(tm)
    return transform_pdf_point(ctm, text_matrix[4], text_matrix[5])


def transformed_rect(
    matrix: PdfMatrix,
    x: float,
    y: float,
    width: float,
    height: float,
    pad: float = 0.0,
) -> tuple[float, float, float, float]:
    points = [
        transform_pdf_point(matrix, x, y),
        transform_pdf_point(matrix, x + width, y),
        transform_pdf_point(matrix, x + width, y + height),
        transform_pdf_point(matrix, x, y + height),
    ]
    return points_rect(points, pad)


def content_operations_with_matrices(
    reader: PdfReader,
    page_index: int,
) -> Iterable[tuple[list[Any], str, PdfMatrix]]:
    page = reader.pages[page_index]
    try:
        content = ContentStream(page.get_contents(), reader)
    except Exception:
        return []

    matrix: PdfMatrix = PDF_MATRIX_IDENTITY
    stack: list[PdfMatrix] = []
    operations: list[tuple[list[Any], str, PdfMatrix]] = []
    for operands, operator in content.operations:
        op = operator.decode("latin1") if isinstance(operator, bytes) else str(operator)
        if op == "q":
            stack.append(matrix)
            continue
        if op == "Q":
            matrix = stack.pop() if stack else PDF_MATRIX_IDENTITY
            continue
        if op == "cm" and len(operands) >= 6:
            matrix = multiply_pdf_matrices(matrix, pdf_matrix_from_values(operands))
            continue
        operations.append((list(operands), op, matrix))
    return operations


def resolve_config_path(config_value: str | Path, folder: Path) -> Path:
    config_path = Path(config_value)
    if config_path.is_absolute():
        return config_path
    folder_path = folder / config_path
    if folder_path.exists():
        return folder_path
    return script_dir() / config_path


@dataclass
class Panel:
    item: int
    page_index: int
    text: str
    width: float | None
    height: float | None
    machine: str
    reasons: list[str] = field(default_factory=list)
    diamon_fusion: bool = False
    label_only: bool = False
    skip_dxf: bool = False
    remake: bool = False
    remake_excluded: bool = False
    indicator_corner: str | None = None
    rotation_degrees: float | None = None
    angle_correction_degrees: float = 0.0
    angle_correction_reason: str = ""
    source_dxf: Path | None = None
    output_dxf: Path | None = None
    process_text: str = ""
    warnings: list[str] = field(default_factory=list)
    hinge_side: str | None = None
    hinges_up: bool = False
    label_nudge_x: float = 0.0
    label_nudge_y: float = 0.0
    indicator_nudge_x: float = 0.0
    indicator_nudge_y: float = 0.0
    diamon_fusion_nudge_x: float = 0.0
    diamon_fusion_nudge_y: float = 0.0
    diamon_fusion_font_size: float | None = None
    label_font_size: float | None = None
    remake_font_size: float | None = None
    indicator_size: float | None = None
    waterjet_indicator_size: float | None = None
    hide_label: bool = False
    hide_indicator: bool = False
    hide_diamon_fusion: bool = False
    hide_remake: bool = False
    label_text: str | None = None
    diamon_fusion_text: str | None = None
    remake_text: str | None = None
    manual_x: bool = False
    label_x: float | None = None
    label_y: float | None = None
    indicator_x: float | None = None
    indicator_y: float | None = None
    diamon_fusion_x: float | None = None
    diamon_fusion_y: float | None = None
    remake_x: float | None = None
    remake_y: float | None = None
    manual_indicator_override: bool = False
    manual_rotation_override: bool = False

    @property
    def label(self) -> str:
        return f".{self.item}"


@dataclass
class Job:
    pdf_path: Path
    aw_order: str
    job_name: str
    panels: list[Panel]
    output_pdf: Path
    report_path: Path
    remake_items: set[int] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark shower PDFs and rotate matching DXFs for machine programming."
    )
    parser.add_argument("--pdf", help="Glass Order PDF to process. If omitted, --job is used to find one.")
    parser.add_argument("--aw-order", required=True, help="A&W order number, for example 234450.")
    parser.add_argument("--job", help="SO/job name, for example \"87793318 RIVERWALK 497\".")
    parser.add_argument("--folder", default=str(default_orders_dir()), help="Folder containing the PDFs and DXFs.")
    parser.add_argument("--output-dir", default=str(default_output_dir() / "Sketches"), help="Folder for marked PDFs/reports/DXFs.")
    parser.add_argument("--config", default=DEFAULT_CONFIG_NAME, help="JSON config with rule defaults and overrides.")
    parser.add_argument("--apply", action="store_true", help="Actually write files. Without this, only a dry-run report is printed.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    parser.add_argument("--skip-pdf", action="store_true", help="Do not write the marked PDF.")
    parser.add_argument("--skip-dxf", action="store_true", help="Do not write adjusted DXF files.")
    parser.add_argument("--dxf-output-dir", help="Optional separate folder for adjusted DXFs.")
    parser.add_argument("--remake-items", help="Mark this as a remake. Optional comma list of remake items, e.g. 1,3.")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def merge_item_overrides(config: dict[str, Any], override_config: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(config)
    incoming = override_config.get("item_overrides", {})
    if not isinstance(incoming, dict):
        return merged
    target = merged.setdefault("item_overrides", {})
    for aw_order, item_overrides in incoming.items():
        if not isinstance(item_overrides, dict):
            continue
        order_target = target.setdefault(str(aw_order), {})
        for item, override in item_overrides.items():
            if not isinstance(override, dict):
                continue
            item_target = order_target.setdefault(str(item), {})
            item_target.update(override)
    return merged


def upper_set(config: dict[str, Any], section: str, key: str) -> set[str]:
    return {str(v).upper() for v in config.get(section, {}).get(key, [])}


def parse_measurement(value: str) -> float | None:
    value = re.sub(r"['\"]+", " ", value.strip())
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None
    total = 0.0
    if "-" in value and re.search(r"\d+-\d+/\d+", value):
        whole, frac = value.split("-", 1)
        total += float(whole)
        value = frac
    elif " " in value and re.search(r"\d+\s+\d+/\d+", value):
        whole, frac = value.split(None, 1)
        total += float(whole)
        value = frac
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return total + float(num) / float(den)
        except ValueError:
            return None
    try:
        return total + float(value)
    except ValueError:
        return None


def parse_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_item_list(value: str | None) -> set[int]:
    if value is None or not value.strip():
        return set()
    items: set[int] = set()
    for token in re.split(r"[,\s;]+", value.upper().replace("P", " ").strip()):
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"Invalid item number: {token}")
        number = int(token)
        if number <= 0:
            raise ValueError(f"Invalid item number: {token}")
        items.add(number)
    return items


def extract_dimensions(text: str) -> tuple[float | None, float | None]:
    dim = re.search(
        r'(?P<w>\d+(?:-\d+/\d+|\s+\d+/\d+|(?:\.\d+)?)?)"\s*x\s*'
        r'(?P<h>\d+(?:-\d+/\d+|\s+\d+/\d+|(?:\.\d+)?)?)"',
        text,
    )
    if not dim:
        return None, None
    return parse_measurement(dim.group("w")), parse_measurement(dim.group("h"))


def extract_item_number(text: str) -> int | None:
    matches = [int(m.group(1)) for m in re.finditer(r"\bP(\d+)\b", text)]
    if not matches:
        return None
    return matches[-1]


def looks_like_template_page(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in TEMPLATE_PAGE_MARKERS)


def extract_transom_label(text: str) -> str | None:
    upper = re.sub(r"\s+", " ", text.upper())
    patterns = (
        r"\bTRN\s*[-#.]?\s*\d+[A-Z]?\b",
        r"\bTRANSOM\s*[-#.]?\s*\d*[A-Z]?\b",
        r"\bTRANS\s*[-#.]?\s*\d+[A-Z]?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, upper)
        if not match:
            continue
        label = re.sub(r"\s+", "", match.group(0).strip())
        if label in {"TRANSOM", "TRANS"}:
            return label
        return label
    return None


def extract_job_from_pdf(pdf_path: Path) -> str:
    name_guess = job_from_filename(pdf_path.name)
    try:
        reader = PdfReader(str(pdf_path))
        text = (reader.pages[0].extract_text() or "").replace("\n", " ")
    except Exception:
        return name_guess or pdf_path.stem

    match = re.search(
        r"(?P<job>\d{7,8}(?:\.\d+)?\s+[A-Z0-9][A-Z0-9 .#&'/_-]+?)(?:Project Name:|Printed On:|Delivery Date:)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return clean_job_name(match.group("job"))
    return name_guess or pdf_path.stem


def job_from_filename(name: str) -> str | None:
    stem = Path(name).stem
    stem = re.sub(r"^Glass Order\s+", "", stem, flags=re.IGNORECASE).strip()
    if "_" in stem:
        stem = stem.split("_", 1)[1].strip()
    match = re.search(r"(\d{7,8}(?:\.\d+)?\s+.+)", stem)
    if match:
        return clean_job_name(match.group(1))
    return None


def clean_job_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" _-")
    value = re.sub(r"Project Name.*$", "", value, flags=re.IGNORECASE).strip()
    return value


def find_pdf(folder: Path, job: str | None) -> Path:
    pdfs = sorted(p for p in folder.rglob("*.pdf") if p.is_file())
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {folder}")
    if job:
        key = normalize_lookup(job)
        matches = [p for p in pdfs if key in normalize_lookup(p.stem) or key in normalize_lookup(extract_job_from_pdf(p))]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            glass_matches = [p for p in matches if p.name.lower().startswith("glass order")]
            if len(glass_matches) == 1:
                return glass_matches[0]
            names = "\n  ".join(str(p.name) for p in matches)
            raise RuntimeError(f"Multiple PDFs match {job!r}:\n  {names}\nPass --pdf to choose one.")
    glass_orders = [p for p in pdfs if p.name.lower().startswith("glass order")]
    if len(glass_orders) == 1:
        return glass_orders[0]
    raise RuntimeError("Could not choose a PDF automatically. Pass --pdf.")


def normalize_lookup(value: str) -> str:
    return re.sub(r"[^A-Z0-9.]+", " ", value.upper()).strip()


def analyze_panels(reader: PdfReader, config: dict[str, Any], aw_order: str) -> list[Panel]:
    panels: list[Panel] = []
    for page_index, page in enumerate(reader.pages):
        if page_index == 0:
            continue
        text = page.extract_text() or ""
        if looks_like_template_page(text):
            continue
        item = extract_item_number(text)
        if item is None:
            continue
        width, height = extract_dimensions(text)
        panel = classify_panel(
            Panel(
                item=item,
                page_index=page_index,
                text=text,
                width=width,
                height=height,
                machine="",
            ),
            config,
            aw_order,
        )
        panels.append(panel)
    panels.sort(key=lambda p: p.item)
    return panels


def classify_panel(panel: Panel, config: dict[str, Any], aw_order: str) -> Panel:
    rules = config.get("rules", {})
    upper = panel.text.upper()
    door_keywords = upper_set(config, "rules", "door_keywords")
    hinge_label_keywords = upper_set(config, "rules", "hinge_label_keywords")
    waterjet_keywords = upper_set(config, "rules", "waterjet_keywords")
    weak_waterjet_keywords = upper_set(config, "rules", "weak_waterjet_keywords")
    fabrication_keywords = upper_set(config, "rules", "fabrication_keywords")
    denver_fabrication_keywords = upper_set(config, "rules", "denver_fabrication_keywords")
    label_only_allow = upper_set(config, "rules", "label_only_allow_keywords")
    denver_min = float(rules.get("denver_min_inches", 6.125))

    has_door = any(k in upper for k in door_keywords | hinge_label_keywords) or has_hinge_label_text(upper, config)
    has_strong_waterjet = has_pdf_waterjet_evidence(panel.text, config)
    has_weak_waterjet = any(k in upper for k in weak_waterjet_keywords)
    has_fabrication = any(k in upper for k in fabrication_keywords)
    has_denver_fabrication = any(k in upper for k in denver_fabrication_keywords)
    has_only_allowed_extra = any(k in upper for k in label_only_allow)
    panel.diamon_fusion = "DIAMON" in upper or "DIAMOND FUSION" in upper

    if panel.width is None or panel.height is None:
        panel.warnings.append("Could not read dimensions from PDF text.")
    small_piece = (
        panel.width is not None
        and panel.height is not None
        and min(panel.width, panel.height) < denver_min
    )

    if small_piece:
        panel.machine = "WJ"
        panel.reasons.append(f"minimum side below {denver_min:g} in")
    elif has_door:
        panel.machine = "DENVER 1"
        panel.reasons.append("door-like keyword in PDF text")
    elif has_strong_waterjet:
        panel.machine = "WJ"
        panel.reasons.append("water-jet keyword in PDF text")
    elif has_fabrication or has_denver_fabrication or has_weak_waterjet:
        panel.machine = "DENVER 2"
        panel.reasons.append("panel fabrication keyword in PDF text")
    else:
        panel.machine = ""
        panel.label_only = True
        panel.skip_dxf = True
        panel.reasons.append("no cutouts/fabrication detected")

    if has_only_allowed_extra and not has_fabrication:
        panel.label_only = True
        panel.skip_dxf = True

    if panel.machine == "WJ":
        panel.indicator_corner = default_waterjet_indicator_corner(panel)
        panel.rotation_degrees = -90 if panel.height and panel.width and panel.height > panel.width else 0
    elif panel.machine.startswith("DENVER"):
        panel.indicator_corner = "bottom_left"
        panel.rotation_degrees = 90 if panel.height and panel.width and panel.height > panel.width else 0
        panel.indicator_corner = denver_grabber_corner_for_panel(panel, panel.rotation_degrees)

    apply_auto_angle_correction(panel, config)
    apply_override(panel, config, aw_order)
    apply_auto_angle_correction(panel, config)
    if not panel.machine:
        panel.label_only = True
        panel.skip_dxf = True
        panel.indicator_corner = None
        panel.rotation_degrees = None
    validate_panel_constraints(panel, config)
    return panel


def has_pdf_waterjet_evidence(text: str, config: dict[str, Any]) -> bool:
    upper = text.upper()
    waterjet_keywords = upper_set(config, "rules", "waterjet_keywords")
    weak_waterjet_keywords = upper_set(config, "rules", "weak_waterjet_keywords")
    if any(keyword in upper for keyword in waterjet_keywords - weak_waterjet_keywords):
        return True
    rules = config.get("rules", {})
    minimum_fp = int(parse_float(rules.get("waterjet_fp_min_count", 6), 6))
    if count_fp_marks(upper) >= minimum_fp:
        return True
    return has_radius_text(upper)


def count_fp_marks(text: str) -> int:
    return len(re.findall(r"\bFP\b(?!-)", text.upper()))


def has_radius_text(text: str) -> bool:
    upper = text.upper()
    return bool(
        re.search(
            r"\b(?:3/8|1/2|0?\.375|0?\.5)\s*(?:\"|IN(?:CH(?:ES)?)?)?\s*RADIUS\b|\bRADIUS\b",
            upper,
        )
    )


def apply_override(panel: Panel, config: dict[str, Any], aw_order: str) -> None:
    overrides = config.get("item_overrides", {})
    order_overrides = overrides.get(str(aw_order), {})
    override = order_overrides.get(str(panel.item), {})
    if not override:
        return
    coerced_denver_indicator_override = False
    coerced_waterjet_indicator_override = False
    position_only_indicator_override = (
        "indicator_corner" in override
        and ("indicator_x" in override or "indicator_y" in override)
        and not bool(override.get("manual_indicator_corner"))
    )
    if "config override" not in panel.reasons:
        panel.reasons.append("config override")
    if "machine" in override:
        panel.machine = str(override["machine"]).strip().upper()
        panel.label_only = not bool(panel.machine)
    if "skip_dxf" in override:
        panel.skip_dxf = bool(override["skip_dxf"])
    if "diamon_fusion" in override:
        panel.diamon_fusion = bool(override["diamon_fusion"])
    if "hide_label" in override:
        panel.hide_label = bool(override["hide_label"])
    if "hide_indicator" in override:
        panel.hide_indicator = bool(override["hide_indicator"])
    if "hide_diamon_fusion" in override:
        panel.hide_diamon_fusion = bool(override["hide_diamon_fusion"])
    if "hide_remake" in override:
        panel.hide_remake = bool(override["hide_remake"])
    if "manual_x" in override:
        panel.manual_x = bool(override["manual_x"])
    if "label_text" in override:
        panel.label_text = clean_override_text(override["label_text"])
    if "diamon_fusion_text" in override:
        panel.diamon_fusion_text = clean_override_text(override["diamon_fusion_text"])
    if "remake_text" in override:
        panel.remake_text = clean_override_text(override["remake_text"])
    if "hinges_up" in override and not position_only_indicator_override:
        panel.hinges_up = bool(override["hinges_up"])
    if "hinge_side" in override and not position_only_indicator_override:
        side = str(override["hinge_side"]).strip().lower()
        if side in {"left", "right"}:
            panel.hinge_side = side
            panel.rotation_degrees = door_rotation_for_hinge_side(side, panel.hinges_up)
            panel.indicator_corner = door_indicator_corner_for_hinge_side(side, panel.hinges_up)
            panel.manual_indicator_override = True
            panel.manual_rotation_override = True
    if "indicator_corner" in override and not position_only_indicator_override:
        corner = str(override["indicator_corner"]).strip().lower()
        if corner:
            allow_manual_denver_corner = bool(override.get("manual_indicator_corner"))
            if panel.machine.startswith("DENVER") and not allow_manual_denver_corner:
                coerced_denver_indicator_override = denver_allowed_indicator_corner(corner) != corner
            elif panel.machine == "WJ":
                coerced_waterjet_indicator_override = waterjet_allowed_indicator_corner(corner) != corner
            apply_indicator_corner_override_with_options(
                panel,
                corner,
                config,
                allow_manual_denver_corner=allow_manual_denver_corner,
            )
        else:
            panel.indicator_corner = None
    if "rotation_degrees" in override and not position_only_indicator_override:
        value = override["rotation_degrees"]
        panel.rotation_degrees = None if value is None else float(value)
        panel.manual_rotation_override = value is not None
    if "angle_correction_degrees" in override:
        panel.angle_correction_degrees = float(override["angle_correction_degrees"])
        panel.angle_correction_reason = "config angle correction"
    elif "out_of_square" in override and "out_of_square_length" in override:
        out_of_square = parse_measurement(str(override["out_of_square"]))
        length = parse_measurement(str(override["out_of_square_length"]))
        direction = float(override.get("angle_direction", 1))
        if out_of_square and length:
            panel.angle_correction_degrees = math.degrees(math.atan(out_of_square / length)) * direction
            panel.angle_correction_reason = (
                f"out of square {out_of_square:g} over {length:g}"
            )
    if "label_nudge_x" in override:
        panel.label_nudge_x = parse_float(override["label_nudge_x"], 0)
    if "label_nudge_y" in override:
        panel.label_nudge_y = parse_float(override["label_nudge_y"], 0)
    if "indicator_nudge_x" in override:
        panel.indicator_nudge_x = parse_float(override["indicator_nudge_x"], 0)
    if "indicator_nudge_y" in override:
        panel.indicator_nudge_y = parse_float(override["indicator_nudge_y"], 0)
    if "diamon_fusion_nudge_x" in override:
        panel.diamon_fusion_nudge_x = parse_float(override["diamon_fusion_nudge_x"], 0)
    if "diamon_fusion_nudge_y" in override:
        panel.diamon_fusion_nudge_y = parse_float(override["diamon_fusion_nudge_y"], 0)
    if "diamon_fusion_font_size" in override:
        panel.diamon_fusion_font_size = parse_float(override["diamon_fusion_font_size"], 0) or None
    if "label_font_size" in override:
        panel.label_font_size = parse_float(override["label_font_size"], 0) or None
    if "remake_font_size" in override:
        panel.remake_font_size = parse_float(override["remake_font_size"], 0) or None
    if "indicator_size" in override:
        panel.indicator_size = parse_float(override["indicator_size"], 0) or None
    if "waterjet_indicator_size" in override:
        panel.waterjet_indicator_size = parse_float(override["waterjet_indicator_size"], 0) or None
    if "label_x" in override:
        panel.label_x = parse_float(override["label_x"], 0)
    if "label_y" in override:
        panel.label_y = parse_float(override["label_y"], 0)
    if "indicator_x" in override:
        panel.indicator_x = parse_float(override["indicator_x"], 0)
    if "indicator_y" in override:
        panel.indicator_y = parse_float(override["indicator_y"], 0)
    if coerced_denver_indicator_override:
        panel.indicator_x = None
        panel.indicator_y = None
        panel.reasons.append("Denver marker corner coerced to allowed position")
    if coerced_waterjet_indicator_override:
        panel.indicator_x = None
        panel.indicator_y = None
        panel.reasons.append("WJ marker corner coerced to top-left/bottom-right")
    if "diamon_fusion_x" in override:
        panel.diamon_fusion_x = parse_float(override["diamon_fusion_x"], 0)
    if "diamon_fusion_y" in override:
        panel.diamon_fusion_y = parse_float(override["diamon_fusion_y"], 0)
    if "remake_x" in override:
        panel.remake_x = parse_float(override["remake_x"], 0)
    if "remake_y" in override:
        panel.remake_y = parse_float(override["remake_y"], 0)
    sanitize_denver_indicator_override(panel)
    sanitize_waterjet_indicator(panel)


def clean_override_text(value: object) -> str | None:
    text = str(value).replace("\\n", "\n").strip()
    return text or None


def override_text_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.replace("\\n", "\n").splitlines() if line.strip()]


def sanitize_denver_indicator_override(panel: Panel) -> None:
    if not panel.machine.startswith("DENVER"):
        return
    if panel.manual_indicator_override and panel.indicator_corner in {"bottom_left", "bottom_right", "top_left", "top_right"}:
        return
    allowed = denver_allowed_indicator_corner(panel.indicator_corner)
    if allowed == panel.indicator_corner:
        return
    panel.indicator_corner = allowed
    panel.indicator_x = None
    panel.indicator_y = None
    panel.manual_indicator_override = False


def waterjet_allowed_indicator_corner(corner: str | None) -> str | None:
    if corner in {"top_left", "bottom_right"}:
        return corner
    if corner == "top_right":
        return "top_left"
    if corner == "bottom_left":
        return "bottom_right"
    return corner


def sanitize_waterjet_indicator(panel: Panel) -> None:
    if panel.machine != "WJ":
        return
    allowed = waterjet_allowed_indicator_corner(panel.indicator_corner)
    if allowed == panel.indicator_corner:
        return
    panel.indicator_corner = allowed
    panel.indicator_x = None
    panel.indicator_y = None
    panel.manual_indicator_override = False


def apply_auto_angle_correction(panel: Panel, config: dict[str, Any]) -> None:
    rules = config.get("rules", {})
    if not bool(rules.get("auto_angle_correction", True)):
        return
    if panel.angle_correction_degrees or panel.machine != "DENVER 1":
        return
    upper = panel.text.upper()
    if "OUT OF SQUARE" not in upper and not re.search(r"\bOOS\b", upper):
        return
    # The side that needs compensation has to be proven from the DXF. Text alone can
    # say "out of square" without telling us whether the hinge/bottom side is the
    # side that must become flat on the Denver.
    return


def extract_out_of_square_amount(text: str) -> float | None:
    search_text = re.split(
        r"\b(?:CLEAR TEMPERED|GLASS TYPE|STANDARD SHAPE|PROCESSING|EDGEWORK)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    candidates: list[float] = []
    for match in re.finditer(r"\b(?:\d+\s+)?\d+/\d+\b|\b\d+-\d+/\d+\b|\b0?\.\d+\b", search_text):
        value = parse_measurement(match.group(0))
        if value and 0 < value <= 0.75:
            candidates.append(value)
    if not candidates:
        return None
    return min(candidates)


def validate_panel_constraints(panel: Panel, config: dict[str, Any]) -> None:
    rules = config.get("rules", {})
    waterjet_limit = float(rules.get("waterjet_fit_limit_inches", 75))
    if panel.machine != "WJ":
        return
    if panel.width is None or panel.height is None:
        add_panel_warning(panel, "Cannot verify WJ size limit because dimensions are unknown.")
        return
    if min(panel.width, panel.height) > waterjet_limit:
        add_panel_warning(
            panel,
            f"WJ size limit: neither side is {waterjet_limit:g} in or smaller "
            f"({panel.width:g} x {panel.height:g}). DXF skipped.",
        )
        panel.skip_dxf = True


def add_panel_warning(panel: Panel, message: str) -> None:
    if message not in panel.warnings:
        panel.warnings.append(message)


def refine_panel_orientations(reader: PdfReader, panels: list[Panel], config: dict[str, Any]) -> None:
    for panel in panels:
        if panel.machine != "DENVER 1":
            continue
        if panel.manual_rotation_override:
            continue
        if not has_door_programming_evidence(panel, config):
            continue
        bbox = estimate_panel_bbox(reader, panel.page_index)
        hinge_side = estimate_hinge_side(reader, panel.page_index, bbox, config)
        hinges_up = has_door_cut_in(panel, config)
        panel.hinges_up = hinges_up
        if hinge_side is None:
            if hinges_up and panel.indicator_corner:
                fallback_side = "right" if "right" in panel.indicator_corner else "left"
                panel.hinge_side = fallback_side
                panel.rotation_degrees = door_rotation_for_hinge_side(fallback_side, hinges_up)
                panel.indicator_corner = door_indicator_corner_for_hinge_side(fallback_side, hinges_up)
                panel.reasons.append("hinges up from cut-in/K-cut/PPH hint; hinge side not confirmed")
            continue
        panel.hinge_side = hinge_side
        panel.rotation_degrees = door_rotation_for_hinge_side(hinge_side, hinges_up)
        panel.indicator_corner = door_indicator_corner_for_hinge_side(hinge_side, hinges_up)
        direction = "up" if hinges_up else "down"
        panel.reasons.append(f"hinge side {hinge_side}; hinges {direction}")


def has_door_cut_in(panel: Panel, config: dict[str, Any]) -> bool:
    keywords = set(upper_set(config, "rules", "door_cut_in_keywords"))
    if not keywords:
        keywords = {"CUT IN", "CUT-IN", "CUTIN", "DOOR CUT IN"}
    keywords.update({"K CUT", "K-CUT", "K CUTS", "K-CUTS"})
    upper = panel_combined_text(panel).upper()
    if re.search(r"\b[A-Z0-9-]*PPH[A-Z0-9-]*\b", upper):
        return True
    return any(keyword in upper for keyword in keywords)


def needs_manual_review_for_fps_cut(panel: Panel, config: dict[str, Any]) -> bool:
    upper = panel_combined_text(panel).upper()
    has_fps = bool(re.search(r"\bFP\s*-\s*S\b|\bFPS\b", upper))
    if not has_fps:
        return False
    cut_keywords = set(upper_set(config, "rules", "door_cut_in_keywords"))
    cut_keywords.update(
        {
            "CUT IN",
            "CUT-IN",
            "CUTIN",
            "CUT OUT",
            "CUT-OUT",
            "CUTOUT",
            "K CUT",
            "K-CUT",
            "JUT OUT",
            "JUT-OUT",
        }
    )
    return any(keyword in upper for keyword in cut_keywords)


def panel_combined_text(panel: Panel) -> str:
    return f"{panel.text}\n{panel.process_text}"


def has_door_programming_evidence(panel: Panel, config: dict[str, Any]) -> bool:
    upper = panel_combined_text(panel).upper()
    if re.search(r"\b[A-Z0-9-]*PPH[A-Z0-9-]*\b", upper):
        return True
    if has_hinge_label_text(upper, config):
        return True
    keywords = upper_set(config, "rules", "door_keywords")
    keywords.update(upper_set(config, "rules", "hinge_label_keywords"))
    keywords.update({"DOOR", "HINGE", "PULL", "HANDLE", "GEN037", "V1E037", "AV1E037"})
    if any(keyword and keyword in upper for keyword in keywords):
        return True
    normalized = re.sub(r"[^A-Z0-9]", "", upper)
    for keyword in keywords:
        normalized_keyword = re.sub(r"[^A-Z0-9]", "", keyword.upper())
        if normalized_keyword and normalized_keyword in normalized:
            return True
    return False


def has_hinge_label_text(text: str, config: dict[str, Any]) -> bool:
    upper = text.upper()
    labels = upper_set(config, "rules", "hinge_label_keywords")
    labels.update({"GEN037", "V1E037", "AV1E037"})
    if any(label and label in upper for label in labels):
        return True
    return bool(re.search(r"\b(?:A?V1E|GEN)\d{3}\b", upper))


def door_rotation_for_hinge_side(hinge_side: str, hinges_up: bool) -> float:
    if hinges_up:
        return -90 if hinge_side == "left" else 90
    return 90 if hinge_side == "left" else -90


def door_indicator_corner_for_hinge_side(hinge_side: str, hinges_up: bool) -> str:
    if hinges_up:
        return door_indicator_corner_off_hinge_side(hinge_side, hinges_up)
    return "bottom_left" if hinge_side == "left" else "top_right"


def door_indicator_corner_off_hinge_side(hinge_side: str, hinges_up: bool) -> str:
    return "top_right" if hinge_side == "left" else "bottom_left"


def denver_allowed_indicator_corner(corner: str | None) -> str | None:
    if corner in {"bottom_left", "top_right"}:
        return corner
    if corner == "bottom_right":
        return "top_right"
    if corner == "top_left":
        return "bottom_left"
    return corner


def door_orientation_for_indicator_corner(corner: str) -> tuple[str, bool, float] | None:
    return {
        "bottom_left": ("left", False, 90.0),
        "bottom_right": ("right", True, 90.0),
        "top_left": ("left", True, -90.0),
        "top_right": ("right", False, -90.0),
    }.get(corner)


def denver_door_orientation_for_indicator_corner(
    panel: Panel,
    corner: str,
    config: dict[str, Any],
    *,
    allow_manual_corner: bool = False,
) -> tuple[str, bool, float] | None:
    if allow_manual_corner:
        raw_orientation = door_orientation_for_indicator_corner(corner)
        if raw_orientation is not None:
            return raw_orientation
    corner = denver_allowed_indicator_corner(corner) or corner
    if corner not in {"bottom_left", "top_right"}:
        return None
    cut_in = has_door_cut_in(panel, config)
    if panel.source_dxf is not None:
        candidate_side = panel.hinge_side if panel.hinge_side in {"left", "right"} else dxf_hinge_side_candidate(panel.source_dxf)
        if candidate_side in {"left", "right"} and dxf_hinge_side_has_cut_in(panel.source_dxf, candidate_side, config):
            cut_in = True
    if cut_in:
        hinge_side = "right" if corner == "bottom_left" else "left"
        hinges_up = True
    else:
        hinge_side = "left" if corner == "bottom_left" else "right"
        hinges_up = bool(panel.hinges_up)
    return hinge_side, hinges_up, door_rotation_for_hinge_side(hinge_side, hinges_up)


def denver_grabber_corner_for_rotation(rotation_degrees: float | None) -> str:
    normalized = ((float(rotation_degrees or 0) + 180) % 360) - 180
    if abs(normalized - 90) <= 1:
        return "bottom_left"
    if abs(normalized + 90) <= 1:
        return "top_right"
    if abs(abs(normalized) - 180) <= 1:
        return "top_right"
    return "bottom_left"


def denver_grabber_corner_for_panel(panel: Panel, rotation_degrees: float | None) -> str:
    corner = denver_grabber_corner_for_rotation(rotation_degrees)
    if panel.width is not None and panel.height is not None and panel.height < panel.width:
        normalized = ((float(rotation_degrees or 0) + 180) % 360) - 180
        if abs(normalized) <= 1:
            return "top_right"
    return corner


def default_waterjet_indicator_corner(panel: Panel) -> str:
    if panel.width is not None and panel.height is not None and panel.height < panel.width:
        return "bottom_right"
    return "top_left"


def denver_grabber_rotation_for_corner(corner: str) -> float | None:
    return {
        "bottom_left": 90.0,
        "top_right": -90.0,
    }.get(corner)


def apply_indicator_corner_override(panel: Panel, corner: str, config: dict[str, Any]) -> None:
    apply_indicator_corner_override_with_options(panel, corner, config)


def apply_indicator_corner_override_with_options(
    panel: Panel,
    corner: str,
    config: dict[str, Any],
    *,
    allow_manual_denver_corner: bool = False,
) -> None:
    corner = corner.strip().lower()
    if corner not in {"bottom_left", "bottom_right", "top_left", "top_right"}:
        return
    if panel.machine.startswith("DENVER") and not allow_manual_denver_corner:
        corner = denver_allowed_indicator_corner(corner) or corner
    elif panel.machine == "WJ":
        corner = waterjet_allowed_indicator_corner(corner) or corner
    panel.indicator_corner = corner
    panel.manual_indicator_override = True
    if panel.machine == "WJ":
        rotation = wj_rotation_for_indicator_corner(panel, config, corner)
        if rotation is not None:
            panel.rotation_degrees = rotation
        else:
            adjust_wj_rotation_for_indicator(panel, config)
        panel.manual_rotation_override = True
    elif panel.machine == "DENVER 1" and has_door_programming_evidence(panel, config):
        orientation = denver_door_orientation_for_indicator_corner(
            panel,
            corner,
            config,
            allow_manual_corner=allow_manual_denver_corner,
        )
        if orientation is not None:
            side, hinges_up, rotation = orientation
            panel.hinge_side = side
            panel.hinges_up = hinges_up
            panel.rotation_degrees = rotation
            panel.manual_rotation_override = True
    elif panel.machine.startswith("DENVER"):
        rotation = denver_grabber_rotation_for_corner(corner)
        if rotation is None and allow_manual_denver_corner:
            raw_orientation = door_orientation_for_indicator_corner(corner)
            rotation = None if raw_orientation is None else raw_orientation[2]
        if rotation is not None:
            panel.rotation_degrees = rotation
            panel.manual_rotation_override = True


def estimate_hinge_side_from_text(
    reader: PdfReader,
    page_index: int,
    bbox: tuple[float, float, float, float],
    config: dict[str, Any],
) -> str | None:
    labels = upper_set(config, "rules", "hinge_label_keywords") | {"GEN037", "V1E037", "AV1E037"}
    normalized_labels = {re.sub(r"[^A-Z0-9]", "", label.upper()) for label in labels}
    for label in list(normalized_labels):
        if len(label) > 4:
            normalized_labels.add(label[1:])
        if label.startswith("AV") and len(label) > 5:
            normalized_labels.add(label[2:])
    normalized_labels = {label for label in normalized_labels if label}

    left, bottom, right, top = bbox
    center_x = (left + right) / 2
    rows: list[dict[str, Any]] = []

    def add_char(char: str, x: float, y: float) -> None:
        if x <= 0 or y < bottom - 60 or y > top + 60 or x < left - 100 or x > right + 100:
            return
        for row in rows:
            if abs(row["y"] - y) <= 4:
                row["chars"].append((x, char))
                row["y"] = (row["y"] + y) / 2
                return
        rows.append({"y": y, "chars": [(x, char)]})

    def visitor_text(text: str, cm: list[float], tm: list[float], font_dict: Any, font_size: float) -> None:
        value = str(text)
        if not value.strip():
            return
        try:
            x, y = text_origin_from_matrices(cm, tm)
            size = float(font_size or 7)
        except Exception:
            return
        advance = max(size * 0.45, 3.5)
        position = x
        for char in value.upper():
            if char.isalnum():
                add_char(char, position, y)
                position += advance
            elif not char.isspace():
                position += advance

    try:
        reader.pages[page_index].extract_text(visitor_text=visitor_text)
    except Exception:
        return None

    left_hits = 0
    right_hits = 0
    pattern_parts = [re.escape(label) for label in sorted(normalized_labels, key=len, reverse=True)]
    pattern_parts.append(r"(?:A?V1E|GEN)\d{3}")
    pattern = re.compile("|".join(pattern_parts))
    for row in rows:
        chars = sorted(row["chars"], key=lambda entry: entry[0])
        text = "".join(char for _, char in chars)
        for match in pattern.finditer(text):
            x_values = [x for x, _ in chars[match.start() : match.end()]]
            if not x_values:
                continue
            if sum(x_values) / len(x_values) < center_x:
                left_hits += 1
            else:
                right_hits += 1

    if left_hits == right_hits:
        return None
    return "left" if left_hits > right_hits else "right"


def estimate_hinge_side(
    reader: PdfReader,
    page_index: int,
    bbox: tuple[float, float, float, float] | None,
    config: dict[str, Any],
) -> str | None:
    if bbox is None:
        return None
    text_side = estimate_hinge_side_from_text(reader, page_index, bbox, config)
    if text_side is not None:
        return text_side
    pdf_cfg = config.get("pdf", {})
    left, bottom, right, top = bbox
    width = right - left
    side_band = width * parse_float(pdf_cfg.get("hinge_side_band_ratio", 0.28), 0.28)
    minimum_delta = parse_float(pdf_cfg.get("hinge_side_min_delta", 8), 8)
    obstacles = collect_page_drawing_obstacles(reader, page_index, include_text=False)
    left_score = 0.0
    right_score = 0.0
    for rect in obstacles:
        cx = (rect[0] + rect[2]) / 2
        cy = (rect[1] + rect[3]) / 2
        rw = rect[2] - rect[0]
        rh = rect[3] - rect[1]
        if cy < bottom or cy > top:
            continue
        if rw > width * 0.45 or rh > (top - bottom) * 0.45:
            continue
        weight = 1.0 + min(rw * rh / 500, 4.0)
        if cx <= left + side_band:
            left_score += weight
        elif cx >= right - side_band:
            right_score += weight
    if abs(left_score - right_score) < minimum_delta:
        return None
    return "left" if left_score > right_score else "right"


def find_source_dxf(folder: Path, job_name: str, panel: Panel) -> Path | None:
    norm_job = normalize_lookup(job_name)
    candidates: list[tuple[tuple[int, int, int, int], Path]] = []
    for path in folder.rglob("*.dxf"):
        if not path.is_file():
            continue
        score = dxf_match_score(path, norm_job, panel.item)
        if score is not None:
            candidates.append((score, path))
    if candidates:
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        return candidates[0][1]
    return None


def dxf_match_score(path: Path, norm_job: str, item_number: int) -> tuple[int, int, int, int] | None:
    stem = path.stem
    norm_stem = normalize_lookup(stem)
    if norm_job not in norm_stem:
        return None

    item_pattern = rf"(?:^|[_\s-]){item_number}(?:$|__|[_\s-]|[^0-9])"
    p_pattern = rf"__P{item_number}(?:$|[^0-9])"
    if not re.search(item_pattern, stem, re.IGNORECASE) and not re.search(p_pattern, stem, re.IGNORECASE):
        return None

    has_weight = bool(re.search(r"\(\s*\d+(?:\.\d+)?\s*lb\s*\)", stem, re.IGNORECASE))
    has_detail_suffix = bool(re.search(rf"_{item_number}__.+", stem, re.IGNORECASE))
    has_panel_suffix = bool(re.search(p_pattern, stem, re.IGNORECASE))
    exact_plain = stem.upper().endswith(f"_{item_number}".upper())
    return (
        4 if has_weight else 0,
        2 if has_detail_suffix else 0,
        1 if has_panel_suffix else 0,
        0 if exact_plain else -1,
    )


def assign_dxf_paths(job: Job, dxf_folder: Path, dxf_output_dir: Path, config: dict[str, Any]) -> None:
    for panel in job.panels:
        if panel.skip_dxf:
            continue
        validate_panel_constraints(panel, config)
        if panel.skip_dxf:
            continue
        panel.source_dxf = find_source_dxf(dxf_folder, job.job_name, panel)
        panel.output_dxf = dxf_output_dir / f"{job.aw_order}{panel.item:02d}.dxf"
        if panel.source_dxf is None:
            panel.warnings.append("No matching source DXF found.")
        else:
            adjust_indicator_for_source_dxf(panel, config)
            apply_dxf_angle_correction(panel, config)
            apply_dxf_manual_review_warning(panel, config)


def adjust_indicator_for_source_dxf(panel: Panel, config: dict[str, Any]) -> None:
    if panel.source_dxf is None:
        return
    if panel.manual_rotation_override:
        return
    if panel.machine == "WJ":
        adjust_wj_indicator_corner(panel)
        adjust_wj_rotation_for_indicator(panel, config)
    elif panel.machine == "DENVER 1":
        if has_door_programming_evidence(panel, config):
            adjust_denver_door_hinge_side_from_dxf(panel, config)
        else:
            adjust_denver_panel_square_side(panel)
    elif panel.machine == "DENVER 2":
        adjust_denver_panel_square_side(panel)


def apply_dxf_manual_review_warning(panel: Panel, config: dict[str, Any]) -> None:
    if needs_manual_review_for_fps_cut(panel, config) or needs_manual_review_for_fps_dxf_cut(panel, config):
        add_panel_warning(panel, "FP-S cut-in/cut-out detected; manual DXF review required.")


def needs_manual_review_for_fps_dxf_cut(panel: Panel, config: dict[str, Any]) -> bool:
    if panel.source_dxf is None:
        return False
    upper = panel_combined_text(panel).upper()
    has_fps = bool(re.search(r"\bFP\s*-\s*S\b|\bFPS\b", upper))
    if not has_fps:
        return False
    return any(dxf_hinge_side_has_cut_in(panel.source_dxf, side, config) for side in ("left", "right"))


def apply_dxf_angle_correction(panel: Panel, config: dict[str, Any]) -> None:
    rules = config.get("rules", {})
    if not bool(rules.get("auto_angle_correction", True)):
        return
    if not bool(rules.get("auto_dxf_angle_correction", True)):
        return
    if panel.source_dxf is None or panel.rotation_degrees is None:
        return
    if panel.angle_correction_degrees and not panel.angle_correction_reason.startswith("auto "):
        return
    if panel.machine == "DENVER 1" and has_door_programming_evidence(panel, config):
        result = dxf_bottom_angle_correction(panel, config)
        bottom_side = side_for_rotation(panel.rotation_degrees)
        reason = "hinge/bottom side" if bottom_side == panel.hinge_side else "bottom side"
    elif panel.machine.startswith("DENVER"):
        result = dxf_bottom_angle_correction(panel, config)
        reason = "bottom side"
    else:
        return
    if result is None:
        return
    correction, amount, side_length = result
    if not correction:
        if panel.angle_correction_degrees and panel.angle_correction_reason.startswith("auto "):
            panel.angle_correction_degrees = 0.0
            panel.angle_correction_reason = ""
        return
    panel.angle_correction_degrees = correction
    panel.angle_correction_reason = f"auto DXF {reason} {amount:g} over {side_length:g}"


def dxf_hinge_angle_correction(panel: Panel, config: dict[str, Any]) -> tuple[float, float, float] | None:
    if panel.source_dxf is None or panel.rotation_degrees is None:
        return None
    source_side = panel.hinge_side or infer_hinge_side_from_rotation(panel)
    if source_side not in {"left", "right"}:
        return None

    rules = config.get("rules", {})
    min_degrees = parse_float(rules.get("auto_dxf_angle_min_degrees", 0.02), 0.02)
    max_degrees = parse_float(rules.get("auto_dxf_angle_max_degrees", 1.0), 1.0)
    min_segment_ratio = parse_float(rules.get("auto_dxf_angle_min_side_ratio", 0.20), 0.20)

    candidates: list[tuple[float, float, float]] = []
    for start, end in dxf_side_segments(panel.source_dxf, source_side):
        rx, ry = rotate_vector(end[0] - start[0], end[1] - start[1], panel.rotation_degrees)
        side_length = abs(rx)
        amount = abs(ry)
        if side_length <= 0:
            continue
        if panel.height and side_length < panel.height * min_segment_ratio:
            continue
        correction = -math.degrees(math.atan2(ry, rx))
        correction = normalize_axis_deviation(correction)
        if abs(correction) > max_degrees:
            continue
        if abs(correction) < min_degrees:
            correction = 0.0
        candidates.append((side_length, amount, correction))

    if not candidates:
        return None
    side_length, amount, correction = max(candidates, key=lambda item: (item[1], item[0]))
    return correction, amount, side_length


def dxf_bottom_angle_correction(panel: Panel, config: dict[str, Any]) -> tuple[float, float, float] | None:
    if panel.source_dxf is None or panel.rotation_degrees is None:
        return None
    source_side = side_for_rotation(panel.rotation_degrees)
    if source_side not in {"left", "right", "bottom", "top"}:
        return None

    rules = config.get("rules", {})
    min_degrees = parse_float(rules.get("auto_dxf_angle_min_degrees", 0.02), 0.02)
    max_degrees = parse_float(rules.get("auto_dxf_angle_max_degrees", 1.0), 1.0)
    min_segment_ratio = parse_float(rules.get("auto_dxf_angle_min_side_ratio", 0.20), 0.20)
    expected_length = panel.height if source_side in {"left", "right"} else panel.width

    candidates: list[tuple[float, float, float]] = []
    for start, end in dxf_side_segments(panel.source_dxf, source_side):
        rx, ry = rotate_vector(end[0] - start[0], end[1] - start[1], panel.rotation_degrees)
        side_length = abs(rx)
        amount = abs(ry)
        if side_length <= 0:
            continue
        if expected_length and side_length < expected_length * min_segment_ratio:
            continue
        correction = -math.degrees(math.atan2(ry, rx))
        correction = normalize_axis_deviation(correction)
        if abs(correction) > max_degrees:
            continue
        if abs(correction) < min_degrees:
            correction = 0.0
        candidates.append((side_length, amount, correction))

    if not candidates:
        return None
    side_length, amount, correction = max(candidates, key=lambda item: (item[1], item[0]))
    return correction, amount, side_length


def infer_hinge_side_from_rotation(panel: Panel) -> str | None:
    bottom_side = side_for_rotation(panel.rotation_degrees or 0)
    if bottom_side not in {"left", "right"}:
        return None
    return opposite_side(bottom_side) if panel.hinges_up else bottom_side


def opposite_side(side: str) -> str:
    return {
        "left": "right",
        "right": "left",
        "top": "bottom",
        "bottom": "top",
    }.get(side, side)


def dxf_side_segments(path: Path, side: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segments = collect_dxf_outer_line_segments(path)
    if not segments:
        return []
    points = [point for start, end in segments for point in (start, end)]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    width = max_x - min_x
    height = max_y - min_y
    side_tolerance = max(0.35, min(width, height) * 0.025)
    minimum_length = max(6.0, max(width, height) * 0.12)
    matches: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for start, end in segments:
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length < minimum_length:
            continue
        if segment_near_side(start, end, side, min_x, max_x, min_y, max_y, side_tolerance):
            matches.append((start, end))
    return matches


def segment_near_side(
    start: tuple[float, float],
    end: tuple[float, float],
    side: str,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    tolerance: float,
) -> bool:
    if side == "left":
        return min(start[0], end[0]) <= min_x + tolerance and max(start[0], end[0]) <= min_x + tolerance * 2.5
    if side == "right":
        return max(start[0], end[0]) >= max_x - tolerance and min(start[0], end[0]) >= max_x - tolerance * 2.5
    if side == "bottom":
        return min(start[1], end[1]) <= min_y + tolerance and max(start[1], end[1]) <= min_y + tolerance * 2.5
    if side == "top":
        return max(start[1], end[1]) >= max_y - tolerance and min(start[1], end[1]) >= max_y - tolerance * 2.5
    return False


def rotate_vector(dx: float, dy: float, rotation_degrees: float) -> tuple[float, float]:
    angle = math.radians(rotation_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a


def normalize_axis_deviation(angle_degrees: float) -> float:
    normalized = ((angle_degrees + 180) % 360) - 180
    if normalized > 90:
        normalized -= 180
    elif normalized < -90:
        normalized += 180
    return normalized


def apply_remake_selection(panels: list[Panel], remake_items: set[int] | None) -> set[int] | None:
    if remake_items is None:
        return None
    selected = set(remake_items) or {panel.item for panel in panels}
    available = {panel.item for panel in panels}
    for missing in sorted(selected - available):
        selected.discard(missing)
    for panel in panels:
        if panel.item in selected:
            panel.remake = True
            panel.reasons.append("remake item")
        else:
            panel.remake_excluded = True
            panel.skip_dxf = True
            panel.source_dxf = None
            panel.output_dxf = None
            panel.reasons.append("not selected for remake; X out")
    return selected


def adjust_wj_indicator_corner(panel: Panel) -> None:
    if panel.source_dxf is None:
        return
    corners = dxf_square_corners(panel.source_dxf)
    if not corners:
        panel.indicator_corner = waterjet_allowed_indicator_corner(panel.indicator_corner) or "top_left"
        return
    preferred = waterjet_allowed_indicator_corner(panel.indicator_corner) or "bottom_right"
    if preferred in corners:
        panel.indicator_corner = preferred
        return
    for candidate in ("bottom_right", "top_left"):
        if candidate in corners:
            panel.indicator_corner = candidate
            panel.reasons.append(f"WJ marker moved to square corner: {candidate}")
            return
    panel.indicator_corner = preferred
    panel.reasons.append(f"WJ marker kept at allowed corner: {preferred}")


def adjust_wj_rotation_for_indicator(panel: Panel, config: dict[str, Any]) -> None:
    if panel.source_dxf is None or panel.width is None or panel.height is None:
        return
    if panel.height <= panel.width or not panel.indicator_corner:
        return
    rotation = wj_rotation_for_indicator_corner(panel, config, panel.indicator_corner)
    if rotation is None:
        return
    if abs((panel.rotation_degrees or 0) - rotation) > 1e-6:
        panel.rotation_degrees = rotation
        panel.reasons.append(f"WJ rotation follows {panel.indicator_corner} marker")


def wj_rotation_for_indicator_corner(panel: Panel, config: dict[str, Any], corner: str | None) -> float | None:
    if panel.width is None or panel.height is None:
        return None
    if panel.height <= panel.width or not corner:
        return None
    rules = config.get("rules", {})
    mapping = rules.get("waterjet_tall_rotation_by_indicator", {})
    if not isinstance(mapping, dict):
        mapping = {}
    default_mapping = {
        "top_left": 90,
        "bottom_right": -90,
    }
    allowed_corner = waterjet_allowed_indicator_corner(corner)
    value = mapping.get(allowed_corner, default_mapping.get(allowed_corner))
    if value is None:
        return None
    return parse_float(value, panel.rotation_degrees or 0)


def adjust_denver_door_hinge_side_from_dxf(panel: Panel, config: dict[str, Any]) -> None:
    if panel.source_dxf is None or panel.machine != "DENVER 1":
        return
    if panel.manual_rotation_override:
        return
    if not has_door_programming_evidence(panel, config):
        return
    rules = config.get("rules", {})
    if not bool(rules.get("auto_dxf_hinge_side_detection", True)):
        return
    side = dxf_hinge_side_candidate(panel.source_dxf)
    if side is None:
        return
    dxf_cut_in = dxf_hinge_side_has_cut_in(panel.source_dxf, side, config)
    previous = panel.hinge_side or "unknown"
    side_changed = panel.hinge_side != side
    if side_changed:
        if panel.hinge_side is not None and not (panel.hinges_up or dxf_cut_in or has_door_cut_in(panel, config)):
            return
        panel.hinge_side = side
        panel.reasons.append(f"DXF hinge side {side} overrides {previous}")
    moved_off_hinge = False
    if dxf_cut_in and not panel.hinges_up:
        panel.hinges_up = True
        remove_hinge_side_reasons(panel)
        panel.reasons.append(f"hinge side {side}; hinges up from DXF K-cut/kick-in/jut-out")
        moved_off_hinge = True
    elif dxf_cut_in:
        moved_off_hinge = True
    if dxf_cut_in and needs_manual_review_for_fps_cut(panel, config):
        add_panel_warning(panel, "FP-S cut-in/cut-out detected; manual DXF review required.")
    if not side_changed and not dxf_cut_in:
        return
    panel.hinge_side = side
    panel.rotation_degrees = door_rotation_for_hinge_side(side, panel.hinges_up)
    panel.indicator_corner = door_indicator_corner_for_hinge_side(side, panel.hinges_up)
    if moved_off_hinge:
        panel.indicator_corner = door_indicator_corner_off_hinge_side(side, panel.hinges_up)
        panel.reasons.append(f"Denver K-cut indicator moved off hinge side: {panel.indicator_corner}")


def remove_hinge_side_reasons(panel: Panel) -> None:
    panel.reasons = [
        reason
        for reason in panel.reasons
        if not re.match(r"^hinge side (?:left|right); hinges (?:up|down)$", reason)
    ]


def dxf_hinge_side_candidate(path: Path) -> str | None:
    scores = {
        "left": dxf_hinge_side_score(path, "left"),
        "right": dxf_hinge_side_score(path, "right"),
    }
    left_score = scores["left"]
    right_score = scores["right"]
    if left_score < 4 and right_score < 4:
        return None
    if abs(left_score - right_score) < 3:
        return None
    return "left" if left_score > right_score else "right"


def dxf_hinge_side_has_cut_in(path: Path, side: str, config: dict[str, Any]) -> bool:
    if side not in {"left", "right"}:
        return False
    segments = dxf_side_segments(path, side)
    if len(segments) < 2:
        return False
    points = [point for start, end in segments for point in (start, end)]
    if not points:
        return False
    span = max(y for _, y in points) - min(y for _, y in points)
    if span <= 0:
        return False
    rules = config.get("rules", {})
    min_ratio = parse_float(rules.get("auto_dxf_cut_in_min_segment_ratio", 0.20), 0.20)
    min_degrees = parse_float(rules.get("auto_dxf_cut_in_min_degrees", 0.05), 0.05)
    min_offset = parse_float(rules.get("auto_dxf_cut_in_min_offset", 0.03125), 0.03125)
    long_segments = []
    x_values: list[float] = []
    vertical_segment_x_values: list[float] = []
    has_angled_segment = False
    for start, end in segments:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        if length < span * min_ratio:
            continue
        if abs(dy) >= span * 0.90 and abs(dx) >= min_offset:
            continue
        long_segments.append((start, end))
        x_values.extend([start[0], end[0]])
        if abs(dy) >= length * 0.80:
            vertical_segment_x_values.append((start[0] + end[0]) / 2)
        angle = math.degrees(math.atan2(dy, dx))
        deviation = abs(normalize_axis_deviation(angle - 90))
        deviation = min(deviation, abs(normalize_axis_deviation(angle + 90)))
        if deviation >= min_degrees:
            has_angled_segment = True
    if len(long_segments) < 2:
        return False
    has_parallel_offset = (
        len(vertical_segment_x_values) >= 2
        and (max(vertical_segment_x_values) - min(vertical_segment_x_values)) >= min_offset
    )
    return (has_angled_segment or has_parallel_offset) and (max(x_values) - min(x_values)) >= min_offset


def dxf_hinge_side_score(path: Path, side: str) -> float:
    segments = dxf_side_segments(path, side)
    if not segments:
        return 0.0
    score = 0.0
    long_segments = 0
    angled_segments = 0
    vertical_segment_x_values: list[float] = []
    for start, end in segments:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        if length >= 5:
            long_segments += 1
            score += 1.5
            if abs(dy) >= length * 0.80:
                vertical_segment_x_values.append((start[0] + end[0]) / 2)
        if length >= 2:
            deviation = abs(normalize_axis_deviation(math.degrees(math.atan2(dy, dx)) - 90))
            deviation = min(deviation, abs(normalize_axis_deviation(math.degrees(math.atan2(dy, dx)) + 90)))
            if deviation >= 0.08:
                angled_segments += 1
                score += min(4.0, deviation * 6)
    if long_segments >= 2:
        score += 2.0
    if angled_segments:
        score += 2.0
    if len(vertical_segment_x_values) >= 2 and max(vertical_segment_x_values) - min(vertical_segment_x_values) >= 0.03125:
        score += 2.5
    return score


def adjust_denver_panel_square_side(panel: Panel) -> None:
    if panel.source_dxf is None:
        return
    square_corners = dxf_square_corners(panel.source_dxf)
    square_sides = dxf_square_sides(panel.source_dxf)
    current_bottom = side_for_rotation(panel.rotation_degrees or 0)
    current_corner = denver_grabber_corner_for_rotation(panel.rotation_degrees)
    if current_bottom in square_sides and current_corner in square_corners:
        return
    target_side = choose_square_panel_bottom_side(panel, square_sides)
    if target_side is not None:
        panel.rotation_degrees = rotation_for_bottom_side(target_side)
        panel.indicator_corner = denver_indicator_corner_for_bottom_side(target_side)
        panel.reasons.append(f"Denver panel uses square {target_side} side down")
        return
    target_rotation = choose_square_panel_grabber_rotation(panel, square_corners)
    if target_rotation is not None:
        panel.rotation_degrees = target_rotation
        panel.indicator_corner = denver_grabber_corner_for_rotation(target_rotation)
        panel.reasons.append(f"Denver panel uses square {panel.indicator_corner} grabber corner")
        return
    panel.reasons.append("no square long side/corner found; kept long side down")


def choose_square_panel_bottom_side(panel: Panel, square_sides: set[str]) -> str | None:
    if panel.source_dxf is not None:
        source_dims = dxf_outline_dimensions(panel.source_dxf)
        if source_dims is not None:
            source_width, source_height = source_dims
            if source_height > source_width + 0.01:
                candidates = ("right", "left")
            elif source_width > source_height + 0.01:
                candidates = ("bottom",)
            else:
                candidates = ("bottom", "right", "left")
            for side in candidates:
                if side in square_sides:
                    return side
            return None
    if panel.width is not None and panel.height is not None:
        if panel.height > panel.width:
            candidates = ("left", "right")
        elif panel.width > panel.height:
            candidates = ("bottom",)
        else:
            candidates = ("bottom", "left", "right")
    else:
        candidates = ("bottom", "left", "right")
    for side in candidates:
        if side in square_sides:
            return side
    return None


def choose_square_panel_grabber_rotation(panel: Panel, square_corners: set[str]) -> float | None:
    if not square_corners:
        return None
    if panel.source_dxf is not None:
        source_dims = dxf_outline_dimensions(panel.source_dxf)
        if source_dims is not None:
            source_width, source_height = source_dims
            if source_height > source_width + 0.01:
                candidates = (-90.0, 90.0)
            elif source_width > source_height + 0.01:
                candidates = (0.0,)
            else:
                candidates = (0.0, 90.0, -90.0)
        else:
            candidates = ()
    elif panel.width is not None and panel.height is not None:
        if panel.height > panel.width:
            candidates = (90.0, -90.0)
        elif panel.width > panel.height:
            candidates = (0.0,)
        else:
            candidates = (0.0, 90.0, -90.0)
    else:
        candidates = (0.0, 90.0, -90.0)
    current = panel.rotation_degrees or 0
    ordered = sorted(candidates, key=lambda value: 0 if abs(value - current) <= 1 else 1)
    for rotation in ordered:
        if denver_grabber_corner_for_rotation(rotation) in square_corners:
            return rotation
    return None


def side_for_rotation(rotation_degrees: float) -> str:
    normalized = ((rotation_degrees + 180) % 360) - 180
    if abs(normalized - 90) <= 1:
        return "left"
    if abs(normalized + 90) <= 1:
        return "right"
    if abs(abs(normalized) - 180) <= 1:
        return "top"
    return "bottom"


def rotation_for_bottom_side(side: str) -> float:
    return {
        "bottom": 0.0,
        "left": 90.0,
        "right": -90.0,
        "top": 180.0,
    }.get(side, 0.0)


def denver_indicator_corner_for_bottom_side(side: str) -> str:
    return denver_grabber_corner_for_rotation(rotation_for_bottom_side(side))


def dxf_outline_dimensions(path: Path) -> tuple[float, float] | None:
    segments = collect_dxf_outer_line_segments(path)
    points = [point for start, end in segments for point in (start, end)]
    if not points:
        return None
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_x = max(x for x, _ in points)
    max_y = max(y for _, y in points)
    return max_x - min_x, max_y - min_y


def dxf_square_corners(path: Path) -> set[str]:
    segments = collect_dxf_outer_line_segments(path)
    points = [point for start, end in segments for point in (start, end)]
    if len(points) < 4:
        return set()
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_x = max(x for x, _ in points)
    max_y = max(y for _, y in points)
    corners = {
        "bottom_left": (min_x, min_y),
        "bottom_right": (max_x, min_y),
        "top_left": (min_x, max_y),
        "top_right": (max_x, max_y),
    }
    square: set[str] = set()
    axis_tolerance = 0.015
    corner_tolerance = 0.125
    for name, (corner_x, corner_y) in corners.items():
        corner = nearest_point(points, (corner_x, corner_y), corner_tolerance)
        if corner is None:
            continue
        vectors = connected_vectors_at_point(segments, corner, corner_tolerance)
        has_horizontal = any(abs(vector[1]) <= axis_tolerance and abs(vector[0]) > axis_tolerance for vector in vectors)
        has_vertical = any(abs(vector[0]) <= axis_tolerance and abs(vector[1]) > axis_tolerance for vector in vectors)
        if has_horizontal and has_vertical:
            square.add(name)
    return square


def nearest_point(
    points: list[tuple[float, float]],
    target: tuple[float, float],
    tolerance: float,
) -> tuple[float, float] | None:
    best: tuple[float, tuple[float, float]] | None = None
    for point in points:
        distance = math.hypot(point[0] - target[0], point[1] - target[1])
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, point)
    return best[1] if best else None


def connected_vectors_at_point(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    point: tuple[float, float],
    tolerance: float,
) -> list[tuple[float, float]]:
    vectors: list[tuple[float, float]] = []
    for start, end in segments:
        if math.hypot(start[0] - point[0], start[1] - point[1]) <= tolerance:
            vectors.append((end[0] - start[0], end[1] - start[1]))
        elif math.hypot(end[0] - point[0], end[1] - point[1]) <= tolerance:
            vectors.append((start[0] - end[0], start[1] - end[1]))
    return vectors


def dxf_square_sides(path: Path) -> set[str]:
    corners = dxf_square_corners(path)
    sides: set[str] = set()
    if {"bottom_left", "top_left"}.issubset(corners):
        sides.add("left")
    if {"bottom_right", "top_right"}.issubset(corners):
        sides.add("right")
    if {"bottom_left", "bottom_right"}.issubset(corners):
        sides.add("bottom")
    if {"top_left", "top_right"}.issubset(corners):
        sides.add("top")
    return sides


def collect_dxf_outer_line_points(path: Path) -> list[tuple[float, float]]:
    return [point for start, end in collect_dxf_outer_line_segments(path) for point in (start, end)]


def collect_dxf_outer_line_segments(path: Path) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    lines = path.read_text(encoding="latin1", errors="ignore").splitlines()
    pairs = [[lines[i].strip(), lines[i + 1].strip()] for i in range(0, len(lines) - 1, 2)]
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    in_entities = False
    entity: dict[str, list[str] | str] | None = None

    def flush() -> None:
        if not entity or entity.get("type") != "LINE":
            return
        if str(entity.get("8", "0")) != "0":
            return
        try:
            x1 = float(entity["10"][0])  # type: ignore[index]
            y1 = float(entity["20"][0])  # type: ignore[index]
            x2 = float(entity["11"][0])  # type: ignore[index]
            y2 = float(entity["21"][0])  # type: ignore[index]
        except Exception:
            return
        segments.append(((x1, y1), (x2, y2)))

    for code, value in pairs:
        if code == "2" and value.upper() == "ENTITIES":
            in_entities = True
            continue
        if not in_entities:
            continue
        if code == "0":
            flush()
            if value.upper() == "ENDSEC":
                in_entities = False
                entity = None
            elif value.upper() == "LINE":
                entity = {"type": "LINE"}
            else:
                entity = {"type": value.upper()}
            continue
        if entity is not None and code in {"8", "10", "20", "11", "21"}:
            if code == "8":
                entity[code] = value
            else:
                entity.setdefault(code, [])  # type: ignore[union-attr]
                entity[code].append(value)  # type: ignore[index,union-attr]
    flush()
    return segments


def collect_dxf_preview_segments(path: Path) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    pairs = read_dxf_pairs(path)
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    in_entities = False
    current_type: str | None = None
    current: dict[str, list[str]] = {}
    active_polyline: list[tuple[float, float]] | None = None
    active_polyline_closed = False

    def append_polyline(points: list[tuple[float, float]], closed: bool) -> None:
        if len(points) < 2:
            return
        for start, end in zip(points, points[1:]):
            segments.append((start, end))
        if closed:
            segments.append((points[-1], points[0]))

    def values(code: str) -> list[str]:
        return current.get(code, [])

    def first_float(code: str) -> float | None:
        try:
            return float(values(code)[0])
        except Exception:
            return None

    def polyline_points() -> list[tuple[float, float]]:
        xs = values("10")
        ys = values("20")
        points: list[tuple[float, float]] = []
        for x_value, y_value in zip(xs, ys):
            try:
                points.append((float(x_value), float(y_value)))
            except ValueError:
                continue
        return points

    def flag_closed(default: bool = False) -> bool:
        try:
            return any(int(float(value)) & 1 for value in values("70"))
        except Exception:
            return default

    def append_circle_segments(cx: float, cy: float, radius: float, start_angle: float, end_angle: float) -> None:
        if radius <= 0:
            return
        sweep = (end_angle - start_angle) % 360
        if sweep <= 1e-9:
            sweep = 360.0
        steps = max(12, min(72, int(abs(sweep) / 10) + 1))
        points: list[tuple[float, float]] = []
        for index in range(steps + 1):
            angle = math.radians(start_angle + sweep * index / steps)
            points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
        append_polyline(points, closed=abs(sweep - 360.0) <= 1e-9)

    def flush() -> None:
        nonlocal active_polyline, active_polyline_closed
        if current_type == "LINE":
            x1 = first_float("10")
            y1 = first_float("20")
            x2 = first_float("11")
            y2 = first_float("21")
            if None not in (x1, y1, x2, y2):
                segments.append(((x1, y1), (x2, y2)))  # type: ignore[arg-type]
        elif current_type == "LWPOLYLINE":
            append_polyline(polyline_points(), flag_closed())
        elif current_type == "POLYLINE":
            active_polyline = []
            active_polyline_closed = flag_closed()
        elif current_type == "VERTEX" and active_polyline is not None:
            x = first_float("10")
            y = first_float("20")
            if x is not None and y is not None:
                active_polyline.append((x, y))
        elif current_type == "CIRCLE":
            cx = first_float("10")
            cy = first_float("20")
            radius = first_float("40")
            if cx is not None and cy is not None and radius is not None:
                append_circle_segments(cx, cy, radius, 0.0, 360.0)
        elif current_type == "ARC":
            cx = first_float("10")
            cy = first_float("20")
            radius = first_float("40")
            start = first_float("50")
            end = first_float("51")
            if None not in (cx, cy, radius, start, end):
                append_circle_segments(cx, cy, radius, start, end)  # type: ignore[arg-type]

    for code_raw, value_raw in pairs:
        code = code_raw.strip()
        value = value_raw.strip()
        upper = value.upper()
        if code == "2" and upper == "ENTITIES":
            in_entities = True
            continue
        if not in_entities:
            continue
        if code == "0":
            flush()
            if upper == "SEQEND":
                if active_polyline is not None:
                    append_polyline(active_polyline, active_polyline_closed)
                active_polyline = None
                active_polyline_closed = False
                current_type = None
                current = {}
                continue
            if upper == "ENDSEC":
                in_entities = False
                current_type = None
                current = {}
                continue
            current_type = upper
            current = {}
            continue
        if current_type is not None:
            current.setdefault(code, []).append(value)
    flush()
    if active_polyline is not None:
        append_polyline(active_polyline, active_polyline_closed)
    return segments


def estimate_panel_bbox(
    reader: PdfReader,
    page_index: int,
    use_outer_edges: bool = False,
) -> tuple[float, float, float, float] | None:
    current: tuple[float, float] | None = None
    vertical_x: list[float] = []
    horizontal_y: list[float] = []
    min_len = 35.0

    for operands, op, matrix in content_operations_with_matrices(reader, page_index):
        if op == "m" and len(operands) >= 2:
            current = transform_pdf_point(matrix, float(operands[0]), float(operands[1]))
        elif op == "l" and current is not None and len(operands) >= 2:
            end = transform_pdf_point(matrix, float(operands[0]), float(operands[1]))
            dx = end[0] - current[0]
            dy = end[1] - current[1]
            length = math.hypot(dx, dy)
            in_body = all(15 <= x <= 590 for x in (current[0], end[0])) and all(
                20 <= y <= 660 for y in (current[1], end[1])
            )
            if in_body and length >= min_len:
                if abs(dx) <= 0.25:
                    vertical_x.append((current[0] + end[0]) / 2)
                elif abs(dy) <= 0.25:
                    horizontal_y.append((current[1] + end[1]) / 2)
            current = end

    xs = unique_sorted(vertical_x, tolerance=3.0)
    ys = unique_sorted(horizontal_y, tolerance=3.0)
    if use_outer_edges and len(xs) >= 2:
        left, right = xs[0], xs[-1]
    elif len(xs) >= 4:
        left, right = xs[1], xs[-2]
    elif len(xs) >= 2:
        left, right = xs[0], xs[-1]
    else:
        return None

    if use_outer_edges and len(ys) >= 2:
        bottom, top = ys[0], ys[-1]
    elif len(ys) >= 4:
        bottom, top = ys[1], ys[-2]
    elif len(ys) >= 2:
        bottom, top = ys[0], ys[-1]
    else:
        return None

    if right - left < 40 or top - bottom < 40:
        return None
    return left, bottom, right, top


def estimate_panel_outline_bbox(
    reader: PdfReader,
    page_index: int,
    expected_width: float | None = None,
    expected_height: float | None = None,
) -> tuple[float, float, float, float] | None:
    segments = collect_page_line_segments(reader, page_index, min_length=4.0)
    components = connected_line_components(segments, tolerance=4.0)
    best: tuple[float, tuple[float, float, float, float]] | None = None
    for component in components:
        points = [point for start, end, _ in component for point in (start, end)]
        if not points:
            continue
        left = min(x for x, _ in points)
        right = max(x for x, _ in points)
        bottom = min(y for _, y in points)
        top = max(y for _, y in points)
        width = right - left
        height = top - bottom
        area = width * height
        total_length = sum(length for _, _, length in component)
        if width < 50 or height < 50 or area < 8000 or total_length < 250:
            continue
        horizontal = sum(1 for start, end, _ in component if abs(start[1] - end[1]) <= 0.5)
        vertical = sum(1 for start, end, _ in component if abs(start[0] - end[0]) <= 0.5)
        if horizontal == 0 or vertical == 0:
            continue
        score = total_length + area * 0.035 + min(horizontal, vertical) * 35
        if expected_width and expected_height:
            observed_ratio = width / height if height else 0
            expected_ratio = expected_width / expected_height if expected_height else 0
            if observed_ratio and expected_ratio:
                ratio_error = min(
                    abs(math.log(observed_ratio / expected_ratio)),
                    abs(math.log(observed_ratio / (1 / expected_ratio))),
                )
                score += max(0.0, 650.0 - ratio_error * 500.0)
        if best is None or score > best[0]:
            best = (score, (left, bottom, right, top))
    return best[1] if best else None


def collect_page_line_segments(
    reader: PdfReader,
    page_index: int,
    min_length: float,
) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
    segments: list[tuple[tuple[float, float], tuple[float, float], float]] = []
    current: tuple[float, float] | None = None
    for operands, op, matrix in content_operations_with_matrices(reader, page_index):
        if op == "m" and len(operands) >= 2:
            current = transform_pdf_point(matrix, float(operands[0]), float(operands[1]))
        elif op == "l" and current is not None and len(operands) >= 2:
            end = transform_pdf_point(matrix, float(operands[0]), float(operands[1]))
            length = math.hypot(end[0] - current[0], end[1] - current[1])
            in_body = all(0 <= x <= 612 for x in (current[0], end[0])) and all(
                0 <= y <= 690 for y in (current[1], end[1])
            )
            if in_body and length >= min_length:
                segments.append((current, end, length))
            current = end
    return segments


def connected_line_components(
    segments: list[tuple[tuple[float, float], tuple[float, float], float]],
    tolerance: float,
) -> list[list[tuple[tuple[float, float], tuple[float, float], float]]]:
    if not segments:
        return []
    parent = list(range(len(segments)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    def close(a: tuple[float, float], b: tuple[float, float]) -> bool:
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= tolerance

    for index, (start, end, _) in enumerate(segments):
        for other_index in range(index):
            other_start, other_end, _ = segments[other_index]
            if close(start, other_start) or close(start, other_end) or close(end, other_start) or close(end, other_end):
                union(index, other_index)

    components: dict[int, list[tuple[tuple[float, float], tuple[float, float], float]]] = {}
    for index, segment in enumerate(segments):
        components.setdefault(find(index), []).append(segment)
    return list(components.values())


def unique_sorted(values: Iterable[float], tolerance: float) -> list[float]:
    result: list[float] = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > tolerance:
            result.append(value)
        else:
            result[-1] = (result[-1] + value) / 2
    return result


def make_overlay_page(
    width: float,
    height: float,
    panel: Panel,
    order_number: str,
    bbox: tuple[float, float, float, float] | None,
    indicator_bbox: tuple[float, float, float, float] | None,
    marker_bbox: tuple[float, float, float, float] | None,
    obstacles: list[tuple[float, float, float, float]],
    config: dict[str, Any],
) -> bytes:
    pdf_cfg = config.get("pdf", {})
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))
    color_values = pdf_cfg.get("label_color_rgb", [0, 120, 212])
    label_color = Color(color_values[0] / 255, color_values[1] / 255, color_values[2] / 255)
    font_size = panel.label_font_size or float(pdf_cfg.get("label_font_size", 21))
    label_bbox = marker_bbox or bbox
    active_marker_bbox = marker_bbox or (indicator_bbox if panel.machine == "WJ" and indicator_bbox is not None else bbox)
    marker_avoid_rect = (
        indicator_marker_rect(
            panel.machine,
            panel.indicator_corner,
            active_marker_bbox,
            width,
            height,
            pdf_cfg,
            precise_edges=marker_bbox is not None,
            panel=panel,
        )
        if panel.indicator_corner and panel.machine
        else None
    )

    remake_rect: tuple[float, float, float, float] | None = None
    if panel.remake_excluded or panel.manual_x:
        draw_remake_x(c, width, height, pdf_cfg, label_color)
        c.save()
        return packet.getvalue()

    remake_text = panel.remake_text or "REMAKE"
    diamon_text = panel.diamon_fusion_text or "DIAMON FUSION"
    if panel.remake and not panel.hide_remake:
        remake_rect = draw_remake_banner(c, width, height, pdf_cfg, bbox, indicator_bbox, label_color, panel, remake_text)

    lines = override_text_lines(panel.label_text) or [f"{order_number}.{panel.item}"]
    if panel.machine and not panel.label_text:
        lines.append(panel.machine)

    avoid_rects: list[tuple[float, float, float, float]] = []
    if marker_avoid_rect is not None:
        avoid_rects.append(marker_avoid_rect)
    if remake_rect is not None:
        avoid_rects.append(remake_rect)
    if panel.diamon_fusion and not panel.hide_diamon_fusion:
        df_font = panel.diamon_fusion_font_size or float(pdf_cfg.get("diamon_fusion_font_size", 36))
        if remake_rect is not None:
            df_x, df_y, df_rect = choose_diamon_above_rect(width, height, diamon_text, df_font, remake_rect, pdf_cfg)
        else:
            df_x, df_y, df_font, df_rect = choose_diamon_banner_position(
                width,
                height,
                pdf_cfg,
                bbox,
                indicator_bbox,
                diamon_text,
                df_font,
                obstacles,
                avoid_rects,
                panel,
            )
        if panel.diamon_fusion_x is not None and panel.diamon_fusion_y is not None:
            df_x, df_y = panel.diamon_fusion_x, panel.diamon_fusion_y
            df_width = stringWidth(diamon_text, "Helvetica-Bold", df_font) + 12
            df_height = df_font + 10
            df_rect = (df_x - df_width / 2, df_y - 4, df_x + df_width / 2, df_y + df_height)
            if remake_rect is not None and rects_overlap(pad_rect(df_rect, 4), pad_rect(remake_rect, 2)):
                df_x, df_y, df_rect = choose_diamon_above_rect(width, height, diamon_text, df_font, remake_rect, pdf_cfg)
                add_panel_warning(panel, "Manual DIAMON FUSION position overlapped REMAKE; moved above REMAKE.")
        avoid_rects.append(df_rect)
        c.setFillColor(label_color)
        c.setStrokeColor(label_color)
        c.setFont("Helvetica-Bold", df_font)
        c.drawCentredString(df_x, df_y, diamon_text)

    if not panel.hide_label:
        x, y = choose_label_position(width, height, label_bbox, lines, font_size, obstacles, avoid_rects, panel, pdf_cfg)
        if panel.label_x is not None and panel.label_y is not None:
            x, y = panel.label_x, panel.label_y
        draw_centered_lines(c, lines, x, y, font_size, label_color)

    if panel.indicator_corner and panel.machine and not panel.hide_indicator:
        draw_indicator(
            c,
            panel.machine,
            panel.indicator_corner,
            active_marker_bbox,
            width,
            height,
            pdf_cfg,
            label_color,
            precise_edges=marker_bbox is not None,
            panel=panel,
        )

    c.save()
    return packet.getvalue()


def draw_remake_banner(
    c: canvas.Canvas,
    width: float,
    height: float,
    pdf_cfg: dict[str, Any],
    piece_bbox: tuple[float, float, float, float] | None,
    top_measurement_bbox: tuple[float, float, float, float] | None,
    color: Color,
    panel: Panel | None = None,
    text: str = "REMAKE",
) -> tuple[float, float, float, float]:
    x, y, font_size, rect = choose_remake_banner_position(width, height, pdf_cfg, piece_bbox, top_measurement_bbox, panel, text)
    c.setFillColor(color)
    c.setStrokeColor(color)
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(x, y, text)
    return rect


def choose_remake_banner_position(
    width: float,
    height: float,
    pdf_cfg: dict[str, Any],
    piece_bbox: tuple[float, float, float, float] | None,
    top_measurement_bbox: tuple[float, float, float, float] | None,
    panel: Panel | None = None,
    text: str = "REMAKE",
) -> tuple[float, float, float, tuple[float, float, float, float]]:
    remake_cfg = pdf_cfg.get("remake", {})
    font_size = panel.remake_font_size if panel is not None and panel.remake_font_size else parse_float(remake_cfg.get("font_size", 40), 40)
    x, y, rect = banner_text_position(width, height, pdf_cfg, piece_bbox, top_measurement_bbox, text, font_size)
    if panel is not None and panel.remake_x is not None and panel.remake_y is not None:
        x, y = panel.remake_x, panel.remake_y
        text_width = stringWidth(text, "Helvetica-Bold", font_size) + 12
        text_height = font_size + 10
        rect = (x - text_width / 2, y - 4, x + text_width / 2, y + text_height)
    return x, y, font_size, rect


def banner_text_position(
    width: float,
    height: float,
    pdf_cfg: dict[str, Any],
    piece_bbox: tuple[float, float, float, float] | None,
    top_measurement_bbox: tuple[float, float, float, float] | None,
    text: str,
    font_size: float,
) -> tuple[float, float, tuple[float, float, float, float]]:
    remake_cfg = pdf_cfg.get("remake", {})
    if piece_bbox is not None and top_measurement_bbox is not None and top_measurement_bbox[3] > piece_bbox[3]:
        y = (piece_bbox[3] + top_measurement_bbox[3]) / 2
        y += parse_float(remake_cfg.get("midpoint_nudge_y", 0), 0)
    elif piece_bbox is not None:
        y = piece_bbox[3] + parse_float(remake_cfg.get("above_piece_y", 28), 28)
    else:
        y = parse_float(remake_cfg.get("banner_y", height - 120), height - 120)
    text_width = stringWidth(text, "Helvetica-Bold", font_size) + 12
    text_height = font_size + 10
    x = width / 2
    return x, y, (x - text_width / 2, y - 4, x + text_width / 2, y + text_height)


def choose_diamon_banner_position(
    page_width: float,
    page_height: float,
    pdf_cfg: dict[str, Any],
    piece_bbox: tuple[float, float, float, float] | None,
    top_measurement_bbox: tuple[float, float, float, float] | None,
    text: str,
    font_size: float,
    obstacles: list[tuple[float, float, float, float]],
    avoid_rects: list[tuple[float, float, float, float]],
    panel: Panel,
) -> tuple[float, float, float, tuple[float, float, float, float]]:
    min_font = parse_float(pdf_cfg.get("diamon_fusion_min_font_size", 28), 28)
    edge_gap = parse_float(pdf_cfg.get("diamon_fusion_edge_gap", 8), 8)
    anchor_top = piece_bbox[3] if piece_bbox is not None else None
    x_ratios = [0.5, 0.58, 0.42, 0.66, 0.34]
    for candidate_font in descending_font_sizes(font_size, min_font):
        text_width = stringWidth(text, "Helvetica-Bold", candidate_font) + 12
        text_height = candidate_font + 10
        slots: list[tuple[float, float]] = []
        if anchor_top is not None:
            slots.append((anchor_top, anchor_top + edge_gap + 4))
        else:
            slots.append((page_height * 0.60, page_height * 0.60))

        for _, y in slots:
            y += panel.diamon_fusion_nudge_y
            for ratio in x_ratios:
                x = page_width * ratio + panel.diamon_fusion_nudge_x
                rect = (x - text_width / 2, y - 4, x + text_width / 2, y + text_height)
                if rect[0] < 20 or rect[2] > page_width - 20 or rect[1] < 35 or rect[3] > page_height - 35:
                    continue
                if rect_is_clear(rect, obstacles, avoid_rects):
                    return x, y, candidate_font, rect

    fallback_font = max(min_font, min(font_size, parse_float(pdf_cfg.get("diamon_fusion_font_size", font_size), font_size)))
    fallback_bbox = piece_bbox
    if anchor_top is not None:
        if fallback_bbox is None:
            fallback_bbox = (page_width * 0.2, 0, page_width * 0.8, anchor_top)
        else:
            fallback_bbox = (fallback_bbox[0], fallback_bbox[1], fallback_bbox[2], anchor_top)
    x, y, rect = banner_text_position(page_width, page_height, pdf_cfg, fallback_bbox, None, text, fallback_font)
    if anchor_top is not None:
        y = anchor_top + edge_gap + 4
    x += panel.diamon_fusion_nudge_x
    y += panel.diamon_fusion_nudge_y
    width = stringWidth(text, "Helvetica-Bold", fallback_font) + 12
    height = fallback_font + 10
    rect = (x - width / 2, y - 4, x + width / 2, y + height)
    return x, y, fallback_font, rect


def descending_font_sizes(font_size: float, min_font: float) -> Iterable[float]:
    current = font_size
    while current >= min_font:
        yield current
        current -= 2
    if current + 2 > min_font:
        yield min_font


def draw_remake_x(c: canvas.Canvas, width: float, height: float, pdf_cfg: dict[str, Any], color: Color) -> None:
    remake_cfg = pdf_cfg.get("remake", {})
    line_width = parse_float(remake_cfg.get("x_line_width", 10), 10)
    margin = parse_float(remake_cfg.get("x_margin", 48), 48)
    c.setStrokeColor(color)
    c.setLineWidth(line_width)
    c.line(margin, margin, width - margin, height - margin)
    c.line(margin, height - margin, width - margin, margin)


def draw_centered_lines(c: canvas.Canvas, lines: list[str], x: float, y: float, font_size: float, color: Color) -> None:
    c.setFillColor(color)
    c.setStrokeColor(color)
    c.setFont(LABEL_FONT, font_size)
    leading = font_size * 1.18
    first_y = y + leading * (len(lines) - 1) / 2
    for index, line in enumerate(lines):
        c.drawCentredString(x, first_y - index * leading, line)


def label_rect(lines: list[str], x: float, y: float, font_size: float) -> tuple[float, float, float, float]:
    leading = font_size * 1.18
    width = max(stringWidth(line, LABEL_FONT, font_size) for line in lines) + 10
    height = leading * len(lines) + 8
    return x - width / 2, y - height / 2, x + width / 2, y + height / 2


def choose_label_position(
    page_width: float,
    page_height: float,
    bbox: tuple[float, float, float, float] | None,
    lines: list[str],
    font_size: float,
    obstacles: list[tuple[float, float, float, float]],
    avoid_rects: list[tuple[float, float, float, float]],
    panel: Panel,
    pdf_cfg: dict[str, Any],
) -> tuple[float, float]:
    if bbox is None:
        bbox = (page_width * 0.2, page_height * 0.16, page_width * 0.8, page_height * 0.7)
    left, bottom, right, top = bbox
    label_width = max(stringWidth(line, LABEL_FONT, font_size) for line in lines) + 10
    label_height = font_size * 1.18 * len(lines) + 8
    preferred_x, preferred_y = label_preference(pdf_cfg, panel)
    label_cfg = pdf_cfg.get("label_position", {})
    center_first = bool(label_cfg.get("center_first", True))
    bias_x = 0.5 if center_first else preferred_x
    bias_y = 0.5 if center_first else preferred_y
    nudge_x, nudge_y = label_nudge_offsets(pdf_cfg, panel)

    inside_candidates = build_label_candidates(preferred_x, preferred_y, center_first=center_first)
    best_inside: tuple[float, float, float] | None = None
    for xr, yr in inside_candidates:
        use_center_without_nudge = (
            center_first
            and not bool(label_cfg.get("center_uses_nudge", False))
            and abs(xr - 0.5) < 0.001
            and abs(yr - 0.5) < 0.001
        )
        local_nudge_x = 0 if use_center_without_nudge else nudge_x
        local_nudge_y = 0 if use_center_without_nudge else nudge_y
        x = left + (right - left) * xr + local_nudge_x
        y = bottom + (top - bottom) * yr + local_nudge_y
        x, y = clamp_label_point_to_bounds(x, y, lines, font_size, bbox)
        x, y = clamp_label_point(x, y, lines, font_size, page_width, page_height)
        rect = label_rect(lines, x, y, font_size)
        if label_width <= (right - left) - 12 and label_height <= (top - bottom) - 12:
            if rect_inside(rect, bbox, margin=4):
                score = placement_score(rect, obstacles, avoid_rects)
                score += position_bias(xr, yr, bias_x, bias_y)
                if best_inside is None or score < best_inside[0]:
                    best_inside = (score, x, y)
                if score <= 2:
                    return x, y

    if best_inside is not None and best_inside[0] <= 80:
        if best_inside[0] > 2:
            add_panel_warning(panel, "Label placed in best available open area inside glass.")
        return best_inside[1], best_inside[2]

    outside_candidates = [
        ((left + right) / 2, top + label_height / 2 + 16),
        ((left + right) / 2, bottom - label_height / 2 - 16),
        (page_width / 2, top + label_height / 2 + 28),
        (page_width / 2, page_height * 0.64),
    ]
    first_in_bounds_outside: tuple[float, float] | None = None
    for x, y in outside_candidates:
        x += nudge_x
        y += nudge_y
        x, y = clamp_label_point(x, y, lines, font_size, page_width, page_height)
        rect = label_rect(lines, x, y, font_size)
        if rect[1] < 45 or rect[3] > page_height - 45:
            continue
        if first_in_bounds_outside is None:
            first_in_bounds_outside = (x, y)
        if rect_is_clear(rect, obstacles, avoid_rects):
            add_panel_warning(panel, "Label placed outside glass to avoid overlapping drawing lines.")
            return x, y

    if first_in_bounds_outside is not None:
        add_panel_warning(panel, "Label placed outside glass because it did not fit cleanly inside.")
        x, y = first_in_bounds_outside
        return x, y

    add_panel_warning(panel, "Could not find fully clear label space; placed at glass center for review.")
    return clamp_label_point((left + right) / 2 + nudge_x, (bottom + top) / 2 + nudge_y, lines, font_size, page_width, page_height)


def fit_label_font_size(
    lines: list[str],
    font_size: float,
    bbox: tuple[float, float, float, float] | None,
    pdf_cfg: dict[str, Any],
) -> float:
    if bbox is None:
        return font_size
    min_font = parse_float(pdf_cfg.get("label_min_font_size", 13), 13)
    available_width = max(20.0, bbox[2] - bbox[0] - 12)
    available_height = max(20.0, bbox[3] - bbox[1] - 12)
    for candidate in descending_font_sizes(font_size, min_font):
        label_width = max(stringWidth(line, LABEL_FONT, candidate) for line in lines) + 10
        label_height = candidate * 1.18 * len(lines) + 8
        if label_width <= available_width and label_height <= available_height:
            return candidate
    return min_font


def choose_diamon_position(
    page_width: float,
    page_height: float,
    bbox: tuple[float, float, float, float] | None,
    text: str,
    font_size: float,
    obstacles: list[tuple[float, float, float, float]],
) -> tuple[float, float, tuple[float, float, float, float]]:
    if bbox is None:
        bbox = (page_width * 0.2, page_height * 0.16, page_width * 0.8, page_height * 0.7)
    left, bottom, right, top = bbox
    width = stringWidth(text, "Helvetica-Bold", font_size) + 12
    height = font_size + 10
    candidates = [
        ((left + right) / 2, top + height / 2 + 14),
        (page_width / 2, top + height / 2 + 22),
        (page_width / 2, page_height * 0.71),
    ]
    for x, y in candidates:
        rect = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        if rect[1] >= 45 and rect[3] <= page_height - 45 and rect_is_clear(rect, obstacles, []):
            return x, y, rect
    x, y = page_width / 2, page_height * 0.71
    rect = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
    return x, y, rect


def choose_diamon_above_rect(
    page_width: float,
    page_height: float,
    text: str,
    font_size: float,
    anchor_rect: tuple[float, float, float, float],
    pdf_cfg: dict[str, Any],
) -> tuple[float, float, tuple[float, float, float, float]]:
    width = stringWidth(text, "Helvetica-Bold", font_size) + 12
    height = font_size + 10
    gap = parse_float(pdf_cfg.get("diamon_fusion_above_remake_gap", 8), 8)
    x = page_width / 2
    y = anchor_rect[3] + gap
    if y + height > page_height - 35:
        y = page_height - 35 - height
    rect = (x - width / 2, y - 4, x + width / 2, y + height)
    return x, y, rect


def rect_inside(
    rect: tuple[float, float, float, float],
    bounds: tuple[float, float, float, float],
    margin: float = 0,
) -> bool:
    return (
        rect[0] >= bounds[0] + margin
        and rect[1] >= bounds[1] + margin
        and rect[2] <= bounds[2] - margin
        and rect[3] <= bounds[3] - margin
    )


def rect_is_clear(
    rect: tuple[float, float, float, float],
    obstacles: list[tuple[float, float, float, float]],
    avoid_rects: list[tuple[float, float, float, float]],
) -> bool:
    padded = pad_rect(rect, 4)
    return not any(rects_overlap(padded, obs) for obs in obstacles + avoid_rects)


def label_preference(pdf_cfg: dict[str, Any], panel: Panel) -> tuple[float, float]:
    label_cfg = pdf_cfg.get("label_position", {})
    preferred_x = parse_float(label_cfg.get("x_ratio", pdf_cfg.get("label_x_ratio", 0.5)), 0.5)
    if panel.machine == "WJ":
        y_default = label_cfg.get("waterjet_y_ratio", label_cfg.get("default_y_ratio", 0.82))
    elif panel.machine.startswith("DENVER"):
        y_default = label_cfg.get("denver_y_ratio", label_cfg.get("default_y_ratio", 0.74))
    else:
        y_default = label_cfg.get("default_y_ratio", pdf_cfg.get("label_y_ratio", 0.74))
    preferred_y = parse_float(y_default, 0.74)
    return clamp_ratio(preferred_x), clamp_ratio(preferred_y)


def apply_label_nudge(
    x: float,
    y: float,
    lines: list[str],
    font_size: float,
    pdf_cfg: dict[str, Any],
    panel: Panel,
    page_width: float,
    page_height: float,
) -> tuple[float, float]:
    nudge_x, nudge_y = label_nudge_offsets(pdf_cfg, panel)
    if not nudge_x and not nudge_y:
        return x, y
    nudged_x = x + nudge_x
    nudged_y = y + nudge_y
    return clamp_label_point(nudged_x, nudged_y, lines, font_size, page_width, page_height)


def label_nudge_offsets(pdf_cfg: dict[str, Any], panel: Panel) -> tuple[float, float]:
    label_cfg = pdf_cfg.get("label_position", {})
    machine_key = "waterjet" if panel.machine == "WJ" else "denver" if panel.machine.startswith("DENVER") else "default"
    nudge_x = parse_float(label_cfg.get("manual_nudge_x", 0), 0) + parse_float(label_cfg.get(f"{machine_key}_nudge_x", 0), 0)
    nudge_y = parse_float(label_cfg.get("manual_nudge_y", 0), 0) + parse_float(label_cfg.get(f"{machine_key}_nudge_y", 0), 0)
    nudge_x += panel.label_nudge_x
    nudge_y += panel.label_nudge_y
    return nudge_x, nudge_y


def clamp_label_point(
    x: float,
    y: float,
    lines: list[str],
    font_size: float,
    page_width: float,
    page_height: float,
) -> tuple[float, float]:
    rect = label_rect(lines, x, y, font_size)
    label_width = rect[2] - rect[0]
    label_height = rect[3] - rect[1]
    x = min(max(x, 25 + label_width / 2), page_width - 25 - label_width / 2)
    y = min(max(y, 25 + label_height / 2), page_height - 25 - label_height / 2)
    return x, y


def clamp_label_point_to_bounds(
    x: float,
    y: float,
    lines: list[str],
    font_size: float,
    bounds: tuple[float, float, float, float],
    margin: float = 7.0,
) -> tuple[float, float]:
    rect = label_rect(lines, x, y, font_size)
    label_width = rect[2] - rect[0]
    label_height = rect[3] - rect[1]
    if label_width > max(0.0, bounds[2] - bounds[0] - margin * 2):
        return x, y
    if label_height > max(0.0, bounds[3] - bounds[1] - margin * 2):
        return x, y
    x = min(max(x, bounds[0] + margin + label_width / 2), bounds[2] - margin - label_width / 2)
    y = min(max(y, bounds[1] + margin + label_height / 2), bounds[3] - margin - label_height / 2)
    return x, y


def clamp_ratio(value: float) -> float:
    return min(max(value, 0.05), 0.95)


def unique_ratios(values: Iterable[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        clamped = clamp_ratio(value)
        if not any(abs(clamped - existing) < 0.001 for existing in result):
            result.append(clamped)
    return result


def build_label_candidates(preferred_x: float, preferred_y: float, center_first: bool = True) -> list[tuple[float, float]]:
    candidates: list[tuple[float, float]] = []
    if center_first:
        y_seed = [0.50, preferred_y, preferred_y - 0.08, preferred_y + 0.08]
        x_seed = [0.50, preferred_x, preferred_x - 0.08, preferred_x + 0.08]
    else:
        y_seed = [preferred_y, preferred_y - 0.08, preferred_y + 0.08, 0.50]
        x_seed = [preferred_x, preferred_x - 0.08, preferred_x + 0.08, 0.50]
    y_ratios = unique_ratios(y_seed + [0.74, 0.82, 0.66, 0.58, 0.90, 0.42, 0.34, 0.26])
    x_ratios = unique_ratios(x_seed + [0.42, 0.58, 0.34, 0.66, 0.26, 0.74])
    for y in y_ratios:
        for x in x_ratios:
            candidates.append((x, y))
    return candidates


def placement_score(
    rect: tuple[float, float, float, float],
    obstacles: list[tuple[float, float, float, float]],
    avoid_rects: list[tuple[float, float, float, float]],
) -> float:
    padded = pad_rect(rect, 3)
    score = 0.0
    for obstacle in obstacles:
        score += rect_overlap_area(padded, obstacle)
    for avoid in avoid_rects:
        score += rect_overlap_area(padded, avoid) * 5
    return score / 100


def position_bias(x_ratio: float, y_ratio: float, preferred_x: float, preferred_y: float) -> float:
    return (abs(x_ratio - preferred_x) * 14) + (abs(y_ratio - preferred_y) * 10)


def rect_overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x_overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    y_overlap = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return x_overlap * y_overlap


def rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def pad_rect(rect: tuple[float, float, float, float], pad: float) -> tuple[float, float, float, float]:
    return rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad


def collect_page_obstacles(reader: PdfReader, page_index: int) -> list[tuple[float, float, float, float]]:
    obstacles = collect_page_drawing_obstacles(reader, page_index)
    obstacles.extend(collect_page_text_obstacles(reader, page_index))
    return obstacles


def collect_page_drawing_obstacles(
    reader: PdfReader,
    page_index: int,
    include_text: bool = False,
) -> list[tuple[float, float, float, float]]:
    obstacles: list[tuple[float, float, float, float]] = []
    current: tuple[float, float] | None = None
    for operands, op, matrix in content_operations_with_matrices(reader, page_index):
        if op == "m" and len(operands) >= 2:
            current = transform_pdf_point(matrix, float(operands[0]), float(operands[1]))
        elif op == "l" and current is not None and len(operands) >= 2:
            end = transform_pdf_point(matrix, float(operands[0]), float(operands[1]))
            if segment_is_relevant(current, end):
                obstacles.append(line_rect(current, end, pad=3))
            current = end
        elif op == "c" and current is not None and len(operands) >= 6:
            pts = [
                current,
                transform_pdf_point(matrix, float(operands[0]), float(operands[1])),
                transform_pdf_point(matrix, float(operands[2]), float(operands[3])),
                transform_pdf_point(matrix, float(operands[4]), float(operands[5])),
            ]
            obstacles.append(points_rect(pts, pad=3))
            current = pts[-1]
        elif op == "re" and len(operands) >= 4:
            x, y, w, h = [float(value) for value in operands[:4]]
            if abs(w) > 500 and abs(h) > 600:
                continue
            if abs(w) > 2 and abs(h) > 2:
                obstacles.append(transformed_rect(matrix, x, y, w, h, pad=2))
    if include_text:
        obstacles.extend(collect_page_text_obstacles(reader, page_index))
    return obstacles


def collect_page_text_obstacles(reader: PdfReader, page_index: int) -> list[tuple[float, float, float, float]]:
    page = reader.pages[page_index]
    obstacles: list[tuple[float, float, float, float]] = []

    def visitor(text: str, cm: list[float], tm: list[float], font_dict: object, font_size: float) -> None:
        value = (text or "").strip()
        if not value:
            return
        try:
            x, y = text_origin_from_matrices(cm, tm)
            size = max(5.0, float(font_size))
        except Exception:
            return
        if not (10 <= x <= 590 and 35 <= y <= 700):
            return
        width = max(len(value) * size * 0.55, 4)
        height = size * 1.25
        obstacles.append((x - 2, y - 2, x + width + 2, y + height + 2))

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return []
    return obstacles


def segment_is_relevant(start: tuple[float, float], end: tuple[float, float]) -> bool:
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length < 5:
        return False
    return all(10 <= point[0] <= 590 and 20 <= point[1] <= 690 for point in (start, end))


def line_rect(start: tuple[float, float], end: tuple[float, float], pad: float) -> tuple[float, float, float, float]:
    return (
        min(start[0], end[0]) - pad,
        min(start[1], end[1]) - pad,
        max(start[0], end[0]) + pad,
        max(start[1], end[1]) + pad,
    )


def points_rect(points: list[tuple[float, float]], pad: float) -> tuple[float, float, float, float]:
    return (
        min(x for x, _ in points) - pad,
        min(y for _, y in points) - pad,
        max(x for x, _ in points) + pad,
        max(y for _, y in points) + pad,
    )


def draw_indicator(
    c: canvas.Canvas,
    machine: str,
    corner: str,
    bbox: tuple[float, float, float, float] | None,
    page_width: float,
    page_height: float,
    pdf_cfg: dict[str, Any],
    marker_color: Color,
    precise_edges: bool = False,
    panel: Panel | None = None,
) -> None:
    geometry = indicator_marker_geometry(
        machine,
        corner,
        bbox,
        page_width,
        page_height,
        pdf_cfg,
        precise_edges=precise_edges,
        panel=panel,
    )
    if geometry is None:
        return
    c.setStrokeColor(marker_color)
    c.setFillColor(marker_color)
    if geometry["kind"] == "wj":
        c.setLineWidth(float(geometry["line_width"]))
        for start, end in geometry["lines"]:
            c.line(start[0], start[1], end[0], end[1])
    else:
        x, y = geometry["center"]
        c.circle(x, y, float(geometry["radius"]), stroke=0, fill=1)


def indicator_marker_geometry(
    machine: str,
    corner: str | None,
    bbox: tuple[float, float, float, float] | None,
    page_width: float,
    page_height: float,
    pdf_cfg: dict[str, Any],
    precise_edges: bool = False,
    panel: Panel | None = None,
) -> dict[str, Any] | None:
    if not machine or not corner:
        return None
    size = (panel.indicator_size if panel is not None and panel.indicator_size else float(pdf_cfg.get("indicator_size", 18)))
    if bbox is None:
        bbox = (page_width * 0.22, page_height * 0.14, page_width * 0.78, page_height * 0.72)
    left, bottom, right, top = bbox
    offset = effective_indicator_offset(float(pdf_cfg.get("indicator_offset", 54)), size, bbox)
    dot_anchors = {
        "bottom_left": (left + offset, bottom + offset),
        "bottom_right": (right - offset, bottom + offset),
        "top_left": (left + offset, top - offset),
        "top_right": (right - offset, top - offset),
    }
    corner_anchors = {
        "bottom_left": (left, bottom),
        "bottom_right": (right, bottom),
        "top_left": (left, top),
        "top_right": (right, top),
    }
    manual_point = (
        (panel.indicator_x, panel.indicator_y)
        if panel is not None and panel.indicator_x is not None and panel.indicator_y is not None
        else None
    )
    if machine == "WJ":
        size = (
            panel.waterjet_indicator_size
            if panel is not None and panel.waterjet_indicator_size
            else parse_float(pdf_cfg.get("waterjet_indicator_size", size), size)
        )
        x, y = corner_anchors.get(corner, corner_anchors["bottom_left"])
        if manual_point is not None:
            x, y = manual_point
        else:
            x, y = apply_indicator_nudge_for_corner(x, y, machine, corner, pdf_cfg, precise_edges=precise_edges, panel=panel)
        line_size = size * parse_float(pdf_cfg.get("waterjet_indicator_length_ratio", 1.6), 1.6)
        if manual_point is None:
            x, y = clamp_waterjet_marker_point(x, y, corner, line_size, page_width, page_height)
        if corner == "bottom_right":
            lines = [((x, y), (x - line_size, y)), ((x, y), (x, y + line_size))]
        elif corner == "top_left":
            lines = [((x, y), (x + line_size, y)), ((x, y), (x, y - line_size))]
        elif corner == "top_right":
            lines = [((x, y), (x - line_size, y)), ((x, y), (x, y - line_size))]
        else:
            lines = [((x, y), (x + line_size, y)), ((x, y), (x, y + line_size))]
        points = [point for line in lines for point in line]
        return {
            "kind": "wj",
            "point": (x, y),
            "size": size,
            "lines": lines,
            "line_width": parse_float(pdf_cfg.get("waterjet_indicator_line_width", 6), 6),
            "rect": points_rect(points, 8),
        }
    x, y = dot_anchors.get(corner, dot_anchors["bottom_left"])
    if manual_point is not None:
        x, y = manual_point
    else:
        x, y = apply_indicator_nudge_for_corner(x, y, machine, corner, pdf_cfg, precise_edges=precise_edges, panel=panel)
        x, y = clamp_denver_marker_point(x, y, size, page_width, page_height)
    radius = size / 2
    return {
        "kind": "dot",
        "center": (x, y),
        "size": size,
        "point": (x, y),
        "radius": radius,
        "rect": (x - radius - 6, y - radius - 6, x + radius + 6, y + radius + 6),
    }


def indicator_marker_rect(
    machine: str,
    corner: str | None,
    bbox: tuple[float, float, float, float] | None,
    page_width: float,
    page_height: float,
    pdf_cfg: dict[str, Any],
    precise_edges: bool = False,
    panel: Panel | None = None,
) -> tuple[float, float, float, float] | None:
    if not machine or not corner:
        return None
    geometry = indicator_marker_geometry(
        machine,
        corner,
        bbox,
        page_width,
        page_height,
        pdf_cfg,
        precise_edges=precise_edges,
        panel=panel,
    )
    return None if geometry is None else geometry["rect"]


def nearest_indicator_corner_for_point(
    machine: str,
    point: tuple[float, float],
    bbox: tuple[float, float, float, float] | None,
    page_width: float,
    page_height: float,
    pdf_cfg: dict[str, Any],
    precise_edges: bool = False,
    allowed_denver_only: bool = True,
) -> str:
    best: tuple[float, str] | None = None
    corners = (
        ("bottom_left", "top_right")
        if machine.startswith("DENVER") and allowed_denver_only
        else ("top_left", "bottom_right")
        if machine == "WJ"
        else ("bottom_left", "bottom_right", "top_left", "top_right")
    )
    for corner in corners:
        geometry = indicator_marker_geometry(
            machine,
            corner,
            bbox,
            page_width,
            page_height,
            pdf_cfg,
            precise_edges=precise_edges,
            panel=None,
        )
        if geometry is None:
            continue
        anchor = geometry["point"]
        distance = math.hypot(float(point[0]) - anchor[0], float(point[1]) - anchor[1])
        if best is None or distance < best[0]:
            best = (distance, corner)
    return best[1] if best is not None else "bottom_left"


def apply_indicator_nudge(
    x: float,
    y: float,
    machine: str,
    pdf_cfg: dict[str, Any],
) -> tuple[float, float]:
    nudge_cfg = pdf_cfg.get("indicator_nudge", {})
    machine_key = "waterjet" if machine == "WJ" else "denver"
    nudge_x = parse_float(nudge_cfg.get("x", 0), 0) + parse_float(nudge_cfg.get(f"{machine_key}_x", 0), 0)
    nudge_y = parse_float(nudge_cfg.get("y", 0), 0) + parse_float(nudge_cfg.get(f"{machine_key}_y", 0), 0)
    return x + nudge_x, y + nudge_y


def apply_indicator_nudge_for_corner(
    x: float,
    y: float,
    machine: str,
    corner: str,
    pdf_cfg: dict[str, Any],
    precise_edges: bool = False,
    panel: Panel | None = None,
) -> tuple[float, float]:
    nudge_cfg = pdf_cfg.get("indicator_nudge", {})
    machine_key = "waterjet" if machine == "WJ" else "denver"
    if precise_edges and machine == "WJ":
        nudge_x = parse_float(nudge_cfg.get("waterjet_outline_x", 0), 0)
        nudge_y = parse_float(nudge_cfg.get("waterjet_outline_y", 0), 0)
        if panel is not None:
            nudge_x += panel.indicator_nudge_x
            nudge_y += panel.indicator_nudge_y
        return x + nudge_x, y + nudge_y
    else:
        nudge_x = parse_float(nudge_cfg.get("x", 0), 0) + parse_float(nudge_cfg.get(f"{machine_key}_x", 0), 0)
        nudge_y = parse_float(nudge_cfg.get("y", 0), 0) + parse_float(nudge_cfg.get(f"{machine_key}_y", 0), 0)
    if panel is not None:
        nudge_x += panel.indicator_nudge_x
        nudge_y += panel.indicator_nudge_y
    if machine == "WJ":
        if "right" in corner:
            nudge_x *= -1
        if "top" in corner:
            nudge_y *= -1
    return x + nudge_x, y + nudge_y


def effective_indicator_offset(
    configured_offset: float,
    size: float,
    bbox: tuple[float, float, float, float],
) -> float:
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    minimum = size / 2 + 10
    dynamic_cap = max(minimum, min(width, height) * 0.10)
    return min(configured_offset, dynamic_cap)


def clamp_waterjet_marker_point(
    x: float,
    y: float,
    corner: str,
    line_size: float,
    page_width: float,
    page_height: float,
) -> tuple[float, float]:
    margin = 24.0
    if "right" in corner:
        x = min(max(x, margin + line_size), page_width - margin)
    else:
        x = min(max(x, margin), page_width - margin - line_size)
    if "top" in corner:
        y = min(max(y, margin + line_size), page_height - margin)
    else:
        y = min(max(y, margin), page_height - margin - line_size)
    return x, y


def clamp_denver_marker_point(
    x: float,
    y: float,
    size: float,
    page_width: float,
    page_height: float,
) -> tuple[float, float]:
    margin = max(18.0, size / 2 + 6)
    return (
        min(max(x, margin), page_width - margin),
        min(max(y, margin), page_height - margin),
    )


def write_marked_pdf(job: Job, reader: PdfReader, config: dict[str, Any], force: bool) -> None:
    if job.output_pdf.exists() and not force:
        raise FileExistsError(f"{job.output_pdf} already exists. Use --force to overwrite.")

    writer = PdfWriter()
    panel_by_page = {panel.page_index: panel for panel in job.panels}
    for page_index, page in enumerate(reader.pages):
        page_copy = page
        panel = panel_by_page.get(page_index)
        if panel:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            bbox = estimate_panel_bbox(reader, page_index)
            indicator_bbox = estimate_panel_bbox(reader, page_index, use_outer_edges=True)
            marker_bbox = estimate_panel_outline_bbox(reader, page_index, panel.width, panel.height)
            obstacles = collect_page_obstacles(reader, page_index)
            overlay_bytes = make_overlay_page(
                width,
                height,
                panel,
                job.aw_order,
                bbox,
                indicator_bbox,
                marker_bbox,
                obstacles,
                config,
            )
            overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
            page_copy.merge_page(overlay_reader.pages[0])
        writer.add_page(page_copy)

    job.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with job.output_pdf.open("wb") as handle:
        writer.write(handle)


def read_dxf_pairs(path: Path) -> list[list[str]]:
    lines = path.read_text(encoding="latin1", errors="ignore").splitlines()
    pairs: list[list[str]] = []
    index = 0
    while index < len(lines):
        code = lines[index]
        value = lines[index + 1] if index + 1 < len(lines) else ""
        pairs.append([code, value])
        index += 2
    return pairs


def write_dxf_pairs(path: Path, pairs: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    cleaned_pairs: list[list[str]] = []
    for pair in pairs:
        if len(pair) < 2:
            continue
        cleaned_pairs.append([str(pair[0]), str(pair[1])])

    if not cleaned_pairs or not (
        cleaned_pairs[-1][0].strip() == "0"
        and cleaned_pairs[-1][1].strip().upper() == "EOF"
    ):
        cleaned_pairs.append(["0", "EOF"])

    text = "\r\n".join(line for pair in cleaned_pairs for line in pair) + "\r\n"
    with path.open("w", encoding="latin1", errors="replace", newline="") as handle:
        handle.write(text)


def transform_dxf(
    source: Path,
    output: Path,
    rotation_degrees: float,
    force: bool,
) -> None:
    if output.exists() and not force:
        raise FileExistsError(f"{output} already exists. Use --force to overwrite.")
    pairs = read_dxf_pairs(source)
    points = collect_entity_points(pairs)
    transformed_points = rotate_points(points, rotation_degrees)
    translate_x, translate_y = normalize_translation(transformed_points)
    final_points = [(x + translate_x, y + translate_y) for x, y in transformed_points]

    angle = math.radians(rotation_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    in_entities = False
    entity_start = 0
    index = 0
    while index < len(pairs):
        code, value = pairs[index][0].strip(), pairs[index][1].strip()
        if code == "2" and value.upper() == "ENTITIES":
            in_entities = True
        if in_entities and code == "0":
            if value.upper() == "ENDSEC":
                in_entities = False
            entity_start = index
        if in_entities and code in {"10", "11", "12", "13", "14", "15", "16", "17", "18"}:
            y_code = str(int(code) + 10)
            y_index = find_next_code(pairs, index + 1, y_code, entity_start)
            if y_index is not None:
                try:
                    x = float(pairs[index][1])
                    y = float(pairs[y_index][1])
                except ValueError:
                    index += 1
                    continue
                nx = x * cos_a - y * sin_a + translate_x
                ny = x * sin_a + y * cos_a + translate_y
                pairs[index][1] = format_number(nx)
                pairs[y_index][1] = format_number(ny)
        if in_entities and code in {"50", "51"} and abs(rotation_degrees) > 1e-9:
            try:
                pairs[index][1] = format_number((float(pairs[index][1]) + rotation_degrees) % 360)
            except ValueError:
                pass
        index += 1
    update_header_extents(pairs, final_points)
    normalize_dxf_header_metadata(pairs)
    write_dxf_pairs(output, pairs)


def find_next_code(pairs: list[list[str]], start: int, wanted: str, entity_start: int) -> int | None:
    for idx in range(start, min(start + 8, len(pairs))):
        code = pairs[idx][0].strip()
        if code == "0" and idx > entity_start:
            return None
        if code == wanted:
            return idx
    return None


def collect_entity_points(pairs: list[list[str]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    in_entities = False
    entity_start = 0
    for index, pair in enumerate(pairs):
        code, value = pair[0].strip(), pair[1].strip()
        if code == "2" and value.upper() == "ENTITIES":
            in_entities = True
        if in_entities and code == "0":
            if value.upper() == "ENDSEC":
                in_entities = False
            entity_start = index
        if in_entities and code in {"10", "11", "12", "13", "14", "15", "16", "17", "18"}:
            y_index = find_next_code(pairs, index + 1, str(int(code) + 10), entity_start)
            if y_index is None:
                continue
            try:
                points.append((float(value), float(pairs[y_index][1])))
            except ValueError:
                continue
    return points


def rotate_points(points: list[tuple[float, float]], rotation_degrees: float) -> list[tuple[float, float]]:
    angle = math.radians(rotation_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return [(x * cos_a - y * sin_a, x * sin_a + y * cos_a) for x, y in points]


def normalize_translation(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    tx = -min_x if min_x < -1e-8 else 0.0
    ty = -min_y if min_y < -1e-8 else 0.0
    return tx, ty


def update_header_extents(pairs: list[list[str]], points: list[tuple[float, float]]) -> None:
    if not points:
        return
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_x = max(x for x, _ in points)
    max_y = max(y for _, y in points)
    variables = {
        "$EXTMIN": (min_x, min_y),
        "$EXTMAX": (max_x, max_y),
        "$LIMMIN": (min_x, min_y),
        "$LIMMAX": (max_x, max_y),
    }
    for index, pair in enumerate(pairs):
        if pair[0].strip() != "9":
            continue
        variable = pair[1].strip().upper()
        if variable not in variables:
            continue
        x_value, y_value = variables[variable]
        for target in range(index + 1, min(index + 8, len(pairs))):
            code = pairs[target][0].strip()
            if code == "9":
                break
            if code == "10":
                pairs[target][1] = format_number(x_value)
            elif code == "20":
                pairs[target][1] = format_number(y_value)


def normalize_dxf_header_metadata(pairs: list[list[str]]) -> None:
    set_header_variable(pairs, "$INSUNITS", "70", "1")
    set_header_variable(pairs, "$MEASUREMENT", "70", "0")


def set_header_variable(pairs: list[list[str]], variable: str, value_code: str, value: str) -> None:
    for index, pair in enumerate(pairs):
        if pair[0].strip() != "9" or pair[1].strip().upper() != variable:
            continue
        for target in range(index + 1, min(index + 10, len(pairs))):
            code = pairs[target][0].strip()
            if code == "9":
                break
            if code == value_code:
                pairs[target][1] = value
                return
        pairs.insert(index + 1, [value_code, value])
        return


def format_number(value: float) -> str:
    if abs(value) < 1e-10:
        value = 0.0
    return f"{value:.12g}"





def write_adjusted_dxfs(job: Job, force: bool, config: dict[str, Any] | None = None) -> None:
    for panel in job.panels:
        if panel.skip_dxf:
            continue
        if panel.source_dxf is None or panel.output_dxf is None:
            continue
        rotation = effective_rotation(panel)
        transform_dxf(panel.source_dxf, panel.output_dxf, rotation, force=force)


def effective_rotation(panel: Panel) -> float:
    return (panel.rotation_degrees or 0.0) + (panel.angle_correction_degrees or 0.0)


def build_report(job: Job, apply: bool, skip_pdf: bool, skip_dxf: bool) -> str:
    lines = [
        f"Shower Programmer {'APPLY' if apply else 'DRY RUN'}",
        f"A&W order: {job.aw_order}",
        f"Job/SO: {job.job_name}",
        f"Input PDF: {job.pdf_path}",
        f"Output PDF: {'(skipped)' if skip_pdf else job.output_pdf}",
    ]
    if job.remake_items is not None:
        remake_text = "all pieces" if not job.remake_items else ", ".join(f"P{i}" for i in sorted(job.remake_items))
        lines.append(f"Remake: {remake_text}")
    lines.extend(["", "Items:"])
    for panel in job.panels:
        dims = "unknown"
        if panel.width is not None and panel.height is not None:
            dims = f"{panel.width:g} x {panel.height:g}"
        machine = panel.machine or "label only"
        lines.append(f"- P{panel.item}: {job.aw_order}.{panel.item} | {machine} | {dims}")
        if panel.remake:
            lines.append("  remake: yes")
        elif panel.remake_excluded:
            lines.append("  remake: X out; not programmed")
        if panel.reasons:
            lines.append(f"  reasons: {', '.join(panel.reasons)}")
        if panel.diamon_fusion:
            lines.append("  diamon fusion: yes")
        if not skip_dxf:
            if panel.skip_dxf:
                lines.append("  dxf: skipped")
            elif panel.source_dxf and panel.output_dxf:
                lines.append(
                    f"  dxf: {panel.source_dxf.name} -> {panel.output_dxf.name} "
                    f"({effective_rotation(panel):g} deg)"
                )
            else:
                lines.append("  dxf: missing source")
        if panel.indicator_corner:
            lines.append(f"  indicator: {panel.indicator_corner}")
        if panel.angle_correction_degrees:
            detail = f"  angle correction: {panel.angle_correction_degrees:g} deg"
            if panel.angle_correction_reason:
                detail += f" ({panel.angle_correction_reason})"
            lines.append(detail)
        for warning in panel.warnings:
            lines.append(f"  WARNING: {warning}")
    return "\n".join(lines) + "\n"


def write_report(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_if_pdf_only(job: Job, force: bool) -> None:
    if job.output_pdf.exists() and not force:
        raise FileExistsError(f"{job.output_pdf} already exists. Use --force to overwrite.")
    job.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(job.pdf_path, job.output_pdf)


def main() -> int:
    args = parse_args()
    folder = Path(args.folder).resolve()
    config = load_config(resolve_config_path(args.config, folder))

    pdf_path = Path(args.pdf).resolve() if args.pdf else find_pdf(folder, args.job).resolve()
    reader = PdfReader(str(pdf_path))
    job_name = clean_job_name(args.job) if args.job else extract_job_from_pdf(pdf_path)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root() / output_dir
    dxf_output_dir = Path(args.dxf_output_dir) if args.dxf_output_dir else output_dir
    if not dxf_output_dir.is_absolute():
        dxf_output_dir = project_root() / dxf_output_dir

    panels = analyze_panels(reader, config, args.aw_order)
    if not panels:
        raise RuntimeError("No panel pages were found in the PDF.")
    refine_panel_orientations(reader, panels, config)
    for panel in panels:
        apply_override(panel, config, args.aw_order)
    remake_items = parse_item_list(args.remake_items) if args.remake_items is not None else None
    selected_remake_items = apply_remake_selection(panels, remake_items)
    job = Job(
        pdf_path=pdf_path,
        aw_order=str(args.aw_order),
        job_name=job_name,
        panels=panels,
        output_pdf=output_dir / f"{args.aw_order}.pdf",
        report_path=output_dir / f"{args.aw_order}_programming_report.txt",
        remake_items=selected_remake_items,
    )
    assign_dxf_paths(job, folder, dxf_output_dir, config)
    report = build_report(job, apply=args.apply, skip_pdf=args.skip_pdf, skip_dxf=args.skip_dxf)
    print(report)

    if not args.apply:
        print("Dry run only. Add --apply to write the marked PDF, DXFs, and report.")
        return 0

    if args.skip_pdf:
        pass
    else:
        write_marked_pdf(job, reader, config, force=args.force)
    if not args.skip_dxf:
        write_adjusted_dxfs(job, force=args.force, config=config)
    write_report(job.report_path, report, force=args.force)
    print(f"Wrote report: {job.report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
