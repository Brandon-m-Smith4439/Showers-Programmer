#!/usr/bin/env python3
"""Structured operator-facing errors for Shower Programmer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ErrorCode:
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    MISSING_PROCESS_ORDER = "MISSING_PROCESS_ORDER"
    AMBIGUOUS_PDF = "AMBIGUOUS_PDF"
    PDF_NOT_FOUND = "PDF_NOT_FOUND"
    DXF_NOT_FOUND = "DXF_NOT_FOUND"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_IO = "NETWORK_IO"
    PROCESS_LIST_READ = "PROCESS_LIST_READ"
    FILE_LOCKED = "FILE_LOCKED"
    CANCELLED = "CANCELLED"
    INTERNAL = "INTERNAL"


@dataclass
class ShowerProgrammerError(RuntimeError):
    code: str
    message: str
    title: str = "Shower Programmer"
    aw_order: str = ""
    batch_key: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


def classify_exception(error: BaseException, *, title: str = "Shower Programmer") -> ShowerProgrammerError:
    if isinstance(error, ShowerProgrammerError):
        return error
    text = str(error).strip() or error.__class__.__name__
    lower = text.casefold()
    if "dimension" in lower and "match" in lower:
        code = ErrorCode.DIMENSION_MISMATCH
    elif "process list" in lower and ("no matching" in lower or "missing" in lower):
        code = ErrorCode.MISSING_PROCESS_ORDER
    elif "ambiguous" in lower and "pdf" in lower:
        code = ErrorCode.AMBIGUOUS_PDF
    elif isinstance(error, FileNotFoundError) and ".pdf" in lower:
        code = ErrorCode.PDF_NOT_FOUND
    elif isinstance(error, FileNotFoundError) and ".dxf" in lower:
        code = ErrorCode.DXF_NOT_FOUND
    elif "timed out" in lower or "timeout" in lower:
        code = ErrorCode.NETWORK_TIMEOUT
    elif isinstance(error, PermissionError) or "being used by another process" in lower or "locked" in lower:
        code = ErrorCode.FILE_LOCKED
    elif isinstance(error, OSError):
        code = ErrorCode.NETWORK_IO
    else:
        code = ErrorCode.INTERNAL
    return ShowerProgrammerError(code=code, message=text, title=title, details={"exception": error.__class__.__name__})
