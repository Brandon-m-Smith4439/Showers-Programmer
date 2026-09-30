from __future__ import annotations

import json
import queue
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class Version192PackagedUpdateDetectionReliabilityTests(unittest.TestCase):
    def _app(self, *, local_version: int, current_sha: str, local_hash: str, descriptor: dict[str, object]):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.worker_queue = queue.Queue()
        app.APP_VERSION_NUMBER = local_version
        app.APP_VERSION = f"Version {local_version // 100}.{local_version % 100:02d}"
        app.github_update_repo = lambda _repo: ("owner", "repo")
        app.github_latest_commit = lambda *_args: ("branch-tip-sha", "2026-09-30T18:00:00Z")
        app.github_update_package_descriptor = lambda *_args: dict(descriptor)
        app.current_update_revision = lambda _repo: current_sha
        app.current_packaged_exe_hash = lambda: local_hash
        app.github_packaged_exe_hash = lambda *_args: str(descriptor.get("exe_sha256", ""))
        app.current_installed_version = lambda: app.APP_VERSION
        app.write_update_metadata = mock.Mock()
        return app

    def test_version_184_stale_revision_marker_cannot_hide_version_189(self) -> None:
        descriptor = {
            "version": "Version 1.89",
            "version_number": 189,
            "release_name": "Published 1.89",
            "commit": "same-stale-revision",
            "built_at": "2026-09-30T17:00:00Z",
            "exe_sha256": "new-exe-hash",
        }
        app = self._app(
            local_version=184,
            current_sha="same-stale-revision",
            local_hash="old-exe-hash",
            descriptor=descriptor,
        )
        with mock.patch.object(gui.sys, "frozen", True, create=True):
            app.worker_check_for_updates(Path("."), "", False, True)
        kind, payload = app.worker_queue.get_nowait()
        self.assertEqual(kind, "update_available")
        self.assertEqual(payload["latest_version"], "Version 1.89")
        self.assertEqual(payload["current_version"], "Version 1.84")

    def test_same_packaged_version_and_hash_is_up_to_date_even_if_revision_differs(self) -> None:
        descriptor = {
            "version": "Version 1.92",
            "version_number": 192,
            "commit": "published-build-sha",
            "exe_sha256": "same-exe-hash",
        }
        app = self._app(local_version=192, current_sha="old-marker", local_hash="same-exe-hash", descriptor=descriptor)
        with mock.patch.object(gui.sys, "frozen", True, create=True):
            app.worker_check_for_updates(Path("."), "", False, True)
        kind, payload = app.worker_queue.get_nowait()
        self.assertEqual(kind, "update_no_updates")
        self.assertEqual(payload["latest_version"], "Version 1.92")
        app.write_update_metadata.assert_called_once_with(Path("."), "published-build-sha", "version-match")

    def test_executable_hash_fallback_beats_equal_revision_when_version_number_missing(self) -> None:
        descriptor = {
            "version": "",
            "version_number": 0,
            "commit": "same-revision",
            "exe_sha256": "published-hash",
        }
        app = self._app(local_version=0, current_sha="older-revision", local_hash="old-hash", descriptor=descriptor)
        with mock.patch.object(gui.sys, "frozen", True, create=True):
            app.worker_check_for_updates(Path("."), "", False, True)
        kind, _payload = app.worker_queue.get_nowait()
        self.assertEqual(kind, "update_available")

    def test_package_descriptor_carries_published_exe_hash(self) -> None:
        metadata = {
            "zip_path": "release/Shower-Programmer-Windows.zip",
            "sha256": "zip-hash",
            "exe_sha256": "published-exe-hash",
            "version": "Version 1.92",
            "version_number": 192,
            "commit": "build-sha",
        }
        with mock.patch.object(gui.ShowerProgrammerApp, "download_text", return_value=json.dumps(metadata)):
            descriptor = gui.ShowerProgrammerApp.github_update_package_descriptor("owner", "repo", "main")
        self.assertEqual(descriptor["exe_sha256"], "published-exe-hash")
        self.assertEqual(descriptor["version_number"], 192)

    def test_updater_commits_external_metadata_only_after_launch_survives(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = source.index("    def stage_app_bundle_replacement")
        end = source.index("    @staticmethod\n    def stage_exe_replacement", start)
        body = source[start:end]
        launch = body.index('call :status "Starting the updated Shower Programmer..."')
        verified = body.index("if errorlevel 1 goto rollback_after_launch", launch)
        metadata = body.index("{metadata_commands}", verified)
        self.assertLess(launch, verified)
        self.assertLess(verified, metadata)
        self.assertNotIn("if errorlevel 1 goto rollback\\n'", body[body.index('metadata_commands = ""'):launch])
        self.assertIn("installed bundle metadata remains authoritative", body)

    def test_github_text_requests_disable_intermediary_cache(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn('"Cache-Control": "no-cache, no-store, max-age=0"', source)
        self.assertIn('"Pragma": "no-cache"', source)
        self.assertIn("$client.Headers.Set('Cache-Control', 'no-cache, no-store, max-age=0')", source)
        self.assertIn("$client.Headers.Set('Pragma', 'no-cache')", source)

    def test_version_192_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 192)
        self.assertEqual(version["marker"], "VERSION_1_92_PACKAGED_UPDATE_DETECTION_RELIABILITY")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_92_PACKAGED_UPDATE_DETECTION_RELIABILITY", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self_test = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        required = (
            "packaged_version_precedes_revision_metadata",
            "rollback_safe_update_metadata_commit",
            "github_update_cache_bypass",
            "published_exe_hash_comparison",
            "version_1_92_packaged_update_detection_reliability",
        )
        for flag in required:
            self.assertIn(flag, flags)
            self.assertIn(f'"{flag}": True', self_test)


if __name__ == "__main__":
    unittest.main()
