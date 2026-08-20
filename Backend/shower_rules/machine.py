"""Machine-routing primitives shared by batch processing and diagnostics."""

from __future__ import annotations

from typing import Any


def minimum_dimension_forces_waterjet(
    width: float | None,
    height: float | None,
    config: dict[str, Any],
) -> bool:
    """Return whether either finished edge is below Denver's configured minimum."""
    if width is None or height is None:
        return False
    rules = config.get("rules", {})
    if not isinstance(rules, dict):
        rules = {}
    try:
        denver_min = float(rules.get("denver_min_inches", 6.125))
    except (TypeError, ValueError):
        denver_min = 6.125
    return min(float(width), float(height)) < denver_min
