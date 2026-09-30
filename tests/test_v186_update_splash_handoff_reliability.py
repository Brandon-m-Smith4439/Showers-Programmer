from __future__ import annotations

import inspect
import json
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class UpdateSplashHandoffReliabilityTests(unittest.TestCase):
    def test_packaged_self_test_closes_splash_before_running_validation(self) -> None:
        source = inspect.getsource(gui.main)
        branch = source.split('if len(sys.argv) >= 2 and sys.argv[1].lower() == "--self-test":', 1)[1]
        self.assertLess(branch.index("close_packager_splash_early()"), branch.index("run_packaged_self_test(report)"))

    def test_duplicate_instance_closes_its_splash_before_warning(self) -> None:
        source = inspect.getsource(gui.main)
        duplicate = source.split("if not guard.acquire():", 1)[1].split("startup_shield = StartupShield(", 1)[0]
        self.assertLess(duplicate.index("close_packager_splash_early()"), duplicate.index("messagebox.showwarning("))

    def test_normal_startup_keeps_shield_before_splash_handoff_and_retries(self) -> None:
        source = inspect.getsource(gui.main)
        startup = source.split("startup_shield = StartupShield(", 1)[1]
        self.assertLess(startup.index("close_packager_splash()"), startup.index("construct_application"))
        self.assertIn("schedule_packager_splash_cleanup(root)", startup)
        retry_source = inspect.getsource(gui.schedule_packager_splash_cleanup)
        self.assertIn("(120, 450, 1200)", retry_source)
        self.assertIn("root.after(delay_ms, close_packager_splash)", retry_source)

    def test_close_helper_attempts_close_even_if_status_probe_fails(self) -> None:
        close = mock.Mock()
        fake = types.SimpleNamespace(is_alive=mock.Mock(side_effect=RuntimeError("probe failed")), close=close)
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.dict(sys.modules, {"pyi_splash": fake}):
            self.assertTrue(gui.close_packager_splash())
        close.assert_called_once_with()

    def test_version_186_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 186)
        self.assertGreaterEqual(version["version_number"], 186)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_86_UPDATE_SPLASH_HANDOFF_RELIABILITY", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "packaged_selftest_splash_cleanup",
            "duplicate_launch_splash_cleanup",
            "startup_splash_close_retry",
            "version_1_86_update_splash_handoff_reliability",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
