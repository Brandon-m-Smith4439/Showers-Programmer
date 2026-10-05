"""Real startup-recovery button and tour navigation in a disposable workstation."""
from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from PIL import ImageGrab
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


def run(report_dir: Path):
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {"production_paths_untouched": True, "callback_errors": []}
    with workspace_temporary_directory(prefix="onboarding-probe") as raw, ExitStack() as stack:
        runtime = Path(raw)
        cls = gui.ShowerProgrammerApp
        stack.enter_context(mock.patch.object(cls, "preferred_runtime_root", return_value=runtime))
        stack.enter_context(mock.patch.object(cls, "preferred_ui_settings_path", return_value=runtime / "ui.json"))
        stack.enter_context(mock.patch.object(cls, "load_ui_settings", return_value={"dark_mode": True}))
        for method in ("start_deferred_startup_housekeeping", "start_startup_recovery_check_async", "check_network_health_async", "start_startup_update_check"):
            stack.enter_context(mock.patch.object(cls, method))
        stack.enter_context(mock.patch.object(gui.shower_maintenance.CacheMaintenanceService, "start"))
        stack.enter_context(mock.patch.object(cls, "scan_orders"))
        root = gui.tk.Tk()
        root.withdraw()
        app = None
        try:
            root.report_callback_exception = lambda kind, error, tb: report["callback_errors"].append(f"{kind.__name__}: {error}")
            app = cls(root)
            root.state("normal")
            root.geometry("1500x900+20+20")
            root.deiconify()

            def pump(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    root.update()
                    time.sleep(0.004)

            def widgets(parent):
                yield parent
                for child in parent.winfo_children():
                    yield from widgets(child)

            def click(parent, text):
                button = next(child for child in widgets(parent) if isinstance(child, gui.ctk.CTkButton) and child.cget("text") == text)
                button.invoke()

            def capture(window, name):
                window.attributes("-topmost", True)
                window.lift()
                pump(0.2)
                x, y = window.winfo_rootx(), window.winfo_rooty()
                ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height())).save(report_dir / name)
                window.attributes("-topmost", False)

            pump(0.5)
            warning = {"type": "send", "severity": "WARN", "title": "QA interrupted Send", "detail": "Disposable test record. No production files are involved.", "occurred_at": datetime.now().astimezone().isoformat()}
            deadline = time.monotonic() + 10

            def choose_recovery():
                if time.monotonic() > deadline:
                    report["recovery_timed_out"] = True
                    for child in list(widgets(root)):
                        if isinstance(child, gui.tk.Toplevel) and child.title() == "Startup recovery check":
                            child.event_generate("<Escape>")
                    return
                for child in widgets(root):
                    if isinstance(child, gui.tk.Toplevel) and child.title() == "Startup recovery check" and child.attributes("-alpha") == 1.0:
                        click(child, "Open Recovery")
                        report["clicked_open_recovery"] = True
                        return
                root.after(40, choose_recovery)

            root.after(40, choose_recovery)
            app.apply_startup_recovery_results([warning])
            pump(1.5)
            settings = app.managed_page_window("settings")
            if settings is None or app.settings_tabview.get() != "Recovery" or settings.attributes("-alpha") != 1.0:
                raise AssertionError("Startup Open Recovery did not reveal the Recovery tab")
            report["recovery_selected"] = True
            report["startup_scan_deferred"] = app._startup_initial_scan_deferred_for_recovery
            capture(settings, "recovery.png")
            root.tk.call(settings.protocol("WM_DELETE_WINDOW"))
            pump(0.4)
            report["startup_scan_resumed_after_recovery"] = not app._startup_initial_scan_deferred_for_recovery
            old = dict(warning, title="Old QA warning", occurred_at=(datetime.now().astimezone() - timedelta(days=15)).isoformat())
            with mock.patch.object(gui.messagebox, "_show") as old_prompt:
                app.apply_startup_recovery_results([old])
                report["old_warning_suppressed"] = old_prompt.call_count == 0

            original_borders = {key: (target.cget("border_width"), target.cget("border_color")) for key, target in app.guided_tour_targets.items()}
            click(root, "Guided Tour")
            pump(0.3)
            tour = app.managed_page_window("guided_tour")
            capture(root, "main-with-tour.png")
            capture(tour, "tour.png")
            report["tour_modal_visible"] = root.grab_current() is tour and tour.attributes("-alpha") == 1.0
            for index in range(len(app.GUIDED_TOUR_STEPS) - 1):
                click(tour, "Next")
                pump(0.08)
            click(tour, "Back")
            click(tour, "Next")
            click(tour, "Finish")
            pump(0.1)
            report["tour_finish_releases_grab"] = root.grab_current() is None
            report["tour_restores_highlights"] = all((target.cget("border_width"), target.cget("border_color")) == original_borders[key] for key, target in app.guided_tour_targets.items())
            click(root, "Guided Tour")
            pump(0.2)
            click(app.managed_page_window("guided_tour"), "Skip Tour")
            report["tour_skip_releases_grab"] = root.grab_current() is None
            report["ok"] = all(report.get(key) for key in ("clicked_open_recovery", "recovery_selected", "startup_scan_deferred", "startup_scan_resumed_after_recovery", "old_warning_suppressed", "tour_modal_visible", "tour_finish_releases_grab", "tour_restores_highlights", "tour_skip_releases_grab")) and not report["callback_errors"]
        finally:
            if app is not None:
                app.review_context_prefetcher.shutdown()
                app.cache_maintenance.shutdown()
            for after_id in root.tk.call("after", "info"):
                root.after_cancel(after_id)
            try:
                root.destroy()
            except gui.tk.TclError:
                root.tk.call("destroy", ".")
    (report_dir / "onboarding.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.report_dir.resolve())
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
