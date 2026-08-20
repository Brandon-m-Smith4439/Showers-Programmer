"""Dimension-comparison primitives used by production PDF/DXF reconciliation."""

from __future__ import annotations


def dimensions_match(
    expected: tuple[float, float],
    actual: tuple[float, float],
    tolerance: float,
) -> bool:
    """Match dimensions in direct or rotated orientation within tolerance."""
    expected_width, expected_height = expected
    actual_width, actual_height = actual
    direct = (
        abs(expected_width - actual_width) <= tolerance
        and abs(expected_height - actual_height) <= tolerance
    )
    swapped = (
        abs(expected_width - actual_height) <= tolerance
        and abs(expected_height - actual_width) <= tolerance
    )
    return direct or swapped
