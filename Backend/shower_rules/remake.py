"""A+W Location-field REMAKE rules.

This module intentionally owns only Location-field extraction and the REMAK stem
policy.  It does not inspect arbitrary PDF notes, which prevents unrelated text
from silently changing production routing.
"""

from __future__ import annotations

import re
from typing import Any


LOCATION_FIELD_RE = re.compile(
    r"location\s*:\s*(.*?)"
    r"(?="
    r"\s*(?:marks?|project(?:\s*#)?|shape|quantity|glass|page|notes?|customer\s+notes?|printed\s+on|delivery\s+date|address|supplier)\s*:"
    r"|\s+measurements\s+are\s+in\s+inches"
    r"|\s+page\s+\d+\s+of\s+\d+"
    r"|$"
    r")",
    re.IGNORECASE,
)



def pdf_location_values(reader: Any) -> list[str]:
    """Return A+W Location values despite both common PDF extraction orders."""
    values: list[str] = []
    for page in reader.pages:
        raw_text = page.extract_text() or ""

        # Reverse extraction seen in production A+W PDFs:
        # ``MASTER LEFTLocation:`` / ``REMAKELocation:``.
        for label_match in re.finditer(r"location\s*:", raw_text, flags=re.IGNORECASE):
            start = label_match.start()
            if start <= 0 or raw_text[start - 1].isspace():
                continue
            line_start = max(raw_text.rfind("\n", 0, start), raw_text.rfind("\r", 0, start)) + 1
            prefix = raw_text[line_start:start].strip(" :-\t")
            if not prefix or ":" in prefix or len(prefix) > 80:
                continue
            value = re.sub(r"\s+", " ", prefix).strip(" :-")
            if value and value not in values:
                values.append(value)

        # Conventional label/value extraction, including multiline values after
        # whitespace normalization.  Joined reverse labels are skipped here.
        text = re.sub(r"\s+", " ", raw_text).strip()
        for match in LOCATION_FIELD_RE.finditer(text):
            if match.start() > 0 and not text[match.start() - 1].isspace():
                continue
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
            if value and value not in values:
                values.append(value)
    return values


def location_value_indicates_remake(value: str) -> bool:
    """Return True when the isolated Location value contains a REMAK* token."""
    normalized = re.sub(r"[^A-Z]+", " ", str(value).upper()).strip()
    if not normalized:
        return False
    return any(token.startswith("REMAK") for token in normalized.split())


def pdf_location_indicates_remake(reader: Any) -> bool:
    """Detect supported REMAKE forms only from the parsed Location field."""
    return any(location_value_indicates_remake(value) for value in pdf_location_values(reader))
