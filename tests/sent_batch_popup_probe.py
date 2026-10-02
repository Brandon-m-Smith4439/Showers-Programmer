"""Exercise real right-click archive dialogs using a disposable copy of Batch 8671."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
import shower_batch
import shower_legacy_xls
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory
from PIL import ImageGrab


def run(report_dir: Path):
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {"production_paths_untouched": True, "errors": [], "events": []}
    source_runtime = ROOT / "Shower Programmer"
    source_batch = source_runtime / "Input" / "Process List" / "Batch 8671.xls"
    orders = shower_batch.load_process_orders_from_rows(shower_legacy_xls.load_rows(source_batch))
    history = gui.ShowerProgrammerApp.load_processing_history_for_output(source_runtime / "Output")
    history = {"orders": {order.aw_order: history["orders"].get(order.aw_order, {}) for order in orders}}
    report["orders"] = [order.aw_order for order in orders]
    with workspace_temporary_directory(prefix="sent-batch-popup") as raw, ExitStack() as stack:
        runtime = Path(raw)
        local = runtime / "Input" / "Orders"
        lists = runtime / "Input" / "Process List"
        output = runtime / "Output"
        for path in (local, lists, output):
            path.mkdir(parents=True)
        batch_file = lists / source_batch.name
        shutil.copy2(source_batch, batch_file)
        gui.ShowerProgrammerApp.save_processing_history_for_output(output, history)
        archived = local / gui.ShowerProgrammerApp.dated_archive_folder_name()
        archived.mkdir()
        for entry in history["orders"].values():
            for filename in entry.get("archived_inputs", []):
                candidates = list((source_runtime / "Input" / "Orders").glob("*/" + Path(filename).name))
                if candidates and not (archived / Path(filename).name).exists():
                    shutil.copy2(candidates[-1], archived / Path(filename).name)
        cls = gui.ShowerProgrammerApp
        stack.enter_context(mock.patch.object(cls, "preferred_runtime_root", return_value=runtime))
        stack.enter_context(mock.patch.object(cls, "preferred_ui_settings_path", return_value=runtime / "ui.json"))
        stack.enter_context(mock.patch.object(cls, "load_ui_settings", return_value={"dark_mode": True}))
        for method in ("start_deferred_startup_housekeeping", "start_startup_recovery_check_async", "check_network_health_async", "start_startup_update_check", "prefetch_adjacent_review_contexts"):
            stack.enter_context(mock.patch.object(cls, method))
        stack.enter_context(mock.patch.object(gui.shower_maintenance.CacheMaintenanceService, "start"))
        root = gui.tk.Tk()
        root.withdraw()
        app = None
        try:
            root.report_callback_exception = lambda kind, error, tb: report["errors"].append(f"{kind.__name__}: {error}")
            app = cls(root)
            root.state("normal")
            root.geometry("1300x850+40+40")
            root.deiconify()
            app.process_batches = {"batch-8671": {"name": source_batch.name, "path": batch_file, "orders": orders, "all_orders": orders}}
            app.orders = orders
            report["receipt_validation"] = app.batch_is_ready_for_input_archive(app.process_batches["batch-8671"], history)
            started = time.monotonic()
            clicked = set()
            notices = {}
            ticks = []
            original_refresh = app.refresh_local_orders

            def observe_refresh(**kwargs):
                report["refresh_while_popup_open"] = any(window.winfo_exists() for window in notices)
                report["events"].append("refresh")
                original_refresh(**kwargs)

            stack.enter_context(mock.patch.object(app, "refresh_local_orders", side_effect=observe_refresh))

            def widgets(parent):
                yield parent
                for child in parent.winfo_children():
                    yield from widgets(child)

            def click(window, text):
                matches = [widget for widget in widgets(window) if isinstance(widget, gui.ctk.CTkButton) and widget.cget("text") == text]
                if not matches:
                    raise AssertionError(f"Missing button {text}")
                matches[0].invoke()

            def drive():
                ticks.append(time.monotonic())
                age = time.monotonic() - started
                if age > 12:
                    report["timed_out"] = True
                    for child in list(root.winfo_children()):
                        if isinstance(child, gui.tk.Toplevel):
                            child.destroy()
                    return
                root.after(30, drive)
                menu = getattr(app, "active_themed_context_popup", None)
                if menu is not None and menu.winfo_viewable() and "menu" not in clicked:
                    clicked.add("menu")
                    report["events"].append("context click")
                    click(menu, "Send Sent Batch to Archives")
                    return
                for child in list(widgets(root)):
                    if not isinstance(child, gui.tk.Toplevel) or not child.winfo_exists():
                        continue
                    title = child.title()
                    if title == "Archive sent batch" and "confirmation" not in clicked:
                        owner = getattr(child, "_shower_logical_owner", None)
                        report["confirmation_owner_state"] = owner.state() if owner is not None else "none"
                        report["confirmation_viewable"] = bool(child.winfo_viewable())
                        if child.winfo_viewable():
                            clicked.add("confirmation")
                            report["events"].append("confirm")
                            click(child, "Yes")
                            return
                    if title in {"Batch archived", "Batch archived with notes"} and child.winfo_viewable():
                        first = notices.setdefault(child, time.monotonic())
                        if "notice" not in clicked:
                            clicked.add("notice")
                        if time.monotonic() - first > 0.3:
                            child.attributes("-topmost", True)
                        if time.monotonic() - first > 0.5:
                            report["notice_alpha"] = child.attributes("-alpha")
                            report["notice_present_pending"] = getattr(child, "_shower_present_pending", False)
                            owner = getattr(child, "_shower_logical_owner", None)
                            report["notice_owner"] = str(owner)
                            report["notice_transient"] = str(child.transient())
                            report["notice_geometry"] = child.geometry()
                            child.lift()
                            child.update_idletasks()
                            x, y = child.winfo_rootx(), child.winfo_rooty()
                            ImageGrab.grab(bbox=(x, y, x + child.winfo_width(), y + child.winfo_height())).save(report_dir / "archive-result.png")
                            report["events"].append("close notice")
                            click(child, "Close")
                            return

            root.after(100, drive)
            app.show_themed_context_menu(root, 300, 240, "Batch 8671", "Disposable QA copy", [
                {"text": "Send Sent Batch to Archives", "icon": "archive", "command": lambda: app.archive_sent_batch_inputs("batch-8671")},
            ])
            while time.monotonic() - started < 13:
                root.update()
                if "close notice" in report["events"] and not app.operation_active() and "refresh" in report["events"]:
                    break
                time.sleep(0.003)
            report["batch_archived"] = not batch_file.exists() and (lists / cls.dated_archive_folder_name() / batch_file.name).exists()
            report["controls_unlocked"] = not app.operation_active()
            report["grab_released"] = root.grab_current() is None
            report["heartbeat_max_gap_ms"] = round(max((b - a for a, b in zip(ticks, ticks[1:])), default=0) * 1000, 2)
            report["ok"] = report["batch_archived"] and report["controls_unlocked"] and report["grab_released"] and not report["errors"] and not report.get("timed_out", False) and not report.get("refresh_while_popup_open", False) and report.get("notice_alpha") == 1.0 and not report.get("notice_present_pending", True)
        finally:
            if app is not None:
                app.review_context_prefetcher.shutdown()
                app.cache_maintenance.shutdown()
            for after_id in root.tk.call("after", "info"):
                root.after_cancel(after_id)
            try:
                root.destroy()
            except gui.tk.TclError:
                try:
                    root.tk.call("destroy", ".")
                except gui.tk.TclError:
                    pass
    (report_dir / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.report_dir.resolve())
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
