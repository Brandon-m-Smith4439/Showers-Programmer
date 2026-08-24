from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_cache
import shower_maintenance
import shower_review_service
import shower_scan_index
from shower_temp import workspace_temporary_directory


class Version141PerformanceReliabilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        shower_cache.configure(None)

    def test_cache_same_source_concurrency_has_no_transient_misses(self) -> None:
        with workspace_temporary_directory(prefix="cache-race") as raw:
            temp = Path(raw)
            source = temp / "source.pdf"
            source.write_bytes(b"stable")
            shower_cache.configure(temp / "cache")
            shower_cache.store("race", source, {"seed": True})
            shower_cache.reset_stats()

            def worker(worker_id: int) -> int:
                misses = 0
                for iteration in range(50):
                    shower_cache.store("race", source, {"worker": worker_id, "iteration": iteration})
                    if shower_cache.load("race", source) is None:
                        misses += 1
                return misses

            with ThreadPoolExecutor(max_workers=8) as executor:
                misses = sum(executor.map(worker, range(8)))

            self.assertEqual(misses, 0)
            self.assertEqual(shower_cache.stats()["errors"], 0, shower_cache.last_error())

    def test_cache_memory_hit_skips_json_disk_read(self) -> None:
        with workspace_temporary_directory(prefix="memory-cache") as raw:
            temp = Path(raw)
            source = temp / "source.txt"
            source.write_text("stable", encoding="utf-8")
            shower_cache.configure(temp / "cache")
            shower_cache.store("memory", source, {"value": 9})
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("disk read")):
                self.assertEqual(shower_cache.load("memory", source), {"value": 9})
            self.assertEqual(shower_cache.stats()["memory_hits"], 1)

    def test_scan_index_extracts_each_pdf_once_for_many_orders(self) -> None:
        pdf = Path("Glass Order unmatched.pdf")
        orders = [
            shower_batch.ProcessOrder(str(800000 + index), f"90{index:06d} TEST {index}", "Customer")
            for index in range(200)
        ]
        index = shower_scan_index.OrderInputIndex([pdf])
        with (
            mock.patch.object(shower_scan_index.programmer, "extract_first_page_text", return_value="unmatched") as text,
            mock.patch.object(shower_scan_index.programmer, "extract_job_from_pdf", return_value="UNMATCHED") as job,
        ):
            self.assertFalse(index.file_matches_orders(pdf, orders, inspect_pdf_text=True))
            self.assertFalse(index.file_matches_orders(pdf, orders, inspect_pdf_text=True))
        text.assert_called_once_with(pdf)
        job.assert_called_once_with(pdf)

    def test_review_prefetcher_deduplicates_pending_context_loads(self) -> None:
        service = shower_review_service.ReviewContextPrefetcher(max_workers=2)
        completed = threading.Event()
        callbacks: list[tuple[object | None, BaseException | None]] = []
        load_count = 0
        lock = threading.Lock()

        def loader() -> dict[str, bool]:
            nonlocal load_count
            with lock:
                load_count += 1
            time.sleep(0.04)
            return {"ready": True}

        def callback(value: object | None, error: BaseException | None) -> None:
            callbacks.append((value, error))
            if len(callbacks) == 2:
                completed.set()

        try:
            self.assertTrue(service.request("order", loader, callback))
            self.assertFalse(service.request("order", loader, callback))
            self.assertTrue(completed.wait(2.0))
            self.assertEqual(load_count, 1)
            self.assertEqual(callbacks, [({"ready": True}, None), ({"ready": True}, None)])
        finally:
            service.shutdown()

    def test_cache_retention_removes_only_expired_files(self) -> None:
        with workspace_temporary_directory(prefix="retention") as raw:
            root = Path(raw)
            old = root / "old.png"
            current = root / "current.png"
            old.write_bytes(b"old")
            current.write_bytes(b"current")
            stale = time.time() - 40 * 24 * 60 * 60
            os.utime(old, (stale, stale))
            report = shower_maintenance.prune_cache_directory(
                root,
                max_age_days=30,
                max_bytes=1024,
            )
            self.assertEqual(report.removed_files, 1)
            self.assertFalse(old.exists())
            self.assertTrue(current.exists())

    def test_send_journal_fallback_is_durable_jsonl(self) -> None:
        with workspace_temporary_directory(prefix="fallback-log") as raw:
            target = Path(raw) / "Diagnostics" / "send_journal_fallback.jsonl"
            shower_maintenance.append_fallback_event(
                target,
                stage="send-failed",
                error=RuntimeError("journal unavailable"),
                transaction_id="tx-123",
                details={"order": "700001"},
            )
            payload = json.loads(target.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["stage"], "send-failed")
            self.assertEqual(payload["transaction_id"], "tx-123")
            self.assertIn("journal unavailable", payload["error"])

    def test_deterministic_workspace_path_stays_short(self) -> None:
        with workspace_temporary_directory(prefix="shower-release-smoke") as raw:
            self.assertLess(len(str(Path(raw))), 150)

    def test_version_141_release_history_is_retained(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        feature_source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("## [Version 1.41]", changelog)
        self.assertIn("VERSION_1_41_PERFORMANCE_RELIABILITY_HARDENING", feature_source)


if __name__ == "__main__":
    unittest.main()
