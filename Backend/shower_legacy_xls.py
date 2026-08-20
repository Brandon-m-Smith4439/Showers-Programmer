#!/usr/bin/env python3
"""Small dependency-free reader for the BIFF8 subset used by legacy process lists.

This is intentionally not a general Excel implementation. It reads the first
worksheet from a normal Excel 97-2003 OLE/BIFF workbook and returns cell values
as row lists. Unsupported/encrypted workbooks raise LegacyXlsError so callers
can fall back to Excel COM conversion.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Iterable

CFB_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC


class LegacyXlsError(RuntimeError):
    pass


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


class CompoundFile:
    def __init__(self, data: bytes) -> None:
        if len(data) < 512 or data[:8] != CFB_SIGNATURE:
            raise LegacyXlsError("Not an OLE Compound File workbook")
        self.data = data
        self.major_version = _u16(data, 26)
        self.sector_size = 1 << _u16(data, 30)
        self.mini_sector_size = 1 << _u16(data, 32)
        if self.sector_size not in (512, 4096):
            raise LegacyXlsError(f"Unsupported OLE sector size {self.sector_size}")
        self.first_dir_sector = _u32(data, 48)
        self.mini_stream_cutoff = _u32(data, 56)
        self.first_mini_fat_sector = _u32(data, 60)
        self.num_mini_fat_sectors = _u32(data, 64)
        self.first_difat_sector = _u32(data, 68)
        self.num_difat_sectors = _u32(data, 72)
        self.fat_sector_ids = [value for value in struct.unpack_from("<109I", data, 76) if value < DIFSECT]
        self._read_extended_difat()
        self.fat = self._read_fat()
        self.directory_entries = self._read_directory()
        self.root = next((entry for entry in self.directory_entries if entry[1] == 5), None)
        if self.root is None:
            raise LegacyXlsError("OLE workbook is missing the root storage")
        self.mini_fat = self._read_mini_fat()
        self.mini_stream = self._read_chain(self.root[2], self.root[3]) if self.root[2] < DIFSECT else b""

    def _sector(self, sector_id: int) -> bytes:
        if sector_id >= DIFSECT:
            raise LegacyXlsError("Invalid OLE sector chain")
        start = (sector_id + 1) * self.sector_size
        end = start + self.sector_size
        if end > len(self.data):
            raise LegacyXlsError("OLE sector points beyond end of file")
        return self.data[start:end]

    def _read_extended_difat(self) -> None:
        sector_id = self.first_difat_sector
        entries_per_sector = self.sector_size // 4 - 1
        for _ in range(self.num_difat_sectors):
            if sector_id >= DIFSECT:
                break
            raw = self._sector(sector_id)
            values = struct.unpack_from(f"<{entries_per_sector + 1}I", raw, 0)
            self.fat_sector_ids.extend(value for value in values[:-1] if value < DIFSECT)
            sector_id = values[-1]

    def _read_fat(self) -> list[int]:
        values: list[int] = []
        for sector_id in self.fat_sector_ids:
            raw = self._sector(sector_id)
            values.extend(struct.unpack_from(f"<{self.sector_size // 4}I", raw, 0))
        if not values:
            raise LegacyXlsError("OLE workbook has no FAT")
        return values

    def _chain_ids(self, start_sector: int, table: list[int], limit: int = 100000) -> list[int]:
        ids: list[int] = []
        current = start_sector
        seen: set[int] = set()
        while current < DIFSECT:
            if current in seen or current >= len(table) or len(ids) >= limit:
                raise LegacyXlsError("Corrupt OLE sector chain")
            seen.add(current)
            ids.append(current)
            current = table[current]
        if current not in (ENDOFCHAIN, FREESECT):
            raise LegacyXlsError("Unsupported OLE chain terminator")
        return ids

    def _read_chain(self, start_sector: int, size: int | None = None) -> bytes:
        raw = b"".join(self._sector(sector_id) for sector_id in self._chain_ids(start_sector, self.fat))
        return raw[:size] if size is not None else raw

    def _read_directory(self) -> list[tuple[str, int, int, int]]:
        raw = self._read_chain(self.first_dir_sector)
        entries: list[tuple[str, int, int, int]] = []
        for offset in range(0, len(raw) - 127, 128):
            entry = raw[offset : offset + 128]
            name_length = _u16(entry, 64)
            object_type = entry[66]
            if object_type == 0 or name_length < 2:
                continue
            name = entry[: max(0, name_length - 2)].decode("utf-16le", errors="replace")
            start_sector = _u32(entry, 116)
            size = _u64(entry, 120)
            if self.major_version == 3:
                size &= 0xFFFFFFFF
            entries.append((name, object_type, start_sector, int(size)))
        return entries

    def _read_mini_fat(self) -> list[int]:
        if self.num_mini_fat_sectors <= 0 or self.first_mini_fat_sector >= DIFSECT:
            return []
        raw = self._read_chain(self.first_mini_fat_sector, self.num_mini_fat_sectors * self.sector_size)
        return list(struct.unpack_from(f"<{len(raw) // 4}I", raw, 0)) if raw else []

    def stream(self, name: str) -> bytes:
        entry = next((entry for entry in self.directory_entries if entry[0].casefold() == name.casefold()), None)
        if entry is None:
            raise LegacyXlsError(f"OLE stream {name!r} was not found")
        _, object_type, start_sector, size = entry
        if object_type != 2:
            raise LegacyXlsError(f"OLE entry {name!r} is not a stream")
        if size < self.mini_stream_cutoff and self.mini_fat and self.mini_stream:
            pieces: list[bytes] = []
            for mini_id in self._chain_ids(start_sector, self.mini_fat):
                start = mini_id * self.mini_sector_size
                pieces.append(self.mini_stream[start : start + self.mini_sector_size])
            return b"".join(pieces)[:size]
        return self._read_chain(start_sector, size)


class _SstReader:
    def __init__(self, segments: list[bytes]) -> None:
        self.segments = segments
        self.segment_index = 0
        self.offset = 0

    def _advance(self) -> None:
        self.segment_index += 1
        self.offset = 0
        if self.segment_index >= len(self.segments):
            raise LegacyXlsError("Unexpected end of shared-string table")

    def read(self, count: int) -> bytes:
        out = bytearray()
        while len(out) < count:
            if self.segment_index >= len(self.segments):
                raise LegacyXlsError("Unexpected end of shared-string table")
            segment = self.segments[self.segment_index]
            available = len(segment) - self.offset
            if available <= 0:
                self._advance()
                continue
            take = min(count - len(out), available)
            out.extend(segment[self.offset : self.offset + take])
            self.offset += take
        return bytes(out)

    def read_u8(self) -> int:
        return self.read(1)[0]

    def read_u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def read_u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def read_string_chars(self, count: int, high_byte: bool) -> str:
        chunks: list[str] = []
        remaining = count
        encoding_high = high_byte
        while remaining > 0:
            if self.segment_index >= len(self.segments):
                raise LegacyXlsError("Unexpected end of shared string")
            segment = self.segments[self.segment_index]
            bytes_per_char = 2 if encoding_high else 1
            available_bytes = len(segment) - self.offset
            available_chars = available_bytes // bytes_per_char
            if available_chars <= 0:
                self._advance()
                # BIFF8 CONTINUE records include a one-byte compression option
                # when the character array of an XLUnicodeRichExtendedString
                # crosses the record boundary.
                option = self.read_u8()
                encoding_high = bool(option & 0x01)
                continue
            take_chars = min(remaining, available_chars)
            raw = self.read(take_chars * bytes_per_char)
            chunks.append(raw.decode("utf-16le" if encoding_high else "latin-1", errors="replace"))
            remaining -= take_chars
            if remaining and self.offset >= len(self.segments[self.segment_index]):
                self._advance()
                option = self.read_u8()
                encoding_high = bool(option & 0x01)
        return "".join(chunks)


def _records(data: bytes, start: int = 0) -> Iterable[tuple[int, bytes, int]]:
    offset = start
    while offset + 4 <= len(data):
        record_id, size = struct.unpack_from("<HH", data, offset)
        payload_start = offset + 4
        payload_end = payload_start + size
        if payload_end > len(data):
            break
        yield record_id, data[payload_start:payload_end], offset
        offset = payload_end


def _parse_sst(workbook: bytes) -> list[str]:
    segments: list[bytes] = []
    collecting = False
    for record_id, payload, _ in _records(workbook):
        if record_id == 0x00FC:  # SST
            segments = [payload]
            collecting = True
            continue
        if collecting and record_id == 0x003C:  # CONTINUE
            segments.append(payload)
            continue
        if collecting:
            break
    if not segments:
        return []
    reader = _SstReader(segments)
    _total = reader.read_u32()
    unique = reader.read_u32()
    strings: list[str] = []
    for _ in range(unique):
        char_count = reader.read_u16()
        flags = reader.read_u8()
        rich_count = reader.read_u16() if flags & 0x08 else 0
        ext_size = reader.read_u32() if flags & 0x04 else 0
        value = reader.read_string_chars(char_count, bool(flags & 0x01))
        if rich_count:
            reader.read(rich_count * 4)
        if ext_size:
            reader.read(ext_size)
        strings.append(value)
    return strings


def _rk_value(raw: int) -> float | int:
    divide_100 = bool(raw & 0x01)
    if raw & 0x02:
        value = raw >> 2
        if value & 0x20000000:
            value -= 0x40000000
        result: float | int = value
    else:
        packed = struct.pack("<Q", (raw & 0xFFFFFFFC) << 32)
        result = struct.unpack("<d", packed)[0]
    if divide_100:
        result = result / 100.0
    if isinstance(result, float) and math.isfinite(result) and result.is_integer():
        return int(result)
    return result


def _bound_sheet_offsets(workbook: bytes) -> list[int]:
    offsets: list[int] = []
    for record_id, payload, _ in _records(workbook):
        if record_id != 0x0085 or len(payload) < 8:
            continue
        if payload[5] != 0x00:  # worksheet only
            continue
        offsets.append(_u32(payload, 0))
    return offsets


def _first_worksheet_rows(workbook: bytes, shared_strings: list[str]) -> list[list[object]]:
    offsets = _bound_sheet_offsets(workbook)
    if not offsets:
        raise LegacyXlsError("BIFF workbook contains no worksheet")
    start = offsets[0]
    cells: dict[tuple[int, int], object] = {}
    max_row = -1
    max_col = -1
    pending_formula_string: tuple[int, int] | None = None
    for record_id, payload, _ in _records(workbook, start):
        if record_id == 0x000A:  # EOF
            break
        if record_id == 0x00FD and len(payload) >= 10:  # LABELSST
            row, col = struct.unpack_from("<HH", payload, 0)
            index = _u32(payload, 6)
            value = shared_strings[index] if 0 <= index < len(shared_strings) else ""
        elif record_id == 0x0204 and len(payload) >= 8:  # LABEL
            row, col = struct.unpack_from("<HH", payload, 0)
            length = _u16(payload, 6)
            raw = payload[8 : 8 + length]
            value = raw.decode("latin-1", errors="replace")
        elif record_id == 0x0203 and len(payload) >= 14:  # NUMBER
            row, col = struct.unpack_from("<HH", payload, 0)
            value = struct.unpack_from("<d", payload, 6)[0]
            if math.isfinite(value) and value.is_integer():
                value = int(value)
        elif record_id == 0x027E and len(payload) >= 10:  # RK
            row, col = struct.unpack_from("<HH", payload, 0)
            value = _rk_value(_u32(payload, 6))
        elif record_id == 0x00BD and len(payload) >= 6:  # MULRK
            row, first_col = struct.unpack_from("<HH", payload, 0)
            last_col = _u16(payload, len(payload) - 2)
            count = max(0, last_col - first_col + 1)
            for index in range(count):
                item_offset = 4 + index * 6
                if item_offset + 6 > len(payload) - 2:
                    break
                col = first_col + index
                value = _rk_value(_u32(payload, item_offset + 2))
                cells[(row, col)] = value
                max_row = max(max_row, row)
                max_col = max(max_col, col)
            continue
        elif record_id == 0x0006 and len(payload) >= 14:  # FORMULA
            row, col = struct.unpack_from("<HH", payload, 0)
            result = payload[6:14]
            if result[6:8] == b"\xff\xff" and result[0] == 0x00:
                pending_formula_string = (row, col)
                continue
            value = struct.unpack("<d", result)[0]
            if math.isfinite(value) and value.is_integer():
                value = int(value)
        elif record_id == 0x0207 and pending_formula_string is not None:  # STRING
            row, col = pending_formula_string
            pending_formula_string = None
            if len(payload) < 3:
                continue
            count = _u16(payload, 0)
            flags = payload[2]
            raw = payload[3 : 3 + count * (2 if flags & 1 else 1)]
            value = raw.decode("utf-16le" if flags & 1 else "latin-1", errors="replace")
        elif record_id == 0x0201 and len(payload) >= 6:  # BLANK
            continue
        else:
            continue
        cells[(row, col)] = value
        max_row = max(max_row, row)
        max_col = max(max_col, col)
    if max_row < 0:
        return []
    rows: list[list[object]] = []
    for row in range(max_row + 1):
        values = [cells.get((row, col), "") for col in range(max_col + 1)]
        if any(value not in (None, "") for value in values):
            rows.append(values)
    return rows


def load_rows(path: Path) -> list[list[object]]:
    data = Path(path).read_bytes()
    compound = CompoundFile(data)
    try:
        workbook = compound.stream("Workbook")
    except LegacyXlsError:
        workbook = compound.stream("Book")
    # BIFF FILEPASS means encrypted/protected workbook; do not attempt to parse it.
    if any(record_id == 0x002F for record_id, _, _ in _records(workbook)):
        raise LegacyXlsError("Encrypted BIFF workbooks require the Excel fallback")
    shared_strings = _parse_sst(workbook)
    return _first_worksheet_rows(workbook, shared_strings)


def can_read(path: Path) -> bool:
    try:
        if Path(path).read_bytes()[:8] != CFB_SIGNATURE:
            return False
        rows = load_rows(path)
        return bool(rows)
    except (OSError, LegacyXlsError, struct.error, UnicodeError):
        return False
