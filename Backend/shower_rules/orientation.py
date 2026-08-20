"""Simple machine-orientation policy independent of UI and file I/O."""

from __future__ import annotations


def default_machine_rotation(machine: str, width: float | None, height: float | None) -> float | None:
    """Return the established long-glass default before geometry-specific correction."""
    normalized = str(machine or "").upper()
    if width is None or height is None:
        return None
    long_vertical = float(height) > float(width)
    if normalized == "WJ":
        return -90.0 if long_vertical else 0.0
    if normalized.startswith("DENVER"):
        return 90.0 if long_vertical else 0.0
    return None
