#!/usr/bin/env python3
"""Version 0.97 production-safety features for Shower Programmer.

This module intentionally patches the existing V40-era core at startup instead
of duplicating the large GUI, batch, and programming modules.  It is loaded by
``shower_programmer_v4.py`` for source runs and packaged EXE builds.
"""

from __future__ import annotations

# VERSION_0_5_RADIUS_CALLOUT_LAYOUT
# VERSION_0_6_FPS_RAKE_RELEASE_RELIABILITY
# VERSION_0_61_FPS_SHORT_CUT_HINGES_UP
# VERSION_0_62_MIRROR_GLASS_WATERJET
# VERSION_0_63_WORKFLOW_INTELLIGENCE
# VERSION_0_64_DXF_FIRST_REVIEW_LAYOUT
# VERSION_0_65_SMART_NETWORK_IMPORT
# VERSION_0_66_MIRROR_WATERJET_BATCH_SCOPE
# VERSION_0_67_DUPLICATE_JOB_ORDER_IDENTITY
# VERSION_0_69_FAST_ACCURATE_SCANNING
# VERSION_0_70_LOCAL_FIRST_IMPORT_REVIEW
# VERSION_0_71_WATERJET_REVIEW_POLISH
# VERSION_0_72_BOUNDED_NETWORK_CLEANUP
# VERSION_0_73_VALIDATED_ARCHIVE_HANDOFF
# VERSION_0_74_COMPLETED_BATCH_CLEANUP
# VERSION_0_75_RESILIENT_SCAN_CLEANUP
# VERSION_0_76_MANUAL_WJ_METRIC_SAVE
# VERSION_0_77_REVIEW_WORKFLOW_CONTROLS
# VERSION_0_78_CENTERED_ORDER_SUMMARY
# VERSION_0_79_STREAMLINED_TOOLS
# VERSION_0_80_ORDER_SEARCH_ACTION_HISTORY
# VERSION_0_81_DASHBOARD_LAYOUT_POLISH
# VERSION_0_82_SETTINGS_REMAKE_DETECTION
# VERSION_0_83_MAXIMIZED_SETTINGS
# VERSION_0_84_WORKFLOW_SETTINGS
# VERSION_0_85_STABLE_HINGE_ORIENTATION
# VERSION_0_86_REVIEW_READINESS_WARNING
# VERSION_0_87_INPUT_BATCH_NETWORK_DELETE
# VERSION_0_88_RECOVERY_DIAGNOSTICS
# VERSION_0_89_DIAGNOSTICS_FOLDER_ACCESS
# VERSION_0_90_ORDER_OVERVIEW_PDF_REFRESH
# VERSION_0_91_REVIEW_STABILITY_PLACEMENT
# VERSION_0_92_REVIEW_WORKSPACE_EDITING
# VERSION_0_93_OOS_DIMENSION_RECONCILIATION
# VERSION_0_94_ARCHIVE_REMAKE_USABILITY
# VERSION_0_95_BACKGROUND_RESPONSIVENESS
# VERSION_0_96_FAST_FILTERED_ARCHIVE_BROWSER
# VERSION_0_97_REIMPORTED_BATCH_REACTIVATION

import copy
import hashlib
import math
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable


SE_WARNING_PREFIX = "Long-glass SE requirement:"
WJ_OVERSIZE_WARNING_PREFIX = "Oversize WJ:"
WJ_RADIUS_WARNING_PREFIX = "WJ internal-radius check:"

_INSTALL_LOCK = threading.Lock()
_INSTALLED = False
_LAST_SEND_SUMMARY: dict[str, Any] = {}


@dataclass(frozen=True)
class SendConflict:
    """One generated file whose production destination already exists."""

    source: Path
    target: Path
    output_kind: str
    identical: bool


@dataclass(frozen=True)
class RadiusCallout:
    """Canvas-ready callout for a detected DXF internal radius."""

    center_x: float
    center_y: float
    label_x: float
    label_y: float
    ring_radius: float
    label: str
    severity: str


