from __future__ import annotations

import json
import sys
import threading
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_tasks
from shower_programmer_gui import ShowerProgrammerApp


class SendCleanupPipelineTests(unittest.TestCase):
    def test_release_metadata_retains_version_131_contract(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self.assertGreaterEqual(int(version["version_number"]), 131)
        self.assertIn("version_1_31_send_pipeline_cleanup_speed", flags)

    def test_terminal_callback_can_start_the_next_managed_task(self) -> None:
        completed = threading.Event()
        events: list[tuple[str, str]] = []
        start_errors: list[Exception] = []
        manager: shower_tasks.BackgroundTaskManager

        def emit(kind: str, payload: dict[str, object]) -> None:
            name = str(payload.get("name", ""))
            events.append((kind, name))
            if kind == "task_done" and name == "Prepare Send Output":
                try:
                    manager.start(
                        "Send Output",
                        lambda _task: "sent",
                        message="Sending...",
                        total=1,
                    )
                except Exception as exc:  # pragma: no cover - assertion captures the failure
                    start_errors.append(exc)
                    completed.set()
            elif kind == "task_done" and name == "Send Output":
                completed.set()

        manager = shower_tasks.BackgroundTaskManager(emit)
        manager.start(
            "Prepare Send Output",
            lambda _task: "prepared",
            message="Preparing...",
            total=1,
        )

        self.assertTrue(completed.wait(2.0), "The chained Send Output task did not complete")
        self.assertEqual(start_errors, [])
        self.assertEqual(
            [(kind, name) for kind, name in events if kind == "task_done"],
            [("task_done", "Prepare Send Output"), ("task_done", "Send Output")],
        )
        self.assertIsNone(manager.active)

    def test_recovery_manifest_is_planned_once_and_committed_once(self) -> None:
        base = ROOT / "tests" / "_verification" / f"v131-recovery-{uuid.uuid4().hex[:8]}"
        source_root = base / "Input" / "Orders"
        recovery_root = base / "Recovery"
        source_root.mkdir(parents=True)
        sources = []
        for index in range(30):
            source = source_root / f"order-{index:02d}.pdf"
            source.write_bytes(f"file-{index}".encode("ascii"))
            sources.append(source)

        original_write = ShowerProgrammerApp.atomic_write_json
        with mock.patch.object(
            ShowerProgrammerApp,
            "atomic_write_json",
            side_effect=original_write,
        ) as write_manifest:
            moved, warnings, bundle_id = ShowerProgrammerApp.quarantine_paths(
                recovery_root,
                sources,
                [source_root],
                ["900000"],
            )

        self.assertEqual(warnings, [])
        self.assertEqual(set(moved), set(sources))
        self.assertIsNotNone(bundle_id)
        self.assertEqual(write_manifest.call_count, 2)
        manifest_path = recovery_root / str(bundle_id) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]), len(sources))
        self.assertTrue(all(entry.get("pending") is False for entry in manifest["files"]))
        self.assertTrue(all(not source.exists() for source in sources))

        restored, restore_warnings = ShowerProgrammerApp.restore_quarantine_bundle(
            recovery_root,
            str(bundle_id),
        )
        self.assertEqual(restore_warnings, [])
        self.assertEqual({path.name for path in restored}, {path.name for path in sources})
        self.assertTrue(all(source.exists() for source in sources))


if __name__ == "__main__":
    unittest.main()
