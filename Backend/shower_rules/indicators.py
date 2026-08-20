"""Operator-facing indicator evidence helpers."""

from __future__ import annotations


def indicator_summary(machine: str, corner: object) -> str:
    normalized = str(machine or "").strip() or "Unassigned"
    value = str(corner or "").strip().replace("_", " ")
    return f"{normalized}: {value or 'no automatic indicator'}"
