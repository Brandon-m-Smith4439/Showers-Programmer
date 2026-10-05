from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
import shower_programmer_gui as gui
import shower_reliability
import build_update_package
from shower_temp import workspace_temporary_directory


class FirstTimeSetupRecoveryTests(unittest.TestCase):
    def test_startup_warning_older_than_two_weeks_does_not_prompt(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        state = {"history": [], "active_fingerprint": ""}
        app.load_startup_recovery_notice_state = lambda: state
        app.save_startup_recovery_notice_state = mock.Mock()
        app.schedule_startup_initial_scan = mock.Mock()
        app.record_action = mock.Mock()
        warning = {"type": "send", "severity": "WARN", "title": "Old Send", "detail": "Needs review", "occurred_at": (datetime.now().astimezone() - timedelta(days=15)).isoformat()}
        with mock.patch.object(gui.messagebox, "_show", return_value="later") as prompt:
            app.apply_startup_recovery_results([warning])
        prompt.assert_not_called()
        self.assertEqual(app.startup_recovery_results, [warning])
        self.assertTrue(any(row["status"] == "REMINDER_EXPIRED" for row in state["history"]))
        app.schedule_startup_initial_scan.assert_called_once()

    def test_warning_age_boundary_unknown_and_future_dates(self):
        now = datetime.now().astimezone()
        recent = gui.ShowerProgrammerApp.startup_recovery_warning_is_recent
        for days, expected in ((13, True), (14, True), (14.01, False), (30, False), (-1, True)):
            with self.subTest(days=days):
                self.assertEqual(recent({"occurred_at": (now - timedelta(days=days)).isoformat()}, now=now), expected)
        self.assertTrue(recent({"occurred_at": "bad date"}, now=now))
        self.assertTrue(recent({}, now=now))

    def test_expired_warning_is_recorded_only_once(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        state = {"history": [], "active_fingerprint": ""}
        app.load_startup_recovery_notice_state = lambda: state
        app.save_startup_recovery_notice_state = mock.Mock()
        app.schedule_startup_initial_scan = mock.Mock()
        app.record_action = mock.Mock()
        old = {"severity": "WARN", "title": "Old warning", "occurred_at": (datetime.now().astimezone() - timedelta(days=15)).isoformat()}
        for _ in range(2):
            app.apply_startup_recovery_results([old])
        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["status"], "REMINDER_EXPIRED")

    def test_update_and_database_warning_age_uses_file_timestamp(self):
        with workspace_temporary_directory(prefix="old-recovery-v203") as raw:
            root = Path(raw)
            update = root / ".__sp_new_fixture"
            update.mkdir()
            output = root / "Output"
            output.mkdir()
            journal = output / "shower_programmer.sqlite3-journal"
            journal.write_bytes(b"fixture")
            old = (datetime.now().astimezone() - timedelta(days=20)).timestamp()
            for path in (update, journal):
                os.utime(path, (old, old))
            warnings = shower_reliability.startup_recovery_issues(root, output)
            self.assertEqual({item["type"] for item in warnings}, {"update", "database"})
            self.assertTrue(all(not gui.ShowerProgrammerApp.startup_recovery_warning_is_recent(item) for item in warnings))

    def test_send_warning_carries_original_journal_timestamp(self):
        with workspace_temporary_directory(prefix="v203") as raw:
            folder = Path(raw)
            journal = shower_reliability.SendJournal(folder / "Output")
            ident = journal.begin(aw_orders=["900001"], output_sources=[], archive_inputs=True)
            journal.update(ident, shower_reliability.SendStage.NEEDS_ATTENTION, "fixture")
            warnings = shower_reliability.startup_recovery_issues(folder, folder / "Output")
            self.assertEqual(warnings[0].get("occurred_at"), journal.read(ident)["updated_at"])

    def test_setup_and_shortcut_scripts_use_local_environment_and_no_fake_taskbar_pin(self):
        setup = (ROOT / "First-Time Setup.ps1").read_text(encoding="utf-8")
        shortcut = (ROOT / "Create-ShowerProgrammerShortcut.ps1").read_text(encoding="utf-8")
        self.assertIn("-m venv", setup)
        self.assertIn("requirements.txt", setup)
        self.assertIn("NoLaunch", setup)
        self.assertIn("NoShortcuts", setup)
        self.assertNotIn("User Pinned", shortcut)
        self.assertIn("pythonw.exe", shortcut)
        self.assertTrue((ROOT / "First-Time Setup.bat").is_file())
        self.assertIn(".venv", (ROOT / "GUI.bat").read_text(encoding="utf-8"))

    @unittest.skipUnless(sys.platform == "win32", "Windows setup")
    def test_packaged_setup_is_repeatable_and_preserves_existing_inputs(self):
        with workspace_temporary_directory(prefix="setup-v203") as raw:
            root = Path(raw)
            (root / "Shower Programmer.exe").write_bytes(b"fixture not launched")
            (root / "_internal").mkdir()
            for relative in ('Assets/ShowersProgrammer.ico', '_internal/pypdfium2_raw/pdfium.dll',
                             '_internal/_tcl_data/init.tcl', '_internal/_tk_data/tk.tcl'):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture not launched')
            orders = root / "Input" / "Orders"
            orders.mkdir(parents=True)
            sentinel = orders / "Keep.pdf"
            sentinel.write_bytes(b"preserve input")
            for _ in range(2):
                result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "First-Time Setup.ps1"), "-AppRoot", str(root), "-NoLaunch", "-NoShortcuts"], capture_output=True, text=True, timeout=25)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(sentinel.read_bytes(), b"preserve input")
                self.assertTrue((root / "Input" / "Process List").is_dir())
                self.assertTrue((root / "Output" / "Runs").is_dir())
                self.assertTrue((root / "Diagnostics").is_dir())

    def test_release_includes_setup_helpers(self):
        build = (ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        self.assertIn('copy /Y "First-Time Setup.bat"', build)
        self.assertIn('copy /Y "First-Time Setup.ps1"', build)
        self.assertIn('copy /Y "Create-ShowerProgrammerShortcut.ps1"', build)

    def test_update_zip_inventory_includes_setup_without_user_data(self):
        with workspace_temporary_directory(prefix="package-v203") as raw:
            root = Path(raw)
            for name in ("First-Time Setup.bat", "First-Time Setup.ps1", "Create-ShowerProgrammerShortcut.ps1"):
                (root / name).write_text("fixture", encoding="ascii")
            (root / "Input").mkdir()
            (root / "Input" / "Keep.pdf").write_bytes(b"private")
            names = {name for _path, name in build_update_package.iter_package_files(root)}
            self.assertIn("First-Time Setup.bat", names)
            self.assertNotIn("Input/Keep.pdf", names)

    def test_tour_has_navigation_and_no_production_actions(self):
        self.assertTrue(callable(getattr(gui.ShowerProgrammerApp, "open_guided_tour", None)))
        steps = gui.ShowerProgrammerApp.GUIDED_TOUR_STEPS
        self.assertGreaterEqual(len(steps), 7)
        self.assertEqual(len({step[0] for step in steps}), len(steps))
        source = inspect.getsource(gui.ShowerProgrammerApp.open_guided_tour)
        for forbidden in ("self.scan_orders(", "self.process_selected(", "self.send_all_to_shop(", "self.open_order_review("):
            self.assertNotIn(forbidden, source)
        for text in ('text="Back"', 'text="Next"', 'text="Skip Tour"'):
            self.assertIn(text, source)

    def test_version_203_metadata(self):
        version = json.loads((ROOT / "Backend" / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 203)


if __name__ == "__main__":
    unittest.main()
