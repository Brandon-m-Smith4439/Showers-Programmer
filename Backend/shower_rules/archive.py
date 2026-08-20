"""Archive-reconciliation primitives."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def ordered_unique_paths(paths: Iterable[object]) -> list[Path]:
    """Preserve newest-first archive order while removing duplicate directories."""
    result: list[Path] = []
    seen: set[str] = set()
    for value in paths:
        if not isinstance(value, Path):
            continue
        try:
            key = os.path.normcase(os.path.abspath(str(value)))
        except OSError:
            key = os.path.normcase(str(value))
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
