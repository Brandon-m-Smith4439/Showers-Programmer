#!/usr/bin/env python3
"""Build and validate the clean Shower Programmer update-only ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

APP_EXE = "Shower Programmer.exe"
REQUIRED_DIRS = ("_internal", "Assets")
REQUIRED_FILES = (
    APP_EXE,
    "Assets/ShowersProgrammer.ico",
    "Assets/ShowersProgrammer.png",
    ".shower_update.json",
)
FORBIDDEN_TOP_LEVEL = {"Input", "Output", "Backend", "build", "release", "__pycache__"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def iter_package_files(app_dir: Path):
    for relative_name in (APP_EXE, ".shower_update.json"):
        path = app_dir / relative_name
        if path.is_file():
            yield path, relative_name
    for directory_name in REQUIRED_DIRS:
        directory = app_dir / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*"), key=lambda item: str(item).casefold()):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(app_dir).as_posix()
            if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo", ".part"}:
                continue
            yield path, relative


def validate_app_dir(app_dir: Path) -> None:
    for relative in REQUIRED_FILES:
        path = app_dir / Path(relative)
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Missing required update-package file: {path}")
    internal = app_dir / "_internal"
    if not internal.is_dir() or not any(internal.iterdir()):
        raise RuntimeError("The staged app is missing its _internal runtime folder.")
    if not any(path.name.casefold() == "pdfium.dll" for path in internal.rglob("pdfium.dll")):
        raise RuntimeError("The staged app is missing pdfium.dll.")


def build_zip(app_dir: Path, zip_path: Path) -> tuple[int, int]:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = zip_path.with_suffix(zip_path.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        for source, archive_name in iter_package_files(app_dir):
            top_level = archive_name.split("/", 1)[0]
            if top_level in FORBIDDEN_TOP_LEVEL:
                raise RuntimeError(f"Refusing to include runtime/user-data path in update ZIP: {archive_name}")
            archive.write(source, archive_name)
            file_count += 1
            total_bytes += source.stat().st_size
    os.replace(temporary, zip_path)
    return file_count, total_bytes


def validate_zip(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Update ZIP integrity test failed at: {bad}")
        names = [name.replace("\\", "/").strip("/") for name in archive.namelist() if name.strip("/")]
    name_set = set(names)
    for required in REQUIRED_FILES:
        if required not in name_set:
            raise RuntimeError(f"The clean update ZIP is missing: {required}")
    if not any(name.startswith("_internal/") and name.endswith("pdfium.dll") for name in names):
        raise RuntimeError("The clean update ZIP is missing pdfium.dll.")
    for name in names:
        top_level = name.split("/", 1)[0]
        if top_level in FORBIDDEN_TOP_LEVEL:
            raise RuntimeError(f"The clean update ZIP contains a forbidden path: {name}")
        if name.startswith("/") or ".." in Path(name).parts:
            raise RuntimeError(f"The clean update ZIP contains an unsafe path: {name}")
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--zip", required=True, dest="zip_path")
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", default="")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    zip_path = Path(args.zip_path).resolve()
    metadata_path = Path(args.metadata).resolve()
    validate_app_dir(app_dir)
    file_count, source_bytes = build_zip(app_dir, zip_path)
    names = validate_zip(zip_path)

    app_metadata = json.loads((app_dir / ".shower_update.json").read_text(encoding="utf-8"))
    metadata = {
        "version": args.version,
        "commit": str(args.commit or app_metadata.get("sha", "")).strip(),
        "zip_name": zip_path.name,
        "zip_path": "release/" + zip_path.name,
        "sha256": sha256_file(zip_path),
        "size": zip_path.stat().st_size,
        "source_size": source_bytes,
        "file_count": file_count,
        "validated_file_count": len(names),
        "exe_sha256": str(app_metadata.get("exe_sha256", "")).strip().lower(),
        "gui_sha256": str(app_metadata.get("gui_sha256", "")).strip().lower(),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Created clean update ZIP: {zip_path}")
    print(f"Files: {file_count}")
    print(f"ZIP size: {zip_path.stat().st_size}")
    print(f"SHA-256: {metadata['sha256']}")
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
