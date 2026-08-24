#!/usr/bin/env python3
"""Persistent file-derived cache shared by scan and review workflows."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any


CACHE_SCHEMA = 1
_CACHE_ROOT: Path | None = None
_THREAD_ROOT = threading.local()
_LOCK = threading.RLock()
_TARGET_LOCKS: dict[str, threading.RLock] = {}
_MEMORY: OrderedDict[tuple[str, str, str, int, int], Any] = OrderedDict()
_MEMORY_MAX_ENTRIES = 2048
_STATS = {"hits": 0, "memory_hits": 0, "hash_hits": 0, "misses": 0, "writes": 0, "errors": 0}
_LAST_ERROR = ""


def configure(root: Path | None) -> None:
    global _CACHE_ROOT
    with _LOCK:
        resolved = Path(root).resolve() if root is not None else None
        if resolved != _CACHE_ROOT:
            _MEMORY.clear()
            _TARGET_LOCKS.clear()
        _CACHE_ROOT = resolved
    _THREAD_ROOT.value = resolved


def configured_root() -> Path | None:
    if hasattr(_THREAD_ROOT, "value"):
        return _THREAD_ROOT.value
    with _LOCK:
        return _CACHE_ROOT


@contextmanager
def using_root(root: Path | None):
    """Bind cache I/O to one workflow root for the current worker thread."""
    sentinel = object()
    previous = getattr(_THREAD_ROOT, "value", sentinel)
    _THREAD_ROOT.value = Path(root).resolve() if root is not None else None
    try:
        yield
    finally:
        if previous is sentinel:
            try:
                delattr(_THREAD_ROOT, "value")
            except AttributeError:
                pass
        else:
            _THREAD_ROOT.value = previous


def reset_stats() -> None:
    global _LAST_ERROR
    with _LOCK:
        for key in _STATS:
            _STATS[key] = 0
        _LAST_ERROR = ""


def stats() -> dict[str, int]:
    with _LOCK:
        return dict(_STATS)


def last_error() -> str:
    with _LOCK:
        return _LAST_ERROR


def _record_error(error: BaseException) -> None:
    global _LAST_ERROR
    with _LOCK:
        _STATS["errors"] += 1
        _LAST_ERROR = f"{error.__class__.__name__}: {error}"


def file_signature(path: Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_path(namespace: str, source: Path) -> Path | None:
    root = configured_root()
    if root is None:
        return None
    source_key = hashlib.sha1(
        str(Path(source).resolve()).encode("utf-8", errors="ignore")
    ).hexdigest()
    safe_namespace = "".join(character if character.isalnum() or character in "_-" else "_" for character in namespace)
    return root / safe_namespace / f"{source_key}.json"


def _target_lock(target: Path) -> threading.RLock:
    key = str(target)
    with _LOCK:
        lock = _TARGET_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _TARGET_LOCKS[key] = lock
        return lock


def _memory_key(namespace: str, source: dict[str, Any], root: Path) -> tuple[str, str, str, int, int]:
    return (
        str(root),
        str(namespace),
        str(source["path"]),
        int(source["mtime_ns"]),
        int(source["size"]),
    )


def _remember(key: tuple[str, str, str, int, int], value: Any) -> None:
    with _LOCK:
        _MEMORY[key] = value
        _MEMORY.move_to_end(key)
        while len(_MEMORY) > _MEMORY_MAX_ENTRIES:
            _MEMORY.popitem(last=False)


def clear_memory() -> None:
    with _LOCK:
        _MEMORY.clear()


def load(namespace: str, source: Path) -> Any | None:
    target = cache_path(namespace, source)
    root = configured_root()
    if target is None or root is None or not Path(source).exists():
        with _LOCK:
            _STATS["misses"] += 1
        return None
    try:
        current = file_signature(source)
        memory_key = _memory_key(namespace, current, root)
    except Exception as exc:
        with _LOCK:
            _STATS["misses"] += 1
        _record_error(exc)
        return None
    with _LOCK:
        if memory_key in _MEMORY:
            value = _MEMORY[memory_key]
            _MEMORY.move_to_end(memory_key)
            _STATS["hits"] += 1
            _STATS["memory_hits"] += 1
            return value
    lock = _target_lock(target)
    try:
        with lock:
            if not target.exists():
                with _LOCK:
                    _STATS["misses"] += 1
                return None
            payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        with _LOCK:
            _STATS["misses"] += 1
        _record_error(exc)
        return None
    if not isinstance(payload, dict) or payload.get("schema") != CACHE_SCHEMA:
        with _LOCK:
            _STATS["misses"] += 1
        return None
    stored = payload.get("source", {})
    if not isinstance(stored, dict) or str(stored.get("path", "")) != current["path"]:
        with _LOCK:
            _STATS["misses"] += 1
        return None
    if (
        int(stored.get("mtime_ns", -1)) == current["mtime_ns"]
        and int(stored.get("size", -1)) == current["size"]
    ):
        with _LOCK:
            _STATS["hits"] += 1
        value = payload.get("value")
        _remember(memory_key, value)
        return value

    # Timestamp-only changes are common when files are recopied. Verify the
    # content hash before paying the cost of reparsing a PDF, workbook, or DXF.
    try:
        current_hash = file_sha256(source)
    except Exception:
        current_hash = ""
    if current_hash and current_hash == str(stored.get("sha256", "")):
        payload["source"] = {**current, "sha256": current_hash}
        try:
            with lock:
                _write_payload(target, payload)
        except Exception as exc:
            _record_error(exc)
        with _LOCK:
            _STATS["hash_hits"] += 1
        value = payload.get("value")
        _remember(memory_key, value)
        return value
    with _LOCK:
        _STATS["misses"] += 1
    return None


def store(
    namespace: str,
    source: Path,
    value: Any,
    *,
    source_sha256: str | None = None,
) -> None:
    target = cache_path(namespace, source)
    if target is None or not Path(source).exists():
        return
    try:
        source_data = file_signature(source)
        source_data["sha256"] = source_sha256 or file_sha256(source)
        payload = {
            "schema": CACHE_SCHEMA,
            "source": source_data,
            "value": value,
        }
        with _target_lock(target):
            _write_payload(target, payload)
        root = configured_root()
        if root is not None:
            _remember(_memory_key(namespace, source_data, root), value)
        with _LOCK:
            _STATS["writes"] += 1
    except Exception as exc:
        _record_error(exc)
        return


def cached_file_sha256(namespace: str, source: Path) -> str:
    """Return an exact content hash without rereading an unchanged file."""
    cached = load(namespace, source)
    if isinstance(cached, str) and cached:
        return cached
    digest = file_sha256(source)
    store(namespace, source, digest, source_sha256=digest)
    return digest


def _write_payload(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"cache-{os.getpid()}-{threading.get_ident()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        last_error: PermissionError | None = None
        for attempt in range(8):
            try:
                os.replace(temporary, target)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.01 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
