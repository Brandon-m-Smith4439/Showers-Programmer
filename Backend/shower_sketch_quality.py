"""Local, cached paper-size checks; never infer glass dimensions from paper size."""
from __future__ import annotations

import hashlib
import json
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
    cached = shower_cache.load("sketch_content_identity_v2", path)
    if isinstance(cached, str):
        return cached
    try:
        reader = PdfReader(path)
        if reader.is_encrypted or any(page.get("/Annots") for page in reader.pages):
            return ""
        # Printer scaling changes extraction spaces between adjacent measurements.
        # Preserve page boundaries and every non-whitespace character.
        normalized = "\f".join(re.sub(r"\s+", "", page.extract_text() or "") for page in reader.pages)
        # Blank/image-only/clipped sketches are insufficient evidence to remove a file.
        if len(normalized) < 30 or not re.search(r"\d", normalized):
            return ""
        identity = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        shower_cache.store("sketch_content_identity_v2", path, identity)
        return identity
    except Exception:
        return ""


def _reprint_text(reader: PdfReader) -> str:
    texts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\s*Printed\s+On\s*:", "Printed On:", text, flags=re.I)
        text = re.sub(r"Page\s+\d+\s+of\s+\d+\s*BFS Operations LLC\s*$", "", text, flags=re.I)
        texts.append(re.sub(r"\s+", "", text))
    return "".join(texts)


def _reprint_text_identity(path: Path) -> str:
    cached = shower_cache.load("sketch_reprint_text_v1", path)
    if isinstance(cached, str):
        return cached
    try:
        reader = PdfReader(path)
        if reader.is_encrypted or any(page.get("/Annots") for page in reader.pages):
            return ""
        text = _reprint_text(reader)
        if ("GLASSORDER" not in text.upper() or "ProjectName:" not in text
                or "Marks:" not in text or not re.search(r"\b(?:P\d+|TRN\d+)\b", " ".join(page.extract_text() or "" for page in reader.pages))):
            return ""
        identity = hashlib.sha256(text.encode()).hexdigest()
        shower_cache.store("sketch_reprint_text_v1", path, identity)
        return identity
    except Exception:
        return ""


def _same_reprint_filename(left: Path, right: Path) -> bool:
    return (programmer.extract_job_number(left.stem) == programmer.extract_job_number(right.stem)
            and set(re.findall(r"(?<![\d.])\d{5,6}(?![\d.])", left.stem))
            == set(re.findall(r"(?<![\d.])\d{5,6}(?![\d.])", right.stem))
            and programmer.filenames_look_like_import_copies(
                Path(re.sub(r"^Glass\s+Order\s*-\s*", "Glass Order ", left.name, flags=re.I)),
                Path(re.sub(r"^Glass\s+Order\s*-\s*", "Glass Order ", right.name, flags=re.I)),
            ))


def preferred_reprint_path(paths: list[Path]) -> Path | None:
    """Prefer full-size identical order text; keep clipped drawings for verification.

    Callers must still enforce duplicate-order authorization and process-list
    matching. This is selection evidence, not permission to remove a PDF.
    """
    if len(paths) < 2 or any(path.is_symlink() for path in paths):
        return None
    papers = {path: inspect_sketch(path) for path in paths}
    normal = [path for path, paper in papers.items() if paper.sizes and not paper.label_pages and not paper.error]
    if len(normal) != 1:
        return None
    good = normal[0]
    signature = _reprint_text_identity(good)
    if not signature:
        return None
    return good if all(path == good or (papers[path].label_pages and _same_reprint_filename(path, good)
                                        and _reprint_text_identity(path) == signature) for path in paths) else None


def _reprint_identity(path: Path) -> str:
    """Recognize printer repagination only with unchanged text and vector drawings."""
    cached = shower_cache.load("sketch_reprint_identity_v1", path)
    if isinstance(cached, str):
        return cached
    try:
        reader = PdfReader(path)
        if reader.is_encrypted or any(page.get("/Annots") for page in reader.pages):
            return ""
        drawings = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if "Marks:" not in text or not re.search(r"\b(?:P\d+|TRN\d+)\b", text, re.I):
                continue
            paths = []
            for operands, op, matrix in programmer.content_operations_with_matrices(reader, index):
                count = {"m": 2, "l": 2, "c": 6, "v": 4, "y": 4}.get(op, 0)
                if count and len(operands) >= count:
                    points = [programmer.transform_pdf_point(matrix, float(operands[i]), float(operands[i + 1]))
                              for i in range(0, count, 2)]
                    paths.append((op, points))
                elif op == "re" and len(operands) >= 4:
                    x, y, w, h = map(float, operands[:4])
                    paths.append((op, [programmer.transform_pdf_point(matrix, px, py)
                                       for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))]))
                elif op == "h":
                    paths.append((op, []))
            points = [point for _op, values in paths for point in values]
            if not points:
                return ""
            left = min(x for x, _y in points)
            bottom = min(y for _x, y in points)
            span = max(max(x for x, _y in points) - left, max(y for _x, y in points) - bottom)
            if not math.isfinite(span) or span <= 0:
                return ""
            drawings.append([(op, [(round((x - left) / span, 5), round((y - bottom) / span, 5))
                                    for x, y in values]) for op, values in paths])
        text = _reprint_text(reader)
        if not drawings or "GLASSORDER" not in text.upper() or "ProjectName:" not in text:
            return ""
        signature = hashlib.sha256(json.dumps([text, drawings], separators=(",", ":")).encode()).hexdigest()
        shower_cache.store("sketch_reprint_identity_v1", path, signature)
        return signature
    except Exception:
        return ""


def replacement_pairs(paths: list[Path]) -> list[tuple[Path, Path]]:
    """Return bad/good pairs only with exact identity and verified sketch contents.

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
            reprint_signature = None

            def same_contents(good: Path) -> bool:
                nonlocal reprint_signature
                if _content_identity(good) == signature:
                    return True
                if reprint_signature is None:
                    reprint_signature = _reprint_identity(bad)
                return bool(reprint_signature and _reprint_identity(good) == reprint_signature)

            aw_ids = set(re.findall(r"(?<![\d.])\d{5,6}(?![\d.])", bad.stem))
            matches = [good for good in normal
                       if set(re.findall(r"(?<![\d.])\d{5,6}(?![\d.])", good.stem)) == aw_ids
                       and programmer.filenames_look_like_import_copies(
                           Path(re.sub(r"^Glass\s+Order\s*-\s*", "Glass Order ", bad.name, flags=re.I)),
                           Path(re.sub(r"^Glass\s+Order\s*-\s*", "Glass Order ", good.name, flags=re.I)),
                       )
                       and same_contents(good)]
            if len(matches) == 1:
                pairs.append((bad, matches[0]))
    return pairs


def paper_warnings(paths: list[Path]) -> dict[Path, str]:
    return {path: paper.warning for path in paths if path.suffix.casefold() == ".pdf"
            and (paper := inspect_sketch(path)).warning}