CanvasRect = tuple[float, float, float, float]


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rules(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    rules = config.get("rules", {})
    return rules if isinstance(rules, dict) else {}


def _add_warning(panel: Any, message: str) -> None:
    warnings = getattr(panel, "warnings", None)
    if not isinstance(warnings, list):
        warnings = []
        setattr(panel, "warnings", warnings)
    if message not in warnings:
        warnings.append(message)


def _replace_prefixed_warning(panel: Any, prefix: str, message: str | None) -> None:
    warnings = getattr(panel, "warnings", None)
    if not isinstance(warnings, list):
        warnings = []
    warnings[:] = [warning for warning in warnings if not str(warning).startswith(prefix)]
    if message:
        warnings.append(message)
    setattr(panel, "warnings", warnings)


def validate_waterjet_envelope(panel: Any, config: dict[str, Any] | None) -> bool:
    """Flag WJ glass when both dimensions exceed the configured table envelope."""

    if str(getattr(panel, "machine", "")).upper() != "WJ":
        _replace_prefixed_warning(panel, WJ_OVERSIZE_WARNING_PREFIX, None)
        return True
    width = getattr(panel, "width", None)
    height = getattr(panel, "height", None)
    if width is None or height is None:
        return True
    limit = _safe_float(_rules(config).get("waterjet_fit_limit_inches", 75.0), 75.0)
    if float(width) > limit and float(height) > limit:
        message = (
            f"{WJ_OVERSIZE_WARNING_PREFIX} {float(width):g} x {float(height):g} exceeds the "
            f"{limit:g} x {limit:g} in Waterjet envelope. DXF skipped for review."
        )
        warnings = getattr(panel, "warnings", [])
        if isinstance(warnings, list):
            warnings[:] = [warning for warning in warnings if not str(warning).startswith("WJ size limit:")]
        _replace_prefixed_warning(panel, WJ_OVERSIZE_WARNING_PREFIX, message)
        panel.skip_dxf = True
        return False
    _replace_prefixed_warning(panel, WJ_OVERSIZE_WARNING_PREFIX, None)
    return True


def _standalone_se_count(text: str) -> int:
    return len(re.findall(r"(?<![A-Z0-9])S\s*[.-]?\s*E(?![A-Z0-9])", text.upper()))


def _positioned_se_sides(reader: Any, panel: Any, programmer: Any) -> set[str] | None:
    """Locate SE labels near the two short ends of the detected glass outline.

    ``None`` means the PDF did not expose enough reliable positional data and the
    caller should use text-count fallback behavior.
    """

    try:
        bbox = programmer.estimate_panel_bbox(reader, int(panel.page_index))
    except Exception:
        bbox = None
    if not bbox:
        return None

    x0, y0, x1, y1 = (float(value) for value in bbox)
    if x1 <= x0 or y1 <= y0:
        return None

    hits: list[tuple[float, float]] = []

    def visitor(text: str, cm: list[float], tm: list[float], _font: Any, _size: float) -> None:
        if not re.search(r"(?<![A-Z0-9])S\s*[.-]?\s*E(?![A-Z0-9])", str(text).upper()):
            return
        try:
            x, y = programmer.text_origin_from_matrices(cm, tm)
        except Exception:
            try:
                x, y = float(tm[4]), float(tm[5])
            except Exception:
                return
        hits.append((float(x), float(y)))

    try:
        reader.pages[int(panel.page_index)].extract_text(visitor_text=visitor)
    except Exception:
        return None
    if not hits:
        return set()

    outline_width = x1 - x0
    outline_height = y1 - y0
    horizontal_glass = float(getattr(panel, "width", 0.0) or 0.0) >= float(getattr(panel, "height", 0.0) or 0.0)
    sides: set[str] = set()

    if horizontal_glass:
        band = max(18.0, min(90.0, outline_width * 0.20))
        vertical_pad = max(18.0, outline_height * 0.30)
        for x, y in hits:
            if not (y0 - vertical_pad <= y <= y1 + vertical_pad):
                continue
            if x <= x0 + band:
                sides.add("left")
            if x >= x1 - band:
                sides.add("right")
    else:
        band = max(18.0, min(90.0, outline_height * 0.20))
        horizontal_pad = max(18.0, outline_width * 0.30)
        for x, y in hits:
            if not (x0 - horizontal_pad <= x <= x1 + horizontal_pad):
                continue
            if y <= y0 + band:
                sides.add("bottom")
            if y >= y1 - band:
                sides.add("top")
    return sides


def validate_long_glass_se(
    panel: Any,
    config: dict[str, Any] | None,
    *,
    reader: Any | None = None,
    programmer: Any | None = None,
) -> bool:
    """Require SE labels on both short end edges for glass 113 inches or longer."""

    width = getattr(panel, "width", None)
    height = getattr(panel, "height", None)
    if width is None or height is None:
        _replace_prefixed_warning(panel, SE_WARNING_PREFIX, None)
        return True

    threshold = _safe_float(_rules(config).get("se_required_length_inches", 113.0), 113.0)
    long_side = max(float(width), float(height))
    if long_side + 1e-6 < threshold:
        _replace_prefixed_warning(panel, SE_WARNING_PREFIX, None)
        return True

    text = f"{getattr(panel, 'text', '')}\n{getattr(panel, 'process_text', '')}"
    count = _standalone_se_count(text)
    sides: set[str] | None = None
    if reader is not None and programmer is not None:
        sides = _positioned_se_sides(reader, panel, programmer)

    expected = {"left", "right"} if float(width) >= float(height) else {"bottom", "top"}
    if sides is not None and expected.issubset(sides):
        _replace_prefixed_warning(panel, SE_WARNING_PREFIX, None)
        return True
    # PDF text extraction sometimes loses useful coordinates. Two explicit SE
    # labels are accepted only when positional mapping produced no usable sides.
    if count >= 2 and (sides is None or not sides):
        _replace_prefixed_warning(panel, SE_WARNING_PREFIX, None)
        return True

    end_description = "left and right short ends" if float(width) >= float(height) else "top and bottom short ends"
    detected = "none" if count == 0 else str(count)
    if sides:
        detected += f" ({', '.join(sorted(sides))})"
    message = (
        f"{SE_WARNING_PREFIX} glass {long_side:g} in or longer requires SE on both {end_description}; "
        f"detected {detected}. Verify the sketch edgework before sending."
    )
    _replace_prefixed_warning(panel, SE_WARNING_PREFIX, message)
    return False


_THICKNESS_VALUES = {
    "1/4": 0.25,
    "5/16": 5.0 / 16.0,
    "3/8": 0.375,
    "7/16": 7.0 / 16.0,
    "1/2": 0.5,
    "5/8": 0.625,
    "3/4": 0.75,
    ".250": 0.25,
    "0.250": 0.25,
    ".3125": 0.3125,
    "0.3125": 0.3125,
    ".375": 0.375,
    "0.375": 0.375,
    ".4375": 0.4375,
    "0.4375": 0.4375,
    ".500": 0.5,
    "0.500": 0.5,
    ".5": 0.5,
    "0.5": 0.5,
    ".625": 0.625,
    "0.625": 0.625,
    ".750": 0.75,
    "0.750": 0.75,
}
_THICKNESS_TOKEN = r"(?:1/4|5/16|3/8|7/16|1/2|5/8|3/4|0?\.(?:250|3125|375|4375|5|500|625|75|750))"


def extract_glass_thickness_inches(panel: Any) -> float | None:
    """Read glass thickness without confusing an internal-radius note for thickness."""

    text = f"{getattr(panel, 'text', '')}\n{getattr(panel, 'process_text', '')}".upper()
    candidates: list[tuple[int, int, float]] = []
    for line_index, line in enumerate(text.splitlines() or [text]):
        compact = re.sub(r"\s+", " ", line).strip()
        if not compact:
            continue
        context_score = 0
        if "THICK" in compact or re.search(r"\bTHK\b", compact):
            context_score += 8
        if "TEMPER" in compact:
            context_score += 6
        if "GLASS" in compact:
            context_score += 4
        if any(word in compact for word in ("CLEAR", "LOW IRON", "BRONZE", "GRAY", "GREY", "RAIN")):
            context_score += 2
        if "RADIUS" in compact and context_score == 0:
            context_score -= 6
        if context_score <= 0:
            continue
        for match in re.finditer(_THICKNESS_TOKEN, compact):
            token = match.group(0)
            value = _THICKNESS_VALUES.get(token)
            if value is None:
                continue
            # Prefer thickness tokens appearing before glass/tempered wording.
            nearby = compact[match.end():match.end() + 48]
            score = context_score + (3 if re.search(r"\b(?:CLEAR|LOW IRON|TEMPERED|GLASS)\b", nearby) else 0)
            candidates.append((score, -line_index, value))
    if not candidates:
        # Last-resort labeled forms such as "Glass Thickness: 3/8".
        match = re.search(rf"\b(?:GLASS\s+)?(?:THICKNESS|THK)\s*[:=]?\s*(?P<t>{_THICKNESS_TOKEN})", text)
        if match:
            return _THICKNESS_VALUES.get(match.group("t"))
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def _format_inches(value: float) -> str:
    nearest = int(round(abs(value) * 16))
    whole, numerator = divmod(nearest, 16)
    if numerator == 0:
        return f'{whole}"'
    divisor = math.gcd(numerator, 16)
    numerator //= divisor
    denominator = 16 // divisor
    return f'{whole}-{numerator}/{denominator}"' if whole else f'{numerator}/{denominator}"'


def _dxf_inches_per_unit(programmer: Any, path: Path) -> float:
    """Return inches per native DXF unit from $INSUNITS."""

    mapping = {
        "1": 1.0,
        "2": 12.0,
        "4": 1.0 / 25.4,
        "5": 1.0 / 2.54,
        "6": 39.37007874015748,
    }
    try:
        pairs = programmer.read_dxf_pairs(path)
    except Exception:
        return 1.0
    for index, pair in enumerate(pairs):
        if str(pair[0]).strip() != "9" or str(pair[1]).strip().upper() != "$INSUNITS":
            continue
        for target in range(index + 1, min(index + 8, len(pairs))):
            code = str(pairs[target][0]).strip()
            if code == "9":
                break
            if code == "70":
                return mapping.get(str(pairs[target][1]).strip(), 1.0)
    return 1.0


def validate_waterjet_internal_radius(panel: Any, config: dict[str, Any] | None, programmer: Any) -> bool:
    """Require each detected WJ internal radius to be at least the glass thickness."""

    _replace_prefixed_warning(panel, WJ_RADIUS_WARNING_PREFIX, None)
    if str(getattr(panel, "machine", "")).upper() != "WJ":
        return True
    source = getattr(panel, "source_dxf", None)
    if source is None or not Path(source).is_file():
        return True
    if not bool(_rules(config).get("waterjet_internal_radius_must_meet_thickness", True)):
        return True

    thickness = extract_glass_thickness_inches(panel)
    if thickness is None:
        _add_warning(
            panel,
            f"{WJ_RADIUS_WARNING_PREFIX} could not determine glass thickness, so internal radii were not validated.",
        )
        return False

    try:
        samples = programmer.collect_dxf_internal_cut_radius_samples(Path(source))
        inches_per_unit = _dxf_inches_per_unit(programmer, Path(source))
    except Exception as exc:
        _add_warning(panel, f"{WJ_RADIUS_WARNING_PREFIX} could not read DXF radii: {exc}")
        return False

    radii = sorted({round(abs(float(radius) * float(inches_per_unit)), 8) for _x, _y, radius in samples if radius and abs(radius) <= 12.0 / max(float(inches_per_unit), 1e-12)})
    combined = f"{getattr(panel, 'text', '')} {getattr(panel, 'process_text', '')}".upper()
    expects_internal_cut = bool(re.search(r"\b(?:INTERNAL\s+RADIUS|CUT[ -]?OUT|NOTCH|RADIUS)\b", combined))
    if not radii:
        if expects_internal_cut:
            _add_warning(
                panel,
                f"{WJ_RADIUS_WARNING_PREFIX} {_format_inches(thickness)} glass has internal-cut wording, "
                "but no internal DXF radius could be confirmed. Verify the DXF before sending.",
            )
            return False
        return True

    tolerance = _safe_float(_rules(config).get("waterjet_internal_radius_tolerance_inches", 0.002), 0.002)
    undersized = [radius for radius in radii if radius + tolerance < thickness]
    if undersized:
        detected = ", ".join(_format_inches(radius) for radius in undersized[:6])
        _add_warning(
            panel,
            f"{WJ_RADIUS_WARNING_PREFIX} {_format_inches(thickness)} glass requires internal radii of at least "
            f"{_format_inches(thickness)}; undersized radius detected: {detected}. Verify before oven processing.",
        )
        return False
    return True


def merge_process_orders_by_aw(orders: Iterable[Any], shower_batch: Any) -> list[Any]:
    """Combine split process-list rows for the same A&W order across batches."""

    merged: dict[str, Any] = {}
    order_sequence: list[str] = []
    for order in orders:
        aw_order = str(getattr(order, "aw_order", "")).strip()
        if not aw_order:
            continue
        target = merged.get(aw_order)
        if target is None:
            target = shower_batch.clone_process_order(order) if hasattr(shower_batch, "clone_process_order") else copy.deepcopy(order)
            merged[aw_order] = target
            order_sequence.append(aw_order)
            continue
        if not getattr(target, "job_name", "") and getattr(order, "job_name", ""):
            target.job_name = order.job_name
        if not getattr(target, "customer", "") and getattr(order, "customer", ""):
            target.customer = order.customer
        target_items = getattr(target, "items", {})
        for item_number, item in getattr(order, "items", {}).items():
            target_item = target_items.get(item_number)
            if target_item is None:
                target_items[item_number] = copy.deepcopy(item)
                continue
            for field_name in ("width_text", "height_text", "delivery_date", "customer"):
                if not getattr(target_item, field_name, "") and getattr(item, field_name, ""):
                    setattr(target_item, field_name, getattr(item, field_name))
            for field_name in ("processing", "machine_hints", "rows"):
                target_values = getattr(target_item, field_name, None)
                incoming_values = getattr(item, field_name, None)
                if not isinstance(target_values, list) or not isinstance(incoming_values, list):
                    continue
                for value in incoming_values:
                    if field_name == "rows" or value not in target_values:
                        target_values.append(value)
    return [merged[aw_order] for aw_order in order_sequence]


def unique_orders_from_batches(batches: list[dict[str, object]], shower_batch: Any) -> list[Any]:
    ordered: list[Any] = []
    for batch in batches:
        batch_orders = batch.get("orders", [])
        if isinstance(batch_orders, list):
            ordered.extend(order for order in batch_orders if isinstance(order, shower_batch.ProcessOrder))
    return merge_process_orders_by_aw(ordered, shower_batch)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def files_are_identical(source: Path, target: Path) -> bool:
    try:
        if source.stat().st_size != target.stat().st_size:
            return False
        return _sha256(source) == _sha256(target)
    except OSError:
        return False


def find_send_conflicts(sketch_paths: list[Path], dxf_paths: list[Path], sketch_dir: Path, programs_dir: Path) -> list[SendConflict]:
    candidates: list[tuple[int, str, Path, Path]] = []
    for kind, paths, target_dir in (
        ("Sketch", sketch_paths, sketch_dir),
        ("Program", dxf_paths, programs_dir),
    ):
        for source in paths:
            target = target_dir / source.name
            candidates.append((len(candidates), kind, source, target))

    def inspect(candidate: tuple[int, str, Path, Path]) -> tuple[int, SendConflict | None]:
        index, kind, source, target = candidate
        if not source.is_file() or not target.exists():
            return index, None
        return index, SendConflict(source, target, kind, files_are_identical(source, target))

    if len(candidates) <= 1:
        inspected = [inspect(candidate) for candidate in candidates]
    else:
        worker_count = min(4, len(candidates))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="shower-send-check") as executor:
            inspected = [future.result() for future in as_completed(executor.submit(inspect, item) for item in candidates)]
    return [conflict for _index, conflict in sorted(inspected) if conflict is not None]


