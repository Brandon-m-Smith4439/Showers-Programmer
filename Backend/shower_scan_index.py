#!/usr/bin/env python3
"""Single-pass local input metadata index for order scanning and matching."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import shower_programmer as programmer


@dataclass(frozen=True)
class InputFileMetadata:
    path: Path
    suffix: str
    normalized_stem: str
    leading_job_number: str | None
    first_page_text: str
    extracted_job: str


class OrderInputIndex:
    """Extract each file's expensive metadata at most once during a scan."""

    def __init__(self, files: Iterable[Path] = ()) -> None:
        self._files = tuple(dict.fromkeys(Path(path) for path in files))
        self._metadata: dict[tuple[Path, bool], InputFileMetadata] = {}
        self._lock = threading.RLock()

    @property
    def files(self) -> tuple[Path, ...]:
        return self._files

    @staticmethod
    def leading_job_number(stem: str) -> str | None:
        job_number = programmer.extract_job_number(stem)
        if not job_number:
            return None
        match = re.match(rf"^\s*{re.escape(job_number)}(?=$|[ _-])", stem, flags=re.IGNORECASE)
        return job_number if match else None

    def metadata(self, path: Path, *, inspect_pdf_text: bool) -> InputFileMetadata:
        candidate = Path(path)
        wants_text = bool(inspect_pdf_text and candidate.suffix.casefold() == ".pdf")
        key = (candidate, wants_text)
        with self._lock:
            cached = self._metadata.get(key)
            if cached is not None:
                return cached

        text = ""
        extracted_job = ""
        if wants_text:
            try:
                text = programmer.extract_first_page_text(candidate)
            except Exception:
                text = ""
            try:
                extracted_job = programmer.extract_job_from_pdf(candidate)
            except Exception:
                extracted_job = ""
        metadata = InputFileMetadata(
            path=candidate,
            suffix=candidate.suffix.casefold(),
            normalized_stem=programmer.normalize_lookup(candidate.stem),
            leading_job_number=self.leading_job_number(candidate.stem),
            first_page_text=text,
            extracted_job=programmer.normalize_lookup(extracted_job),
        )
        with self._lock:
            self._metadata[key] = metadata
        return metadata

    @staticmethod
    def order_job_number(order: Any) -> str | None:
        return programmer.extract_job_number(getattr(order, "job_name", ""))

    def file_matches_order(self, path: Path, order: Any, *, inspect_pdf_text: bool) -> bool:
        metadata = self.metadata(path, inspect_pdf_text=inspect_pdf_text)
        aw_order = str(getattr(order, "aw_order", "") or "")
        job_number = self.order_job_number(order)
        if metadata.leading_job_number is not None:
            return metadata.leading_job_number == job_number
        if programmer.text_contains_aw_order(path.stem, aw_order):
            return True
        if job_number and programmer.text_contains_job_number(path.stem, job_number):
            return True
        if metadata.suffix == ".pdf" and inspect_pdf_text:
            if programmer.text_contains_aw_order(metadata.first_page_text, aw_order):
                return True
            if job_number and programmer.text_contains_job_number(metadata.first_page_text, job_number):
                return True

        normalized_job = programmer.normalize_lookup(getattr(order, "job_name", ""))
        if not normalized_job:
            return False
        if metadata.suffix == ".dxf":
            return any(
                programmer.dxf_match_score(
                    path,
                    normalized_job,
                    item,
                    aw_order=aw_order,
                    job_number=job_number,
                )
                is not None
                for item in getattr(order, "item_numbers", ())
            )
        if metadata.suffix != ".pdf":
            return False
        if normalized_job in metadata.normalized_stem:
            return True
        guessed_job = programmer.job_from_filename(path.name)
        if guessed_job:
            normalized_guess = programmer.normalize_lookup(guessed_job)
            if normalized_job in normalized_guess:
                return True
            if job_number and programmer.extract_job_number(guessed_job) == job_number:
                return True
        if inspect_pdf_text and metadata.extracted_job:
            if normalized_job in metadata.extracted_job:
                return True
            if job_number and programmer.extract_job_number(metadata.extracted_job) == job_number:
                return True
        return False

    def file_matches_orders(self, path: Path, orders: Iterable[Any], *, inspect_pdf_text: bool) -> bool:
        metadata = self.metadata(path, inspect_pdf_text=inspect_pdf_text)
        order_list = tuple(orders)
        if metadata.leading_job_number is not None:
            return any(metadata.leading_job_number == self.order_job_number(order) for order in order_list)
        return any(
            self.file_matches_order(path, order, inspect_pdf_text=inspect_pdf_text)
            for order in order_list
        )

    def order_has_pdf(self, order: Any, pdfs: Iterable[Path]) -> bool:
        candidates = tuple(pdfs)
        return any(self.file_matches_order(path, order, inspect_pdf_text=False) for path in candidates) or any(
            self.file_matches_order(path, order, inspect_pdf_text=True) for path in candidates
        )

