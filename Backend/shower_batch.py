#!/usr/bin/env python3
"""Batch runner for shower programming jobs listed in the process workbook."""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable

from openpyxl import load_workbook
from pypdf import PdfReader

import shower_programmer as programmer


DEFAULT_PROCESS_LIST = "Process List Per Machine.xlsx"


def upper_config_list(config: dict[str, object], key: str, default: list[str]) -> set[str]:
    rules = config.get("rules", {})
    if not isinstance(rules, dict):
        return {value.upper() for value in default}
    values = rules.get(key, default)
    if not isinstance(values, list):
        return {value.upper() for value in default}
    return {str(value).upper() for value in values}


@dataclass
class ProcessItem:
    item: int
    width_text: str = ""
    height_text: str = ""
    delivery_date: str = ""
    customer: str = ""
    processing: list[str] = field(default_factory=list)
    machine_hints: list[str] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)

    def add_row(
        self,
        row_number: int,
        width_text: str,
        height_text: str,
        delivery_date: str,
        customer: str,
        processing: str,
        machine_hint: str,
    ) -> None:
        self.rows.append(row_number)
        if width_text and not self.width_text:
            self.width_text = width_text
        if height_text and not self.height_text:
            self.height_text = height_text
        if delivery_date and not self.delivery_date:
            self.delivery_date = delivery_date
        if customer and not self.customer:
            self.customer = customer
        if processing and processing not in self.processing:
            self.processing.append(processing)
        if machine_hint and machine_hint not in self.machine_hints:
            self.machine_hints.append(machine_hint)

    @property
    def processing_text(self) -> str:
        return " | ".join(self.processing)

    @property
    def machine_text(self) -> str:
        return " | ".join(self.machine_hints)

    @property
    def has_diamon_fusion(self) -> bool:
        return "DIAMON" in self.processing_text.upper() or "DIAMOND FUSION" in self.processing_text.upper()

    def desired_machine(self) -> str:
        text = self.machine_text.upper()
        if "WATER" in text or re.search(r"\bWJ\b", text):
            return "WJ"
        if "DENVER 1" in text:
            return "DENVER 1"
        if "DENVER 2" in text:
            return "DENVER 2"
        return ""

    def inferred_denver_machine(self, config: dict[str, object]) -> str:
        text = self.processing_text.upper()
        if not text:
            return ""
        door_keywords = upper_config_list(config, "door_keywords", ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"])
        door_keywords.update(upper_config_list(config, "hinge_label_keywords", ["GEN037", "V1E037", "AV1E037"]))
        fabrication = process_list_fabrication_keywords(config)
        if any(keyword in text for keyword in door_keywords):
            return "DENVER 1"
        if any(keyword in text for keyword in fabrication):
            return "DENVER 2"
        return ""

    def has_strong_waterjet_fabrication(self, config: dict[str, object]) -> bool:
        text = self.processing_text.upper()
        if not text:
            return False
        if re.search(r"\b[1-9]\d*\s+(?:EDGE\s+NOTCH(?:ES)?|CORNER\s+NOTCH(?:ES)?|NOTCHED\s+CORNERS?)\b", text):
            return True
        if re.search(r"\b(?:[1-9]\d*\s+)?(?:1/2\s+)?RADIUS\b", text):
            return True
        return False

    def text_blob(self) -> str:
        return " ".join(
            [
                self.width_text,
                self.height_text,
                self.delivery_date,
                self.customer,
                self.processing_text,
                self.machine_text,
            ]
        ).upper()

    def is_mirror(self, config: dict[str, object]) -> bool:
        keywords = upper_config_list(config, "mirror_keywords", ["MIRROR"])
        text = self.text_blob()
        return any(keyword in text for keyword in keywords)

    def has_mirror_fabrication(self, config: dict[str, object]) -> bool:
        keywords = upper_config_list(
            config,
            "mirror_fabrication_keywords",
            ["FAB", "GEN", "HOLE", "NOTCH", "CUTOUT", "CUT-OUT", "RADIUS"],
        )
        text = self.processing_text.upper()
        return any(keyword in text for keyword in keywords)


@dataclass
class ProcessOrder:
    aw_order: str
    job_name: str
    customer: str = ""
    items: dict[int, ProcessItem] = field(default_factory=dict)

    @property
    def item_numbers(self) -> list[int]:
        return sorted(self.items)

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def delivery_date(self) -> str:
        for item in self.items.values():
            if item.delivery_date:
                return item.delivery_date
        return ""

    def text_blob(self) -> str:
        return " ".join(
            [self.job_name, self.customer]
            + [item.text_blob() for item in self.items.values()]
        ).upper()

    def is_mirror(self, config: dict[str, object]) -> bool:
        keywords = upper_config_list(config, "mirror_keywords", ["MIRROR"])
        text = self.text_blob()
        return any(keyword in text for keyword in keywords)

    def has_mirror_fabrication(self, config: dict[str, object]) -> bool:
        return any(item.has_mirror_fabrication(config) for item in self.items.values())


@dataclass
class BatchJobResult:
    aw_order: str
    job_name: str
    customer: str
    items: str
    status: str
    input_pdf: Path | None = None
    output_pdf: Path | None = None
    report_path: Path | None = None
    delivery_date: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class BatchRunResult:
    results: list[BatchJobResult]
    text_report: Path
    csv_report: Path
    html_report: Path


def cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%m/%d/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_order_item(value: str) -> tuple[str, int] | None:
    match = re.search(r"\b(?P<order>\d{5,})\s*-\s*(?P<item>\d+)\b", value)
    if not match:
        return None
    return match.group("order"), int(match.group("item"))


def process_list_files(path: Path) -> list[Path]:
    if path.is_dir():
        files = [
            candidate
            for candidate in path.glob("*.xlsx")
            if candidate.is_file() and not candidate.name.startswith("~$")
        ]
        return sorted(files, key=lambda candidate: candidate.name.lower())
    if path.is_file():
        return [path]
    raise FileNotFoundError(f"Process list path not found: {path}")


def load_process_orders(path: Path) -> list[ProcessOrder]:
    files = process_list_files(path)
    if not files:
        raise FileNotFoundError(f"No .xlsx process lists found in: {path}")
    merged: dict[tuple[str, str], ProcessOrder] = {}
    for workbook_path in files:
        for order in load_process_orders_from_workbook(workbook_path):
            merge_process_order(merged, order)
    return sorted(merged.values(), key=lambda order: (int(order.aw_order), order.job_name))


def load_process_orders_from_workbook(path: Path) -> list[ProcessOrder]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    worksheet = workbook.active

    orders: dict[tuple[str, str], ProcessOrder] = {}
    last_key: tuple[str, str, int] | None = None
    for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        values = list(row)
        order_item = cell_at(values, 6)
        job_name = programmer.clean_job_name(cell_at(values, 13))
        customer = cell_at(values, 10)
        width_text = cell_at(values, 2)
        height_text = cell_at(values, 3)
        processing = cell_at(values, 7)
        delivery_date = cell_at(values, 8)
        machine_hint = cell_at(values, 21)

        parsed = parse_order_item(order_item)
        if parsed:
            aw_order, item_number = parsed
            key = (aw_order, job_name)
            order = orders.get(key)
            if order is None:
                order = ProcessOrder(aw_order=aw_order, job_name=job_name, customer=customer)
                orders[key] = order
            if customer and not order.customer:
                order.customer = customer
            item = order.items.get(item_number)
            if item is None:
                item = ProcessItem(item=item_number)
                order.items[item_number] = item
            item.add_row(row_number, width_text, height_text, delivery_date, customer, processing, machine_hint)
            last_key = (aw_order, job_name, item_number)
            continue

        if last_key and processing and job_name:
            aw_order, previous_job, item_number = last_key
            if job_name != previous_job:
                continue
            order = orders[(aw_order, previous_job)]
            order.items[item_number].add_row(row_number, width_text, height_text, delivery_date, customer, processing, machine_hint)

    workbook.close()
    return sorted(orders.values(), key=lambda order: int(order.aw_order))


def merge_process_order(
    target_orders: dict[tuple[str, str], ProcessOrder],
    order: ProcessOrder,
) -> None:
    key = (order.aw_order, order.job_name)
    target = target_orders.get(key)
    if target is None:
        target_orders[key] = order
        return
    if order.customer and not target.customer:
        target.customer = order.customer
    for item_number, item in order.items.items():
        target_item = target.items.get(item_number)
        if target_item is None:
            target.items[item_number] = item
            continue
        if item.width_text and not target_item.width_text:
            target_item.width_text = item.width_text
        if item.height_text and not target_item.height_text:
            target_item.height_text = item.height_text
        if item.delivery_date and not target_item.delivery_date:
            target_item.delivery_date = item.delivery_date
        if item.customer and not target_item.customer:
            target_item.customer = item.customer
        for processing in item.processing:
            if processing not in target_item.processing:
                target_item.processing.append(processing)
        for machine_hint in item.machine_hints:
            if machine_hint not in target_item.machine_hints:
                target_item.machine_hints.append(machine_hint)
        target_item.rows.extend(item.rows)


def cell_at(values: list[object], index: int) -> str:
    if index >= len(values):
        return ""
    return cell_text(values[index])


def filter_orders(orders: Iterable[ProcessOrder], requested: str | None) -> list[ProcessOrder]:
    if not requested:
        return list(orders)
    wanted = {part.strip() for part in requested.split(",") if part.strip()}
    wanted_jobs = {programmer.normalize_lookup(part) for part in wanted}
    return [order for order in orders if order.aw_order in wanted or programmer.normalize_lookup(order.job_name) in wanted_jobs]


def visible_orders(orders: Iterable[ProcessOrder], config: dict[str, object]) -> list[ProcessOrder]:
    visible: list[ProcessOrder] = []
    for order in orders:
        if order.is_mirror(config) and not order.has_mirror_fabrication(config):
            continue
        visible.append(order)
    return visible


def attach_transom_panels(
    reader: PdfReader,
    panels: list[programmer.Panel],
    process_order: ProcessOrder,
    config: dict[str, object],
) -> None:
    existing_items = {panel.item for panel in panels}
    missing_items = [item for item in process_order.item_numbers if item not in existing_items]
    if not missing_items:
        return

    used_pages = {panel.page_index for panel in panels}
    candidates: list[tuple[int, str, str]] = []
    for page_index, page in enumerate(reader.pages):
        if page_index == 0 or page_index in used_pages:
            continue
        text = page.extract_text() or ""
        if not text.strip() or programmer.looks_like_template_page(text):
            continue
        if programmer.extract_item_number(text) is not None:
            continue
        transom_label = programmer.extract_transom_label(text)
        if transom_label is None:
            continue
        candidates.append((page_index, text, transom_label))

    if not candidates:
        return

    candidates.sort(key=lambda entry: entry[0])
    missing_items = sorted(missing_items)
    pair_count = min(len(missing_items), len(candidates))
    for item_number, (page_index, text, transom_label) in zip(missing_items[-pair_count:], candidates[-pair_count:]):
        width, height = programmer.extract_dimensions(text)
        panel = programmer.classify_panel(
            programmer.Panel(
                item=item_number,
                page_index=page_index,
                text=text,
                width=width,
                height=height,
                machine="",
            ),
            config,
            process_order.aw_order,
        )
        panel.reasons.append(f"transom sketch label {transom_label} mapped to P{item_number}")
        panels.append(panel)

    panels.sort(key=lambda panel: panel.item)


def apply_process_hints(
    panels: list[programmer.Panel],
    process_order: ProcessOrder,
    config: dict[str, object],
) -> None:
    for panel in panels:
        process_item = process_order.items.get(panel.item)
        if process_item is None:
            panel.warnings.append("No matching process-list item row found.")
            continue
        panel.process_text = process_item.text_blob()

        is_mirror_order = process_order.is_mirror(config)
        if is_mirror_order:
            if process_item.has_mirror_fabrication(config):
                set_panel_machine(panel, "WJ", "mirror fabrication uses WJ")
                panel.indicator_corner = "top_left"
                panel.rotation_degrees = -90 if panel.height and panel.width and panel.height > panel.width else 0
            else:
                panel.machine = ""
                panel.label_only = True
                panel.skip_dxf = True
                panel.indicator_corner = None
                panel.rotation_degrees = None
                panel.reasons.append("mirror without fabrication skipped")
                continue

        desired_machine = process_item.desired_machine()
        processing_machine = process_item.inferred_denver_machine(config)
        strong_process_wj = process_item.has_strong_waterjet_fabrication(config)
        strong_pdf_wj = programmer.has_pdf_waterjet_evidence(panel.text, config)
        if not is_mirror_order and desired_machine:
            original_machine = panel.machine
            if desired_machine == "WJ":
                if strong_process_wj or strong_pdf_wj or denver_minimum_forces_wj(panel, config):
                    set_panel_machine(panel, desired_machine, f"process list machine: {desired_machine}")
                elif processing_machine:
                    panel.reasons.append("process list says WJ, but no WJ-only fabrication found")
                    set_panel_machine(panel, processing_machine, f"process-list fabrication suggests {processing_machine}")
                elif original_machine == "WJ":
                    panel.reasons.append(f"process list machine: {desired_machine}")
                else:
                    set_panel_machine(panel, desired_machine, f"process list machine: {desired_machine}")
            else:
                set_panel_machine(panel, desired_machine, f"process list machine: {desired_machine}")
        elif not is_mirror_order and processing_machine:
            if panel.machine != processing_machine and (not panel.machine or panel.label_only):
                set_panel_machine(panel, processing_machine, f"process-list fabrication suggests {processing_machine}")
            else:
                panel.reasons.append(f"process-list fabrication confirms {processing_machine}")
        elif not is_mirror_order:
            panel.machine = ""
            panel.label_only = True
            panel.skip_dxf = True
            panel.indicator_corner = None
            panel.rotation_degrees = None
            panel.reasons.append("process list has no cutting machine")

        if panel.machine == "WJ":
            panel.indicator_corner = "top_left"
            panel.rotation_degrees = -90 if panel.height and panel.width and panel.height > panel.width else 0
        elif panel.machine.startswith("DENVER"):
            panel.rotation_degrees = 90 if panel.height and panel.width and panel.height > panel.width else 0
            panel.indicator_corner = programmer.denver_grabber_corner_for_rotation(panel.rotation_degrees)

        if process_item.has_diamon_fusion:
            panel.diamon_fusion = True
            panel.reasons.append("process list Diamon Fusion")

        programmer.apply_auto_angle_correction(panel, config)
        programmer.apply_override(panel, config, process_order.aw_order)
        programmer.apply_auto_angle_correction(panel, config)
        programmer.validate_panel_constraints(panel, config)


def set_panel_machine(panel: programmer.Panel, machine: str, reason: str) -> None:
    panel.machine = machine
    panel.label_only = False
    panel.skip_dxf = False
    panel.reasons.append(reason)


def denver_minimum_forces_wj(panel: programmer.Panel, config: dict[str, object]) -> bool:
    rules = config.get("rules", {})
    if not isinstance(rules, dict):
        return False
    denver_min = float(rules.get("denver_min_inches", 6.125))
    return (
        panel.width is not None
        and panel.height is not None
        and min(panel.width, panel.height) < denver_min
    )


def process_list_fabrication_keywords(config: dict[str, object]) -> set[str]:
    keywords = upper_config_list(
        config,
        "fabrication_keywords",
        ["PPH", "GEN", "HINGE", "HOLE", "CUTOUT", "CUT-OUT", "CORNER NOTCH", "EDGE NOTCH", "NOTCH", "RADIUS"],
    )
    keywords.update(upper_config_list(config, "denver_fabrication_keywords", ["K CUT", "K-CUT"]))
    keywords.update(
        {
            "SLOT",
            "SLOTTED",
            "SCU",
            "SCU4",
            "MACRO",
            "MITRE",
            "MITER",
            "BACK MITRE",
            "BACK MITER",
            "CUT-IN",
            "CUT IN",
            "CUTIN",
        }
    )
    return keywords


def prepare_job(
    folder: Path,
    sketch_output_dir: Path,
    dxf_output_dir: Path,
    report_dir: Path,
    config: dict[str, object],
    process_order: ProcessOrder,
    remake_items: set[int] | None = None,
) -> tuple[programmer.Job, PdfReader, list[str]]:
    pdf_path = programmer.find_pdf(folder, process_order.job_name).resolve()
    reader = PdfReader(str(pdf_path))
    panels = programmer.analyze_panels(reader, config, process_order.aw_order)
    attach_transom_panels(reader, panels, process_order, config)
    apply_process_hints(panels, process_order, config)
    programmer.refine_panel_orientations(reader, panels, config)
    for panel in panels:
        programmer.apply_override(panel, config, process_order.aw_order)
    effective_remake_items = (
        set(process_order.item_numbers)
        if remake_items is not None and not remake_items
        else remake_items
    )
    selected_remake_items = programmer.apply_remake_selection(panels, effective_remake_items)

    job = programmer.Job(
        pdf_path=pdf_path,
        aw_order=process_order.aw_order,
        job_name=process_order.job_name,
        panels=panels,
        output_pdf=sketch_output_dir / f"{process_order.aw_order}.pdf",
        report_path=report_dir / f"{process_order.aw_order}_programming_report.txt",
        remake_items=selected_remake_items,
    )
    programmer.assign_dxf_paths(job, folder, dxf_output_dir, config)
    return job, reader, collect_issues(job, process_order)


def collect_issues(job: programmer.Job, process_order: ProcessOrder) -> list[str]:
    issues: list[str] = []
    expected = set(process_order.item_numbers)
    actual = {panel.item for panel in job.panels}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        issues.append("Process list item(s) missing from PDF: " + ", ".join(f"P{i}" for i in missing))
    if extra and job.remake_items is None:
        issues.append("PDF item(s) missing from process list: " + ", ".join(f"P{i}" for i in extra))

    for panel in job.panels:
        for warning in panel.warnings:
            issues.append(f"P{panel.item}: {warning}")
        if not panel.skip_dxf and panel.source_dxf is None:
            issues.append(f"P{panel.item}: missing source DXF")
    return issues


def process_one_order(
    process_order: ProcessOrder,
    folder: Path,
    sketch_output_dir: Path,
    dxf_output_dir: Path,
    report_dir: Path,
    config: dict[str, object],
    apply: bool,
    force: bool,
    skip_pdf: bool,
    skip_dxf: bool,
    remake_items: set[int] | None = None,
) -> BatchJobResult:
    item_text = ", ".join(f"P{i}" for i in process_order.item_numbers)
    result = BatchJobResult(
        aw_order=process_order.aw_order,
        job_name=process_order.job_name,
        customer=process_order.customer,
        items=item_text,
        status="PENDING",
        delivery_date=process_order.delivery_date,
    )

    try:
        job, reader, issues = prepare_job(
            folder,
            sketch_output_dir,
            dxf_output_dir,
            report_dir,
            config,
            process_order,
            remake_items=remake_items,
        )
        result.input_pdf = job.pdf_path
        result.output_pdf = job.output_pdf
        result.report_path = job.report_path
        result.issues.extend(issues)

        if apply:
            if not force and not skip_pdf and job.output_pdf.exists():
                result.status = "SKIPPED"
                result.issues.append(f"Output PDF already exists: {job.output_pdf.name}")
                return result
            if not skip_pdf:
                programmer.write_marked_pdf(job, reader, config, force=force)
            if not skip_dxf:
                result.issues.extend(write_dxfs_with_issue_collection(job, force=force, config=config))
            write_individual_report(job, result.issues, apply, skip_pdf, skip_dxf, force=True)

        result.status = "ISSUES" if result.issues else "OK"
        return result
    except Exception as exc:
        result.status = "FAILED"
        result.issues.append(str(exc))
        return result


def write_dxfs_with_issue_collection(job: programmer.Job, force: bool, config: dict[str, object]) -> list[str]:
    issues: list[str] = []
    for panel in job.panels:
        if panel.skip_dxf:
            continue
        if panel.source_dxf is None:
            issues.append(f"P{panel.item}: source DXF missing, skipped")
            continue
        if panel.output_dxf is None:
            issues.append(f"P{panel.item}: output DXF path missing, skipped")
            continue
        try:
            programmer.transform_dxf(
                panel.source_dxf,
                panel.output_dxf,
                programmer.effective_rotation(panel),
                force=force,
            )
        except Exception as exc:
            issues.append(f"P{panel.item}: DXF failed, {exc}")
    return issues


def write_individual_report(
    job: programmer.Job,
    issues: list[str],
    apply: bool,
    skip_pdf: bool,
    skip_dxf: bool,
    force: bool,
) -> None:
    report = programmer.build_report(job, apply=apply, skip_pdf=skip_pdf, skip_dxf=skip_dxf)
    if issues:
        report += "\nBatch issues:\n"
        report += "\n".join(f"- {issue}" for issue in issues) + "\n"
    programmer.write_report(job.report_path, report, force=force)


def run_batch(
    orders: list[ProcessOrder],
    folder: Path,
    sketch_output_dir: Path,
    dxf_output_dir: Path,
    report_dir: Path,
    config: dict[str, object],
    apply: bool,
    force: bool,
    skip_pdf: bool = False,
    skip_dxf: bool = False,
    remake_items_by_order: dict[str, set[int]] | None = None,
    progress: Callable[[BatchJobResult], None] | None = None,
) -> BatchRunResult:
    sketch_output_dir.mkdir(parents=True, exist_ok=True)
    dxf_output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    results: list[BatchJobResult] = []
    for process_order in orders:
        result = process_one_order(
            process_order=process_order,
            folder=folder,
            sketch_output_dir=sketch_output_dir,
            dxf_output_dir=dxf_output_dir,
            report_dir=report_dir,
            config=config,
            apply=apply,
            force=force,
            skip_pdf=skip_pdf,
            skip_dxf=skip_dxf,
            remake_items=None if remake_items_by_order is None else remake_items_by_order.get(process_order.aw_order),
        )
        results.append(result)
        if progress:
            progress(result)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text_report = report_dir / f"batch_programming_report_{timestamp}.txt"
    csv_report = report_dir / f"batch_programming_report_{timestamp}.csv"
    html_report = report_dir / f"batch_programming_report_{timestamp}.html"
    write_batch_text_report(text_report, results, apply)
    write_batch_csv_report(csv_report, results)
    write_batch_html_report(html_report, results, apply)
    return BatchRunResult(results=results, text_report=text_report, csv_report=csv_report, html_report=html_report)


def write_batch_text_report(path: Path, results: list[BatchJobResult], apply: bool) -> None:
    counts = count_statuses(results)
    lines = [
        f"Shower batch {'APPLY' if apply else 'DRY RUN'} report",
        f"Created: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Total orders: {len(results)}",
        "Status counts: " + ", ".join(f"{status}={count}" for status, count in counts.items()),
        "",
    ]
    for result in results:
        lines.append(f"{result.status}: {result.aw_order} | {result.job_name} | {result.items}")
        if result.delivery_date:
            lines.append(f"  delivery date: {result.delivery_date}")
        if result.input_pdf:
            lines.append(f"  input pdf: {result.input_pdf}")
        if result.output_pdf:
            lines.append(f"  output pdf: {result.output_pdf}")
        if result.report_path:
            lines.append(f"  order report: {result.report_path}")
        for issue in result.issues:
            lines.append(f"  issue: {issue}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_batch_csv_report(path: Path, results: list[BatchJobResult]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Status", "A&W Order", "Delivery Date", "Job", "Customer", "Items", "Input PDF", "Output PDF", "Issues"])
        for result in results:
            writer.writerow(
                [
                    result.status,
                    result.aw_order,
                    result.delivery_date,
                    result.job_name,
                    result.customer,
                    result.items,
                    str(result.input_pdf or ""),
                    str(result.output_pdf or ""),
                    " | ".join(result.issues),
                ]
            )