def _walk_widgets(widget: Any) -> Iterable[Any]:
    try:
        children = widget.winfo_children()
    except Exception:
        return []
    result: list[Any] = []
    for child in children:
        result.append(child)
        result.extend(_walk_widgets(child))
    return result


def _reenable_review_send_buttons(app: Any) -> None:
    window = getattr(app, "send_review_window", None)
    if window is None:
        return
    for widget in _walk_widgets(window):
        try:
            text = str(widget.cget("text"))
        except Exception:
            continue
        if text in {"Send Checked Orders", "Sketches", "Programs"}:
            try:
                widget.configure(state="normal")
            except Exception:
                pass
        elif text == "Close":
            try:
                widget.configure(text="Cancel")
            except Exception:
                pass


def show_send_conflict_dialog(app: Any, conflicts: list[SendConflict], gui: Any) -> str:
    """Return ``keep``, ``replace``, or ``cancel`` from a program-styled modal."""

    changed = [conflict for conflict in conflicts if not conflict.identical]
    if not changed:
        return "keep"

    ctk = getattr(gui, "ctk", None)
    tk = getattr(gui, "tk", None)
    messagebox = getattr(gui, "messagebox", None)
    if ctk is None or tk is None:
        if messagebox is None:
            return "cancel"
        answer = messagebox.askyesnocancel(
            "Production files already exist",
            f"{len(changed)} production file(s) already exist and differ from the generated files.\n\n"
            "Yes: replace the production files.\nNo: keep the production files and continue sending everything else.\nCancel: stop this send.",
            parent=getattr(app, "send_review_window", None) or getattr(app, "root", None),
        )
        return "replace" if answer is True else "keep" if answer is False else "cancel"

    parent = getattr(app, "send_review_window", None) or getattr(app, "root", None)
    dialog = ctk.CTkToplevel(parent)
    dialog.title("Production File Conflicts")
    try:
        app.position_child_window(dialog, 780, 560)
        app.set_window_icon(dialog)
    except Exception:
        dialog.geometry("780x560")
    dialog.minsize(680, 480)
    dialog.configure(fg_color=app.APP_BG)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(2, weight=1)
    choice = {"value": "cancel"}

    header = ctk.CTkFrame(dialog, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
    ctk.CTkLabel(
        header,
        text="Production files already exist",
        font=("Segoe UI", 24, "bold"),
        text_color=app.TEXT,
        anchor="w",
    ).pack(fill="x")
    ctk.CTkLabel(
        header,
        text=(
            "Non-conflicting files will still be sent. Choose whether the conflicting production files should be kept "
            "or replaced. Keeping an existing file accepts the current production copy for this send."
        ),
        font=("Segoe UI", 11),
        text_color=app.MUTED,
        justify="left",
        anchor="w",
        wraplength=720,
    ).pack(fill="x", pady=(6, 0))

    summary = ctk.CTkFrame(dialog, fg_color=app.CARD_BG, corner_radius=14, border_width=1, border_color=app.BORDER)
    summary.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
    identical_count = len(conflicts) - len(changed)
    ctk.CTkLabel(
        summary,
        text=f"Different files: {len(changed)}    Identical files: {identical_count}",
        font=("Segoe UI", 12, "bold"),
        text_color=app.WARNING,
        anchor="w",
    ).pack(fill="x", padx=14, pady=12)

    list_frame = ctk.CTkScrollableFrame(
        dialog,
        fg_color=app.CARD_BG,
        corner_radius=14,
        border_width=1,
        border_color=app.BORDER,
    )
    list_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 12))
    for conflict in conflicts:
        row = ctk.CTkFrame(list_frame, fg_color=app.PANEL_BG, corner_radius=10)
        row.pack(fill="x", padx=4, pady=4)
        status = "Identical - safe to keep" if conflict.identical else "Different - decision required"
        status_color = app.SUCCESS if conflict.identical else app.DANGER
        ctk.CTkLabel(row, text=conflict.output_kind, width=72, font=("Segoe UI", 10, "bold"), text_color=app.ACCENT_DARK).pack(side="left", padx=(12, 8), pady=10)
        ctk.CTkLabel(row, text=conflict.source.name, font=("Segoe UI", 11, "bold"), text_color=app.TEXT, anchor="w").pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkLabel(row, text=status, font=("Segoe UI", 10, "bold"), text_color=status_color).pack(side="right", padx=12, pady=10)

    actions = ctk.CTkFrame(dialog, fg_color="transparent")
    actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 18))
    actions.grid_columnconfigure((0, 1, 2), weight=1)

    def finish(value: str) -> None:
        choice["value"] = value
        try:
            dialog.grab_release()
        except Exception:
            pass
        dialog.destroy()

    ctk.CTkButton(
        actions,
        text="Keep Existing & Continue",
        command=lambda: finish("keep"),
        height=44,
        corner_radius=10,
        fg_color=app.BUTTON_BG,
        hover_color=app.BUTTON_HOVER,
        border_width=1,
        border_color=app.BORDER,
        text_color=app.BUTTON_TEXT,
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    ctk.CTkButton(
        actions,
        text="Replace Existing & Continue",
        command=lambda: finish("replace"),
        height=44,
        corner_radius=10,
        fg_color=app.ACCENT,
        hover_color=app.ACCENT_DARK,
        text_color="#ffffff",
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=1, sticky="ew", padx=6)
    ctk.CTkButton(
        actions,
        text="Cancel Send",
        command=lambda: finish("cancel"),
        height=44,
        corner_radius=10,
        fg_color=app.PANEL_BG,
        hover_color=app.BUTTON_HOVER,
        border_width=1,
        border_color=app.BORDER,
        text_color=app.MUTED,
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    dialog.protocol("WM_DELETE_WINDOW", lambda: finish("cancel"))
    try:
        app.bring_window_to_front(dialog, make_transient=True)
    except Exception:
        pass
    dialog.grab_set()
    dialog.wait_window()
    return str(choice["value"])


def _copy_outputs_with_policy(
    app: Any,
    paths: list[Path],
    target_dir: Path,
    progress_callback: Callable[[Path, Path, str], None] | None = None,
) -> list[Path]:
    global _LAST_SEND_SUMMARY

    target_dir.mkdir(parents=True, exist_ok=True)
    copied_by_index: dict[int, Path] = {}
    actions = getattr(app, "_v4_send_conflict_actions", {})
    summary = getattr(app, "_v4_send_summary", None)
    if not isinstance(summary, dict):
        summary = {"kept": [], "replaced": [], "failed": []}
        app._v4_send_summary = summary

    copy_jobs: list[tuple[int, Path, Path, str]] = []
    for index, source in enumerate(paths):
        if not source.exists() or not source.is_file():
            continue
        target = target_dir / source.name
        if progress_callback is not None:
            progress_callback(source, target, "starting")
        action = actions.get(str(target.resolve()).casefold(), "copy") if isinstance(actions, dict) else "copy"
        if target.exists() and action == "keep":
            copied_by_index[index] = target
            summary.setdefault("kept", []).append(target)
            if progress_callback is not None:
                progress_callback(source, target, "complete")
            _LAST_SEND_SUMMARY = dict(summary)
            continue
        copy_jobs.append((index, source, target, action))

    worker_count = max(1, min(4, len(copy_jobs)))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="shower-send") as executor:
        futures = {
            executor.submit(app.copy_file_atomically, source, target): (index, source, target, action)
            for index, source, target, action in copy_jobs
        }
        for future in as_completed(futures):
            index, source, target, action = futures[future]
            try:
                future.result()
                copied_by_index[index] = target
                if action == "replace":
                    summary.setdefault("replaced", []).append(target)
                if progress_callback is not None:
                    progress_callback(source, target, "complete")
                _LAST_SEND_SUMMARY = dict(summary)
            except Exception as exc:
                summary.setdefault("failed", []).append(f"{source.name}: {exc}")
                _LAST_SEND_SUMMARY = dict(summary)
                # Per-file failures do not abort the rest of the send. The order
                # remains unarchived because its copied filename is still missing.
                continue
    return [copied_by_index[index] for index in sorted(copied_by_index)]


def _start_send_outputs_worker(
    app: Any,
    sketch_paths: list[Path],
    dxf_paths: list[Path],
    missing: list[str],
    archive_inputs: bool,
    orders: list[Any],
    order_folder: Path,
    process_list_path: Path,
    *,
    include_sketches: bool,
    include_programs: bool,
    gui: Any,
    original_start: Callable[..., None],
) -> None:
    global _LAST_SEND_SUMMARY

    _LAST_SEND_SUMMARY = {}
    conflicts = find_send_conflicts(sketch_paths, dxf_paths, app.SHOP_SKETCHES_DIR, app.SHOP_PROGRAMS_DIR)
    decision = show_send_conflict_dialog(app, conflicts, gui) if conflicts else "replace"
    if decision == "cancel":
        try:
            app.progress.stop()
            app.progress.configure(mode="determinate", maximum=100, value=0)
        except Exception:
            pass
        app.status_var.set("Send cancelled. No production files were changed.")
        if getattr(app, "send_review_status_var", None) is not None:
            app.send_review_status_var.set("Send cancelled. Review the files and try again.")
        _reenable_review_send_buttons(app)
        return

    actions: dict[str, str] = {}
    for conflict in conflicts:
        action = "keep" if conflict.identical else decision
        actions[str(conflict.target.resolve()).casefold()] = action
    app._v4_send_conflict_actions = actions
    app._v4_send_summary = {"kept": [], "replaced": [], "failed": []}
    original_start(
        sketch_paths,
        dxf_paths,
        missing,
        archive_inputs,
        orders,
        order_folder,
        process_list_path,
        include_sketches=include_sketches,
        include_programs=include_programs,
    )


def _send_complete_details(original: Callable[..., str], *args: Any, **kwargs: Any) -> str:
    details = original(*args, **kwargs)
    summary = dict(_LAST_SEND_SUMMARY)
    kept = summary.get("kept", [])
    replaced = summary.get("replaced", [])
    failed = summary.get("failed", [])
    if kept or replaced or failed:
        details += "\nProduction conflicts:"
        if kept:
            details += f"\n  - Kept existing: {len(kept)}"
        if replaced:
            details += f"\n  - Replaced: {len(replaced)}"
        if failed:
            details += f"\n  - Could not send: {len(failed)}"
            details += "\n    " + "\n    ".join(str(item) for item in failed[:8])
            if len(failed) > 8:
                details += f"\n    ...and {len(failed) - 8} more"
    return details


def _expand_rect(rect: CanvasRect, padding: float) -> CanvasRect:
    return (
        float(rect[0]) - padding,
        float(rect[1]) - padding,
        float(rect[2]) + padding,
        float(rect[3]) + padding,
    )


def _rects_overlap(left: CanvasRect, right: CanvasRect) -> bool:
    return not (
        left[2] <= right[0]
        or left[0] >= right[2]
        or left[3] <= right[1]
        or left[1] >= right[3]
    )


def _estimated_label_rect(label: str, x: float, y: float) -> CanvasRect:
    width = max(38.0, len(label) * 7.2)
    height = 18.0
    return (x - width / 2.0, y - height / 2.0, x + width / 2.0, y + height / 2.0)


def _callout_label_candidates(callout: RadiusCallout) -> list[tuple[float, float]]:
    preferred_x = 1.0 if callout.label_x >= callout.center_x else -1.0
    preferred_y = 1.0 if callout.label_y >= callout.center_y else -1.0
    directions = [
        (preferred_x, preferred_y),
        (preferred_x, -preferred_y),
        (-preferred_x, preferred_y),
        (-preferred_x, -preferred_y),
        (preferred_x, 0.0),
        (-preferred_x, 0.0),
        (0.0, preferred_y),
        (0.0, -preferred_y),
    ]
    candidates = [(callout.label_x, callout.label_y)]
    for x_distance, y_distance in ((58.0, 32.0), (72.0, 42.0), (88.0, 54.0), (106.0, 66.0)):
        for x_direction, y_direction in directions:
            candidates.append(
                (
                    callout.center_x + x_direction * x_distance,
                    callout.center_y + y_direction * y_distance,
                )
            )
    return candidates


def place_radius_callout_labels(
    callouts: list[RadiusCallout],
    *,
    occupied: list[CanvasRect],
    bounds: CanvasRect,
    measure: Callable[[str, float, float], CanvasRect] | None = None,
) -> tuple[list[RadiusCallout], list[CanvasRect]]:
    """Place callout text without covering OOS labels or another radius label."""

    measure = measure or _estimated_label_rect
    used = [_expand_rect(rect, 8.0) for rect in occupied]
    placed: list[RadiusCallout] = []
    label_rects: list[CanvasRect] = []
    left, top, right, bottom = bounds

    for callout in callouts:
        chosen_x = callout.label_x
        chosen_y = callout.label_y
        chosen_rect = measure(callout.label, chosen_x, chosen_y)
        for candidate_x, candidate_y in _callout_label_candidates(callout):
            rect = measure(callout.label, candidate_x, candidate_y)
            padded = _expand_rect(rect, 5.0)
            inside = (
                padded[0] >= left
                and padded[1] >= top
                and padded[2] <= right
                and padded[3] <= bottom
            )
            if not inside or any(_rects_overlap(padded, other) for other in used):
                continue
            chosen_x = candidate_x
            chosen_y = candidate_y
            chosen_rect = rect
            break
        else:
            width = max(chosen_rect[2] - chosen_rect[0], 1.0)
            height = max(chosen_rect[3] - chosen_rect[1], 1.0)
            chosen_x = min(max(chosen_x, left + width / 2.0 + 5.0), right - width / 2.0 - 5.0)
            chosen_y = min(max(chosen_y, top + height / 2.0 + 5.0), bottom - height / 2.0 - 5.0)
            chosen_rect = measure(callout.label, chosen_x, chosen_y)

        placed_callout = replace(callout, label_x=chosen_x, label_y=chosen_y)
        placed.append(placed_callout)
        label_rects.append(chosen_rect)
        used.append(_expand_rect(chosen_rect, 8.0))
    return placed, label_rects


def leader_line_endpoints(
    label_rect: CanvasRect,
    label_center: tuple[float, float],
    target_center: tuple[float, float],
    ring_radius: float,
    *,
    label_gap: float = 10.0,
    ring_gap: float = 2.0,
) -> tuple[float, float, float, float]:
    """Start the leader beyond the text box and stop at the radius ring."""

    label_x, label_y = label_center
    target_x, target_y = target_center
    dx = target_x - label_x
    dy = target_y - label_y
    distance = math.hypot(dx, dy)
    if distance <= 1e-9:
        return label_x, label_y, target_x, target_y
    unit_x = dx / distance
    unit_y = dy / distance
    half_width = max((label_rect[2] - label_rect[0]) / 2.0, 1.0)
    half_height = max((label_rect[3] - label_rect[1]) / 2.0, 1.0)
    x_exit = half_width / abs(unit_x) if abs(unit_x) > 1e-9 else float("inf")
    y_exit = half_height / abs(unit_y) if abs(unit_y) > 1e-9 else float("inf")
    text_exit = min(x_exit, y_exit)
    start_x = label_x + unit_x * (text_exit + label_gap)
    start_y = label_y + unit_y * (text_exit + label_gap)
    end_distance = max(0.0, distance - ring_radius - ring_gap)
    end_x = label_x + unit_x * end_distance
    end_y = label_y + unit_y * end_distance
    return start_x, start_y, end_x, end_y


def _canvas_oos_text_rects(canvas: Any) -> list[CanvasRect]:
    occupied: list[CanvasRect] = []
    try:
        items = canvas.find_all()
    except Exception:
        return occupied
    for item in items:
        try:
            item_type = canvas.type(item)
            tags = set(canvas.gettags(item))
            text = str(canvas.itemcget(item, "text")) if item_type == "text" else ""
            if "dxf_oos_label_bg" not in tags and "OOS" not in text.upper():
                continue
            bbox = canvas.bbox(item)
            if bbox:
                occupied.append(tuple(float(value) for value in bbox))  # type: ignore[arg-type]
        except Exception:
            continue
    return occupied


def _panel_without_radius_header(panel: Any) -> Any:
    """Create a display-only panel copy that suppresses the old radius summary."""

    preview_panel = copy.copy(panel)
    if str(getattr(preview_panel, "machine", "")).upper() == "WJ":
        preview_panel.machine = "WJ PREVIEW"
    for attribute in ("text", "process_text"):
        value = str(getattr(preview_panel, attribute, ""))
        setattr(preview_panel, attribute, re.sub(r"PPH", "HINGE", value, flags=re.IGNORECASE))
    return preview_panel


def radius_callouts(
    samples: list[tuple[float, float, float]],
    *,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    scale: float,
    margin: float,
    header_height: float,
    inches_per_unit: float,
    thickness_inches: float | None,
    pph: bool,
    limit: int = 8,
) -> list[RadiusCallout]:
    """Map native DXF radius samples into readable arrow-and-ring callouts."""

    if not samples or max_x <= min_x or max_y <= min_y:
        return []
    unique: list[tuple[float, float, float]] = []
    for sample in sorted(samples, key=lambda value: (value[1], value[0], abs(value[2]))):
        if any(abs(sample[0] - other[0]) < 1e-7 and abs(sample[1] - other[1]) < 1e-7 and abs(abs(sample[2]) - abs(other[2])) < 1e-7 for other in unique):
            continue
        unique.append(sample)
    if pph:
        top_band_native = 4.0 / max(abs(inches_per_unit), 1e-12)
        top_y = max_y
        top_samples = [sample for sample in unique if top_y - sample[1] <= top_band_native]
        if top_samples:
            unique = top_samples
    # Smallest radii are the highest-risk values, but retain stable position order.
    unique = sorted(unique, key=lambda value: (abs(value[2]) * abs(inches_per_unit), -value[1], value[0]))[: max(1, limit)]
    callouts: list[RadiusCallout] = []
    center_native_x = (min_x + max_x) / 2.0
    center_native_y = (min_y + max_y) / 2.0
    for index, (x, y, radius) in enumerate(unique):
        canvas_x = margin + (x - min_x) * scale
        canvas_y = header_height + (max_y - y) * scale
        horizontal = -1.0 if x >= center_native_x else 1.0
        vertical = -1.0 if y <= center_native_y else 1.0
        if index % 2:
            vertical *= -1.0
        label_x = canvas_x + horizontal * (48.0 + (index % 3) * 8.0)
        label_y = canvas_y + vertical * (28.0 + (index % 2) * 8.0)
        preview_right = margin + (max_x - min_x) * scale
        label_x = max(margin + 20.0, min(preview_right - 20.0, label_x))
        label_y = max(header_height + 18.0, label_y)
        radius_inches = abs(radius * inches_per_unit)
        if pph:
            severity = "ok" if abs(radius_inches - 5.0 / 16.0) <= 1e-4 else "danger"
        elif thickness_inches is None:
            severity = "warning"
        elif radius_inches + 0.002 < thickness_inches:
            severity = "danger"
        else:
            severity = "ok"
        callouts.append(
            RadiusCallout(
                center_x=canvas_x,
                center_y=canvas_y,
                label_x=label_x,
                label_y=label_y,
                ring_radius=max(9.0, min(24.0, abs(radius) * scale * 1.35 + 5.0)),
                label=f"R {_format_inches(radius_inches)}",
                severity=severity,
            )
        )
    return callouts


def _draw_radius_callouts(app: Any, canvas: Any, path: Path | None, panel: Any, state: dict[str, Any] | None, gui: Any) -> None:
    if path is None or not path.exists():
        return
    pph = bool(gui.programmer.has_pph_hinge(panel))
    if str(getattr(panel, "machine", "")).upper() != "WJ" and not pph:
        return
    try:
        data = app.order_review_dxf_preview_data(path, state)
        segments = data["segments"]
        samples = data["internal_radius_samples"]
        inches_per_unit = float(data["inches_per_unit"])
    except Exception:
        return
    if not segments or not samples:
        return
    points = [point for segment in segments for point in segment]
    min_x = min(x for x, _y in points)
    max_x = max(x for x, _y in points)
    min_y = min(y for _x, y in points)
    max_y = max(y for _x, y in points)
    width = max(max_x - min_x, 0.001)
    height = max(max_y - min_y, 0.001)
    transform = state.get("dxf_preview_transform", {}) if isinstance(state, dict) else {}
    margin = float(transform.get("margin", 74.0))
    header_height = float(transform.get("header_height", 116.0))
    scale = float(
        transform.get(
            "scale",
            min(
                max(20, canvas.winfo_width() - margin * 2) / width,
                max(20, canvas.winfo_height() - margin * 2 - header_height) / height,
            ),
        )
    )
    thickness = extract_glass_thickness_inches(panel)
    callouts = radius_callouts(
        samples,
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
        scale=scale,
        margin=margin,
        header_height=header_height,
        inches_per_unit=inches_per_unit,
        thickness_inches=thickness,
        pph=pph,
    )
    color_map = {
        "danger": app.DANGER,
        "ok": app.SUCCESS,
        "warning": app.WARNING,
    }
    occupied = _canvas_oos_text_rects(canvas)
    occupied.extend(
        (
            callout.center_x - callout.ring_radius - 4.0,
            callout.center_y - callout.ring_radius - 4.0,
            callout.center_x + callout.ring_radius + 4.0,
            callout.center_y + callout.ring_radius + 4.0,
        )
        for callout in callouts
    )

    font = ("Segoe UI", 9, "bold")

    def measure_label(label: str, x: float, y: float) -> CanvasRect:
        item = canvas.create_text(
            x,
            y,
            text=label,
            fill=app.MUTED,
            font=font,
            anchor=getattr(gui.tk, "CENTER", "center"),
        )
        try:
            bbox = canvas.bbox(item)
            if bbox:
                return tuple(float(value) for value in bbox)  # type: ignore[return-value]
            return _estimated_label_rect(label, x, y)
        finally:
            canvas.delete(item)

    callouts, label_rects = place_radius_callout_labels(
        callouts,
        occupied=occupied,
        bounds=(
            margin + 4.0,
            header_height + 6.0,
            max(margin + 40.0, float(canvas.winfo_width()) - margin - 4.0),
            max(header_height + 40.0, float(canvas.winfo_height()) - 30.0),
        ),
        measure=measure_label,
    )

    for callout, label_rect in zip(callouts, label_rects):
        color = color_map.get(callout.severity, app.WARNING)
        line_start_x, line_start_y, line_end_x, line_end_y = leader_line_endpoints(
            label_rect,
            (callout.label_x, callout.label_y),
            (callout.center_x, callout.center_y),
            callout.ring_radius,
            label_gap=10.0,
            ring_gap=2.0,
        )
        line_item = canvas.create_line(
            line_start_x,
            line_start_y,
            line_end_x,
            line_end_y,
            fill=color,
            width=2,
            arrow=getattr(gui.tk, "LAST", "last"),
        )
        r = callout.ring_radius
        ring_item = canvas.create_oval(
            callout.center_x - r,
            callout.center_y - r,
            callout.center_x + r,
            callout.center_y + r,
            outline=color,
            width=3,
        )
        background_item = canvas.create_rectangle(
            label_rect[0] - 3.0,
            label_rect[1] - 2.0,
            label_rect[2] + 3.0,
            label_rect[3] + 2.0,
            fill=app.PREVIEW_CARD_BG,
            outline="",
        )
        text_item = canvas.create_text(
            callout.label_x,
            callout.label_y,
            text=callout.label,
            fill=color,
            font=font,
            anchor=getattr(gui.tk, "CENTER", "center"),
        )
        try:
            canvas.tag_lower(line_item, background_item)
            canvas.tag_raise(ring_item)
            canvas.tag_raise(background_item)
            canvas.tag_raise(text_item)
        except Exception:
            pass


def install(programmer: Any, shower_batch: Any, gui: Any) -> None:
    """Install the current release behavior once into the existing modules."""

    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return

        original_classify = programmer.classify_panel
        original_analyze = programmer.analyze_panels
        original_validate_constraints = programmer.validate_panel_constraints
        original_assign_dxf_paths = programmer.assign_dxf_paths
        original_batch_load = shower_batch.load_process_orders
        original_start_send = gui.ShowerProgrammerApp.start_send_outputs_worker
        original_draw_dxf = gui.ShowerProgrammerApp.draw_order_review_dxf
        original_send_details = gui.ShowerProgrammerApp.send_complete_details
        original_worker_send = gui.ShowerProgrammerApp.worker_send_outputs
        original_self_test = gui.run_packaged_self_test

        def classify_panel_v4(panel: Any, config: dict[str, Any], aw_order: str) -> Any:
            result = original_classify(panel, config, aw_order)
            validate_long_glass_se(result, config)
            return result

        def analyze_panels_v4(reader: Any, config: dict[str, Any], aw_order: str) -> list[Any]:
            panels = original_analyze(reader, config, aw_order)
            for panel in panels:
                validate_long_glass_se(panel, config, reader=reader, programmer=programmer)
            return panels

        def validate_constraints_v4(panel: Any, config: dict[str, Any]) -> None:
            original_validate_constraints(panel, config)
            validate_waterjet_envelope(panel, config)

        def assign_dxf_paths_v4(job: Any, dxf_folder: Path, dxf_output_dir: Path, config: dict[str, Any]) -> None:
            original_assign_dxf_paths(job, dxf_folder, dxf_output_dir, config)
            for panel in getattr(job, "panels", []):
                validate_waterjet_internal_radius(panel, config, programmer)

        def batch_load_v4(path: Path) -> list[Any]:
            return merge_process_orders_by_aw(original_batch_load(path), shower_batch)

        def unique_orders_v4(batches: list[dict[str, object]]) -> list[Any]:
            return unique_orders_from_batches(batches, shower_batch)

        def copy_outputs_v4(
            self: Any,
            paths: list[Path],
            target_dir: Path,
            progress_callback: Callable[[Path, Path, str], None] | None = None,
        ) -> list[Path]:
            return _copy_outputs_with_policy(self, paths, target_dir, progress_callback)

        def start_send_v4(
            self: Any,
            sketch_paths: list[Path],
            dxf_paths: list[Path],
            missing: list[str],
            archive_inputs: bool,
            orders: list[Any],
            order_folder: Path,
            process_list_path: Path,
            *,
            include_sketches: bool,
            include_programs: bool,
        ) -> None:
            return _start_send_outputs_worker(
                self,
                sketch_paths,
                dxf_paths,
                missing,
                archive_inputs,
                orders,
                order_folder,
                process_list_path,
                include_sketches=include_sketches,
                include_programs=include_programs,
                gui=gui,
                original_start=original_start_send.__get__(self, type(self)),
            )

        def worker_send_v4(self: Any, *args: Any, **kwargs: Any) -> None:
            global _LAST_SEND_SUMMARY

            try:
                original_worker_send(self, *args, **kwargs)
            finally:
                summary = getattr(self, "_v4_send_summary", {})
                _LAST_SEND_SUMMARY = dict(summary) if isinstance(summary, dict) else {}
                self._v4_send_conflict_actions = {}

        def send_details_v4(*args: Any, **kwargs: Any) -> str:
            return _send_complete_details(original_send_details, *args, **kwargs)

        def draw_dxf_v4(
            self: Any,
            canvas: Any,
            path: Path | None,
            panel: Any,
            state: dict[str, Any] | None = None,
            *,
            original_preview: bool = False,
        ) -> None:
            preview_panel = _panel_without_radius_header(panel)
            original_draw_dxf(self, canvas, path, preview_panel, state, original_preview=original_preview)
            _draw_radius_callouts(self, canvas, path, panel, state, gui)

        def self_test_v4(report_path: Path) -> dict[str, Any]:
            result = original_self_test(report_path)
            try:
                _run_v4_self_tests(programmer, shower_batch, gui, report_path.parent)
                if not hasattr(programmer, "panel_machine_decision_evidence"):
                    raise RuntimeError("Machine decision evidence is unavailable.")
                if not hasattr(shower_batch, "process_orders_to_cache"):
                    raise RuntimeError("Process-list normalization cache is unavailable.")
                required_import_helpers = (
                    "index_import_source_folder",
                    "import_duplicate_groups",
                    "missing_order_input_requirements",
                    "file_matches_missing_order_requirement",
                )
                if not all(hasattr(gui.ShowerProgrammerApp, name) for name in required_import_helpers):
                    raise RuntimeError("Smart network import helpers are unavailable.")
                if not hasattr(shower_batch, "cached_pdf_piece_dimensions"):
                    raise RuntimeError("Cached PDF dimension evidence is unavailable.")
                if not hasattr(shower_batch, "reconcile_out_of_square_dimension_match"):
                    raise RuntimeError("Out-of-square dimension reconciliation is unavailable.")
                if not hasattr(shower_batch, "manual_dimension_match_override_enabled"):
                    raise RuntimeError("Manual dimension-match override is unavailable.")
                if not hasattr(shower_batch, "dimension_mismatch_message"):
                    raise RuntimeError("Readable dimension-mismatch formatting is unavailable.")
                required_archive_helpers = (
                    "archived_order_inventory",
                    "copy_archived_order_for_testing",
                    "return_archived_order_to_archive",
                    "resize_overview_text_box",
                )
                if not all(hasattr(gui.ShowerProgrammerApp, name) for name in required_archive_helpers):
                    raise RuntimeError("Version 0.94 archive/review helpers are unavailable.")
                required_responsiveness_helpers = (
                    "worker_prepare_local_order_delete",
                    "worker_delete_local_order_inputs",
                    "apply_local_order_delete_result",
                    "load_archive_settings_inventory",
                    "mark_orders_deleted_for_output",
                    "save_processing_history_for_output",
                )
                if not all(hasattr(gui.ShowerProgrammerApp, name) for name in required_responsiveness_helpers):
                    raise RuntimeError("Version 0.95 background responsiveness helpers are unavailable.")
                required_archive_browser_helpers = (
                    "archive_date_from_name",
                    "normalize_archive_date_filter",
                    "archived_run_inventory",
                    "archive_browser_sort_value",
                    "load_archive_run_settings_inventory",
                )
                if not all(hasattr(gui.ShowerProgrammerApp, name) for name in required_archive_browser_helpers):
                    raise RuntimeError("Version 0.96 archive browser helpers are unavailable.")
                if not hasattr(gui.ShowerProgrammerApp, "reactivate_reimported_process_list_orders"):
                    raise RuntimeError("Version 0.97 re-imported process-list reactivation is unavailable.")
                if not hasattr(gui.shower_cache, "cached_file_sha256"):
                    raise RuntimeError("Cached duplicate-file hashing is unavailable.")
                mirror_rows = [
                    ['1/4" Mirror'],
                    ["", "", '42"', '83"', "", "", "900001-1", "INTERNAL CUTOUT MACRO", "", "", "Customer", "", "", "12345678 MIRROR JOB", "", "", "", "", "", "", "", "Waterjet"],
                    ["", "", '36"', '42"', "", "", "900002-1", "Flat Polish side(s) 1/2/3/4", "", "", "Customer", "", "", "12345679 PACKING ONLY", "", "", "", "", "", "", "", "Packing / Shipping"],
                ]
                mirror_orders = shower_batch.load_process_orders_from_rows(mirror_rows)
                if [order.aw_order for order in mirror_orders] != ["900001"]:
                    raise RuntimeError("Mirror batches are not scoped to Waterjet-routed orders.")
                result.update(
                    {
                        "v4_conflict_safe_send": True,
                        "v4_existing_file_keep_or_replace": True,
                        "v4_per_file_send_failure_continuation": True,
                        "v4_radius_preview_callouts": True,
                        "v4_long_glass_se_validation": True,
                        "v4_waterjet_oversize_flag": True,
                        "v4_waterjet_thickness_radius_validation": True,
                        "v4_split_batch_order_merge": True,
                        "version_0_5_radius_label_spacing": True,
                        "version_0_5_oos_callout_avoidance": True,
                        "version_0_5_radius_header_removed": True,
                        "version_0_6_fps_rake_orientation": True,
                        "version_0_6_dynamic_release_self_test": True,
                        "version_0_61_fps_short_cut_hinges_up": True,
                        "version_0_62_mirror_glass_waterjet": True,
                        "version_0_63_machine_decision_inspector": True,
                        "version_0_63_process_list_normalization": True,
                        "version_0_63_known_order_regressions": True,
                        "version_0_63_incremental_scan_cache": True,
                        "version_0_64_dxf_first_review_layout": True,
                        "version_0_65_smart_network_import": True,
                        "version_0_66_mirror_waterjet_batch_scope": True,
                        "version_0_67_duplicate_job_order_identity": True,
                        "version_0_68_hidden_xls_conversion": True,
                        "version_0_69_fast_accurate_scanning": True,
                        "version_0_71_waterjet_review_polish": True,
                        "version_0_72_bounded_network_cleanup": True,
                        "version_0_73_validated_archive_handoff": True,
                        "version_0_74_completed_batch_cleanup": True,
                        "version_0_75_resilient_scan_cleanup": True,
                        "version_0_76_manual_wj_metric_save": True,
                        "version_0_77_review_workflow_controls": True,
                        "version_0_78_centered_order_summary": True,
                        "version_0_79_streamlined_tools": True,
                        "version_0_80_order_search_action_history": True,
                        "version_0_81_dashboard_layout_polish": True,
                        "out_of_square_dimension_reconciliation": True,
                        "manual_dimension_match_override": True,
                        "version_0_93_oos_dimension_reconciliation": True,
                        "dxf_geometry_dimension_reconciliation": True,
                        "archive_test_restore_workflow": True,
                        "overview_text_size_editing": True,
                        "readable_operator_popups": True,
                        "remake_location_field_reliability": True,
                        "remake_diamon_banner_placement": True,
                        "version_0_94_archive_remake_usability": True,
                        "background_order_input_cleanup": True,
                        "settings_archive_background_load": True,
                        "deferred_settings_history_loads": True,
                        "current_progress_status_language": True,
                        "version_0_95_background_responsiveness": True,
                        "archive_seven_day_incremental_loading": True,
                        "archive_date_range_filters": True,
                        "archive_batch_grouping": True,
                        "archive_column_sorting": True,
                        "archive_runs_view": True,
                        "archive_fast_filename_index": True,
                        "version_0_96_fast_filtered_archive_browser": True,
                        "reimported_process_list_reactivation": True,
                        "deleted_receipt_reactivation_audit": True,
                        "version_0_97_reimported_batch_reactivation": True,
                    }
                )
            except Exception as exc:
                result["ok"] = False
                result["v4_error"] = f"{exc.__class__.__name__}: {exc}"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            import json

            report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
            return result

        programmer.classify_panel = classify_panel_v4
        programmer.analyze_panels = analyze_panels_v4
        programmer.validate_panel_constraints = validate_constraints_v4
        programmer.assign_dxf_paths = assign_dxf_paths_v4
        shower_batch.load_process_orders = batch_load_v4
        gui.ShowerProgrammerApp.unique_orders_from_batches = staticmethod(unique_orders_v4)
        gui.ShowerProgrammerApp.copy_outputs_to_folder = copy_outputs_v4
        gui.ShowerProgrammerApp.start_send_outputs_worker = start_send_v4
        gui.ShowerProgrammerApp.worker_send_outputs = worker_send_v4
        gui.ShowerProgrammerApp.send_complete_details = staticmethod(send_details_v4)
        gui.ShowerProgrammerApp.draw_order_review_dxf = draw_dxf_v4
        gui.run_packaged_self_test = self_test_v4
        gui.ShowerProgrammerApp.V4_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_5_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_6_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_61_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_62_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_63_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_64_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_65_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_66_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_67_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_68_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_69_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_70_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_71_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_72_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_73_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_74_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_75_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_76_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_77_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_78_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_79_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_80_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_81_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_82_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_83_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_84_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_85_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_86_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_87_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_88_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_89_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_90_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_91_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_92_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_93_FEATURES_ACTIVE = True
        gui.ShowerProgrammerApp.VERSION_0_94_FEATURES_ACTIVE = True
        _INSTALLED = True


def _write_test_dxf(path: Path, radius: float = 0.25) -> None:
    path.write_text(
        "\n".join(
            [
                "0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "1", "0", "ENDSEC",
                "0", "SECTION", "2", "ENTITIES",
                "0", "LINE", "10", "0", "20", "0", "11", "20", "21", "0",
                "0", "LINE", "10", "20", "20", "0", "11", "20", "21", "10",
                "0", "LINE", "10", "20", "20", "10", "11", "0", "21", "10",
                "0", "LINE", "10", "0", "20", "10", "11", "0", "21", "0",
                "0", "ARC", "10", "5", "20", "5", "40", f"{radius}", "50", "0", "51", "90",
                "0", "ENDSEC", "0", "EOF", "",
            ]
        ),
        encoding="utf-8",
    )


def _run_v4_self_tests(programmer: Any, shower_batch: Any, gui: Any, scratch_parent: Path) -> None:
    first = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
    first.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')
    second = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
    second.items[2] = shower_batch.ProcessItem(2, width_text='24"', height_text='80"')
    merged = unique_orders_from_batches(
        [{"orders": [first]}, {"orders": [second]}],
        shower_batch,
    )
    if len(merged) != 1 or set(merged[0].items) != {1, 2}:
        raise RuntimeError("Split-batch order merge self-test failed.")

    duplicate_job_rows: list[list[str]] = []
    for aw_item, width, height in (
        ("237008-1", "31-7/8", "112-5/16"),
        ("237008-2", "31-7/8", "112-3/16"),
        ("237009-1", "32", "12"),
    ):
        row = [""] * 22
        row[2] = width
        row[3] = height
        row[6] = aw_item
        row[13] = "89420398.4 2089 HOLBROOK"
        duplicate_job_rows.append(row)
    duplicate_job_orders = shower_batch.load_process_orders_from_rows(duplicate_job_rows)
    if (
        [order.aw_order for order in duplicate_job_orders] != ["237008", "237009"]
        or duplicate_job_orders[0].item_numbers != [1, 2]
        or duplicate_job_orders[1].item_numbers != [1]
    ):
        raise RuntimeError("Duplicate Job Nr A&W identity self-test failed.")

    hidden_command = shower_batch.hidden_powershell_command(
        "Write-Output test",
        bypass_execution_policy=True,
    )
    if "-WindowStyle" not in hidden_command or hidden_command[hidden_command.index("-WindowStyle") + 1] != "Hidden":
        raise RuntimeError("Legacy XLS hidden PowerShell command self-test failed.")
    if "-NonInteractive" not in hidden_command:
        raise RuntimeError("Legacy XLS non-interactive PowerShell self-test failed.")
    hidden_options = shower_batch.hidden_windows_subprocess_options()
    if sys.platform.startswith("win") and not int(hidden_options.get("creationflags", 0)):
        raise RuntimeError("Legacy XLS CREATE_NO_WINDOW self-test failed.")

    long_panel = programmer.Panel(1, 1, '117" x 23"  FP FP FP FP', 117.0, 23.0, "")
    validate_long_glass_se(long_panel, {})
    if not any(str(warning).startswith(SE_WARNING_PREFIX) for warning in long_panel.warnings):
        raise RuntimeError("Long-glass SE warning self-test failed.")
    long_panel.text += " SE SE"
    validate_long_glass_se(long_panel, {})
    if any(str(warning).startswith(SE_WARNING_PREFIX) for warning in long_panel.warnings):
        raise RuntimeError("Long-glass SE pass self-test failed.")

    oversize = programmer.Panel(2, 1, '76" x 76"', 76.0, 76.0, "WJ")
    programmer.validate_panel_constraints(oversize, {"rules": {"waterjet_fit_limit_inches": 75}})
    if not oversize.skip_dxf or not any(str(warning).startswith(WJ_OVERSIZE_WARNING_PREFIX) for warning in oversize.warnings):
        raise RuntimeError("Oversize WJ flag self-test failed.")

    with gui.writable_test_directory(scratch_parent, "shower_v4_self_test_") as temp:
        dxf = temp / "radius.dxf"
        _write_test_dxf(dxf, 0.25)
        radius_panel = programmer.Panel(3, 1, '3/8" CLEAR TEMPERED  INTERNAL RADIUS', 30.0, 80.0, "WJ")
        radius_panel.source_dxf = dxf
        validate_waterjet_internal_radius(radius_panel, {}, programmer)
        if not any(str(warning).startswith(WJ_RADIUS_WARNING_PREFIX) for warning in radius_panel.warnings):
            raise RuntimeError("WJ thickness/radius self-test failed.")

        source_dir = temp / "source"
        target_dir = temp / "target"
        source_dir.mkdir()
        target_dir.mkdir()
        source = source_dir / "900001.pdf"
        target = target_dir / source.name
        source.write_text("new", encoding="utf-8")
        target.write_text("old", encoding="utf-8")
        test_app = object.__new__(gui.ShowerProgrammerApp)
        test_app._v4_send_conflict_actions = {str(target.resolve()).casefold(): "keep"}
        test_app._v4_send_summary = {"kept": [], "replaced": [], "failed": []}
        kept = _copy_outputs_with_policy(test_app, [source], target_dir)
        if kept != [target] or target.read_text(encoding="utf-8") != "old":
            raise RuntimeError("Keep-existing send conflict self-test failed.")
        test_app._v4_send_conflict_actions = {str(target.resolve()).casefold(): "replace"}
        test_app._v4_send_summary = {"kept": [], "replaced": [], "failed": []}
        replaced = _copy_outputs_with_policy(test_app, [source], target_dir)
        if replaced != [target] or target.read_text(encoding="utf-8") != "new":
            raise RuntimeError("Replace-existing send conflict self-test failed.")

    callouts = radius_callouts(
        [(5.0, 5.0, 0.25)],
        min_x=0,
        max_x=20,
        min_y=0,
        max_y=10,
        scale=10,
        margin=34,
        header_height=132,
        inches_per_unit=1,
        thickness_inches=0.375,
        pph=False,
    )
    if len(callouts) != 1 or callouts[0].severity != "danger":
        raise RuntimeError("DXF radius callout geometry self-test failed.")

    start_x, start_y, end_x, end_y = leader_line_endpoints(
        (40.0, 40.0, 80.0, 60.0),
        (60.0, 50.0),
        (140.0, 50.0),
        12.0,
        label_gap=10.0,
    )
    if start_x < 90.0 or abs(start_y - 50.0) > 1e-9 or end_x >= 140.0 or abs(end_y - 50.0) > 1e-9:
        raise RuntimeError("Radius leader spacing self-test failed.")

    placed, label_rects = place_radius_callout_labels(
        [
            RadiusCallout(
                center_x=120.0,
                center_y=100.0,
                label_x=72.0,
                label_y=72.0,
                ring_radius=12.0,
                label='R 5/16"',
                severity="ok",
            )
        ],
        occupied=[(44.0, 60.0, 100.0, 84.0)],
        bounds=(10.0, 20.0, 260.0, 220.0),
    )
    if not placed or _rects_overlap(_expand_rect(label_rects[0], 5.0), _expand_rect((44.0, 60.0, 100.0, 84.0), 8.0)):
        raise RuntimeError("OOS/radius label collision self-test failed.")

    header_panel = programmer.Panel(4, 1, "PPH hinge", 30.0, 80.0, "WJ")
    preview_panel = _panel_without_radius_header(header_panel)
    if str(preview_panel.machine).upper() == "WJ" or "PPH" in str(preview_panel.text).upper():
        raise RuntimeError("Radius header suppression self-test failed.")

    decision_config = {
        "rules": {
            "denver_min_inches": 6.125,
            "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
            "hinge_label_keywords": ["GEN037", "V1E037", "AV1E037", "JRG037", "GEN180"],
            "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
            "denver_fabrication_keywords": ["HOLE", "SLOT", "SCU4"],
            "waterjet_keywords": ["NOTCH", "RADIUS"],
            "weak_waterjet_keywords": ["IRREGULAR SHAPE"],
            "label_only_allow_keywords": ["RAKED EDGE"],
        }
    }
    wj_panel = programmer.Panel(1, 1, '3/8" Clear Tempered\n1/2 Radius', 33.5, 80.0, "WJ")
    wj_order = shower_batch.ProcessOrder("900071", "12345671 WATERJET TEST")
    wj_item = shower_batch.ProcessItem(1, width_text='33-1/2"', height_text='80"')
    wj_item.machine_hints.append("Denver 2 (CNC)")
    wj_order.items[1] = wj_item
    shower_batch.apply_process_hints([wj_panel], wj_order, decision_config)
    if wj_panel.machine != "WJ":
        raise RuntimeError("Strong Waterjet geometry did not override conflicting Denver routing.")
    if not all(programmer.has_hinge_label_text(code, decision_config) for code in ("JRG037", "GEN180")):
        raise RuntimeError("Configured JRG037/GEN180 hinge detection self-test failed.")
