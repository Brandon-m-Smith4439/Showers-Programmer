"""Isolated live-Tk responsiveness probe; never scans or sends production data."""
from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from PIL import ImageGrab
from reportlab.pdfgen import canvas
import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


def run(report_dir: Path, *, dark: bool = False):
    report_dir.mkdir(parents=True, exist_ok=True)
    result = {"production_paths_untouched": True, "theme": "dark" if dark else "light"}
    errors = []
    with workspace_temporary_directory(prefix="desktop-probe") as raw_temp, ExitStack() as stack:
        runtime = Path(raw_temp)
        cls = gui.ShowerProgrammerApp
        stack.enter_context(mock.patch.object(cls, "preferred_runtime_root", return_value=runtime))
        stack.enter_context(mock.patch.object(cls, "preferred_ui_settings_path", return_value=runtime / "ui.json"))
        stack.enter_context(mock.patch.object(cls, "load_ui_settings", return_value={"dark_mode": dark}))
        for method in ("start_deferred_startup_housekeeping", "start_startup_recovery_check_async", "check_network_health_async", "start_startup_update_check", "prefetch_adjacent_review_contexts"):
            stack.enter_context(mock.patch.object(cls, method))
        stack.enter_context(mock.patch.object(gui.shower_maintenance.CacheMaintenanceService, "start"))
        stack.enter_context(mock.patch.object(cls, "resolve_exact_duplicate_order", return_value=False))
        root = gui.tk.Tk()
        root.withdraw()
        app = None
        try:
            root.report_callback_exception = lambda kind, error, tb: errors.append(f"{kind.__name__}: {error}")
            started = time.perf_counter()
            app = cls(root)
            result["main_shell_build_ms"] = round((time.perf_counter() - started) * 1000, 2)
            root.title("Shower Programmer - Isolated QA")
            root.state("normal")
            root.geometry("1500x900+20+20")
            root.deiconify()

            def pump(seconds):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.003)

            def capture(window, name):
                window.attributes("-topmost", True)
                window.attributes("-alpha", 1.0)
                window.lift()
                window.update()
                time.sleep(0.15)
                window.update_idletasks()
                x, y = window.winfo_rootx(), window.winfo_rooty()
                try:
                    ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height())).save(report_dir / name)
                finally:
                    window.attributes("-topmost", False)

            pump(0.5)
            row_metadata = {"issues": [], "status": "OK", "processed": "Yes", "review": "", "sent": "No"}
            started = time.perf_counter()
            for index in range(1000):
                aw = f"900{index:03d}"
                order = shower_batch.ProcessOrder(aw, f"QA JOB {index}", "SANITIZED QA")
                app.orders.append(order)
                app.order_by_aw[aw] = order
                row = shower_batch.BatchJobResult(aw_order=aw, job_name=order.job_name, customer=order.customer, items="P1", status="READY", delivery_date="10/02/2026")
                app.insert_or_update_result(row, metadata=row_metadata, defer_summary=True)
            app.update_summary_strip()
            result["thousand_row_insert_ms"] = round((time.perf_counter() - started) * 1000, 2)
            pump(0.3)
            capture(root, "main.png")

            heartbeat = []
            active = [True]

            def tick():
                heartbeat.append(time.perf_counter())
                if active[0]:
                    root.after(20, tick)

            root.after(20, tick)

            def worker(task):
                for index in range(100):
                    task.progress(index, 100, "Isolated responsiveness test")
                    time.sleep(0.01)
                return "done"

            done = []
            started = time.perf_counter()
            app.run_managed_task("QA Fixture", worker, message="Isolated responsiveness test", total=100, on_done=done.append)
            pump(1.5)
            active[0] = False
            result["task_completed"] = done == ["done"]
            result["controls_unlocked"] = not app.operation_active()
            result["heartbeat_max_gap_ms"] = round(max((b - a for a, b in zip(heartbeat, heartbeat[1:])), default=0) * 1000, 2)
            result["heartbeat_ticks"] = len(heartbeat)

            original = runtime / "Input" / "Orders" / "90000001 Original.pdf"
            duplicate = original.with_name("90000001 Original - Copy.pdf")
            fixture = canvas.Canvas(str(original))
            fixture.drawString(72, 720, "90000001 SANITIZED DUPLICATE QA")
            fixture.save()
            duplicate.write_bytes(original.read_bytes())
            duplicate_order = shower_batch.ProcessOrder("990001", "90000001 SANITIZED DUPLICATE QA", "QA")
            app.orders.append(shower_batch.ProcessOrder("990002", duplicate_order.job_name, "QA"))
            collision = programmer.classify_pdf_duplicate_collision([original, duplicate])
            if collision is None:
                raise AssertionError("Duplicate QA fixture did not collide")

            def inspect_duplicate_dialog():
                dialogs = [child for child in root.winfo_children() if isinstance(child, gui.tk.Toplevel) and "Resolve Duplicate Orders" in child.title()]
                if len(dialogs) != 1:
                    raise AssertionError("Duplicate dialog did not appear")
                dialog = dialogs[0]
                capture(dialog, "duplicate-resolution.png")
                def widgets(parent):
                    yield parent
                    for child in parent.winfo_children():
                        yield from widgets(child)
                button = next(child for child in widgets(dialog) if isinstance(child, gui.ctk.CTkButton) and str(child.cget("text")) == "Confirm Removal")
                button.invoke()

            root.after(600, inspect_duplicate_dialog)
            with mock.patch.object(app, "ask_themed_confirmation", return_value=True):
                choice = app.show_intentional_duplicate_dialog(duplicate_order, [original, duplicate], collision)
            if not choice or choice.get("action") != "remove_duplicates" or choice.get("path") != original:
                raise AssertionError("Duplicate dialog failed to retain the selected original")
            result["duplicate_dialog_keep_original"] = True

            def inspect_allow_dialog():
                dialog = next(child for child in root.winfo_children() if isinstance(child, gui.tk.Toplevel) and "Resolve Duplicate Orders" in child.title())
                def widgets(parent):
                    yield parent
                    for child in parent.winfo_children():
                        yield from widgets(child)
                controls = list(widgets(dialog))
                mode = next(child for child in controls if isinstance(child, gui.ctk.CTkSegmentedButton))
                selector = next(child for child in controls if isinstance(child, gui.ctk.CTkOptionMenu))
                selector.set("990002")
                mode.set("Allow Intentional Duplicate")
                mode._command(mode.get())
                action = next(child for child in controls if isinstance(child, gui.ctk.CTkButton) and child.cget("text") == "Verify & Allow Duplicate")
                action.invoke()
                confirmation.assert_not_called()
                if not dialog.winfo_exists():
                    raise AssertionError("Unchecked duplicate verification allowed production")
                verification = next(child for child in controls if isinstance(child, gui.ctk.CTkCheckBox) and str(child.cget("text")).startswith("I inspected"))
                verification.select()
                confirmation.return_value = False
                action.invoke()
                if not dialog.winfo_exists() or not original.exists() or not duplicate.exists():
                    raise AssertionError("Cancelling duplicate confirmation changed files or dismissed verification")
                capture(dialog, "duplicate-allow-verification.png")
                confirmation.return_value = True
                action.invoke()

            root.after(600, inspect_allow_dialog)
            with mock.patch.object(app, "ask_themed_confirmation", return_value=False) as confirmation:
                authorization = app.show_intentional_duplicate_dialog(duplicate_order, [original, duplicate], collision)
            if not authorization or authorization.get("action") != "authorize_duplicate" or authorization["order"].aw_order != "990002":
                raise AssertionError("Verified duplicate failed to authorize the explicitly chosen order")
            if not original.exists() or not duplicate.exists():
                raise AssertionError("Allowing an intentional duplicate removed source files")
            result["duplicate_verification_required"] = True
            result["duplicate_confirmation_cancel_safe"] = True
            result["duplicate_allow_chosen_order"] = True
            shared = runtime / "Configured Import"
            shared.mkdir()
            (shared / duplicate.name).write_bytes(duplicate.read_bytes())
            app.import_source_var.set(str(shared))
            with mock.patch.object(app, "show_themed_notice"), mock.patch.object(app, "refresh_local_orders"):
                started = time.perf_counter()
                app.apply_ambiguous_pdf_choice(duplicate_order, choice)
                result["duplicate_cleanup_click_ms"] = round((time.perf_counter() - started) * 1000, 2)
                pump(1)
            if not original.exists() or duplicate.exists() or (shared / duplicate.name).exists() or app.operation_active():
                raise AssertionError("Duplicate managed cleanup did not complete and unlock controls")
            result["duplicate_cleanup_completed"] = True
            app.save_processing_history_for_output(runtime / "Output", {
                "orders": {duplicate_order.aw_order: {
                    "sent_at": "2026-10-02",
                    "sent_process_signature": app.sent_process_signature(duplicate_order),
                }},
            })
            archive_ticks = []
            archive_running = [True]

            def archive_tick():
                archive_ticks.append(time.perf_counter())
                if archive_running[0]:
                    root.after(20, archive_tick)

            root.after(20, archive_tick)
            match_original = app.matching_order_files
            def delayed_local_match(*args, **kwargs):
                time.sleep(0.15)
                return match_original(*args, **kwargs)

            with mock.patch.object(gui.messagebox, "askyesno", return_value=True), mock.patch.object(app, "show_themed_notice"), mock.patch.object(app, "refresh_local_orders"), mock.patch.object(app, "matching_order_files", side_effect=delayed_local_match):
                started = time.perf_counter()
                app.archive_sent_order_inputs([duplicate_order])
                result["archive_click_ms"] = round((time.perf_counter() - started) * 1000, 2)
                pump(1.5)
            archive_running[0] = False
            if original.exists() or app.operation_active():
                raise AssertionError("Sent-input archive did not move the fixture and unlock controls")
            result["archive_completed"] = True
            result["archive_heartbeat_ticks"] = len(archive_ticks)
            result["archive_heartbeat_max_gap_ms"] = round(max((b - a for a, b in zip(archive_ticks, archive_ticks[1:])), default=0) * 1000, 2)

            source = runtime / "Input" / "Orders" / "QA ONLY.pdf"
            pdf = canvas.Canvas(str(source), pagesize=(612, 792))
            for item, height in ((1, 40), (2, 30)):
                pdf.setFont("Helvetica", 12)
                pdf.drawString(75, 745, "SANITIZED QA FIXTURE - NOT FOR PRODUCTION")
                pdf.drawString(75, 720, f"Marks: P{item}    80 x {height}    FP")
                pdf.rect(90, 270, 420, height * 5)
                pdf.showPage()
            pdf.save()
            dxf_paths = {}
            for item, height in ((1, 40), (2, 30)):
                dxf_path = runtime / "Output" / f"QA ONLY P{item}.dxf"
                pairs = [("0", "SECTION"), ("2", "HEADER"), ("9", "$INSUNITS"), ("70", "1"), ("0", "ENDSEC"), ("0", "SECTION"), ("2", "ENTITIES")]
                for start, end in [((0, 0), (80, 0)), ((80, 0), (80, height)), ((80, height), (0, height)), ((0, height), (0, 0))]:
                    pairs.extend([("0", "LINE"), ("10", str(start[0])), ("20", str(start[1])), ("11", str(end[0])), ("21", str(end[1]))])
                pairs.extend([("0", "ENDSEC"), ("0", "EOF")])
                dxf_path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")
                dxf_paths[item] = dxf_path
            config = programmer.load_config(ROOT / "Backend" / "shower_programmer_config.json")
            panels = [programmer.Panel(item, item - 1, f"Marks: P{item}\nFP", 80, height, "DENVER 2", indicator_corner="bottom_right", rotation_degrees=0, source_dxf=dxf_paths[item], output_dxf=dxf_paths[item]) for item, height in ((1, 40), (2, 30))]
            order = app.orders[0]
            job = programmer.Job(source, order.aw_order, order.job_name, panels, source, runtime / "Output" / "qa.txt")
            reader = gui.PdfReader(str(source))
            output = runtime / "Output"
            context = {"run_folder": output, "sketch_dir": output / "Sketches", "programs_dir": output / "Programs", "report_dir": output / "Reports", "sketch_path": source, "generated_sketch_path": source, "config": config, "job": job, "source_reader": reader, "sketch_reader": reader, "issues": [], "visible_issues": [], "dxf_preview_cache": {}}
            started = time.perf_counter()
            app.open_order_review(process_order_override=order, review_confirmed=True, opening_ready=True, prepared_context=context)
            result["review_shell_build_ms"] = round((time.perf_counter() - started) * 1000, 2)
            pump(1)
            review = app.managed_page_window("review_order")
            if review is None:
                raise AssertionError("Review did not open")
            capture(review, "review.png")

            def visit(widget):
                yield widget
                for child in widget.winfo_children():
                    yield from visit(child)

            next_buttons = [widget for widget in visit(review) if isinstance(widget, gui.ctk.CTkButton) and str(widget.cget("text")).strip() == "Next"]
            if len(next_buttons) != 1:
                raise AssertionError("Could not identify the review Next button")
            started = time.perf_counter()
            next_buttons[0].invoke()
            result["next_piece_callback_ms"] = round((time.perf_counter() - started) * 1000, 2)
            pump(0.5)
            capture(review, "review-next.png")
            result["callback_errors"] = errors
            if errors or not result["task_completed"] or not result["controls_unlocked"]:
                raise AssertionError(f"Live responsiveness probe failed: {result}")
            result["ok"] = True
        finally:
            if app is not None:
                app.review_context_prefetcher.shutdown()
                app.cache_maintenance.shutdown()
            try:
                for after_id in root.tk.call("after", "info"):
                    root.after_cancel(after_id)
                root.destroy()
            except gui.tk.TclError:
                pass
    (report_dir / "desktop.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--dark", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.report_dir.resolve(), dark=args.dark), indent=2))