def write_batch_html_report(path: Path, results: list[BatchJobResult], apply: bool) -> None:
    counts = count_statuses(results)
    rows = []
    for result in results:
        rows.append(
            "<tr>"
            f"<td class='{html.escape(result.status.lower())}'>{html.escape(result.status)}</td>"
            f"<td>{html.escape(result.aw_order)}</td>"
            f"<td>{html.escape(result.delivery_date)}</td>"
            f"<td>{html.escape(result.job_name)}</td>"
            f"<td>{html.escape(result.customer)}</td>"
            f"<td>{html.escape(result.items)}</td>"
            f"<td>{path_link(result.input_pdf)}</td>"
            f"<td>{path_link(result.output_pdf)}</td>"
            f"<td>{html.escape('; '.join(result.issues))}</td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Shower Batch Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2933; }}
h1 {{ margin-bottom: 4px; }}
.summary {{ margin: 10px 0 18px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #d7dde5; padding: 7px 9px; vertical-align: top; }}
th {{ background: #eef3f8; text-align: left; position: sticky; top: 0; }}
tr:nth-child(even) {{ background: #f8fafc; }}
.ok {{ color: #0f7a3b; font-weight: bold; }}
.issues {{ color: #9a5b00; font-weight: bold; }}
.failed, .skipped {{ color: #b42318; font-weight: bold; }}
</style>
</head>
<body>
<h1>Shower Batch {'Apply' if apply else 'Dry Run'} Report</h1>
<div class="summary">Created {datetime.now():%Y-%m-%d %H:%M:%S} | Total orders: {len(results)} | {html.escape(', '.join(f'{k}={v}' for k, v in counts.items()))}</div>
<table>
<thead><tr><th>Status</th><th>A&amp;W Order</th><th>Delivery Date</th><th>Job</th><th>Customer</th><th>Items</th><th>Input PDF</th><th>Output PDF</th><th>Issues</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def path_link(path: Path | None) -> str:
    if path is None:
        return ""
    label = html.escape(path.name)
    try:
        return f'<a href="{html.escape(path.resolve().as_uri())}">{label}</a>'
    except ValueError:
        return html.escape(str(path))


def count_statuses(results: list[BatchJobResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def preview_orders(orders: list[ProcessOrder], folder: Path) -> list[BatchJobResult]:
    results: list[BatchJobResult] = []
    for order in orders:
        result = BatchJobResult(
            aw_order=order.aw_order,
            job_name=order.job_name,
            customer=order.customer,
            items=", ".join(f"P{i}" for i in order.item_numbers),
            status="READY",
            delivery_date=order.delivery_date,
        )
        try:
            result.input_pdf = programmer.find_pdf(folder, order.job_name).resolve()
        except Exception as exc:
            result.status = "ISSUES"
            result.issues.append(str(exc))
        results.append(result)
    return results


def resolve_process_list_path(process_list_value: str, folder: Path) -> Path:
    process_list = Path(process_list_value)
    if process_list.is_absolute():
        return process_list
    candidates = [
        Path.cwd() / process_list,
        programmer.project_root() / process_list,
        folder / process_list,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (folder / process_list).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch process shower orders from Process List Per Machine.xlsx.")
    parser.add_argument("--folder", default=str(programmer.default_orders_dir()), help="Folder containing the PDFs and DXFs.")
    parser.add_argument(
        "--process-list",
        default=str(programmer.default_process_list_path()),
        help="Path to one process-list workbook or a folder of immediate .xlsx process lists.",
    )
    parser.add_argument("--output-dir", default=str(programmer.default_output_dir()), help="Root folder for Sketches, Programs, and Reports.")
    parser.add_argument("--sketch-dir", help="Optional folder for marked PDFs. Defaults to OUTPUT\\Sketches.")
    parser.add_argument("--programs-dir", help="Optional folder for adjusted DXFs. Defaults to OUTPUT\\Programs.")
    parser.add_argument("--report-dir", help="Optional folder for reports. Defaults to OUTPUT\\Reports.")
    parser.add_argument("--dxf-output-dir", help="Optional separate folder for adjusted DXFs.")
    parser.add_argument("--config", default=programmer.DEFAULT_CONFIG_NAME, help="JSON config file.")
    parser.add_argument("--orders", help="Comma-separated A&W order numbers to process.")
    parser.add_argument("--apply", action="store_true", help="Write marked PDFs and DXFs. Without this, writes reports only.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing per-order outputs.")
    parser.add_argument("--skip-pdf", action="store_true", help="Do not write marked PDFs.")
    parser.add_argument("--skip-dxf", action="store_true", help="Do not write adjusted DXFs.")
    parser.add_argument("--remake-orders", help="Comma-separated A&W order numbers to mark REMAKE.")
    parser.add_argument("--remake-items", help="Optional comma list of remake items applied to remake orders, e.g. 1,3.")
    parser.add_argument("--preview", action="store_true", help="Only list orders and PDF availability.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    folder = Path(args.folder).resolve()
    process_list = resolve_process_list_path(args.process_list, folder)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = programmer.project_root() / output_dir
    sketch_output_dir = Path(args.sketch_dir) if args.sketch_dir else output_dir / "Sketches"
    if not sketch_output_dir.is_absolute():
        sketch_output_dir = programmer.project_root() / sketch_output_dir
    dxf_output_dir = Path(args.dxf_output_dir or args.programs_dir) if (args.dxf_output_dir or args.programs_dir) else output_dir / "Programs"
    if not dxf_output_dir.is_absolute():
        dxf_output_dir = programmer.project_root() / dxf_output_dir
    report_dir = Path(args.report_dir) if args.report_dir else output_dir / "Reports"
    if not report_dir.is_absolute():
        report_dir = programmer.project_root() / report_dir
    config = programmer.load_config(programmer.resolve_config_path(args.config, folder))
    manual_overrides = output_dir / "manual_overrides.json"
    if manual_overrides.exists():
        config = programmer.merge_item_overrides(config, programmer.load_config(manual_overrides))
    loaded_orders = load_process_orders(process_list)
    orders = filter_orders(loaded_orders, args.orders) if args.orders else visible_orders(loaded_orders, config)
    if not orders:
        raise RuntimeError("No orders found in the process list.")

    remake_items_by_order = None
    if args.remake_orders:
        remake_orders = {part.strip() for part in args.remake_orders.split(",") if part.strip()}
        remake_items = programmer.parse_item_list(args.remake_items)
        remake_items_by_order = {order.aw_order: set(remake_items) for order in orders if order.aw_order in remake_orders}

    if args.preview:
        for result in preview_orders(orders, folder):
            issue_text = "; ".join(result.issues)
            print(f"{result.status:7} {result.aw_order} {result.job_name} {result.items} {issue_text}")
        return 0

    run = run_batch(
        orders=orders,
        folder=folder,
        sketch_output_dir=sketch_output_dir,
        dxf_output_dir=dxf_output_dir,
        report_dir=report_dir,
        config=config,
        apply=args.apply,
        force=args.force,
        skip_pdf=args.skip_pdf,
        skip_dxf=args.skip_dxf,
        remake_items_by_order=remake_items_by_order,
        progress=lambda result: print(f"{result.status:7} {result.aw_order} {result.job_name}"),
    )
    print(f"\nText report: {run.text_report}")
    print(f"CSV report: {run.csv_report}")
    print(f"HTML report: {run.html_report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
