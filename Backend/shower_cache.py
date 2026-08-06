#!/usr/bin/env python3
"""Persistent file-derived cache shared by scan and review workflows."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any


CACHE_SCHEMA = 1
_CACHE_ROOT: Path | None = None
_LOCK = threading.RLock()
_STATS = {"hits": 0, "hash_hits": 0, "misses": 0, "writes": 0}


def configure(root: Path | None) -> None:
    global _CACHE_ROOT
    with _LOCK:
        _CACHE_ROOT = Path(root).resolve() if root is not None else None


def configured_root() -> Path | None:
    with _LOCK:
        return _CACHE_ROOT


def reset_stats() -> None:
    with _LOCK:
        for key in _STATS:
            _STATS[key] = 0


def stats() -> dict[str, int]:
    with _LOCK:
        return dict(_STATS)


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


def load(namespace: str, source: Path) -> Any | None:
    target = cache_path(namespace, source)
    if target is None or not target.exists() or not Path(source).exists():
        with _LOCK:
            _STATS["misses"] += 1
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        current = file_signature(source)
    except Exception:
        with _LOCK:
            _STATS["misses"] += 1
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
        return payload.get("value")

    # Timestamp-only changes are common when files are recopied. Verify the
    # content hash before paying the cost of reparsing a PDF, workbook, or DXF.
    try:
        current_hash = file_sha256(source)
    except Exception:
        current_hash = ""
    if current_hash and current_hash == str(stored.get("sha256", "")):
        payload["source"] = {**current, "sha256": current_hash}
        _write_payload(target, payload)
        with _LOCK:
            _STATS["hash_hits"] += 1
        return payload.get("value")
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
        _write_payload(target, payload)
        with _LOCK:
            _STATS["writes"] += 1
    except Exception:
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
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
