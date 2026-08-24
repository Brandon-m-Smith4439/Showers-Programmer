#!/usr/bin/env python3
"""Deterministic temporary workspaces for tests and packaged self-validation."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def default_workspace_root() -> Path:
    configured = str(os.environ.get("SHOWER_TEST_TEMP_ROOT", "")).strip()
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[1] / "tmp" / "_tests"


@contextmanager
def workspace_temporary_directory(
    *,
    prefix: str = "shower-test-",
    root: Path | None = None,
) -> Iterator[str]:
    safe_prefix = (re.sub(r"[^A-Za-z0-9_.-]+", "-", str(prefix)).strip("-.") or "shower-test")[:24]
    base = Path(root).resolve() if root is not None else default_workspace_root()
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{safe_prefix}-{uuid.uuid4().hex[:10]}"
    path.mkdir(parents=False, exist_ok=False)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)
