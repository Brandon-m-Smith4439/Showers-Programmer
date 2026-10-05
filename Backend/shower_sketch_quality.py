"""Local, cached paper-size checks; never infer glass dimensions from paper size."""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

import shower_cache
import shower_programmer as programmer


@dataclass(frozen=True)
class SketchPaper:
    sizes: tuple[tuple[float, float], ...] = ()
    label_pages: tuple[int, ...] = ()
    error: str = ""

    @property
    def warning(self) -> str:
        if not self.label_pages:
            return ""
        pages = ", ".join(
            f"{number} ({self.sizes[number - 1][0]:g} x {self.sizes[number - 1][1]:g} in)"
            for number in self.label_pages[:3]
        )
        extra = f", +{len(self.label_pages) - 3} more" if len(self.label_pages) > 3 else ""
        return f"Sketch paper size: label-sized page(s) {pages}{extra}. Reprint as Letter/Legal/A4."


def inspect_sketch(path: Path) -> SketchPaper:
    """Letter, Legal, A4 and larger pages pass regardless of orientation."""
    try:
        cached = shower_cache.load("sketch_paper_v1", path)
        if isinstance(cached, dict):
            return SketchPaper(tuple(tuple(size) for size in cached["sizes"]), tuple(cached["label_pages"]))
        sizes = []
        reader = PdfReader(path)
        if reader.is_encrypted or not reader.pages:
            raise ValueError("Sketch pages cannot be inspected")
        for page in reader.pages:
            unit = float(page.get("/UserUnit", 1))
            box = page.cropbox
            width, height = abs(float(box.width)) * unit / 72, abs(float(box.height)) * unit / 72
            if any(not math.isfinite(value) or value <= 0 for value in (width, height, unit)):
                raise ValueError("Invalid PDF paper dimensions")
            sizes.append((round(width, 4), round(height, 4)))
        labels = tuple(i + 1 for i, size in enumerate(sizes) if min(size) < 7 or max(size) < 10)
        result = SketchPaper(tuple(sizes), labels)
        shower_cache.store("sketch_paper_v1", path, {"sizes": sizes, "label_pages": labels})
        return result
    except Exception as exc:
        # An unreadable PDF remains available for the existing source-review workflow.
        return SketchPaper(error=str(exc))


def _content_identity(path: Path) -> str:
    cached = shower_cache.load("sketch_content_identity_v1", path)
    if isinstance(cached, str):
        return cached
    try:
        reader = PdfReader(path)
        if reader.is_encrypted or any(page.get("/Annots") for page in reader.pages):
            return ""
        text = " ".join((page.extract_text() or "") for page in reader.pages)
        normalized = re.sub(r"\s+", " ", text).strip()
        # Blank/image-only/clipped sketches are insufficient evidence to remove a file.
        if len(normalized) < 30 or not re.search(r"\d", normalized):
            return ""
        identity = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        shower_cache.store("sketch_content_identity_v1", path, identity)
        return identity
    except Exception:
        return ""


def replacement_pairs(paths: list[Path]) -> list[tuple[Path, Path]]:
    """Return bad/good pairs only with exact job revision AND identical sketch text.

    Explicit A&W filename identities must also agree. No deletion by Job Nr alone,
    mtime, PDF dimensions, glass dimensions, or a guessed processing-list assignment.
    """
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        if path.suffix.casefold() != ".pdf" or path.is_symlink():
            continue
        job = programmer.extract_job_number(path.stem)
        if job:
            groups[job.casefold()].append(path)
    pairs = []
    for group in groups.values():
        papers = {path: inspect_sketch(path) for path in group}
        normal = [path for path, paper in papers.items() if paper.sizes and not paper.label_pages and not paper.error]
        for bad, paper in papers.items():
            if not paper.label_pages:
                continue
            signature = _content_identity(bad)
            if not signature:
                continue
            aw_ids = set(re.findall(r"(?<![\d.])\d{5,6}(?![\d.])", bad.stem))
            matches = [good for good in normal
                       if set(re.findall(r"(?<![\d.])\d{5,6}(?![\d.])", good.stem)) == aw_ids
                       and programmer.filenames_look_like_import_copies(
                           Path(re.sub(r"^Glass\s+Order\s*-\s*", "Glass Order ", bad.name, flags=re.I)),
                           Path(re.sub(r"^Glass\s+Order\s*-\s*", "Glass Order ", good.name, flags=re.I)),
                       )
                       and _content_identity(good) == signature]
            if len(matches) == 1:
                pairs.append((bad, matches[0]))
    return pairs


def paper_warnings(paths: list[Path]) -> dict[Path, str]:
    return {path: paper.warning for path in paths if path.suffix.casefold() == ".pdf"
            and (paper := inspect_sketch(path)).warning}
