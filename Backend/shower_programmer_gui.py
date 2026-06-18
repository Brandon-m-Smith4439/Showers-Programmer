#!/usr/bin/env python3
"""Small Tkinter front end for shower batch programming."""

from __future__ import annotations

import os
import html
import json
import math
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from pypdf import PdfReader, PdfWriter

import shower_batch
import shower_programmer as programmer

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None


class ShowerProgrammerApp:
    GITHUB_UPDATE_OWNER = "Brandon-m-Smith4439"
    GITHUB_UPDATE_REPO = "Showers-Programmer"
    GITHUB_UPDATE_BRANCH = "main"
    SHOP_SKETCHES_DIR = Path(r"I:\BAREFOOT-INSTALL\Glass Production\Sketches")
    SHOP_PROGRAMS_DIR = Path(r"I:\BAREFOOT-INSTALL\Glass Production\Programs")
    EDI_IMPORT_ORDERS_DIR = Path(r"I:\BAREFOOT-INSTALL\Glass Production\EDIImportSG\Showers Programmer Input")
    ORDER_FILE_EXTENSIONS = {".pdf", ".dxf"}
    PROCESS_LIST_FILE_EXTENSIONS = shower_batch.PROCESS_LIST_EXTENSIONS
    INPUT_ARCHIVE_FOLDER_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Shower Programmer")
        self.root.geometry("1180x720")
        self.root.minsize(980, 560)
        self.root.after(0, lambda: self.maximize_window(self.root))
        self.folder_var = tk.StringVar(value=str(programmer.default_orders_dir()))
        self.process_list_var = tk.StringVar(value=str(programmer.default_process_list_path()))
        self.output_dir_var = tk.StringVar(value=str(programmer.default_output_dir()))
        self.force_var = tk.BooleanVar(value=False)
        self.skip_dxf_var = tk.BooleanVar(value=False)
        self.remake_var = tk.BooleanVar(value=False)
        self.remake_items_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Scan the process list to begin.")

        self.orders: list[shower_batch.ProcessOrder] = []
        self.order_by_aw: dict[str, shower_batch.ProcessOrder] = {}
        self.tree_rows: dict[str, str] = {}
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_reports: shower_batch.BatchRunResult | None = None
        self.last_run_folder: Path | None = None
        self.is_busy = False

        self.build_ui()
        self.root.after(150, self.drain_worker_queue)
        self.root.after(350, self.scan_orders)

    @staticmethod
    def maximize_window(window: Any) -> None:
        try:
            window.state("zoomed")
            return
        except tk.TclError:
            pass

        try:
            window.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass

        try:
            window.attributes("-fullscreen", True)
        except tk.TclError:
            pass

    @staticmethod
    def toggle_window_maximize(window: Any) -> None:
        try:
            window.state("normal" if window.state() == "zoomed" else "zoomed")
            return
        except tk.TclError:
            pass
        try:
            window.attributes("-fullscreen", not bool(window.attributes("-fullscreen")))
        except tk.TclError:
            pass

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        paths = ttk.Frame(outer)
        paths.pack(fill=tk.X)
        self.add_path_row(paths, 0, "Folder", self.folder_var, self.choose_folder)
        self.add_path_row(paths, 1, "Process Lists", self.process_list_var, self.choose_process_list)
        self.add_path_row(paths, 2, "Output", self.output_dir_var, self.choose_output_dir)

        actions = ttk.Frame(outer)
        actions.pack(fill=tk.X, pady=(8, 8))
        ttk.Button(actions, text="Scan Orders", command=self.scan_orders).pack(side=tk.LEFT)
        ttk.Button(actions, text="Process Selected", command=self.process_selected).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Process All", command=lambda: self.run_orders(self.orders, apply=True)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Review Order", command=self.open_order_review).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Open Sketches", command=self.open_sketches_folder).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Open Programs", command=self.open_programs_folder).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Mark Checked", command=self.mark_selected_orders_checked).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(actions, text="Overwrite existing outputs", variable=self.force_var).pack(side=tk.LEFT, padx=(18, 0))
        ttk.Checkbutton(actions, text="Skip DXF output", variable=self.skip_dxf_var).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(actions, text="REMAKE", variable=self.remake_var).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(actions, text="Open Last Report", command=self.open_last_report).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Open Output Folder", command=self.open_output_folder).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(actions, text="Open Config", command=self.open_config).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(actions, text="Minimize", command=self.root.iconify).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(actions, text="Maximize", command=lambda: self.toggle_window_maximize(self.root)).pack(side=tk.RIGHT, padx=(0, 8))

        maintenance = ttk.Frame(outer)
        maintenance.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(maintenance, text="Maintenance").pack(side=tk.LEFT)
        ttk.Button(maintenance, text="Clear Sketch Memory", command=self.clear_sketch_memory).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(maintenance, text="Check for Updates", command=self.check_for_updates).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(maintenance, text="AutoCAD Save-As DXFs", command=self.autocad_save_as_programs).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(maintenance, text="Import EDI Orders", command=self.import_edi_orders).pack(side=tk.LEFT, padx=(8, 0))

        table_frame = ttk.Frame(outer)
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("status", "processed", "last_processed", "delivery", "order", "job", "customer", "items", "review", "pdf", "issues")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        headings = {
            "status": "Status",
            "processed": "Processed",
            "last_processed": "Last Processed",
            "delivery": "Delivery Date",
            "order": "A&W",
            "job": "Job",
            "customer": "Customer",
            "items": "Items",
            "review": "Review",
            "pdf": "PDF",
            "issues": "Issues",
        }
        widths = {
            "status": 92,
            "processed": 82,
            "last_processed": 132,
            "delivery": 105,
            "order": 82,
            "job": 230,
            "customer": 190,
            "items": 110,
            "review": 150,
            "pdf": 230,
            "issues": 330,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], minwidth=70, anchor=tk.W)
        self.tree.tag_configure("OK", foreground="#0f7a3b")
        self.tree.tag_configure("READY", foreground="#1f4e79")
        self.tree.tag_configure("ISSUES", foreground="#9a5b00")
        self.tree.tag_configure("FAILED", foreground="#b42318")
        self.tree.tag_configure("SKIPPED", foreground="#b42318")
        self.tree.bind("<Double-1>", self.open_order_review)
        self.tree.bind("<Control-a>", self.select_all_orders)
        self.tree.bind("<Control-A>", self.select_all_orders)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(8, 0))
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(bottom, textvariable=self.status_var, anchor=tk.W).pack(side=tk.LEFT, padx=(10, 0))
        send_buttons = ttk.Frame(bottom)
        send_buttons.pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(send_buttons, text="Send Sketches", command=self.send_sketches_to_shop).pack(side=tk.LEFT)
        ttk.Button(send_buttons, text="Send Programs", command=self.send_programs_to_shop).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(send_buttons, text="Select All", command=self.select_all_orders).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(send_buttons, text="Send All", command=self.send_all_to_shop).pack(side=tk.LEFT, padx=(6, 0))

    def add_path_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label, width=12).grid(row=row, column=0, sticky=tk.W, pady=2)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=(4, 6), pady=2)
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2, sticky=tk.E, pady=2)
        parent.columnconfigure(1, weight=1)

    def choose_folder(self) -> None:
        path = filedialog.askdirectory(initialdir=self.folder_var.get())
        if path:
            self.folder_var.set(path)

    def choose_process_list(self) -> None:
        current = Path(self.process_list_var.get())
        initial = current if current.is_dir() else current.parent
        path = filedialog.askdirectory(initialdir=str(initial), title="Select process-list folder")
        if path:
            self.process_list_var.set(path)

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)

    def scan_orders(self) -> None:
        if self.is_busy:
            self.status_var.set("Busy. Please wait for the current task to finish.")
            return
        try:
            folder = Path(self.folder_var.get()).resolve()
            process_list = Path(self.process_list_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.start_background_activity("Scanning process lists and importing matching EDI order files...")
        worker = threading.Thread(
            target=self.worker_scan_orders,
            args=(folder, process_list, output_dir),
            daemon=True,
        )
        worker.start()

    def import_edi_orders(self) -> None:
        if self.is_busy:
            self.status_var.set("Busy. Please wait for the current task to finish.")
            return
        try:
            folder = Path(self.folder_var.get()).resolve()
            process_list = Path(self.process_list_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.start_background_activity("Importing matching EDI order files...")
        worker = threading.Thread(
            target=self.worker_import_edi_orders,
            args=(folder, process_list, output_dir),
            daemon=True,
        )
        worker.start()

    def start_background_activity(self, message: str) -> None:
        self.is_busy = True
        self.set_controls_enabled(False)
        self.progress.stop()
        self.progress.configure(mode="indeterminate", maximum=100, value=0)
        self.progress.start(12)
        self.status_var.set(message)

    def finish_background_activity(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.is_busy = False
        self.set_controls_enabled(True)

    def worker_scan_orders(self, folder: Path, process_list: Path, output_dir: Path) -> None:
        try:
            config = self.config_with_manual_overrides(folder, output_dir)
            process_list_import_summary = self.copy_process_lists_from_import_folder(process_list)
            process_list_files = shower_batch.process_list_files(process_list)
            orders = shower_batch.visible_orders(shower_batch.load_process_orders(process_list), config)
            import_summary = self.copy_edi_orders_for_process_orders(folder, orders)
            previews = shower_batch.preview_orders(orders, folder)
            self.worker_queue.put(
                (
                    "scan_done",
                    {
                        "orders": orders,
                        "previews": previews,
                        "process_list_count": len(process_list_files),
                        "process_list_import_summary": process_list_import_summary,
                        "import_summary": import_summary,
                    },
                )
            )
        except Exception as exc:
            self.worker_queue.put(("scan_error", str(exc)))

    def worker_import_edi_orders(self, folder: Path, process_list: Path, output_dir: Path) -> None:
        try:
            process_list_import_summary = self.copy_process_lists_from_import_folder(process_list)
            if self.orders:
                orders = self.orders
                process_list_count = 0
            else:
                config = self.config_with_manual_overrides(folder, output_dir)
                process_list_files = shower_batch.process_list_files(process_list)
                process_list_count = len(process_list_files)
                orders = shower_batch.visible_orders(shower_batch.load_process_orders(process_list), config)
            import_summary = self.copy_edi_orders_for_process_orders(folder, orders)
            self.worker_queue.put(
                (
                    "import_done",
                    {
                        "orders": orders,
                        "process_list_count": process_list_count,
                        "process_list_import_summary": process_list_import_summary,
                        "import_summary": import_summary,
                    },
                )
            )
        except Exception as exc:
            self.worker_queue.put(("scan_error", str(exc)))

    def config_path(self, folder: Path) -> Path:
        return programmer.resolve_config_path(programmer.DEFAULT_CONFIG_NAME, folder)

    def config_with_manual_overrides(self, folder: Path, output_dir: Path) -> dict[str, object]:
        config = programmer.load_config(self.config_path(folder))
        manual = self.load_manual_overrides_for_output(output_dir)
        return programmer.merge_item_overrides(config, manual)

    def manual_overrides_path(self) -> Path:
        return Path(self.output_dir_var.get()).resolve() / "manual_overrides.json"

    def processing_history_path(self) -> Path:
        return Path(self.output_dir_var.get()).resolve() / "processing_history.json"

    @staticmethod
    def load_manual_overrides_for_output(output_dir: Path) -> dict[str, object]:
        path = output_dir / "manual_overrides.json"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}

    def load_manual_overrides(self) -> dict[str, object]:
        return self.load_manual_overrides_for_output(Path(self.output_dir_var.get()).resolve())

    def save_manual_overrides(self, data: dict[str, object]) -> None:
        path = self.manual_overrides_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    def load_processing_history(self) -> dict[str, object]:
        path = self.processing_history_path()
        if not path.exists():
            return {"orders": {}}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {"orders": {}}

    def save_processing_history(self, data: dict[str, object]) -> None:
        path = self.processing_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    def history_for_order(self, aw_order: str) -> dict[str, object]:
        try:
            data = self.load_processing_history()
        except Exception:
            return {}
        orders = data.get("orders", {})
        if not isinstance(orders, dict):
            return {}
        entry = orders.get(str(aw_order), {})
        return entry if isinstance(entry, dict) else {}

    def insert_or_update_result(self, result: shower_batch.BatchJobResult) -> None:
        processed, last_processed = self.processed_summary_for_order(result.aw_order)
        values = (
            result.status,
            processed,
            last_processed,
            result.delivery_date,
            result.aw_order,
            result.job_name,
            result.customer,
            result.items,
            self.review_status_for_order(result.aw_order),
            result.input_pdf.name if result.input_pdf else "",
            "; ".join(result.issues),
        )
        row_id = self.tree_rows.get(result.aw_order)
        tag = result.status if result.status in {"OK", "READY", "ISSUES", "FAILED", "SKIPPED"} else ""
        if row_id:
            self.tree.item(row_id, values=values, tags=(tag,))
        else:
            row_id = self.tree.insert("", tk.END, values=values, tags=(tag,))
            self.tree_rows[result.aw_order] = row_id

    def processed_summary_for_order(self, aw_order: str) -> tuple[str, str]:
        history = self.history_for_order(aw_order)
        last_processed = str(history.get("last_processed", ""))
        if last_processed:
            return "Yes", last_processed
        output_dir = Path(self.output_dir_var.get()).resolve()
        sketch_path = self.find_order_sketch_path(aw_order, output_dir)
        if sketch_path.exists():
            return "Yes", datetime.fromtimestamp(sketch_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        return "No", ""

    def output_dirs_for_run(self, run_folder: Path) -> tuple[Path, Path, Path]:
        return run_folder / "Sketches", run_folder / "Programs", run_folder / "Reports"

    def run_folder_for_order(self, aw_order: str, output_dir: Path) -> Path | None:
        history = self.history_for_order(aw_order)
        run_value = str(history.get("run_folder", "")).strip()
        if run_value:
            run_folder = Path(run_value)
            if not run_folder.is_absolute():
                run_folder = output_dir / run_folder
            if run_folder.exists() and (run_folder / "Sketches" / f"{aw_order}.pdf").exists():
                return run_folder
        runs_dir = output_dir / "Runs"
        if runs_dir.exists():
            numeric_runs = sorted(
                (path for path in runs_dir.iterdir() if path.is_dir() and path.name.isdigit()),
                key=lambda path: int(path.name),
                reverse=True,
            )
            other_runs = sorted(
                (path for path in runs_dir.iterdir() if path.is_dir() and not path.name.isdigit()),
                key=lambda path: path.name,
                reverse=True,
            )
            for run_folder in numeric_runs + other_runs:
                if (run_folder / "Sketches" / f"{aw_order}.pdf").exists():
                    return run_folder
        return None

    def output_dirs_for_order(self, aw_order: str, output_dir: Path) -> tuple[Path | None, Path, Path, Path]:
        run_folder = self.run_folder_for_order(aw_order, output_dir)
        if run_folder is not None:
            sketch_dir, programs_dir, report_dir = self.output_dirs_for_run(run_folder)
            return run_folder, sketch_dir, programs_dir, report_dir
        return None, output_dir / "Sketches", output_dir / "Programs", output_dir / "Reports"

    def find_order_sketch_path(self, aw_order: str, output_dir: Path) -> Path:
        _run_folder, sketch_dir, _programs_dir, _report_dir = self.output_dirs_for_order(aw_order, output_dir)
        path = sketch_dir / f"{aw_order}.pdf"
        if path.exists():
            return path
        return output_dir / "Sketches" / f"{aw_order}.pdf"

    def review_status_for_order(self, aw_order: str) -> str:
        try:
            data = self.load_manual_overrides()
        except Exception:
            return ""
        item_overrides = data.get("item_overrides", {})
        if not isinstance(item_overrides, dict):
            return ""
        order_overrides = item_overrides.get(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            return ""
        if bool(order_overrides.get("_order_checked")):
            return "Order checked"
        checked: list[str] = []
        for key, value in order_overrides.items():
            if not str(key).isdigit() or not isinstance(value, dict):
                continue
            if bool(value.get("checked")):
                checked.append(f"P{int(key)} checked")
        return ", ".join(sorted(checked, key=lambda text: int(text.split()[0][1:])))

    def mark_selected_orders_checked(self) -> None:
        orders = self.selected_orders()
        if not orders:
            messagebox.showinfo("No selection", "Select one or more orders first.")
            return
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        for order in orders:
            order_overrides = item_overrides.setdefault(order.aw_order, {})
            if not isinstance(order_overrides, dict):
                order_overrides = {}
                item_overrides[order.aw_order] = order_overrides
            order_overrides["_order_checked"] = True
            row_id = self.tree_rows.get(order.aw_order)
            if row_id:
                values = list(self.tree.item(row_id, "values"))
                if len(values) >= 9:
                    values[8] = "Order checked"
                    self.tree.item(row_id, values=values)
        self.save_manual_overrides(data)
        self.status_var.set(f"Marked {len(orders)} order(s) checked.")

    def selected_orders(self) -> list[shower_batch.ProcessOrder]:
        selected = []
        for row_id in self.tree.selection():
            values = self.tree.item(row_id, "values")
            if len(values) >= 5:
                order = self.order_by_aw.get(values[4])
                if order:
                    selected.append(order)
        return selected

    def select_all_orders(self, _event: tk.Event | None = None) -> str | None:
        row_ids = self.tree.get_children()
        if not row_ids:
            self.status_var.set("No scanned orders to select.")
            return "break" if _event is not None else None
        self.tree.selection_set(*row_ids)
        self.tree.focus(row_ids[0])
        self.tree.see(row_ids[0])
        self.status_var.set(f"Selected {len(row_ids)} order(s).")
        return "break" if _event is not None else None

    def selected_or_visible_aw_orders(self) -> list[str]:
        selected = [order.aw_order for order in self.selected_orders()]
        if selected:
            return selected
        aw_orders: list[str] = []
        for row_id in self.tree.get_children():
            values = self.tree.item(row_id, "values")
            if len(values) >= 5 and values[4]:
                aw_orders.append(str(values[4]))
        return aw_orders

    def process_selected(self) -> None:
        orders = self.selected_orders()
        if not orders:
            messagebox.showinfo("No selection", "Select one or more orders first.")
            return
        remake_items_by_order = None
        if self.remake_var.get():
            self.remake_items_var.set("")
            remake_items_by_order = {order.aw_order: set() for order in orders}
        self.run_orders(
            orders,
            apply=True,
            remake_items_by_order=remake_items_by_order,
            force_override=True if remake_items_by_order is not None else None,
        )

    def run_orders(
        self,
        orders: list[shower_batch.ProcessOrder],
        apply: bool,
        remake_items_by_order: dict[str, set[int]] | None = None,
        force_override: bool | None = None,
        skip_dxf_override: bool | None = None,
    ) -> None:
        if self.is_busy:
            messagebox.showinfo("Batch running", "A batch is already running.")
            return
        if not orders:
            messagebox.showinfo("No orders", "Scan the process list first.")
            return
        try:
            folder = Path(self.folder_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            process_list_path = Path(self.process_list_var.get()).resolve()
            force = self.force_var.get() if force_override is None else force_override
            skip_dxf = self.skip_dxf_var.get() if skip_dxf_override is None else skip_dxf_override
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        if apply and not force:
            conflicts = self.existing_output_conflicts(orders, output_dir, skip_dxf)
            if conflicts:
                preview = "\n".join(conflicts[:8])
                if len(conflicts) > 8:
                    preview += f"\n...and {len(conflicts) - 8} more"
                if not messagebox.askyesno(
                    "Existing outputs found",
                    "Some selected outputs already exist:\n\n"
                    f"{preview}\n\nOverwrite them and create a new indexed run folder?",
                ):
                    return
                force = True

        self.is_busy = True
        self.set_controls_enabled(False)
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=len(orders), value=0)
        self.status_var.set(("Processing" if apply else "Dry running") + f" {len(orders)} order(s)...")

        worker = threading.Thread(
            target=self.worker_run_batch,
            args=(orders, apply, folder, output_dir, process_list_path, force, skip_dxf, remake_items_by_order),
            daemon=True,
        )
        worker.start()

    def existing_output_conflicts(
        self,
        orders: list[shower_batch.ProcessOrder],
        output_dir: Path,
        skip_dxf: bool,
    ) -> list[str]:
        conflicts: list[str] = []
        for order in orders:
            search_roots = [output_dir]
            runs_dir = output_dir / "Runs"
            if runs_dir.exists():
                search_roots.extend(path for path in runs_dir.iterdir() if path.is_dir())
            for root in search_roots:
                sketch = root / "Sketches" / f"{order.aw_order}.pdf"
                if sketch.exists():
                    conflicts.append(str(sketch.relative_to(output_dir)))
                programs_dir = root / "Programs"
                if not skip_dxf and programs_dir.exists():
                    for path in sorted(programs_dir.glob(f"{order.aw_order}*.dxf")):
                        conflicts.append(str(path.relative_to(output_dir)))
        return conflicts

    def worker_run_batch(
        self,
        orders: list[shower_batch.ProcessOrder],
        apply: bool,
        folder: Path,
        output_dir: Path,
        process_list_path: Path,
        force: bool,
        skip_dxf: bool,
        remake_items_by_order: dict[str, set[int]] | None,
    ) -> None:
        try:
            run_folder = self.next_batch_run_folder(output_dir, process_list_path) if apply else output_dir / "Reviews" / "DryRun"
            sketch_dir, programs_dir, report_dir = self.output_dirs_for_run(run_folder)
            if apply and force:
                self.clear_existing_outputs_for_orders(orders, output_dir, skip_dxf)
            config = self.config_with_manual_overrides(folder, output_dir)
            run = shower_batch.run_batch(
                orders=orders,
                folder=folder,
                sketch_output_dir=sketch_dir,
                dxf_output_dir=programs_dir,
                report_dir=report_dir,
                config=config,
                apply=apply,
                force=force,
                skip_pdf=False,
                skip_dxf=skip_dxf,
                remake_items_by_order=remake_items_by_order,
                progress=lambda result: self.worker_queue.put(("result", result)),
            )
            if apply:
                processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.write_run_manifest(run, run_folder, sketch_dir, programs_dir, report_dir, processed_at, remake_items_by_order)
                self.update_processing_history(run, output_dir, processed_at, run_folder, remake_items_by_order)
            self.worker_queue.put(("done", (run, run_folder)))
        except Exception as exc:
            self.worker_queue.put(("error", str(exc)))

    def write_run_manifest(
        self,
        run: shower_batch.BatchRunResult,
        run_folder: Path,
        sketch_dir: Path,
        programs_dir: Path,
        report_dir: Path,
        processed_at: str,
        remake_items_by_order: dict[str, set[int]] | None,
    ) -> None:
        run_folder.mkdir(parents=True, exist_ok=True)
        manifest = {
            "created": processed_at,
            "sketches": str(sketch_dir),
            "programs": str(programs_dir),
            "reports": str(report_dir),
            "remake_items_by_order": {
                order: sorted(items) for order, items in (remake_items_by_order or {}).items()
            },
        }
        with (run_folder / "manifest.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)

    @staticmethod
    def clear_existing_outputs_for_orders(
        orders: list[shower_batch.ProcessOrder],
        output_dir: Path,
        skip_dxf: bool,
    ) -> int:
        removed = 0
        for order in orders:
            roots = [output_dir]
            runs_dir = output_dir / "Runs"
            if runs_dir.exists():
                roots.extend(path for path in runs_dir.iterdir() if path.is_dir())
            candidates: list[Path] = []
            for root in roots:
                candidates.extend(
                    [
                        root / "Sketches" / f"{order.aw_order}.pdf",
                        root / "Reports" / f"{order.aw_order}_programming_report.txt",
                    ]
                )
                programs_dir = root / "Programs"
                if not skip_dxf and programs_dir.exists():
                    candidates.extend(sorted(programs_dir.glob(f"{order.aw_order}*.dxf")))
            for path in candidates:
                if not path.exists() or not path.is_file():
                    continue
                if not path.resolve().is_relative_to(output_dir.resolve()):
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed

    @staticmethod
    def next_indexed_run_folder(output_dir: Path) -> Path:
        runs_dir = output_dir / "Runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        indexes = [
            int(path.name)
            for path in runs_dir.iterdir()
            if path.is_dir() and path.name.isdigit()
        ]
        return runs_dir / str((max(indexes) if indexes else 0) + 1)

    def next_batch_run_folder(self, output_dir: Path, process_list_path: Path) -> Path:
        runs_dir = output_dir / "Runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        label = self.process_list_run_label(process_list_path)
        if not label:
            return self.next_indexed_run_folder(output_dir)
        folder = runs_dir / label
        if not folder.exists():
            return folder
        index = 2
        while (runs_dir / f"{label}_{index}").exists():
            index += 1
        return runs_dir / f"{label}_{index}"

    @staticmethod
    def process_list_run_label(process_list_path: Path) -> str:
        try:
            files = shower_batch.process_list_files(process_list_path)
        except Exception:
            files = [process_list_path] if process_list_path.is_file() else []
        stems = [path.stem for path in files if path.name and not path.name.startswith("~$")]
        if not stems:
            return ""
        raw = stems[0] if len(stems) == 1 else f"{stems[0]}_plus{len(stems) - 1}"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")[:80]

    def update_processing_history(
        self,
        run: shower_batch.BatchRunResult,
        output_dir: Path,
        processed_at: str,
        run_folder: Path,
        remake_items_by_order: dict[str, set[int]] | None,
    ) -> None:
        history = self.load_processing_history()
        orders = history.setdefault("orders", {})
        if not isinstance(orders, dict):
            orders = {}
            history["orders"] = orders
        for result in run.results:
            if result.status not in {"OK", "ISSUES"}:
                continue
            entry = orders.setdefault(result.aw_order, {})
            if not isinstance(entry, dict):
                entry = {}
                orders[result.aw_order] = entry
            entry["last_processed"] = processed_at
            entry["delivery_date"] = result.delivery_date
            entry["status"] = result.status
            entry["run_folder"] = str(run_folder)
            entry["output_pdf"] = str(result.output_pdf or "")
            entry["report_path"] = str(result.report_path or "")
            if remake_items_by_order and result.aw_order in remake_items_by_order:
                entry["remake_items"] = sorted(remake_items_by_order[result.aw_order])
            else:
                entry.pop("remake_items", None)
        self.save_processing_history(history)

    def latest_run_folder(self, output_dir: Path) -> Path | None:
        runs_dir = output_dir / "Runs"
        if not runs_dir.exists():
            return None
        runs = [path for path in runs_dir.iterdir() if path.is_dir()]
        return max(runs, key=lambda path: path.stat().st_mtime) if runs else None

    def drain_worker_queue(self) -> None:
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "result":
                    result = payload
                    assert isinstance(result, shower_batch.BatchJobResult)
                    self.insert_or_update_result(result)
                    self.progress.step(1)
                    self.status_var.set(f"{result.status}: {result.aw_order} {result.job_name}")
                elif kind == "done":
                    run, run_folder = payload
                    assert isinstance(run, shower_batch.BatchRunResult)
                    self.last_reports = run
                    self.last_run_folder = run_folder if isinstance(run_folder, Path) else self.latest_run_folder(Path(self.output_dir_var.get()).resolve())
                    self.is_busy = False
                    self.set_controls_enabled(True)
                    for result in run.results:
                        self.insert_or_update_result(result)
                    counts = shower_batch.count_statuses(run.results)
                    self.status_var.set("Done. " + ", ".join(f"{k}={v}" for k, v in counts.items()))
                    messagebox.showinfo("Batch complete", f"Report written:\n{run.html_report}")
                elif kind == "error":
                    self.finish_background_activity()
                    self.status_var.set("Error")
                    messagebox.showerror("Batch failed", str(payload))
                elif kind == "scan_done":
                    data = payload
                    assert isinstance(data, dict)
                    orders = data.get("orders", [])
                    previews = data.get("previews", [])
                    process_list_count = int(data.get("process_list_count", 0))
                    process_list_import_summary = data.get("process_list_import_summary", {})
                    import_summary = data.get("import_summary", {})
                    assert isinstance(orders, list)
                    assert isinstance(previews, list)
                    self.orders = orders
                    self.order_by_aw = {order.aw_order: order for order in self.orders}
                    self.tree.delete(*self.tree.get_children())
                    self.tree_rows.clear()
                    for result in previews:
                        assert isinstance(result, shower_batch.BatchJobResult)
                        self.insert_or_update_result(result)
                    self.finish_background_activity()
                    self.status_var.set(
                        self.scan_status_message(
                            len(self.orders),
                            process_list_count,
                            import_summary,
                            process_list_import_summary,
                        )
                    )
                elif kind == "import_done":
                    data = payload
                    assert isinstance(data, dict)
                    orders = data.get("orders", [])
                    process_list_count = int(data.get("process_list_count", 0))
                    process_list_import_summary = data.get("process_list_import_summary", {})
                    import_summary = data.get("import_summary", {})
                    if orders:
                        assert isinstance(orders, list)
                        self.orders = orders
                        self.order_by_aw = {order.aw_order: order for order in self.orders}
                    self.finish_background_activity()
                    messages = [
                        self.process_list_import_status_message(process_list_import_summary),
                        self.import_status_message(import_summary, process_list_count),
                    ]
                    self.status_var.set(" ".join(message for message in messages if message))
                elif kind == "scan_error":
                    self.finish_background_activity()
                    self.status_var.set("Scan failed")
                    messagebox.showerror("Scan failed", str(payload))
                elif kind == "send_done":
                    data = payload
                    assert isinstance(data, dict)
                    copied = data.get("copied", [])
                    missing = data.get("missing", [])
                    archived = data.get("archived", [])
                    archive_warnings = data.get("archive_warnings", [])
                    assert isinstance(copied, list)
                    assert isinstance(missing, list)
                    assert isinstance(archived, list)
                    assert isinstance(archive_warnings, list)
                    self.finish_background_activity()
                    if not copied:
                        messagebox.showinfo("Nothing sent", "No matching generated files were found.")
                        self.status_var.set("No matching generated files were found.")
                        continue
                    details = self.send_complete_details(copied, missing, archived, archive_warnings)
                    self.status_var.set(details)
                    messagebox.showinfo("Send complete", details)
                elif kind == "send_error":
                    self.finish_background_activity()
                    self.status_var.set("Send failed")
                    messagebox.showerror("Send failed", str(payload))
        except queue.Empty:
            pass
        self.root.after(150, self.drain_worker_queue)

    @staticmethod
    def scan_status_message(
        order_count: int,
        process_list_count: int,
        import_summary: object,
        process_list_import_summary: object | None = None,
    ) -> str:
        message = f"Found {order_count} orders from {process_list_count} process list(s)."
        process_list_message = ShowerProgrammerApp.process_list_import_status_message(process_list_import_summary)
        if process_list_message:
            message += " " + process_list_message
        import_message = ShowerProgrammerApp.import_status_message(import_summary, 0)
        if import_message:
            message += " " + import_message
        return message

    @staticmethod
    def process_list_import_status_message(import_summary: object) -> str:
        if not isinstance(import_summary, dict):
            return ""
        copied = import_summary.get("copied", [])
        skipped = int(import_summary.get("skipped", 0) or 0)
        source_missing = bool(import_summary.get("source_missing", False))
        if source_missing:
            return ""
        copied_count = len(copied) if isinstance(copied, list) else 0
        if copied_count:
            return f"Imported/updated {copied_count} process list file(s); {skipped} already current."
        if skipped:
            return f"No process list files needed copying; {skipped} already current."
        return ""

    @staticmethod
    def import_status_message(import_summary: object, process_list_count: int) -> str:
        if not isinstance(import_summary, dict):
            return ""
        copied = import_summary.get("copied", [])
        skipped = int(import_summary.get("skipped", 0) or 0)
        source_missing = bool(import_summary.get("source_missing", False))
        if source_missing:
            return f"EDI import skipped; source folder not found: {import_summary.get('source', '')}"
        copied_count = len(copied) if isinstance(copied, list) else 0
        if copied_count:
            return f"Imported/updated {copied_count} matching EDI file(s); {skipped} already current."
        if process_list_count:
            return f"No EDI files needed copying for {process_list_count} process list(s); {skipped} already current."
        return f"No EDI files needed copying; {skipped} already current."

    def set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for child in self.root.winfo_children():
            self.set_child_state(child, state)

    def set_child_state(self, widget: tk.Widget, state: str) -> None:
        try:
            if isinstance(widget, (ttk.Button, ttk.Checkbutton, ttk.Entry)):
                widget.configure(state=state)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self.set_child_state(child, state)

    def review_sketches(self) -> None:
        try:
            output_dir = Path(self.output_dir_var.get()).resolve()
            run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
            sketch_dir = (run_folder / "Sketches") if run_folder else output_dir / "Sketches"
            paths = self.generated_sketch_paths(output_dir, sketch_dir)
            if not paths:
                if sketch_dir.exists():
                    os.startfile(sketch_dir)
                else:
                    messagebox.showinfo("No sketches", "No generated sketch PDFs were found.")
                return

            review_dir = output_dir / "Reviews"
            review_dir.mkdir(parents=True, exist_ok=True)
            review_path = review_dir / f"sketch_review_{datetime.now():%Y%m%d_%H%M%S}.pdf"
            config = self.config_with_manual_overrides(
                Path(self.folder_var.get()).resolve(),
                output_dir,
            )
            writer = PdfWriter()
            added_pages = 0
            for path in paths:
                reader = PdfReader(str(path))
                aw_order = path.stem
                for page_index in self.sketch_review_page_indices(reader, aw_order, config):
                    writer.add_page(reader.pages[page_index])
                    added_pages += 1
            if not added_pages:
                messagebox.showinfo("No sketch pages", "No piece pages were found in the generated sketches.")
                return
            with review_path.open("wb") as handle:
                writer.write(handle)
            os.startfile(review_path)
            self.status_var.set(f"Opened sketch review: {review_path.name}")
        except Exception as exc:
            messagebox.showerror("Review sketches failed", str(exc))

    def generated_sketch_paths(self, output_dir: Path, sketch_dir: Path) -> list[Path]:
        aw_orders = self.selected_or_visible_aw_orders()
        if aw_orders:
            paths: list[Path] = []
            for aw_order in aw_orders:
                path = self.find_order_sketch_path(aw_order, output_dir)
                if path.exists():
                    paths.append(path)
            return paths
        return sorted(sketch_dir.glob("*.pdf")) if sketch_dir.exists() else []

    def sketch_review_page_indices(
        self,
        reader: PdfReader,
        aw_order: str,
        config: dict[str, object],
    ) -> list[int]:
        try:
            panels = programmer.analyze_panels(reader, config, aw_order)
            indexes = sorted({panel.page_index for panel in panels if 0 <= panel.page_index < len(reader.pages)})
            if indexes:
                return indexes
        except Exception:
            pass
        return list(range(len(reader.pages)))

    def review_dxfs(self) -> None:
        try:
            output_dir = Path(self.output_dir_var.get()).resolve()
            run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
            programs_dir = (run_folder / "Programs") if run_folder else output_dir / "Programs"
            paths = self.generated_dxf_paths(output_dir, programs_dir)
            if not paths:
                if programs_dir.exists():
                    os.startfile(programs_dir)
                else:
                    messagebox.showinfo("No DXFs", "No generated DXF files were found.")
                return
            review_dir = output_dir / "Reviews"
            review_dir.mkdir(parents=True, exist_ok=True)
            review_path = review_dir / f"dxf_review_{datetime.now():%Y%m%d_%H%M%S}.html"
            review_path.write_text(self.build_dxf_review_html(paths), encoding="utf-8")
            webbrowser.open(review_path.resolve().as_uri())
            self.status_var.set(f"Opened DXF review: {review_path.name}")
        except Exception as exc:
            messagebox.showerror("Review DXFs failed", str(exc))

    def generated_dxf_paths(self, output_dir: Path, programs_dir: Path) -> list[Path]:
        aw_orders = self.selected_or_visible_aw_orders()
        if aw_orders:
            paths: list[Path] = []
            for aw_order in aw_orders:
                _run_folder, _sketch_dir, order_programs_dir, _report_dir = self.output_dirs_for_order(aw_order, output_dir)
                paths.extend(sorted(order_programs_dir.glob(f"{aw_order}*.dxf")))
            return paths
        return sorted(programs_dir.glob("*.dxf")) if programs_dir.exists() else []

    def build_dxf_review_html(self, paths: list[Path]) -> str:
        cards = "\n".join(self.dxf_preview_card(path) for path in paths)
        return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>DXF Review</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 18px; color: #1f2933; }}
h1 {{ font-size: 22px; margin: 0 0 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }}
.card {{ border: 1px solid #cfd8e3; border-radius: 6px; padding: 10px; background: #fff; }}
.name {{ font-weight: 700; margin-bottom: 4px; overflow-wrap: anywhere; }}
.meta {{ color: #536471; font-size: 12px; margin-bottom: 8px; }}
svg {{ width: 100%; height: 240px; background: #f8fafc; border: 1px solid #e2e8f0; }}
line {{ stroke: #1f4e79; stroke-width: 2; vector-effect: non-scaling-stroke; }}
a {{ color: #1f4e79; }}
</style>
</head>
<body>
<h1>DXF Review</h1>
<div class="grid">
{cards}
</div>
</body>
</html>
"""

    def dxf_preview_card(self, path: Path) -> str:
        title = html.escape(path.name)
        link = html.escape(path.resolve().as_uri(), quote=True)
        try:
            segments = programmer.collect_dxf_preview_segments(path)
        except Exception as exc:
            return (
                "<div class='card'>"
                f"<div class='name'><a href='{link}'>{title}</a></div>"
                f"<div class='meta'>Could not read DXF: {html.escape(str(exc))}</div>"
                "</div>"
            )
        if not segments:
            return (
                "<div class='card'>"
                f"<div class='name'><a href='{link}'>{title}</a></div>"
                "<div class='meta'>No drawable DXF entities found.</div>"
                "</div>"
            )
        points = [point for segment in segments for point in segment]
        min_x = min(x for x, _ in points)
        max_x = max(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_y = max(y for _, y in points)
        width = max(max_x - min_x, 0.001)
        height = max(max_y - min_y, 0.001)
        scale = min(260 / width, 210 / height)
        margin = 15.0

        def map_point(point: tuple[float, float]) -> tuple[float, float]:
            x, y = point
            return margin + (x - min_x) * scale, margin + (max_y - y) * scale

        lines = []
        for start, end in segments:
            x1, y1 = map_point(start)
            x2, y2 = map_point(end)
            lines.append(f"<line x1='{x1:.2f}' y1='{y1:.2f}' x2='{x2:.2f}' y2='{y2:.2f}' />")
        svg_width = width * scale + margin * 2
        svg_height = height * scale + margin * 2
        meta = f"{width:g} x {height:g} | {len(segments)} segment(s)"
        return (
            "<div class='card'>"
            f"<div class='name'><a href='{link}'>{title}</a></div>"
            f"<div class='meta'>{html.escape(meta)}</div>"
            f"<svg viewBox='0 0 {svg_width:.2f} {svg_height:.2f}'>{''.join(lines)}</svg>"
            "</div>"
        )

    def open_order_review(self, event: tk.Event | None = None) -> None:
        if event is not None:
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
        selected = self.selected_orders()
        if len(selected) != 1:
            messagebox.showinfo("Select one order", "Select exactly one scanned order to review.")
            return
        process_order = selected[0]
        try:
            folder = Path(self.folder_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            run_folder, sketch_dir, programs_dir, report_dir = self.output_dirs_for_order(process_order.aw_order, output_dir)
            sketch_path = sketch_dir / f"{process_order.aw_order}.pdf"
            if not sketch_path.exists():
                messagebox.showinfo("No sketch yet", "Process this order first so the marked sketch exists.")
                return
            config = self.config_with_manual_overrides(folder, output_dir)
            job, source_reader, issues = shower_batch.prepare_job(
                folder,
                sketch_dir,
                programs_dir,
                report_dir,
                config,
                process_order,
                remake_items=self.editor_remake_items(process_order.aw_order),
            )
            sketch_reader = PdfReader(str(sketch_path))
        except Exception as exc:
            messagebox.showerror("Order review failed", str(exc))
            return
        if not job.panels:
            messagebox.showinfo("No pieces", "No piece pages were found for this order.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Review Order - {process_order.aw_order}")
        dialog.geometry("1180x820")
        dialog.after(0, lambda: self.maximize_window(dialog))
        dialog.transient(self.root)
        
        toolbar = ttk.Frame(dialog, padding=(8, 8, 8, 4))
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="Piece").pack(side=tk.LEFT)
        item_var = tk.StringVar(value=f"P{job.panels[0].item}")
        item_box = ttk.Combobox(
            toolbar,
            textvariable=item_var,
            values=[f"P{panel.item}" for panel in job.panels],
            state="readonly",
            width=8,
        )
        item_box.pack(side=tk.LEFT, padx=(6, 12))
        page_count_var = tk.StringVar(value=f"1/{len(job.panels)}")
        ttk.Label(toolbar, textvariable=page_count_var).pack(side=tk.LEFT, padx=(0, 12))
        rotation_var = tk.IntVar(value=0)
        status = tk.StringVar(value="Double-check the sketch and matching DXF together.")
        ttk.Button(toolbar, text="Prev P", command=lambda: change_piece(-1)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Next P", command=lambda: change_piece(1)).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(toolbar, text="Save Edits", command=lambda: save_review_edits()).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Process DXF", command=lambda: process_review_order()).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(toolbar, text="Add Indicator", command=lambda: add_indicator_mark()).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Add X", command=lambda: add_x_mark()).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(toolbar, text="Rotate Left", command=lambda: rotate_view(-90)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Rotate Right", command=lambda: rotate_view(90)).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(toolbar, text="Open Sketch PDF", command=lambda: os.startfile(sketch_path)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Open DXF", command=lambda: open_current_dxf()).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(toolbar, textvariable=status).pack(side=tk.LEFT, fill=tk.X, expand=True)

        panes = ttk.PanedWindow(dialog, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        sketch_frame = ttk.Frame(panes)
        dxf_frame = ttk.Frame(panes)
        panes.add(sketch_frame, weight=3)
        panes.add(dxf_frame, weight=2)

        sketch_canvas = tk.Canvas(sketch_frame, background="#e8edf3", highlightthickness=0)
        sketch_y_scroll = ttk.Scrollbar(sketch_frame, orient=tk.VERTICAL, command=sketch_canvas.yview)
        sketch_x_scroll = ttk.Scrollbar(sketch_frame, orient=tk.HORIZONTAL, command=sketch_canvas.xview)
        sketch_canvas.configure(yscrollcommand=sketch_y_scroll.set, xscrollcommand=sketch_x_scroll.set)
        sketch_canvas.grid(row=0, column=0, sticky="nsew")
        sketch_y_scroll.grid(row=0, column=1, sticky="ns")
        sketch_x_scroll.grid(row=1, column=0, sticky="ew")
        sketch_frame.columnconfigure(0, weight=1)
        sketch_frame.rowconfigure(0, weight=1)
        dxf_canvas = tk.Canvas(dxf_frame, background="#f8fafc", highlightthickness=0)
        dxf_canvas.pack(fill=tk.BOTH, expand=True)

        state: dict[str, Any] = {
            "objects": {},
            "positions": {},
            "dirty": set(),
            "drag_key": None,
            "selected_key": None,
            "last_x": 0.0,
            "last_y": 0.0,
            "page_images": [],
            "render_cache": {},
            "render_temp_dir": tempfile.mkdtemp(prefix="shower_order_review_"),
            "current_item": job.panels[0].item,
            "pending_items": set(),
            "needs_output_save": False,
        }

        def selected_panel() -> programmer.Panel:
            item = int(item_var.get().replace("P", ""))
            return next(panel for panel in job.panels if panel.item == item)

        def has_pending_item_edits(item_number: int | None = None) -> bool:
            dirty = state.get("dirty", set())
            pending = state.get("pending_items", set())
            if item_number is None:
                return bool(dirty or pending or state.get("needs_output_save"))
            return any(item == item_number for item, _key in dirty) or item_number in pending

        def discard_pending_item_edits(item_number: int | None = None) -> None:
            if item_number is None:
                state.get("dirty", set()).clear()
                state.get("positions", {}).clear()
                state.get("pending_items", set()).clear()
                state["needs_output_save"] = False
                return
            state["dirty"] = {entry for entry in state.get("dirty", set()) if entry[0] != item_number}
            state["positions"] = {
                entry: position
                for entry, position in state.get("positions", {}).items()
                if entry[0] != item_number
            }
            state.get("pending_items", set()).discard(item_number)
            state["needs_output_save"] = bool(state.get("dirty") or state.get("pending_items"))

        def confirm_save_before_leaving(item_number: int | None = None) -> bool:
            if not has_pending_item_edits(item_number):
                return True
            label = f"P{item_number}" if item_number is not None else "this order"
            answer = messagebox.askyesnocancel(
                "Save sketch edits?",
                f"Save edits for {label} before leaving?",
                parent=dialog,
            )
            if answer is None:
                return False
            if answer:
                return save_review_edits(show_no_edits=False)
            discard_pending_item_edits(item_number)
            return True

        def set_piece(value: str) -> bool:
            try:
                next_item = int(value.replace("P", ""))
            except ValueError:
                return False
            current_item = int(state.get("current_item", selected_panel().item))
            if next_item != current_item and not confirm_save_before_leaving(current_item):
                item_var.set(f"P{current_item}")
                return False
            state["current_item"] = next_item
            item_var.set(f"P{next_item}")
            rotation_var.set(0)
            redraw()
            return True

        def change_piece(delta: int) -> str:
            values = [f"P{panel.item}" for panel in job.panels]
            if not values:
                return "break"
            try:
                index = values.index(item_var.get())
            except ValueError:
                index = 0
            set_piece(values[(index + delta) % len(values)])
            return "break"

        def piece_wheel(event: tk.Event) -> str:
            delta = int(getattr(event, "delta", 0))
            if delta == 0:
                return "break"
            return change_piece(-1 if delta > 0 else 1)

        def rotate_view(delta: int) -> None:
            rotation_var.set((rotation_var.get() + delta) % 360)
            redraw()

        def open_current_dxf() -> None:
            panel = selected_panel()
            path = panel.output_dxf if panel.output_dxf and panel.output_dxf.exists() else panel.source_dxf
            if path and path.exists():
                os.startfile(str(path.resolve()))
                status.set(f"Opened DXF: {path.resolve()}")
            else:
                messagebox.showinfo("No DXF", "No matching DXF exists for this piece.", parent=dialog)

        def start_drag(event: tk.Event, key: str) -> None:
            if rotation_var.get() % 360:
                status.set("Set sketch view back to 0 deg before dragging marks.")
                return
            state["selected_key"] = key
            if state.get("objects", {}).get(key, {}).get("kind") == "x":
                status.set("X marks can be deleted from the popup, but they are not draggable.")
                return
            state["drag_key"] = key
            state["last_x"] = float(sketch_canvas.canvasx(event.x))
            state["last_y"] = float(sketch_canvas.canvasy(event.y))

        def drag(event: tk.Event) -> None:
            key = state.get("drag_key")
            if not key:
                return
            x = float(sketch_canvas.canvasx(event.x))
            y = float(sketch_canvas.canvasy(event.y))
            dx = x - float(state["last_x"])
            dy = y - float(state["last_y"])
            state["last_x"] = x
            state["last_y"] = y
            sketch_canvas.move(f"edit_{key}", dx, dy)
            obj = state["objects"][key]
            scale = float(obj.get("scale", 1.0))
            obj["x"] += dx / scale
            obj["y"] -= dy / scale
            item_number = int(obj.get("item", selected_panel().item))
            item_key = (item_number, str(obj.get("key", key)))
            state["dirty"].add(item_key)
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            position = {"x": obj["x"], "y": obj["y"]}
            if obj.get("key") == "indicator":
                corner = programmer.nearest_indicator_corner_for_point(
                    obj["machine"],
                    (obj["x"], obj["y"]),
                    obj.get("anchor_bbox"),
                    float(obj["page_width"]),
                    float(obj["page_height"]),
                    obj["pdf_cfg"],
                    precise_edges=bool(obj.get("precise_edges")),
                )
                position["indicator_corner"] = corner
                if str(obj["machine"]).startswith("DENVER"):
                    position["raw_indicator_corner"] = programmer.nearest_indicator_corner_for_point(
                        obj["machine"],
                        (obj["x"], obj["y"]),
                        obj.get("anchor_bbox"),
                        float(obj["page_width"]),
                        float(obj["page_height"]),
                        obj["pdf_cfg"],
                        precise_edges=bool(obj.get("precise_edges")),
                        allowed_denver_only=False,
                    )
            state["positions"][item_key] = position
            status.set(f"Moved {obj['name']} on {job.aw_order}.{item_number}")

        def release(_event: tk.Event) -> None:
            state["drag_key"] = None

        def regenerate_review_sketch() -> bool:
            nonlocal job, source_reader, sketch_reader, issues, config
            try:
                refreshed_config = self.config_with_manual_overrides(folder, output_dir)
                remake_items = self.editor_remake_items(process_order.aw_order)
                refreshed_job, refreshed_reader, refreshed_issues = shower_batch.prepare_job(
                    folder,
                    sketch_dir,
                    programs_dir,
                    report_dir,
                    refreshed_config,
                    process_order,
                    remake_items=remake_items,
                )
                programmer.write_marked_pdf(refreshed_job, refreshed_reader, refreshed_config, force=True)
                job = refreshed_job
                source_reader = PdfReader(str(job.pdf_path))
                sketch_reader = PdfReader(str(sketch_path))
                issues = refreshed_issues
                config = refreshed_config
                state.get("pending_items", set()).clear()
                state["needs_output_save"] = False
                return True
            except Exception as exc:
                messagebox.showerror("Save sketch failed", str(exc), parent=dialog)
                return False

        def save_review_edits(show_no_edits: bool = True) -> bool:
            dirty = bool(state.get("dirty"))
            pending_output = bool(state.get("pending_items") or state.get("needs_output_save"))
            if dirty and not self.save_editor_state_positions(job, state, config, dialog, show_no_edits=show_no_edits):
                return False
            if dirty or pending_output:
                if not regenerate_review_sketch():
                    return False
                status.set("Saved edits and overwrote the sketch PDF.")
                redraw()
                return True
            if show_no_edits:
                messagebox.showinfo("No edits", "Nothing has been changed yet.", parent=dialog)
            return False

        def process_review_order() -> None:
            nonlocal job, source_reader, sketch_reader, issues, config
            if has_pending_item_edits() and not save_review_edits(show_no_edits=False):
                return
            try:
                refreshed_config = self.config_with_manual_overrides(folder, output_dir)
                remake_items = self.editor_remake_items(process_order.aw_order)
                result = shower_batch.process_one_order(
                    process_order,
                    folder,
                    sketch_dir,
                    programs_dir,
                    report_dir,
                    refreshed_config,
                    apply=True,
                    force=True,
                    skip_pdf=False,
                    skip_dxf=False,
                    remake_items=remake_items,
                )
                job, source_reader, issues = shower_batch.prepare_job(
                    folder,
                    sketch_dir,
                    programs_dir,
                    report_dir,
                    refreshed_config,
                    process_order,
                    remake_items=remake_items,
                )
                config = refreshed_config
                sketch_reader = PdfReader(str(sketch_path))
                self.insert_or_update_result(result)
                status.set(f"Processed {job.aw_order}; DXF preview refreshed.")
                redraw()
            except Exception as exc:
                messagebox.showerror("Process DXF failed", str(exc), parent=dialog)

        def refresh_prepared_job() -> None:
            nonlocal job, source_reader, issues, config
            config = self.config_with_manual_overrides(folder, output_dir)
            job, source_reader, issues = shower_batch.prepare_job(
                folder,
                sketch_dir,
                programs_dir,
                report_dir,
                config,
                process_order,
                remake_items=self.editor_remake_items(process_order.aw_order),
            )

        def delete_selected_mark() -> None:
            key = state.get("selected_key")
            if not key or key not in state.get("objects", {}):
                messagebox.showinfo("No mark selected", "Click a blue mark first.", parent=dialog)
                return
            obj = state["objects"][key]
            item_number = int(obj.get("item", selected_panel().item))
            mark_key = str(obj.get("key", "")).strip()
            if not mark_key:
                return
            if mark_key == "manual_x":
                self.set_manual_x_override(job.aw_order, item_number, False)
                refresh_prepared_job()
                state["selected_key"] = None
                state.get("pending_items", set()).add(item_number)
                state["needs_output_save"] = True
                status.set(f"Deleted manual X on {job.aw_order}.{item_number}. Click Save Edits to overwrite the sketch.")
                redraw()
                return
            self.set_mark_hidden(job.aw_order, item_number, mark_key, hidden=True)
            refresh_prepared_job()
            state["selected_key"] = None
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            status.set(f"Deleted {obj.get('name', mark_key)} on {job.aw_order}.{item_number}. Click Save Edits to overwrite the sketch.")
            redraw()

        def add_indicator_mark() -> None:
            panel = selected_panel()
            self.set_mark_hidden(job.aw_order, panel.item, "indicator", hidden=False)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Restored indicator on {job.aw_order}.{panel.item}. Click Save Edits to overwrite the sketch.")
            redraw()

        def add_x_mark() -> None:
            panel = selected_panel()
            self.set_manual_x_override(job.aw_order, panel.item, True)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Added X-out mark on {job.aw_order}.{panel.item}. Click Save Edits to overwrite the sketch.")
            redraw()

        def set_current_indicator_machine(machine_kind: str) -> None:
            panel = selected_panel()
            self.set_indicator_machine_override(job.aw_order, panel.item, machine_kind, panel, config)
            refresh_prepared_job()
            state.get("pending_items", set()).add(panel.item)
            state["needs_output_save"] = True
            status.set(f"Changed indicator/machine for {job.aw_order}.{panel.item} to {machine_kind}. Click Save Edits to overwrite the sketch.")
            redraw()

        def resize_selected_mark(direction: int) -> None:
            key = state.get("selected_key")
            if not key or key not in state.get("objects", {}):
                messagebox.showinfo("No mark selected", "Click a blue mark first, then use Size - or Size +.", parent=dialog)
                return
            obj = state["objects"][key]
            item_number = int(obj.get("item", selected_panel().item))
            mark_key = str(obj.get("key", "")).strip()
            if not mark_key:
                return
            panel = next(panel for panel in job.panels if panel.item == item_number)
            new_size = self.set_mark_size_override(job.aw_order, item_number, mark_key, direction, obj, panel, config)
            refresh_prepared_job()
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            status.set(f"Changed {obj.get('name', mark_key)} size on {job.aw_order}.{item_number} to {new_size:g}. Click Save Edits to overwrite the sketch.")
            redraw()

        def edit_selected_text() -> None:
            key = state.get("selected_key")
            if not key or key not in state.get("objects", {}):
                messagebox.showinfo("No text selected", "Click a blue text mark first.", parent=dialog)
                return
            obj = state["objects"][key]
            if obj.get("kind") != "text":
                messagebox.showinfo("Not text", "Select a blue text mark to edit.", parent=dialog)
                return
            mark_key = str(obj.get("key", "")).strip()
            item_number = int(obj.get("item", selected_panel().item))
            current = "\\n".join(str(line) for line in obj.get("lines", []))
            value = simpledialog.askstring(
                "Edit Text",
                "Edit generated text. Use \\n for a line break.",
                initialvalue=current,
                parent=dialog,
            )
            if value is None:
                return
            self.set_mark_text_override(job.aw_order, item_number, mark_key, value)
            refresh_prepared_job()
            state.get("pending_items", set()).add(item_number)
            state["needs_output_save"] = True
            status.set(f"Edited {obj.get('name', mark_key)} on {job.aw_order}.{item_number}. Click Save Edits to overwrite the sketch.")
            redraw()

        def show_mark_menu(event: tk.Event, key: str) -> str:
            if key not in state.get("objects", {}):
                return "break"
            state["selected_key"] = key
            obj = state["objects"][key]
            menu = tk.Menu(dialog, tearoff=False)
            if obj.get("kind") != "x":
                menu.add_command(label="Increase Size", command=lambda key=key: (state.__setitem__("selected_key", key), resize_selected_mark(1)))
                menu.add_command(label="Decrease Size", command=lambda key=key: (state.__setitem__("selected_key", key), resize_selected_mark(-1)))
            if obj.get("kind") == "text":
                menu.add_command(label="Edit Text", command=lambda key=key: (state.__setitem__("selected_key", key), edit_selected_text()))
            if obj.get("key") == "indicator":
                menu.add_separator()
                menu.add_command(label="Make WJ", command=lambda: set_current_indicator_machine("WJ"))
                menu.add_command(label="Make Denver", command=lambda: set_current_indicator_machine("DENVER"))
            menu.add_separator()
            menu.add_command(label="Delete", command=lambda key=key: (state.__setitem__("selected_key", key), delete_selected_mark()))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        def redraw() -> None:
            panel = selected_panel()
            ordered_items = [current.item for current in sorted(job.panels, key=lambda current: current.item)]
            if panel.item in ordered_items:
                page_count_var.set(f"{ordered_items.index(panel.item) + 1}/{len(ordered_items)}")
            try:
                self.draw_order_review_sketch(
                    sketch_canvas,
                    source_reader,
                    job.pdf_path,
                    job,
                    panel,
                    config,
                    rotation_var.get(),
                    state,
                )
            except Exception as exc:
                sketch_canvas.delete("all")
                sketch_canvas.create_rectangle(
                    0,
                    0,
                    sketch_canvas.winfo_width(),
                    sketch_canvas.winfo_height(),
                    fill="#e8edf3",
                    outline="",
                )
                sketch_canvas.create_text(16, 16, anchor=tk.NW, text=f"Sketch preview failed: {exc}", fill="#b42318")
            dxf_path = panel.output_dxf if panel.output_dxf and panel.output_dxf.exists() else panel.source_dxf
            try:
                self.draw_order_review_dxf(dxf_canvas, dxf_path, panel)
            except Exception as exc:
                dxf_canvas.delete("all")
                dxf_canvas.create_rectangle(0, 0, dxf_canvas.winfo_width(), dxf_canvas.winfo_height(), fill="#f8fafc", outline="")
                dxf_canvas.create_text(16, 16, anchor=tk.NW, text=f"DXF preview failed: {exc}", fill="#b42318")
            issue_text = "; ".join(issues[:2]) if issues else ""
            rotation_text = self.panel_rotation_summary(panel)
            status.set(
                f"{job.aw_order}.{panel.item}  {panel.machine or 'LABEL ONLY'}  "
                f"Sketch view {rotation_var.get()} deg  |  {rotation_text}"
                + (f"  |  {issue_text}" if issue_text else "")
            )

        def cleanup_render_temp(_event: tk.Event | None = None) -> None:
            temp_dir = state.get("render_temp_dir")
            if _event is not None and _event.widget is not dialog:
                return
            if isinstance(temp_dir, str):
                shutil.rmtree(temp_dir, ignore_errors=True)

        def request_close() -> None:
            if confirm_save_before_leaving(None):
                cleanup_render_temp()
                dialog.destroy()

        item_box.bind("<<ComboboxSelected>>", lambda _event: set_piece(item_var.get()))
        item_box.bind("<MouseWheel>", piece_wheel)
        sketch_canvas.bind("<Configure>", lambda _event: redraw())
        dxf_canvas.bind("<Configure>", lambda _event: redraw())
        sketch_canvas.bind("<B1-Motion>", drag)
        sketch_canvas.bind("<ButtonRelease-1>", release)
        sketch_canvas.bind("<MouseWheel>", lambda event: self.scroll_editor_canvas(sketch_canvas, event))
        sketch_canvas.bind("<Shift-MouseWheel>", lambda event: self.scroll_editor_canvas(sketch_canvas, event, horizontal=True))
        dialog.bind("<Control-MouseWheel>", piece_wheel)
        dialog.bind("<MouseWheel>", lambda event: self.scroll_editor_canvas(sketch_canvas, event))
        state["start_drag"] = start_drag
        state["show_mark_menu"] = show_mark_menu
        dialog.protocol("WM_DELETE_WINDOW", request_close)
        dialog.bind("<Destroy>", cleanup_render_temp, add="+")
        dialog.after(100, redraw)

    def draw_order_review_sketch(
        self,
        canvas: tk.Canvas,
        reader: PdfReader,
        sketch_path: Path,
        job: programmer.Job,
        panel: programmer.Panel,
        config: dict[str, object],
        rotation_degrees: int,
        state: dict[str, Any],
    ) -> None:
        canvas.delete("all")
        state["objects"] = {}
        state["page_images"] = []
        page = reader.pages[panel.page_index]
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        view_width = page_height if rotation_degrees % 180 else page_width
        view_height = page_width if rotation_degrees % 180 else page_height
        available_width = max(200, canvas.winfo_width() - 24)
        scale = min(1.2, max(0.7, available_width / view_width))
        image = self.editor_page_image(
            sketch_path,
            panel.page_index,
            page_width,
            page_height,
            scale,
            state,
            rotation_degrees=rotation_degrees,
        )
        canvas.create_rectangle(0, 0, canvas.winfo_width(), canvas.winfo_height(), fill="#e8edf3", outline="")
        if image is None:
            canvas.create_text(16, 16, anchor=tk.NW, text="Could not render sketch preview.", fill="#334155")
            return
        state["page_images"].append(image)
        x = 16.0
        y = 16.0
        canvas.create_image(x, y, image=image, anchor=tk.NW)
        objects = self.editor_overlay_objects(reader, job, panel, config)
        for obj in objects:
            obj["item"] = panel.item
            obj["scale"] = scale
            self.draw_editor_object(
                canvas,
                obj,
                scale,
                x,
                page_height,
                state,
                top_offset=y - x,
                page_width=page_width,
                rotation_degrees=rotation_degrees,
            )
        if rotation_degrees % 360 != 0:
            canvas.create_text(
                x + 8,
                y + 8,
                anchor=tk.NW,
                text="Rotated view is visual only. Return to 0 deg to drag marks.",
                fill="#9a5b00",
                font=("Arial", 10, "bold"),
            )
        canvas.configure(scrollregion=(0, 0, image.width() + 32, image.height() + 32))

    def draw_order_review_dxf(self, canvas: tk.Canvas, path: Path | None, panel: programmer.Panel) -> None:
        canvas.delete("all")
        canvas.create_rectangle(0, 0, canvas.winfo_width(), canvas.winfo_height(), fill="#f8fafc", outline="")
        canvas.create_text(
            16,
            16,
            anchor=tk.NW,
            text=self.panel_rotation_summary(panel),
            fill="#1f2933",
            font=("Arial", 11, "bold"),
        )
        if path is None or not path.exists():
            canvas.create_text(16, 42, anchor=tk.NW, text="No DXF for this piece.", fill="#334155")
            return
        try:
            segments = programmer.collect_dxf_preview_segments(path)
        except Exception as exc:
            canvas.create_text(16, 42, anchor=tk.NW, text=f"Could not read DXF: {exc}", fill="#b42318")
            return
        canvas.create_text(16, 42, anchor=tk.NW, text=path.name, fill="#1f2933", font=("Arial", 10))
        if not segments:
            canvas.create_text(16, 66, anchor=tk.NW, text="No drawable DXF entities found.", fill="#334155")
            return
        points = [point for segment in segments for point in segment]
        min_x = min(x for x, _ in points)
        max_x = max(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_y = max(y for _, y in points)
        width = max(max_x - min_x, 0.001)
        height = max(max_y - min_y, 0.001)
        margin = 34.0
        header_height = 96.0
        unit_label = self.dxf_unit_label(path)
        inches_per_unit = self.dxf_inches_per_unit(path)
        scale = min(
            max(20, canvas.winfo_width() - margin * 2) / width,
            max(20, canvas.winfo_height() - margin * 2 - header_height) / height,
        )

        def map_point(point: tuple[float, float]) -> tuple[float, float]:
            x, y = point
            return margin + (x - min_x) * scale, header_height + (max_y - y) * scale

        long_side = max(width, height)
        highlight_segments = self.out_of_square_preview_segments(segments, long_side, inches_per_unit)
        for start, end in segments:
            x1, y1 = map_point(start)
            x2, y2 = map_point(end)
            highlight = (start, end) in highlight_segments
            canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill="#d97706" if highlight else "#1f4e79",
                width=4 if highlight else 2,
            )
            if highlight:
                mx = (x1 + x2) / 2
                my = (y1 + y2) / 2
                canvas.create_text(
                    mx,
                    my - 12,
                    anchor=tk.CENTER,
                    text=self.out_of_square_segment_label(start, end, inches_per_unit),
                    fill="#9a5b00",
                    font=("Arial", 9, "bold"),
                )
        if highlight_segments:
            canvas.create_text(
                16,
                66,
                anchor=tk.NW,
                text="Orange = angled/out-of-square side",
                fill="#9a5b00",
                font=("Arial", 9, "bold"),
            )
        canvas.create_text(
            16,
            canvas.winfo_height() - 18,
            anchor=tk.SW,
            text=f"{self.dxf_dimension_text(width, height, unit_label, inches_per_unit)} | {len(segments)} segment(s)",
            fill="#536471",
            font=("Arial", 9),
        )

    @classmethod
    def out_of_square_preview_segments(
        cls,
        segments: list[tuple[tuple[float, float], tuple[float, float]]],
        long_side: float,
        inches_per_unit: float = 1.0,
    ) -> set[tuple[tuple[float, float], tuple[float, float]]]:
        angled: list[tuple[tuple[float, float], tuple[float, float]]] = []
        horizontal: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for start, end in segments:
            if not cls.is_out_of_square_preview_segment(start, end, long_side, inches_per_unit):
                continue
            angled.append((start, end))
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            angle = math.degrees(math.atan2(dy, dx))
            horizontal_deviation = abs(programmer.normalize_axis_deviation(angle))
            vertical_deviation = abs(programmer.normalize_axis_deviation(angle - 90))
            if horizontal_deviation <= vertical_deviation:
                horizontal.append((start, end))
        return set(angled)

    @classmethod
    def out_of_square_segment_label(
        cls,
        start: tuple[float, float],
        end: tuple[float, float],
        inches_per_unit: float = 1.0,
    ) -> str:
        amount = cls.out_of_square_segment_amount(start, end) * inches_per_unit
        return f"{cls.format_inches(amount)} OOS"

    @staticmethod
    def out_of_square_segment_amount(start: tuple[float, float], end: tuple[float, float]) -> float:
        dx = abs(end[0] - start[0])
        dy = abs(end[1] - start[1])
        return min(dx, dy)

    @staticmethod
    def format_inches(value: float) -> str:
        nearest_sixteenth = int(round(abs(value) * 16))
        if nearest_sixteenth == 0:
            return f'{abs(value):.3f}"'
        whole = nearest_sixteenth // 16
        numerator = nearest_sixteenth % 16
        if numerator == 0:
            return f'{whole}"'
        divisor = math.gcd(numerator, 16)
        numerator //= divisor
        denominator = 16 // divisor
        if whole:
            return f'{whole}-{numerator}/{denominator}"'
        return f'{numerator}/{denominator}"'

    @staticmethod
    def is_out_of_square_preview_segment(
        start: tuple[float, float],
        end: tuple[float, float],
        long_side: float,
        inches_per_unit: float = 1.0,
    ) -> bool:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = (dx * dx + dy * dy) ** 0.5
        safe_inches_per_unit = inches_per_unit if inches_per_unit > 0 else 1.0
        if length < max(4.0 / safe_inches_per_unit, long_side * 0.12):
            return False
        angle = math.degrees(math.atan2(dy, dx))
        deviation = abs(programmer.normalize_axis_deviation(angle))
        deviation = min(deviation, abs(programmer.normalize_axis_deviation(angle - 90)))
        amount = ShowerProgrammerApp.out_of_square_segment_amount(start, end) * inches_per_unit
        return deviation >= 0.015 or amount >= 0.03125

    @staticmethod
    def dxf_inches_per_unit(path: Path) -> float:
        insunits = ShowerProgrammerApp.dxf_insunits(path)
        return {
            "1": 1.0,  # inches
            "2": 12.0,  # feet
            "4": 1.0 / 25.4,  # millimeters
            "5": 1.0 / 2.54,  # centimeters
            "6": 39.37007874015748,  # meters
        }.get(insunits, 1.0)

    @staticmethod
    def dxf_unit_label(path: Path) -> str:
        return {
            "1": "in",
            "2": "ft",
            "4": "mm",
            "5": "cm",
            "6": "m",
        }.get(ShowerProgrammerApp.dxf_insunits(path), "units")

    @staticmethod
    def dxf_insunits(path: Path) -> str:
        try:
            pairs = programmer.read_dxf_pairs(path)
        except Exception:
            return "1"
        for index, pair in enumerate(pairs):
            if pair[0].strip() != "9" or pair[1].strip().upper() != "$INSUNITS":
                continue
            for target in range(index + 1, min(index + 8, len(pairs))):
                code = pairs[target][0].strip()
                if code == "9":
                    break
                if code == "70":
                    return pairs[target][1].strip()
        return "1"

    @classmethod
    def dxf_dimension_text(cls, width: float, height: float, unit_label: str, inches_per_unit: float) -> str:
        if abs(inches_per_unit - 1.0) <= 1e-9 and unit_label == "in":
            return f"{width:g} x {height:g} in"
        width_inches = width * inches_per_unit
        height_inches = height * inches_per_unit
        return (
            f"{width:g} x {height:g} {unit_label} "
            f"({cls.format_inches(width_inches)} x {cls.format_inches(height_inches)})"
        )

    @staticmethod
    def format_degrees(value: float) -> str:
        text = f"{value:.8f}".rstrip("0").rstrip(".")
        return text if text else "0"

    @staticmethod
    def panel_rotation_summary(panel: programmer.Panel) -> str:
        base = panel.rotation_degrees
        if base is None:
            return "DXF rotation: none"
        total = base + panel.angle_correction_degrees
        if abs(panel.angle_correction_degrees) > 1e-9:
            return (
                f"DXF rotation: {ShowerProgrammerApp.format_degrees(total)} deg "
                f"({ShowerProgrammerApp.format_degrees(base)} + "
                f"{ShowerProgrammerApp.format_degrees(panel.angle_correction_degrees)} correction)"
            )
        return f"DXF rotation: {ShowerProgrammerApp.format_degrees(base)} deg"

    def save_editor_state_positions(
        self,
        job: programmer.Job,
        state: dict[str, Any],
        config: dict[str, object],
        parent: tk.Widget | None,
        show_no_edits: bool = True,
    ) -> bool:
        dirty = state.get("dirty")
        if not dirty:
            if show_no_edits:
                messagebox.showinfo("No edits", "Nothing has been moved yet.", parent=parent)
            return False
        try:
            data = self.load_manual_overrides()
            item_overrides = data.setdefault("item_overrides", {})
            if not isinstance(item_overrides, dict):
                item_overrides = {}
                data["item_overrides"] = item_overrides
            order_overrides = item_overrides.setdefault(job.aw_order, {})
            if not isinstance(order_overrides, dict):
                order_overrides = {}
                item_overrides[job.aw_order] = order_overrides
            for item_number, key in sorted(dirty):
                position = state.get("positions", {}).get((item_number, key))
                if position is None:
                    continue
                panel = next(panel for panel in job.panels if panel.item == item_number)
                item_override = order_overrides.setdefault(str(item_number), {})
                if not isinstance(item_override, dict):
                    item_override = {}
                    order_overrides[str(item_number)] = item_override
                if key == "label":
                    item_override["label_x"] = round(float(position["x"]), 3)
                    item_override["label_y"] = round(float(position["y"]), 3)
                elif key == "indicator":
                    corner = str(position.get("indicator_corner") or panel.indicator_corner or "").strip().lower()
                    if corner:
                        raw_corner = str(position.get("raw_indicator_corner") or corner).strip().lower()
                        if panel.machine.startswith("DENVER") and raw_corner in {"bottom_left", "bottom_right", "top_left", "top_right"}:
                            corner = raw_corner
                            item_override["manual_indicator_corner"] = True
                        else:
                            item_override.pop("manual_indicator_corner", None)
                        item_override["indicator_x"] = round(float(position["x"]), 3)
                        item_override["indicator_y"] = round(float(position["y"]), 3)
                        panel.indicator_x = float(position["x"])
                        panel.indicator_y = float(position["y"])
                        programmer.apply_indicator_corner_override_with_options(
                            panel,
                            corner,
                            config,
                            allow_manual_denver_corner=bool(item_override.get("manual_indicator_corner")),
                        )
                        item_override["indicator_corner"] = corner
                        if panel.rotation_degrees is not None:
                            item_override["rotation_degrees"] = round(float(panel.rotation_degrees), 6)
                        if panel.machine == "DENVER 1" and programmer.has_door_programming_evidence(panel, config):
                            if panel.hinge_side:
                                item_override["hinge_side"] = panel.hinge_side
                            item_override["hinges_up"] = bool(panel.hinges_up)
                        else:
                            item_override.pop("hinge_side", None)
                            item_override.pop("hinges_up", None)
                elif key == "diamon_fusion":
                    item_override["diamon_fusion_x"] = round(float(position["x"]), 3)
                    item_override["diamon_fusion_y"] = round(float(position["y"]), 3)
                elif key == "remake":
                    item_override["remake_x"] = round(float(position["x"]), 3)
                    item_override["remake_y"] = round(float(position["y"]), 3)
            self.save_manual_overrides(data)
            state["dirty"].clear()
            state["positions"].clear()
            return True
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=parent)
            return False

    def set_mark_hidden(self, aw_order: str, item_number: int, mark_key: str, hidden: bool) -> None:
        field_by_key = {
            "label": "hide_label",
            "indicator": "hide_indicator",
            "diamon_fusion": "hide_diamon_fusion",
            "remake": "hide_remake",
        }
        field = field_by_key.get(mark_key)
        if field is None:
            return
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override
        if hidden:
            item_override[field] = True
        else:
            item_override.pop(field, None)
            if mark_key == "indicator":
                for key in ("indicator_x", "indicator_y", "manual_indicator_corner"):
                    item_override.pop(key, None)
        self.save_manual_overrides(data)

    def set_manual_x_override(self, aw_order: str, item_number: int, enabled: bool) -> None:
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override
        if enabled:
            item_override["manual_x"] = True
        else:
            item_override.pop("manual_x", None)
        self.save_manual_overrides(data)

    def set_mark_text_override(self, aw_order: str, item_number: int, mark_key: str, value: str) -> None:
        field_by_key = {
            "label": "label_text",
            "diamon_fusion": "diamon_fusion_text",
            "remake": "remake_text",
        }
        field = field_by_key.get(mark_key)
        if field is None:
            return
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override
        text = value.replace("\\n", "\n").strip()
        if text:
            item_override[field] = text
        else:
            item_override.pop(field, None)
        self.save_manual_overrides(data)

    def set_indicator_machine_override(
        self,
        aw_order: str,
        item_number: int,
        machine_kind: str,
        panel: programmer.Panel,
        config: dict[str, object],
    ) -> None:
        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override

        kind = machine_kind.strip().upper()
        if kind == "WJ":
            item_override["machine"] = "WJ"
            item_override["indicator_corner"] = programmer.default_waterjet_indicator_corner(panel)
            item_override["rotation_degrees"] = -90 if panel.height and panel.width and panel.height > panel.width else 0
        else:
            machine = "DENVER 1" if programmer.has_door_programming_evidence(panel, config) else "DENVER 2"
            rotation = 90 if panel.height and panel.width and panel.height > panel.width else 0
            item_override["machine"] = machine
            item_override["indicator_corner"] = programmer.denver_grabber_corner_for_panel(panel, rotation)
            item_override["rotation_degrees"] = rotation

        item_override["skip_dxf"] = False
        item_override.pop("hide_indicator", None)
        item_override.pop("indicator_x", None)
        item_override.pop("indicator_y", None)
        item_override.pop("manual_indicator_corner", None)
        item_override.pop("hinge_side", None)
        item_override.pop("hinges_up", None)
        self.save_manual_overrides(data)

    def set_mark_size_override(
        self,
        aw_order: str,
        item_number: int,
        mark_key: str,
        direction: int,
        obj: dict[str, Any],
        panel: programmer.Panel,
        config: dict[str, object],
    ) -> float:
        pdf_cfg = config.get("pdf", {})
        if not isinstance(pdf_cfg, dict):
            pdf_cfg = {}

        if mark_key == "label":
            field = "label_font_size"
            current = panel.label_font_size or float(obj.get("font_size") or pdf_cfg.get("label_font_size", 21))
            step = 2.0
            minimum = 6.0
        elif mark_key == "diamon_fusion":
            field = "diamon_fusion_font_size"
            current = panel.diamon_fusion_font_size or float(obj.get("font_size") or pdf_cfg.get("diamon_fusion_font_size", 36))
            step = 4.0
            minimum = 10.0
        elif mark_key == "remake":
            field = "remake_font_size"
            remake_cfg = pdf_cfg.get("remake", {}) if isinstance(pdf_cfg.get("remake", {}), dict) else {}
            current = panel.remake_font_size or float(obj.get("font_size") or remake_cfg.get("font_size", 40))
            step = 4.0
            minimum = 10.0
        elif mark_key == "indicator":
            if str(obj.get("machine") or panel.machine).upper() == "WJ":
                field = "waterjet_indicator_size"
                current = panel.waterjet_indicator_size or float(obj.get("size") or pdf_cfg.get("waterjet_indicator_size", 30))
                step = 4.0
                minimum = 8.0
            else:
                field = "indicator_size"
                current = panel.indicator_size or float(obj.get("size") or pdf_cfg.get("indicator_size", 18))
                step = 2.0
                minimum = 6.0
        else:
            raise ValueError(f"Unsupported mark size key: {mark_key}")

        new_size = max(minimum, float(current) + step * (1 if direction > 0 else -1))

        data = self.load_manual_overrides()
        item_overrides = data.setdefault("item_overrides", {})
        if not isinstance(item_overrides, dict):
            item_overrides = {}
            data["item_overrides"] = item_overrides
        order_overrides = item_overrides.setdefault(str(aw_order), {})
        if not isinstance(order_overrides, dict):
            order_overrides = {}
            item_overrides[str(aw_order)] = order_overrides
        item_override = order_overrides.setdefault(str(item_number), {})
        if not isinstance(item_override, dict):
            item_override = {}
            order_overrides[str(item_number)] = item_override

        item_override[field] = round(new_size, 3)
        self.save_manual_overrides(data)
        return new_size

    def check_for_updates(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        git = shutil.which("git")
        if not git:
            self.check_for_updates_without_git(repo)
            return
        try:
            status = subprocess.run(
                [git, "status", "--porcelain"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
            fetch = subprocess.run(
                [git, "fetch", "origin", "main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=90,
            )
            if fetch.returncode != 0:
                messagebox.showerror("Update check failed", fetch.stderr.strip() or fetch.stdout.strip())
                return
            current = subprocess.run(
                [git, "rev-parse", "HEAD"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
            remote = subprocess.run(
                [git, "rev-parse", "origin/main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
            base = subprocess.run(
                [git, "merge-base", "HEAD", "origin/main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            ).stdout.strip()
        except Exception as exc:
            messagebox.showerror("Update check failed", str(exc))
            return

        if current == remote:
            self.status_var.set("Program is already up to date with origin/main.")
            messagebox.showinfo("No updates", "This program is already up to date with the GitHub main branch.")
            return
        if status:
            self.status_var.set("Updates are available, but local changes must be committed or stashed first.")
            messagebox.showwarning(
                "Updates available",
                "GitHub has newer code, but this working folder has local changes. "
                "Commit or stash them before using automatic update.",
            )
            return
        if base == current:
            if not messagebox.askyesno("Update program?", "Updates are available on GitHub main. Pull them now?"):
                return
            pull = subprocess.run(
                [git, "pull", "--ff-only", "origin", "main"],
                cwd=repo,
                text=True,
                capture_output=True,
                timeout=120,
            )
            if pull.returncode != 0:
                messagebox.showerror("Update failed", pull.stderr.strip() or pull.stdout.strip())
                return
            self.write_update_metadata(repo, remote, "git")
            self.status_var.set("Program updated from GitHub main. Restart the GUI to use the new code.")
            messagebox.showinfo("Updated", "The program was updated. Close and reopen the GUI to use the new code.")
            return
        if base == remote:
            messagebox.showinfo("Local branch ahead", "This folder has local commits that are not on GitHub main.")
            return
        messagebox.showwarning(
            "Branches diverged",
            "This folder and GitHub main both have different changes. Update manually with Git.",
        )

    def check_for_updates_without_git(self, repo: Path) -> None:
        owner, repo_name = self.github_update_repo(repo)
        try:
            latest_sha, latest_date = self.github_latest_commit(owner, repo_name, self.GITHUB_UPDATE_BRANCH)
        except Exception as exc:
            messagebox.showerror("Update check failed", f"Could not check GitHub for updates:\n\n{exc}")
            return

        current_sha = self.current_update_revision(repo)
        if current_sha and current_sha == latest_sha:
            self.status_var.set("Program is already up to date with GitHub main.")
            messagebox.showinfo("No updates", "This program is already up to date with the GitHub main branch.")
            return

        if current_sha:
            prompt = (
                "Updates are available on GitHub main.\n\n"
                f"Latest update: {latest_date or latest_sha[:12]}\n\n"
                "Download and install them now?"
            )
        else:
            prompt = (
                "Git is not installed, so this computer cannot compare local Git history.\n\n"
                f"Latest GitHub update: {latest_date or latest_sha[:12]}\n\n"
                "Download and install the latest GitHub main files now?"
            )
        if not messagebox.askyesno("Update program?", prompt):
            return

        try:
            self.install_update_zip(repo, owner, repo_name, self.GITHUB_UPDATE_BRANCH, latest_sha)
        except Exception as exc:
            messagebox.showerror("Update failed", str(exc))
            return
        self.write_update_metadata(repo, latest_sha, "zip")
        self.status_var.set("Program updated from GitHub main. Restart the GUI to use the new code.")
        messagebox.showinfo("Updated", "The program was updated. Close and reopen the GUI to use the new code.")

    def github_update_repo(self, repo: Path) -> tuple[str, str]:
        config_path = repo / ".git" / "config"
        if config_path.exists():
            try:
                text = config_path.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r"url\s*=\s*(?:https://github\.com/|git@github\.com:)([^/\s]+)/([^/\s]+?)(?:\.git)?\s*$", text, re.MULTILINE)
                if match:
                    return match.group(1), match.group(2)
            except OSError:
                pass
        return self.GITHUB_UPDATE_OWNER, self.GITHUB_UPDATE_REPO

    @staticmethod
    def github_json(url: str) -> dict[str, object]:
        data = ShowerProgrammerApp.download_text(url, timeout=45)
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise RuntimeError("GitHub returned an unexpected response.")
        return parsed

    def github_latest_commit(self, owner: str, repo_name: str, branch: str) -> tuple[str, str]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{branch}"
        data = self.github_json(url)
        sha = str(data.get("sha", "")).strip()
        if not sha:
            raise RuntimeError("GitHub did not return a commit id.")
        commit = data.get("commit", {})
        latest_date = ""
        if isinstance(commit, dict):
            committer = commit.get("committer", {})
            if isinstance(committer, dict):
                latest_date = str(committer.get("date", "")).strip()
        return sha, latest_date

    def current_update_revision(self, repo: Path) -> str:
        metadata_paths = [
            repo / "Output" / "update_metadata.json",
            repo / ".shower_update.json",
        ]
        for metadata_path in metadata_paths:
            if not metadata_path.exists():
                continue
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                sha = str(data.get("sha", "")).strip() if isinstance(data, dict) else ""
                if sha:
                    return sha
            except Exception:
                pass
        return self.git_head_without_git(repo)

    @staticmethod
    def git_head_without_git(repo: Path) -> str:
        git_dir = repo / ".git"
        head_path = git_dir / "HEAD"
        if not head_path.exists():
            return ""
        try:
            head = head_path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return ""
        if not head.startswith("ref:"):
            return head
        ref = head.split(":", 1)[1].strip().replace("/", os.sep)
        ref_path = git_dir / ref
        if ref_path.exists():
            try:
                return ref_path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                return ""
        packed_refs = git_dir / "packed-refs"
        if packed_refs.exists():
            try:
                for line in packed_refs.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == ref.replace(os.sep, "/"):
                        return parts[0]
            except OSError:
                return ""
        return ""

    def install_update_zip(self, repo: Path, owner: str, repo_name: str, branch: str, latest_sha: str) -> None:
        updates_dir = repo / "Output" / "Updates" / f"update_{datetime.now():%Y%m%d_%H%M%S}"
        updates_dir.mkdir(parents=True, exist_ok=True)
        archive_path = updates_dir / "main.zip"
        extract_dir = updates_dir / "extract"
        backup_dir = updates_dir / "backup"
        zip_url = f"https://codeload.github.com/{owner}/{repo_name}/zip/refs/heads/{branch}"
        self.status_var.set("Downloading update from GitHub...")
        self.download_file(zip_url, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)
        roots = [path for path in extract_dir.iterdir() if path.is_dir()]
        if not roots:
            raise RuntimeError("Downloaded update package was empty.")
        source_root = roots[0]
        self.status_var.set("Installing update files...")
        self.copy_update_tree(source_root, repo, backup_dir)
        (updates_dir / "installed_commit.txt").write_text(latest_sha + "\n", encoding="utf-8")

    @staticmethod
    def download_file(url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "Showers-Programmer-Updater"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        except Exception as exc:
            try:
                ShowerProgrammerApp.download_file_with_powershell(url, destination, timeout=120)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Python HTTPS download failed:\n{exc}\n\n"
                    f"PowerShell HTTPS fallback also failed:\n{fallback_exc}"
                ) from exc

    @staticmethod
    def download_text(url: str, timeout: int) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": "Showers-Programmer-Updater"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            try:
                return ShowerProgrammerApp.download_text_with_powershell(url, timeout=timeout)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Python HTTPS request failed:\n{exc}\n\n"
                    f"PowerShell HTTPS fallback also failed:\n{fallback_exc}"
                ) from exc

    @staticmethod
    def powershell_exe() -> str:
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            raise RuntimeError("PowerShell was not found for HTTPS fallback.")
        return exe

    @staticmethod
    def powershell_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def download_text_with_powershell(url: str, timeout: int) -> str:
        url_literal = ShowerProgrammerApp.powershell_literal(url)
        script = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$client = New-Object Net.WebClient
$client.Headers.Set('User-Agent', 'Showers-Programmer-Updater')
try {{
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $client.DownloadString({url_literal})
}} finally {{
    $client.Dispose()
}}
"""
        result = subprocess.run(
            [ShowerProgrammerApp.powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            text=True,
            capture_output=True,
            timeout=max(timeout, 30),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PowerShell download failed.")
        return result.stdout

    @staticmethod
    def download_file_with_powershell(url: str, destination: Path, timeout: int) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        url_literal = ShowerProgrammerApp.powershell_literal(url)
        destination_literal = ShowerProgrammerApp.powershell_literal(str(destination))
        script = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$client = New-Object Net.WebClient
$client.Headers.Set('User-Agent', 'Showers-Programmer-Updater')
try {{
    $client.DownloadFile({url_literal}, {destination_literal})
}} finally {{
    $client.Dispose()
}}
"""
        result = subprocess.run(
            [ShowerProgrammerApp.powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            text=True,
            capture_output=True,
            timeout=max(timeout, 30),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PowerShell download failed.")

    def copy_update_tree(self, source_root: Path, repo: Path, backup_dir: Path) -> None:
        skip_root_names = {".git", ".github", ".agents", ".codex", "Input", "Output"}
        for source in source_root.iterdir():
            if source.name in skip_root_names:
                continue
            self.copy_update_item(source, repo / source.name, backup_dir / source.name)

    def copy_update_item(self, source: Path, target: Path, backup: Path) -> None:
        if source.name == "__pycache__" or source.suffix.lower() in {".pyc", ".pyo"}:
            return
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                self.copy_update_item(child, target / child.name, backup / child.name)
            return
        if target.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    @staticmethod
    def write_update_metadata(repo: Path, sha: str, method: str) -> None:
        metadata = {
            "sha": sha,
            "method": method,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        metadata_path = repo / "Output" / "update_metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    def send_sketches_to_shop(self) -> None:
        self.send_outputs_to_shop(include_sketches=True, include_programs=False)

    def send_programs_to_shop(self) -> None:
        self.send_outputs_to_shop(include_sketches=False, include_programs=True)

    def send_all_to_shop(self) -> None:
        self.send_outputs_to_shop(include_sketches=True, include_programs=True, archive_inputs=True)

    def send_outputs_to_shop(
        self,
        *,
        include_sketches: bool,
        include_programs: bool,
        archive_inputs: bool = False,
    ) -> None:
        if self.is_busy:
            self.status_var.set("Busy. Please wait for the current task to finish.")
            return
        try:
            output_dir = Path(self.output_dir_var.get()).resolve()
            run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
            sketch_dir = (run_folder / "Sketches") if run_folder else output_dir / "Sketches"
            programs_dir = (run_folder / "Programs") if run_folder else output_dir / "Programs"
            sketch_paths: list[Path] = []
            dxf_paths: list[Path] = []
            missing: list[str] = []
            if include_sketches:
                sketch_paths = self.generated_sketch_paths(output_dir, sketch_dir)
                if not sketch_paths:
                    missing.append("sketches")
            if include_programs:
                dxf_paths = self.generated_dxf_paths(output_dir, programs_dir)
                if not dxf_paths:
                    missing.append("programs")
            if not sketch_paths and not dxf_paths:
                messagebox.showinfo("Nothing sent", "No matching generated files were found.")
                return
            aw_orders = self.selected_or_visible_aw_orders()
            orders = [self.order_by_aw[aw_order] for aw_order in aw_orders if aw_order in self.order_by_aw]
            order_folder = Path(self.folder_var.get()).resolve()
            process_list_path = Path(self.process_list_var.get()).resolve()
        except Exception as exc:
            messagebox.showerror("Send failed", str(exc))
            return

        self.start_background_activity("Sending generated files to shop folders...")
        worker = threading.Thread(
            target=self.worker_send_outputs,
            args=(sketch_paths, dxf_paths, missing, archive_inputs, orders, order_folder, process_list_path),
            daemon=True,
        )
        worker.start()

    def worker_send_outputs(
        self,
        sketch_paths: list[Path],
        dxf_paths: list[Path],
        missing: list[str],
        archive_inputs: bool,
        orders: list[shower_batch.ProcessOrder],
        order_folder: Path,
        process_list_path: Path,
    ) -> None:
        try:
            copied: list[Path] = []
            archived: list[Path] = []
            archive_warnings: list[str] = []
            if sketch_paths:
                copied.extend(self.copy_outputs_to_folder(sketch_paths, self.SHOP_SKETCHES_DIR))
            if dxf_paths:
                copied.extend(self.copy_outputs_to_folder(dxf_paths, self.SHOP_PROGRAMS_DIR))
            if copied and archive_inputs:
                archived, archive_warnings = self.archive_sent_input_files_for_orders(
                    orders,
                    order_folder,
                    process_list_path,
                )
            self.worker_queue.put(
                (
                    "send_done",
                    {
                        "copied": copied,
                        "missing": missing,
                        "archived": archived,
                        "archive_warnings": archive_warnings,
                    },
                )
            )
        except Exception as exc:
            self.worker_queue.put(("send_error", str(exc)))

    @staticmethod
    def send_complete_details(
        copied: list[Path],
        missing: list[str],
        archived: list[Path],
        archive_warnings: list[str],
    ) -> str:
        details = f"Copied {len(copied)} file(s) to the shop folders."
        sent_names = "\n".join(f"- {path.name}" for path in copied[:30])
        if sent_names:
            details += "\n\nSent:\n" + sent_names
        if len(copied) > 30:
            details += f"\n...and {len(copied) - 30} more"
        if missing:
            details += "\nNo matching " + " or ".join(missing) + " were found."
        if archived:
            archive_names = "\n".join(f"- {path}" for path in archived[:20])
            details += f"\n\nArchived {len(archived)} input file(s) into dated folders:\n{archive_names}"
            if len(archived) > 20:
                details += f"\n...and {len(archived) - 20} more"
        if archive_warnings:
            details += "\n\nArchive notes:\n" + "\n".join(f"- {warning}" for warning in archive_warnings)
        return details

    def copy_outputs_to_folder(self, paths: list[Path], target_dir: Path) -> list[Path]:
        target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for source in paths:
            if not source.exists() or not source.is_file():
                continue
            target = target_dir / source.name
            shutil.copy2(source, target)
            copied.append(target)
        return copied

    def archive_sent_input_files(self, aw_orders: list[str]) -> tuple[list[Path], list[str]]:
        if not aw_orders:
            return [], ["No scanned or selected orders were available to archive."]
        orders = [self.order_by_aw[aw_order] for aw_order in aw_orders if aw_order in self.order_by_aw]
        return self.archive_sent_input_files_for_orders(
            orders,
            Path(self.folder_var.get()).resolve(),
            Path(self.process_list_var.get()).resolve(),
        )

    def archive_sent_input_files_for_orders(
        self,
        orders: list[shower_batch.ProcessOrder],
        order_folder: Path,
        process_list_path: Path,
    ) -> tuple[list[Path], list[str]]:
        if not orders:
            return [], ["No matching scanned order records were available to archive."]

        dated_name = self.dated_archive_folder_name()
        order_archive_dir = self.archive_dir_for_input_root(order_folder, dated_name)
        archived: list[Path] = []
        warnings: list[str] = []

        order_files = self.matching_order_files(order_folder, orders, root_only=True, inspect_pdf_text=True)
        if order_files:
            for source in order_files:
                archived.append(self.move_file_to_folder(source, order_archive_dir))
        else:
            warnings.append("No root-level order PDF/DXF input files matched the sent orders.")

        try:
            process_list_files = shower_batch.process_list_files(process_list_path)
        except Exception as exc:
            process_list_files = []
            warnings.append(f"Could not archive process lists: {exc}")

        if process_list_files:
            process_archive_dir = self.process_list_archive_dir(process_list_path, dated_name)
            for source in process_list_files:
                if source.parent.resolve() == process_archive_dir.resolve():
                    continue
                archived.append(self.move_file_to_folder(source, process_archive_dir))
        else:
            warnings.append("No process-list .xlsx files were available to archive.")

        return archived, warnings

    @staticmethod
    def archive_dir_for_input_root(input_root: Path, dated_name: str) -> Path:
        if ShowerProgrammerApp.INPUT_ARCHIVE_FOLDER_RE.match(input_root.name):
            return input_root
        return input_root / dated_name

    @staticmethod
    def process_list_archive_dir(process_list_path: Path, dated_name: str) -> Path:
        if process_list_path.is_file():
            if ShowerProgrammerApp.INPUT_ARCHIVE_FOLDER_RE.match(process_list_path.parent.name):
                return process_list_path.parent
            return process_list_path.parent / dated_name
        if ShowerProgrammerApp.INPUT_ARCHIVE_FOLDER_RE.match(process_list_path.name):
            return process_list_path
        return process_list_path / dated_name

    @staticmethod
    def dated_archive_folder_name(moment: datetime | None = None) -> str:
        moment = moment or datetime.now()
        return f"{moment.month}.{moment.day}.{moment:%y}"

    @staticmethod
    def move_file_to_folder(source: Path, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = ShowerProgrammerApp.unique_target_path(target_dir / source.name)
        shutil.move(str(source), str(target))
        return target

    @staticmethod
    def unique_target_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        for index in range(2, 10_000):
            candidate = path.with_name(f"{stem} ({index}){suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Could not choose a unique archive name for {path}")

    @classmethod
    def copy_process_lists_from_import_folder(cls, process_list_path: Path) -> dict[str, object]:
        source_dir = cls.EDI_IMPORT_ORDERS_DIR
        summary: dict[str, object] = {
            "copied": [],
            "skipped": 0,
            "source": str(source_dir),
            "source_missing": False,
        }
        if not source_dir.exists():
            summary["source_missing"] = True
            return summary

        target_dir = cls.process_list_import_target_dir(process_list_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        skipped = 0
        for source in cls.importable_process_list_files(source_dir):
            target = target_dir / source.name
            if cls.copy_file_if_needed(source, target):
                copied.append(target)
            else:
                skipped += 1
        summary["copied"] = copied
        summary["skipped"] = skipped
        return summary

    @classmethod
    def importable_process_list_files(cls, source_dir: Path) -> list[Path]:
        files = [
            candidate
            for candidate in source_dir.iterdir()
            if candidate.is_file()
            and not candidate.name.startswith("~$")
            and candidate.suffix.lower() in cls.PROCESS_LIST_FILE_EXTENSIONS
        ]
        return sorted(files, key=lambda candidate: candidate.name.lower())

    @staticmethod
    def process_list_import_target_dir(process_list_path: Path) -> Path:
        if process_list_path.suffix:
            return process_list_path.parent
        return process_list_path

    @classmethod
    def copy_edi_orders_for_process_orders(
        cls,
        target_dir: Path,
        orders: list[shower_batch.ProcessOrder],
    ) -> dict[str, object]:
        source_dir = cls.EDI_IMPORT_ORDERS_DIR
        summary: dict[str, object] = {
            "copied": [],
            "skipped": 0,
            "source": str(source_dir),
            "source_missing": False,
        }
        if not orders:
            return summary
        if not source_dir.exists():
            summary["source_missing"] = True
            return summary

        target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        skipped = 0
        for source in cls.matching_order_files(source_dir, orders, root_only=True, inspect_pdf_text=True):
            target = target_dir / source.name
            if cls.copy_file_if_needed(source, target):
                copied.append(target)
            else:
                skipped += 1
        summary["copied"] = copied
        summary["skipped"] = skipped
        return summary

    @classmethod
    def matching_order_files(
        cls,
        folder: Path,
        orders: list[shower_batch.ProcessOrder],
        *,
        root_only: bool,
        inspect_pdf_text: bool,
    ) -> list[Path]:
        if not folder.exists():
            return []
        candidates = folder.glob("*") if root_only else folder.rglob("*")
        matched: list[Path] = []
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in cls.ORDER_FILE_EXTENSIONS:
                continue
            if cls.file_matches_process_orders(path, orders, inspect_pdf_text=inspect_pdf_text):
                matched.append(path)
        return sorted(matched, key=lambda candidate: candidate.name.lower())

    @staticmethod
    def file_matches_process_orders(
        path: Path,
        orders: list[shower_batch.ProcessOrder],
        *,
        inspect_pdf_text: bool,
    ) -> bool:
        suffix = path.suffix.lower()
        norm_stem = programmer.normalize_lookup(path.stem)
        for order in orders:
            norm_job = programmer.normalize_lookup(order.job_name)
            if not norm_job:
                continue
            if suffix == ".dxf":
                if any(programmer.dxf_match_score(path, norm_job, item) is not None for item in order.item_numbers):
                    return True
                continue
            if suffix == ".pdf":
                if norm_job in norm_stem:
                    return True
                guessed_job = programmer.job_from_filename(path.name)
                if guessed_job and norm_job in programmer.normalize_lookup(guessed_job):
                    return True
                if inspect_pdf_text:
                    try:
                        extracted_job = programmer.extract_job_from_pdf(path)
                    except Exception:
                        extracted_job = ""
                    if extracted_job and norm_job in programmer.normalize_lookup(extracted_job):
                        return True
        return False

    @staticmethod
    def copy_file_if_needed(source: Path, target: Path) -> bool:
        if source.resolve() == target.resolve():
            return False
        if target.exists():
            try:
                source_stat = source.stat()
                target_stat = target.stat()
                if source_stat.st_size == target_stat.st_size and target_stat.st_mtime >= source_stat.st_mtime:
                    return False
            except OSError:
                pass
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return True

    def autocad_save_as_programs(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
        programs_dir = (run_folder / "Programs") if run_folder else output_dir / "Programs"
        paths = self.generated_dxf_paths(output_dir, programs_dir)
        if not paths:
            messagebox.showinfo("No DXFs", "No generated program DXFs were found.")
            return
        if not messagebox.askyesno(
            "AutoCAD Save-As DXFs?",
            f"Open and Save-As {len(paths)} generated program DXF file(s) through AutoCAD?",
        ):
            return
        temp_file: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
                temp_file = Path(handle.name)
                for path in paths:
                    handle.write(str(path.resolve()) + "\n")
            list_literal = str(temp_file).replace("'", "''")
            script = f"""
$ErrorActionPreference = 'Stop'
$files = Get-Content -LiteralPath '{list_literal}'
try {{
    $acad = [Runtime.InteropServices.Marshal]::GetActiveObject('AutoCAD.Application')
}} catch {{
    $acad = New-Object -ComObject AutoCAD.Application
}}
$count = 0
foreach ($file in $files) {{
    if (-not (Test-Path -LiteralPath $file)) {{ continue }}
    $doc = $acad.Documents.Open($file)
    try {{
        $doc.SaveAs($file)
        $count += 1
    }} finally {{
        $doc.Close($false)
    }}
}}
Write-Output "AutoCAD saved $count DXF file(s)."
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                text=True,
                capture_output=True,
                timeout=max(120, len(paths) * 30),
            )
            if result.returncode != 0:
                messagebox.showerror("AutoCAD Save-As failed", result.stderr.strip() or result.stdout.strip())
                return
            message = result.stdout.strip() or f"AutoCAD saved {len(paths)} DXF file(s)."
            self.status_var.set(message)
            messagebox.showinfo("AutoCAD Save-As complete", message)
        except Exception as exc:
            messagebox.showerror("AutoCAD Save-As failed", str(exc))
        finally:
            if temp_file is not None:
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear_sketch_memory(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        if not messagebox.askyesno(
            "Clear sketch memory?",
            "This deletes generated sketch PDFs, clears sketch history pointers, and removes "
            "saved sketch-edit positions from manual_overrides.json. Machine overrides, DXFs, "
            "and process-list data are kept.",
        ):
            return
        removed_files = 0
        folders_and_patterns: list[tuple[Path, tuple[str, ...]]] = [
            (output_dir / "Sketches", ("*.pdf",)),
            (output_dir / "Reviews", ("sketch_review_*.pdf", "debug_*.png", "clean_*.png")),
        ]
        runs_dir = output_dir / "Runs"
        if runs_dir.exists():
            for run_folder in runs_dir.iterdir():
                if not run_folder.is_dir():
                    continue
                folders_and_patterns.append((run_folder / "Sketches", ("*.pdf",)))
                folders_and_patterns.append((run_folder / "Reviews", ("sketch_review_*.pdf", "debug_*.png", "clean_*.png")))
        for folder, patterns in folders_and_patterns:
            if not folder.exists():
                continue
            for pattern in patterns:
                for path in folder.glob(pattern):
                    try:
                        path.unlink()
                        removed_files += 1
                    except OSError:
                        pass
        for folder in output_dir.glob("DebugClean*"):
            if folder.is_dir():
                try:
                    shutil.rmtree(folder)
                    removed_files += 1
                except OSError:
                    pass
        changed_fields = self.clear_manual_sketch_fields()
        history_entries = self.clear_processing_history_sketch_fields()
        self.last_run_folder = None
        for aw_order, row_id in self.tree_rows.items():
            values = list(self.tree.item(row_id, "values"))
            if len(values) >= 9:
                values[1] = "No"
                values[2] = ""
                values[8] = self.review_status_for_order(aw_order)
                self.tree.item(row_id, values=values)
        self.status_var.set(
            f"Cleared {removed_files} sketch file(s), {changed_fields} saved sketch field(s), "
            f"and {history_entries} history entries."
        )
        messagebox.showinfo(
            "Sketch memory cleared",
            f"Deleted {removed_files} sketch/review file(s).\n"
            f"Removed {changed_fields} saved sketch field(s).\n"
            f"Cleared {history_entries} sketch history entries.",
        )

    def convert_programs_to_ac1032(self) -> None:
        self.autocad_save_as_programs()

    def clear_manual_sketch_fields(self) -> int:
        path = self.manual_overrides_path()
        if not path.exists():
            return 0
        data = self.load_manual_overrides()
        item_overrides = data.get("item_overrides", {})
        if not isinstance(item_overrides, dict):
            return 0
        sketch_fields = {
            "label_x",
            "label_y",
            "indicator_x",
            "indicator_y",
            "indicator_corner",
            "manual_indicator_corner",
            "rotation_degrees",
            "hinge_side",
            "hinges_up",
            "diamon_fusion_x",
            "diamon_fusion_y",
            "remake_x",
            "remake_y",
            "label_nudge_x",
            "label_nudge_y",
            "indicator_nudge_x",
            "indicator_nudge_y",
            "diamon_fusion_nudge_x",
            "diamon_fusion_nudge_y",
            "label_font_size",
            "diamon_fusion_font_size",
            "remake_font_size",
            "indicator_size",
            "waterjet_indicator_size",
            "checked",
            "hide_label",
            "hide_indicator",
            "hide_diamon_fusion",
            "hide_remake",
            "manual_x",
            "label_text",
            "diamon_fusion_text",
            "remake_text",
        }
        removed = 0
        empty_orders: list[str] = []
        for aw_order, order_overrides in item_overrides.items():
            if not isinstance(order_overrides, dict):
                continue
            if "_order_checked" in order_overrides:
                del order_overrides["_order_checked"]
                removed += 1
            empty_items: list[str] = []
            for item_key, override in order_overrides.items():
                if not isinstance(override, dict):
                    continue
                for field in list(override.keys()):
                    if field in sketch_fields:
                        del override[field]
                        removed += 1
                if not override:
                    empty_items.append(str(item_key))
            for item_key in empty_items:
                order_overrides.pop(item_key, None)
            if not order_overrides:
                empty_orders.append(str(aw_order))
        for aw_order in empty_orders:
            item_overrides.pop(aw_order, None)
        self.save_manual_overrides(data)
        return removed

    def clear_processing_history_sketch_fields(self) -> int:
        path = self.processing_history_path()
        if not path.exists():
            return 0
        data = self.load_processing_history()
        orders = data.get("orders", {})
        if not isinstance(orders, dict):
            return 0
        history_fields = {
            "last_processed",
            "output_pdf",
            "report_path",
            "run_folder",
            "status",
            "remake_items",
        }
        changed = 0
        empty_orders: list[str] = []
        for aw_order, entry in orders.items():
            if not isinstance(entry, dict):
                continue
            removed_any = False
            for field in history_fields:
                if field in entry:
                    del entry[field]
                    removed_any = True
            if removed_any:
                changed += 1
            if not entry:
                empty_orders.append(str(aw_order))
        for aw_order in empty_orders:
            orders.pop(aw_order, None)
        self.save_processing_history(data)
        return changed

    def open_sketch_editor(self) -> None:
        selected = self.selected_orders()
        if len(selected) != 1:
            messagebox.showinfo("Select one order", "Select exactly one scanned order to edit.")
            return
        process_order = selected[0]
        try:
            folder = Path(self.folder_var.get()).resolve()
            output_dir = Path(self.output_dir_var.get()).resolve()
            config = self.config_with_manual_overrides(folder, output_dir)
            remake_items = self.editor_remake_items(process_order.aw_order)
            job, reader, issues = shower_batch.prepare_job(
                folder,
                output_dir / "Sketches",
                output_dir / "Programs",
                output_dir / "Reports",
                config,
                process_order,
                remake_items=remake_items,
            )
        except Exception as exc:
            messagebox.showerror("Sketch editor failed", str(exc))
            return
        if not job.panels:
            messagebox.showinfo("No pieces", "No editable piece pages were found for this order.")
            return
        if issues:
            self.status_var.set("; ".join(issues[:3]))

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Sketch - {process_order.aw_order}")
        dialog.geometry("1040x820")
        dialog.transient(self.root)

        toolbar = ttk.Frame(dialog, padding=(8, 8, 8, 4))
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="Piece").pack(side=tk.LEFT)
        item_var = tk.StringVar(value=f"P{job.panels[0].item}")
        item_values = [f"P{panel.item}" for panel in job.panels]
        item_box = ttk.Combobox(toolbar, textvariable=item_var, values=item_values, state="readonly", width=8)
        item_box.pack(side=tk.LEFT, padx=(6, 12))
        editor_status = tk.StringVar(value="Drag blue markings, then save.")
        ttk.Label(toolbar, textvariable=editor_status).pack(side=tk.LEFT, fill=tk.X, expand=True)

        canvas_frame = ttk.Frame(dialog)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        canvas = tk.Canvas(canvas_frame, background="#e8edf3", highlightthickness=0)
        y_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        x_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        state: dict[str, Any] = {
            "objects": {},
            "positions": {},
            "dirty": set(),
            "drag_key": None,
            "last_x": 0.0,
            "last_y": 0.0,
            "scale": 1.0,
            "current_panel": job.panels[0],
            "page_offsets": {},
            "page_images": [],
            "render_cache": {},
            "render_temp_dir": tempfile.mkdtemp(prefix="shower_sketch_editor_"),
        }

        def selected_panel() -> programmer.Panel:
            item = int(item_var.get().replace("P", ""))
            return next(panel for panel in job.panels if panel.item == item)

        def redraw() -> None:
            self.draw_editor_all_panels(canvas, reader, job, config, state)
            editor_status.set(f"Editing {job.aw_order}. Scroll to any piece, drag blue markings, then save.")

        def start_drag(event: tk.Event, key: str) -> None:
            state["drag_key"] = key
            state["last_x"] = float(canvas.canvasx(event.x))
            state["last_y"] = float(canvas.canvasy(event.y))

        def drag(event: tk.Event) -> None:
            key = state.get("drag_key")
            if not key:
                return
            x = float(canvas.canvasx(event.x))
            y = float(canvas.canvasy(event.y))
            dx = x - float(state["last_x"])
            dy = y - float(state["last_y"])
            state["last_x"] = x
            state["last_y"] = y
            canvas.move(f"edit_{key}", dx, dy)
            obj = state["objects"][key]
            scale = float(obj.get("scale", state["scale"]))
            obj["x"] += dx / scale
            obj["y"] -= dy / scale
            item_number = int(obj.get("item", state["current_panel"].item))
            item_key = (item_number, str(obj.get("key", key)))
            state["dirty"].add(item_key)
            position = {"x": obj["x"], "y": obj["y"]}
            if obj.get("key") == "indicator":
                corner = programmer.nearest_indicator_corner_for_point(
                    obj["machine"],
                    (obj["x"], obj["y"]),
                    obj.get("anchor_bbox"),
                    float(obj["page_width"]),
                    float(obj["page_height"]),
                    obj["pdf_cfg"],
                    precise_edges=bool(obj.get("precise_edges")),
                )
                position["indicator_corner"] = corner
                if str(obj["machine"]).startswith("DENVER"):
                    position["raw_indicator_corner"] = programmer.nearest_indicator_corner_for_point(
                        obj["machine"],
                        (obj["x"], obj["y"]),
                        obj.get("anchor_bbox"),
                        float(obj["page_width"]),
                        float(obj["page_height"]),
                        obj["pdf_cfg"],
                        precise_edges=bool(obj.get("precise_edges")),
                        allowed_denver_only=False,
                    )
            state["positions"][item_key] = position
            editor_status.set(f"Moved {obj['name']} on {job.aw_order}.{item_number}")

        def release(_event: tk.Event) -> None:
            state["drag_key"] = None

        def save() -> bool:
            try:
                dirty = state["dirty"]
                if not dirty:
                    messagebox.showinfo("No edits", "Nothing has been moved yet.", parent=dialog)
                    return False
                data = self.load_manual_overrides()
                item_overrides = data.setdefault("item_overrides", {})
                if not isinstance(item_overrides, dict):
                    item_overrides = {}
                    data["item_overrides"] = item_overrides
                order_overrides = item_overrides.setdefault(job.aw_order, {})
                if not isinstance(order_overrides, dict):
                    order_overrides = {}
                    item_overrides[job.aw_order] = order_overrides
                for item_number, key in sorted(dirty):
                    position = state["positions"].get((item_number, key))
                    if position is None:
                        continue
                    panel = next(panel for panel in job.panels if panel.item == item_number)
                    item_override = order_overrides.setdefault(str(item_number), {})
                    if not isinstance(item_override, dict):
                        item_override = {}
                        order_overrides[str(item_number)] = item_override
                    if key == "label":
                        item_override["label_x"] = round(float(position["x"]), 3)
                        item_override["label_y"] = round(float(position["y"]), 3)
                        panel.label_x = float(position["x"])
                        panel.label_y = float(position["y"])
                    elif key == "indicator":
                        corner = str(position.get("indicator_corner") or panel.indicator_corner or "").strip().lower()
                        if corner:
                            raw_corner = str(position.get("raw_indicator_corner") or corner).strip().lower()
                            if panel.machine.startswith("DENVER") and raw_corner in {"bottom_left", "bottom_right", "top_left", "top_right"}:
                                corner = raw_corner
                                item_override["manual_indicator_corner"] = True
                            else:
                                item_override.pop("manual_indicator_corner", None)
                            item_override["indicator_x"] = round(float(position["x"]), 3)
                            item_override["indicator_y"] = round(float(position["y"]), 3)
                            panel.indicator_x = float(position["x"])
                            panel.indicator_y = float(position["y"])
                            programmer.apply_indicator_corner_override_with_options(
                                panel,
                                corner,
                                config,
                                allow_manual_denver_corner=bool(item_override.get("manual_indicator_corner")),
                            )
                            item_override["indicator_corner"] = corner
                            if panel.rotation_degrees is not None:
                                item_override["rotation_degrees"] = round(float(panel.rotation_degrees), 6)
                            if panel.machine == "DENVER 1" and programmer.has_door_programming_evidence(panel, config):
                                if panel.hinge_side:
                                    item_override["hinge_side"] = panel.hinge_side
                                item_override["hinges_up"] = bool(panel.hinges_up)
                            else:
                                item_override.pop("hinge_side", None)
                                item_override.pop("hinges_up", None)
                    elif key == "diamon_fusion":
                        item_override["diamon_fusion_x"] = round(float(position["x"]), 3)
                        item_override["diamon_fusion_y"] = round(float(position["y"]), 3)
                        panel.diamon_fusion_x = float(position["x"])
                        panel.diamon_fusion_y = float(position["y"])
                    elif key == "remake":
                        item_override["remake_x"] = round(float(position["x"]), 3)
                        item_override["remake_y"] = round(float(position["y"]), 3)
                        panel.remake_x = float(position["x"])
                        panel.remake_y = float(position["y"])
                self.save_manual_overrides(data)
                state["dirty"].clear()
                state["positions"].clear()
                editor_status.set(f"Saved manual positions to {self.manual_overrides_path().name}")
                return True
            except Exception as exc:
                messagebox.showerror("Save failed", str(exc), parent=dialog)
                return False

        def save_and_process() -> None:
            if save():
                dialog.destroy()
                remake_map = None if remake_items is None else {process_order.aw_order: set(remake_items)}
                self.run_orders([process_order], apply=True, remake_items_by_order=remake_map, force_override=True)

        def mark_checked(item_number: int | None = None) -> None:
            try:
                data = self.load_manual_overrides()
                item_overrides = data.setdefault("item_overrides", {})
                if not isinstance(item_overrides, dict):
                    item_overrides = {}
                    data["item_overrides"] = item_overrides
                order_overrides = item_overrides.setdefault(job.aw_order, {})
                if not isinstance(order_overrides, dict):
                    order_overrides = {}
                    item_overrides[job.aw_order] = order_overrides
                if item_number is None:
                    order_overrides["_order_checked"] = True
                    editor_status.set(f"Marked {job.aw_order} as reviewed.")
                else:
                    item_override = order_overrides.setdefault(str(item_number), {})
                    if not isinstance(item_override, dict):
                        item_override = {}
                        order_overrides[str(item_number)] = item_override
                    item_override["checked"] = True
                    editor_status.set(f"Marked {job.aw_order}.{item_number} as reviewed.")
                self.save_manual_overrides(data)
                row_id = self.tree_rows.get(job.aw_order)
                if row_id:
                    values = list(self.tree.item(row_id, "values"))
                    if len(values) >= 9:
                        values[8] = self.review_status_for_order(job.aw_order)
                        self.tree.item(row_id, values=values)
            except Exception as exc:
                messagebox.showerror("Review mark failed", str(exc), parent=dialog)

        def jump_to_selected() -> None:
            offsets = state.get("page_offsets", {})
            offset = offsets.get(selected_panel().item) if isinstance(offsets, dict) else None
            region = canvas.bbox("all")
            if offset is None or not region:
                return
            total_height = max(1.0, float(region[3] - region[1]))
            canvas.yview_moveto(max(0.0, min(1.0, float(offset) / total_height)))

        item_box.bind("<<ComboboxSelected>>", lambda _event: jump_to_selected())
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        canvas.bind("<Enter>", lambda _event: canvas.focus_set())
        canvas.bind("<MouseWheel>", lambda event: self.scroll_editor_canvas(canvas, event))
        dialog.bind("<MouseWheel>", lambda event: self.scroll_editor_canvas(canvas, event))
        canvas.bind("<Shift-MouseWheel>", lambda event: self.scroll_editor_canvas(canvas, event, horizontal=True))
        canvas.bind("<Button-4>", lambda event: canvas.yview_scroll(-3, "units"))
        canvas.bind("<Button-5>", lambda event: canvas.yview_scroll(3, "units"))

        buttons = ttk.Frame(dialog, padding=(8, 0, 8, 8))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Save Edits", command=save).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Save + Overwrite Sketch", command=save_and_process).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Mark P Checked", command=lambda: mark_checked(selected_panel().item)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Mark Order Checked", command=lambda: mark_checked(None)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

        state["start_drag"] = start_drag
        def cleanup_render_temp(_event: tk.Event | None = None) -> None:
            if _event is not None and _event.widget is not dialog:
                return
            temp_dir = state.get("render_temp_dir")
            if isinstance(temp_dir, str):
                shutil.rmtree(temp_dir, ignore_errors=True)

        dialog.bind("<Destroy>", cleanup_render_temp, add="+")
        dialog.after(100, redraw)

    def editor_remake_items(self, aw_order: str) -> set[int] | None:
        if self.remake_var.get():
            return set()
        history = self.history_for_order(aw_order)
        if "remake_items" not in history:
            return self.remake_items_from_report(aw_order)
        value = history.get("remake_items")
        if not isinstance(value, list):
            return self.remake_items_from_report(aw_order)
        return {int(item) for item in value if str(item).strip().isdigit()}

    def remake_items_from_report(self, aw_order: str) -> set[int] | None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        _run_folder, _sketch_dir, _programs_dir, report_dir = self.output_dirs_for_order(aw_order, output_dir)
        report_path = report_dir / f"{aw_order}_programming_report.txt"
        if not report_path.exists():
            return None
        try:
            text = report_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
        match = re.search(r"^Remake:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        value = match.group(1).strip()
        if value.lower() == "all pieces":
            return set()
        items = {int(part) for part in re.findall(r"\bP?(\d+)\b", value, flags=re.IGNORECASE)}
        return items

    def scroll_editor_canvas(self, canvas: tk.Canvas, event: tk.Event, horizontal: bool = False) -> str:
        delta = int(getattr(event, "delta", 0))
        if delta == 0:
            return "break"
        units = -1 if delta > 0 else 1
        if horizontal:
            canvas.xview_scroll(units * 4, "units")
        else:
            canvas.yview_scroll(units * 4, "units")
        return "break"

    def draw_editor_all_panels(
        self,
        canvas: tk.Canvas,
        reader: PdfReader,
        job: programmer.Job,
        config: dict[str, object],
        state: dict[str, Any],
    ) -> None:
        canvas.delete("all")
        state["objects"] = {}
        state["page_offsets"] = {}
        state["page_images"] = []
        y_cursor = 12.0
        max_width = 0.0
        for panel in job.panels:
            page = reader.pages[panel.page_index]
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            scale = min(940 / page_width, 640 / page_height)
            margin = 16.0
            header_height = 28.0
            page_top = y_cursor + header_height
            canvas_width = page_width * scale + margin * 2
            canvas_height = page_height * scale + margin * 2
            state["page_offsets"][panel.item] = y_cursor
            max_width = max(max_width, canvas_width)

            def to_canvas(x: float, y: float) -> tuple[float, float]:
                return margin + x * scale, page_top + margin + (page_height - y) * scale

            canvas.create_rectangle(0, y_cursor, canvas_width, page_top + canvas_height, fill="#e8edf3", outline="")
            canvas.create_text(
                margin,
                y_cursor + 8,
                text=f"P{panel.item}  {job.aw_order}.{panel.item}",
                anchor=tk.NW,
                fill="#1f2933",
                font=("Arial", 12, "bold"),
            )
            canvas.create_rectangle(
                margin,
                page_top + margin,
                canvas_width - margin,
                page_top + canvas_height - margin,
                fill="white",
                outline="#9aa7b5",
            )

            page_image = self.editor_page_image(job.pdf_path, panel.page_index, page_width, page_height, scale, state)
            if page_image is not None:
                state["page_images"].append(page_image)
                canvas.create_image(margin, page_top + margin, image=page_image, anchor=tk.NW)
            else:
                for start, end, _length in programmer.collect_page_line_segments(reader, panel.page_index, min_length=1.0):
                    x1, y1 = to_canvas(*start)
                    x2, y2 = to_canvas(*end)
                    canvas.create_line(x1, y1, x2, y2, fill="#3f4750", width=max(1, int(scale)))
                self.draw_editor_page_text(canvas, page, page_height, scale, margin, top_offset=page_top)
            objects = self.editor_overlay_objects(reader, job, panel, config)
            for obj in objects:
                obj["item"] = panel.item
                obj["scale"] = scale
                self.draw_editor_object(canvas, obj, scale, margin, page_height, state, top_offset=page_top)
            y_cursor = page_top + canvas_height + 20

        canvas.configure(scrollregion=(0, 0, max_width + 24, y_cursor))

    def draw_editor_panel(
        self,
        canvas: tk.Canvas,
        reader: PdfReader,
        job: programmer.Job,
        panel: programmer.Panel,
        config: dict[str, object],
        state: dict[str, Any],
    ) -> None:
        canvas.delete("all")
        state["page_images"] = []
        page = reader.pages[panel.page_index]
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        scale = min(940 / page_width, 700 / page_height)
        margin = 16.0
        state["scale"] = scale
        state["objects"] = {}

        def to_canvas(x: float, y: float) -> tuple[float, float]:
            return margin + x * scale, margin + (page_height - y) * scale

        canvas_width = page_width * scale + margin * 2
        canvas_height = page_height * scale + margin * 2
        canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
        canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="#e8edf3", outline="")
        canvas.create_rectangle(margin, margin, canvas_width - margin, canvas_height - margin, fill="white", outline="#9aa7b5")

        page_image = self.editor_page_image(job.pdf_path, panel.page_index, page_width, page_height, scale, state)
        if page_image is not None:
            state["page_images"].append(page_image)
            canvas.create_image(margin, margin, image=page_image, anchor=tk.NW)
        else:
            for start, end, _length in programmer.collect_page_line_segments(reader, panel.page_index, min_length=1.0):
                x1, y1 = to_canvas(*start)
                x2, y2 = to_canvas(*end)
                canvas.create_line(x1, y1, x2, y2, fill="#3f4750", width=max(1, int(scale)))
            self.draw_editor_page_text(canvas, page, page_height, scale, margin)
        objects = self.editor_overlay_objects(reader, job, panel, config)
        for obj in objects:
            self.draw_editor_object(canvas, obj, scale, margin, page_height, state)

    def editor_page_image(
        self,
        pdf_path: Path,
        page_index: int,
        page_width: float,
        page_height: float,
        scale: float,
        state: dict[str, Any],
        rotation_degrees: int = 0,
    ) -> Any | None:
        if Image is None or ImageTk is None:
            return None
        cache = state.setdefault("render_cache", {})
        normalized_rotation = rotation_degrees % 360
        key = (str(pdf_path), page_index, round(scale, 4), normalized_rotation)
        if isinstance(cache, dict) and key in cache:
            return cache[key]
        ghostscript = self.ghostscript_executable()
        if ghostscript is None:
            return None
        temp_dir = Path(str(state.get("render_temp_dir") or tempfile.gettempdir()))
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / f"page_{page_index + 1}_{abs(hash(key))}.png"
        render_dpi = 144
        command = [
            str(ghostscript),
            "-q",
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=png16m",
            f"-r{render_dpi}",
            f"-dFirstPage={page_index + 1}",
            f"-dLastPage={page_index + 1}",
            f"-sOutputFile={output_path}",
            str(pdf_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=30)
            image = Image.open(output_path)
            if normalized_rotation:
                image = image.rotate(-normalized_rotation, expand=True)
            if normalized_rotation % 180:
                target_size = (max(1, int(round(page_height * scale))), max(1, int(round(page_width * scale))))
            else:
                target_size = (max(1, int(round(page_width * scale))), max(1, int(round(page_height * scale))))
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            image = image.resize(target_size, resampling)
            photo = ImageTk.PhotoImage(image)
        except Exception:
            return None
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except Exception:
                pass
        if isinstance(cache, dict):
            cache[key] = photo
        return photo

    @staticmethod
    def ghostscript_executable() -> Path | None:
        for name in ("gswin64c", "gswin32c", "gs"):
            found = shutil.which(name)
            if found:
                return Path(found)
        candidates = [
            Path(r"C:\Program Files\gs\gs10.05.1\bin\gswin64c.exe"),
            Path(r"C:\Program Files\gs\gs10.04.0\bin\gswin64c.exe"),
            Path(r"C:\Program Files\gs\gs10.03.1\bin\gswin64c.exe"),
            Path(r"C:\Program Files (x86)\GPLGS\gswin32c.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def draw_editor_page_text(
        self,
        canvas: tk.Canvas,
        page: Any,
        page_height: float,
        scale: float,
        margin: float,
        top_offset: float = 0.0,
        page_width: float | None = None,
        rotation_degrees: int = 0,
    ) -> None:
        def to_canvas(x: float, y: float) -> tuple[float, float]:
            rotation = rotation_degrees % 360
            if rotation == 90:
                view_x, view_y = y, x
            elif rotation == 180:
                width = float(page_width or 0)
                view_x, view_y = width - x, y
            elif rotation == 270:
                width = float(page_width or 0)
                view_x, view_y = page_height - y, width - x
            else:
                view_x, view_y = x, page_height - y
            return margin + view_x * scale, top_offset + margin + view_y * scale

        def visitor(text: str, _cm: Any, tm: Any, _font_dict: Any, font_size: float) -> None:
            value = str(text).strip()
            if not value:
                return
            try:
                x, y = programmer.text_origin_from_matrices(_cm, tm)
            except Exception:
                return
            if not (0 <= x <= 620 and 0 <= y <= 800):
                return
            cx, cy = to_canvas(x, y)
            size = max(5, min(12, int(float(font_size) * scale)))
            canvas.create_text(cx, cy, text=value[:80], anchor=tk.SW, fill="#4b5563", font=("Arial", size))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception:
            return

    def editor_overlay_objects(
        self,
        reader: PdfReader,
        job: programmer.Job,
        panel: programmer.Panel,
        config: dict[str, object],
    ) -> list[dict[str, Any]]:
        page = reader.pages[panel.page_index]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        pdf_cfg = config.get("pdf", {})
        bbox = programmer.estimate_panel_bbox(reader, panel.page_index)
        indicator_bbox = programmer.estimate_panel_bbox(reader, panel.page_index, use_outer_edges=True)
        marker_bbox = programmer.estimate_panel_outline_bbox(reader, panel.page_index, panel.width, panel.height)
        obstacles = programmer.collect_page_obstacles(reader, panel.page_index)
        label_bbox = marker_bbox or bbox
        active_marker_bbox = marker_bbox or (indicator_bbox if panel.machine == "WJ" and indicator_bbox is not None else bbox)

        objects: list[dict[str, Any]] = []
        avoid_rects: list[tuple[float, float, float, float]] = []
        marker_rect = (
            programmer.indicator_marker_rect(
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
        if marker_rect is not None:
            avoid_rects.append(marker_rect)

        if panel.remake_excluded or panel.manual_x:
            remake_cfg = pdf_cfg.get("remake", {}) if isinstance(pdf_cfg.get("remake", {}), dict) else {}
            x_margin = programmer.parse_float(remake_cfg.get("x_margin", 48), 48)
            line_width = programmer.parse_float(remake_cfg.get("x_line_width", 10), 10)
            x_key = "manual_x" if panel.manual_x else "remake_xout"
            objects.append({
                "key": x_key,
                "name": "manual X" if panel.manual_x else "remake X-out",
                "kind": "x",
                "lines": [
                    ((x_margin, x_margin), (width - x_margin, height - x_margin)),
                    ((x_margin, height - x_margin), (width - x_margin, x_margin)),
                ],
                "line_width": line_width,
                "rect": (x_margin, x_margin, width - x_margin, height - x_margin),
            })
            return objects

        remake_rect: tuple[float, float, float, float] | None = None
        if panel.remake and not panel.hide_remake:
            remake_text = panel.remake_text or "REMAKE"
            remake_x, remake_y, remake_font, remake_rect = programmer.choose_remake_banner_position(
                width,
                height,
                pdf_cfg,
                bbox,
                indicator_bbox,
                panel,
                remake_text,
            )
            objects.append({
                "key": "remake",
                "name": remake_text,
                "kind": "text",
                "lines": [remake_text],
                "x": remake_x,
                "y": remake_y,
                "font_size": remake_font,
                "rect": remake_rect,
            })
            avoid_rects.append(remake_rect)

        if panel.diamon_fusion and not panel.hide_diamon_fusion:
            diamon_text = panel.diamon_fusion_text or "DIAMON FUSION"
            df_font = panel.diamon_fusion_font_size or float(pdf_cfg.get("diamon_fusion_font_size", 36))
            if remake_rect is not None:
                df_x, df_y, df_rect = programmer.choose_diamon_above_rect(width, height, diamon_text, df_font, remake_rect, pdf_cfg)
            else:
                df_x, df_y, df_font, df_rect = programmer.choose_diamon_banner_position(
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
                df_width = programmer.stringWidth(diamon_text, "Helvetica-Bold", df_font) + 12
                df_height = df_font + 10
                df_rect = (df_x - df_width / 2, df_y - 4, df_x + df_width / 2, df_y + df_height)
                if remake_rect is not None and programmer.rects_overlap(programmer.pad_rect(df_rect, 4), programmer.pad_rect(remake_rect, 2)):
                    df_x, df_y, df_rect = programmer.choose_diamon_above_rect(width, height, diamon_text, df_font, remake_rect, pdf_cfg)
            objects.append({
                "key": "diamon_fusion",
                "name": diamon_text,
                "kind": "text",
                "lines": [diamon_text],
                "x": df_x,
                "y": df_y,
                "font_size": df_font,
                "rect": df_rect,
            })
            avoid_rects.append(df_rect)

        label_lines = programmer.override_text_lines(panel.label_text) or [f"{job.aw_order}.{panel.item}"]
        if panel.machine and not panel.label_text:
            label_lines.append(panel.machine)
        font_size = panel.label_font_size or float(pdf_cfg.get("label_font_size", 21))
        label_x, label_y = programmer.choose_label_position(
            width,
            height,
            label_bbox,
            label_lines,
            font_size,
            obstacles,
            avoid_rects,
            panel,
            pdf_cfg,
        )
        if panel.label_x is not None and panel.label_y is not None:
            label_x, label_y = panel.label_x, panel.label_y
        if not panel.hide_label:
            objects.append({
                "key": "label",
                "name": "order/machine label",
                "kind": "text",
                "lines": label_lines,
                "x": label_x,
                "y": label_y,
                "font_size": font_size,
                "rect": programmer.label_rect(label_lines, label_x, label_y, font_size),
            })

        if panel.indicator_corner and panel.machine and not panel.hide_indicator:
            geometry = programmer.indicator_marker_geometry(
                panel.machine,
                panel.indicator_corner,
                active_marker_bbox,
                width,
                height,
                pdf_cfg,
                precise_edges=marker_bbox is not None,
                panel=panel,
            )
            if geometry is not None:
                geometry.update({
                    "key": "indicator",
                    "name": "indicator",
                    "x": geometry["point"][0],
                    "y": geometry["point"][1],
                    "machine": panel.machine,
                    "anchor_bbox": active_marker_bbox,
                    "page_width": width,
                    "page_height": height,
                    "pdf_cfg": pdf_cfg,
                    "precise_edges": marker_bbox is not None,
                })
                objects.append(geometry)
        return objects

    def draw_editor_object(
        self,
        canvas: tk.Canvas,
        obj: dict[str, Any],
        scale: float,
        margin: float,
        page_height: float,
        state: dict[str, Any],
        top_offset: float = 0.0,
        page_width: float | None = None,
        rotation_degrees: int = 0,
    ) -> None:
        key = obj["key"]
        object_key = f"{obj.get('item')}_{key}" if obj.get("item") is not None else str(key)
        tag = f"edit_{object_key}"
        effective_page_width = page_width if page_width is not None else float(obj.get("page_width", 0.0))
        if effective_page_width <= 0:
            effective_page_width = float(obj.get("page_height", page_height))
        page_pixel_width = effective_page_width * scale
        page_pixel_height = page_height * scale
        rotation = rotation_degrees % 360

        def to_canvas(x: float, y: float) -> tuple[float, float]:
            image_x = x * scale
            image_y = (page_height - y) * scale
            if rotation == 90:
                image_x, image_y = page_pixel_height - image_y, image_x
            elif rotation == 180:
                image_x, image_y = page_pixel_width - image_x, page_pixel_height - image_y
            elif rotation == 270:
                image_x, image_y = image_y, page_pixel_width - image_x
            return margin + image_x, top_offset + margin + image_y

        def bind_item(item_id: int) -> None:
            canvas.addtag_withtag(tag, item_id)
            canvas.addtag_withtag("editable_mark", item_id)

        blue = "#0078d4"
        if obj["kind"] == "text":
            font_size = max(1, int(round(float(obj["font_size"]) * scale)))
            leading = float(obj["font_size"]) * 1.18
            first_y = float(obj["y"]) + leading * (len(obj["lines"]) - 1) / 2
            baseline_center_offset = float(obj["font_size"]) * 0.35
            for index, line in enumerate(obj["lines"]):
                cx, cy = to_canvas(float(obj["x"]), first_y - index * leading + baseline_center_offset)
                bind_item(canvas.create_text(cx, cy, text=line, fill=blue, font=("Arial", -font_size, "bold"), anchor=tk.CENTER))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))
        elif obj.get("kind") == "wj":
            for start, end in obj["lines"]:
                x1, y1 = to_canvas(*start)
                x2, y2 = to_canvas(*end)
                bind_item(canvas.create_line(x1, y1, x2, y2, fill=blue, width=max(1, int(round(float(obj["line_width"]) * scale)))))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))
        elif obj.get("kind") == "x":
            for start, end in obj["lines"]:
                x1, y1 = to_canvas(*start)
                x2, y2 = to_canvas(*end)
                bind_item(canvas.create_line(x1, y1, x2, y2, fill=blue, width=max(2, int(round(float(obj["line_width"]) * scale)))))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))
        else:
            cx, cy = to_canvas(*obj["center"])
            radius = max(1.0, float(obj["radius"]) * scale)
            bind_item(canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=blue, outline=blue))
            rect = obj["rect"]
            x1, y1 = to_canvas(rect[0], rect[3])
            x2, y2 = to_canvas(rect[2], rect[1])
            bind_item(canvas.create_rectangle(x1, y1, x2, y2, outline=blue, dash=(4, 3), width=1))

        state["objects"][object_key] = obj
        canvas.tag_bind(tag, "<ButtonPress-1>", lambda event, object_key=object_key: state["start_drag"](event, object_key))
        show_mark_menu = state.get("show_mark_menu")
        if callable(show_mark_menu):
            canvas.tag_bind(tag, "<Button-3>", lambda event, object_key=object_key: show_mark_menu(event, object_key))
            canvas.tag_bind(tag, "<Double-Button-1>", lambda event, object_key=object_key: show_mark_menu(event, object_key))

    def open_last_report(self) -> None:
        if not self.last_reports:
            messagebox.showinfo("No report yet", "Run a batch first.")
            return
        webbrowser.open(self.last_reports.html_report.resolve().as_uri())

    def open_output_folder(self) -> None:
        path = Path(self.output_dir_var.get()).resolve()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_sketches_folder(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
        path = (run_folder / "Sketches") if run_folder else output_dir / "Sketches"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_programs_folder(self) -> None:
        output_dir = Path(self.output_dir_var.get()).resolve()
        run_folder = self.last_run_folder or self.latest_run_folder(output_dir)
        path = (run_folder / "Programs") if run_folder else output_dir / "Programs"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_config(self) -> None:
        path = self.config_path(Path(self.folder_var.get()).resolve())
        if not path.exists():
            messagebox.showerror("Config not found", f"Could not find:\n{path}")
            return
        os.startfile(path)


def main() -> None:
    root = tk.Tk()
    app = ShowerProgrammerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
