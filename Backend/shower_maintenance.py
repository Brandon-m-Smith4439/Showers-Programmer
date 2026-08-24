#!/usr/bin/env python3
"""Small runtime maintenance services shared by the desktop workflows."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_FALLBACK_LOG_LOCK = threading.RLock()


def append_fallback_event(
    path: Path,
    *,
    stage: str,
    error: BaseException,
    transaction_id: str = "",
    details: dict[str, Any] | None = None,
) -> Path:
    """Persist a last-resort diagnostic without depending on the send journal."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "stage": str(stage),
        "transaction_id": str(transaction_id),
        "error": f"{error.__class__.__name__}: {error}",
        "details": dict(details or {}),
    }
    line = json.dumps(payload, sort_keys=True, default=str) + "\n"
    with _FALLBACK_LOG_LOCK:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return target


@dataclass
class CachePruneReport:
    removed_files: int = 0
    removed_bytes: int = 0
    warnings: list[str] = field(default_factory=list)


def prune_cache_directory(
    root: Path,
    *,
    max_age_days: int,
    max_bytes: int,
) -> CachePruneReport:
    report = CachePruneReport()
    cache_root = Path(root)
    if not cache_root.is_dir() or cache_root.is_symlink():
        return report
    now = datetime.now().timestamp()
    age_seconds = max(1, int(max_age_days)) * 24 * 60 * 60
    files: list[tuple[Path, float, int]] = []
    try:
        candidates = list(cache_root.rglob("*"))
    except OSError as exc:
        report.warnings.append(f"Could not inspect {cache_root}: {exc}")
        return report
    for path in candidates:
        try:
            if not path.is_file() or path.is_symlink():
                continue
            stat = path.stat()
            files.append((path, float(stat.st_mtime), int(stat.st_size)))
        except OSError as exc:
            report.warnings.append(f"Could not inspect {path}: {exc}")

    keep: list[tuple[Path, float, int]] = []
    for path, modified, size in files:
        if now - modified <= age_seconds:
            keep.append((path, modified, size))
            continue
        try:
            path.unlink()
            report.removed_files += 1
            report.removed_bytes += size
        except OSError as exc:
            keep.append((path, modified, size))
            report.warnings.append(f"Could not remove stale cache file {path}: {exc}")

    remaining_bytes = sum(size for _path, _modified, size in keep)
    for path, _modified, size in sorted(keep, key=lambda item: item[1]):
        if remaining_bytes <= max(0, int(max_bytes)):
            break
        try:
            path.unlink()
            remaining_bytes -= size
            report.removed_files += 1
            report.removed_bytes += size
        except OSError as exc:
            report.warnings.append(f"Could not trim cache file {path}: {exc}")

    for directory in sorted(
        (path for path in candidates if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            continue
    return report


class CacheMaintenanceService:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shower-maintenance")
        self._lock = threading.RLock()
        self._future: Future[dict[str, CachePruneReport]] | None = None

    @staticmethod
    def prune(output_dir: Path) -> dict[str, CachePruneReport]:
        output = Path(output_dir)
        return {
            "review": prune_cache_directory(
                output / ".review_preview_cache",
                max_age_days=30,
                max_bytes=512 * 1024 * 1024,
            ),
            "scan": prune_cache_directory(
                output / ".scan_cache",
                max_age_days=30,
                max_bytes=128 * 1024 * 1024,
            ),
        }

    def start(self, output_dir: Path) -> bool:
        with self._lock:
            if self._future is not None and not self._future.done():
                return False
            self._future = self._executor.submit(self.prune, Path(output_dir))
            return True

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

