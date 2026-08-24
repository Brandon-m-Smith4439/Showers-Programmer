#!/usr/bin/env python3
"""Sanitized real-order regression corpus support used by release validation."""
from __future__ import annotations

import json
import math
from pathlib import Path

from shower_temp import workspace_temporary_directory
from typing import Any


def known_order_directory(project_root: Path) -> Path:
    return Path(project_root) / "tests" / "known_orders"


def load_known_order_cases(project_root: Path) -> list[dict[str, Any]]:
    root = known_order_directory(project_root)
    cases: list[dict[str, Any]] = []
    if not root.exists():
        return cases
    for path in sorted(root.glob("*.json")):
        if path.name == "manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload["_source"] = str(path)
            cases.append(payload)
    return cases


def _write_outline_dxf(path: Path, points: list[list[float]]) -> None:
    if len(points) < 3:
        raise ValueError("A known-order DXF outline needs at least three points")
    lines = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "1", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        lines.extend([
            "0", "LINE", "8", "0",
            "10", f"{float(start[0]):.10f}", "20", f"{float(start[1]):.10f}",
            "11", f"{float(end[0]):.10f}", "21", f"{float(end[1]):.10f}",
        ])
    lines.extend(["0", "ENDSEC", "0", "EOF", ""])
    path.write_text("\n".join(lines), encoding="ascii")


def validate_known_order_case(case: dict[str, Any], shower_batch: Any) -> dict[str, Any]:
    case_id = str(case.get("id", "unknown"))
    kind = str(case.get("kind", ""))
    if kind != "dxf_dimension_reconciliation":
        raise ValueError(f"Unsupported known-order regression kind {kind!r} for {case_id}")
    expected = tuple(float(value) for value in case["process_dimensions"])
    actual = tuple(float(value) for value in case["sketch_dimensions"])
    if len(expected) != 2 or len(actual) != 2:
        raise ValueError(f"Invalid dimensions in known-order case {case_id}")
    expected_normal_match = bool(case.get("normal_match", False))
    normal_match = shower_batch.dimensions_match(expected, actual)
    if normal_match != expected_normal_match:
        raise AssertionError(f"{case_id}: normal dimension match changed to {normal_match}")
    points = case.get("dxf_outline_points", [])
    if not isinstance(points, list):
        raise ValueError(f"{case_id}: dxf_outline_points must be a list")
    with workspace_temporary_directory(prefix="shower-known-order") as temp_dir:
        dxf_path = Path(temp_dir) / f"{case_id}.dxf"
        _write_outline_dxf(dxf_path, points)
        profile = shower_batch._dxf_oos_profile(dxf_path, expected, actual)
    if not isinstance(profile, dict):
        raise AssertionError(f"{case_id}: expected DXF reconciliation profile was not produced")
    expected_basis = str(case.get("expected_match_basis", ""))
    if expected_basis and str(profile.get("match_basis", "")) != expected_basis:
        raise AssertionError(
            f"{case_id}: expected match basis {expected_basis!r}, got {profile.get('match_basis')!r}"
        )
    expected_shift = case.get("expected_skew_shift")
    if expected_shift is not None and not math.isclose(
        float(profile.get("skew_shift", 0.0)), float(expected_shift), abs_tol=0.002
    ):
        raise AssertionError(
            f"{case_id}: expected skew shift {expected_shift}, got {profile.get('skew_shift')}"
        )
    return {
        "id": case_id,
        "kind": kind,
        "match_basis": str(profile.get("match_basis", "")),
        "skew_shift": float(profile.get("skew_shift", 0.0)),
    }


def run_known_order_library(project_root: Path, shower_batch: Any) -> list[dict[str, Any]]:
    cases = load_known_order_cases(project_root)
    if not cases:
        raise RuntimeError("Known-order regression library is empty")
    return [validate_known_order_case(case, shower_batch) for case in cases]
