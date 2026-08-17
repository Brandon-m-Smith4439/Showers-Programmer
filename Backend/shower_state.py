#!/usr/bin/env python3
"""SQLite-backed operational state for Shower Programmer.

The desktop application historically inferred state from a mix of JSON receipts,
folder contents, and in-memory batches.  This module gives the production workflow
one durable place for order lifecycle, batch identity, archive indexing,
performance timings, and structured error history while preserving the existing
JSON files for backward compatibility.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1
DATABASE_NAME = "shower_programmer.sqlite3"


class LifecycleState:
    DISCOVERED = "DISCOVERED"
    ACTIVE = "ACTIVE"
    READY = "READY"
    ISSUES = "ISSUES"
    PROCESSED = "PROCESSED"
    SENT = "SENT"
    DELETED_LOCAL = "DELETED_LOCAL"
    ARCHIVED = "ARCHIVED"
    TESTING = "TESTING"
    REACTIVATED = "REACTIVATED"
    ORPHANED_INPUT = "ORPHANED_INPUT"

    ALL = {
        DISCOVERED,
        ACTIVE,
        READY,
        ISSUES,
        PROCESSED,
        SENT,
        DELETED_LOCAL,
        ARCHIVED,
        TESTING,
        REACTIVATED,
        ORPHANED_INPUT,
    }


@dataclass(frozen=True)
class BatchIdentity:
    key: str
    normalized_name: str
    content_hash: str
    file_size: int


@dataclass(frozen=True)
class ArchiveRecord:
    archive_name: str
    archive_date: str
    batch_key: str
    batch_name: str
    aw_order: str
    job_name: str
    customer: str
    process_list_path: str
    order_archive_dir: str
    order_files: tuple[str, ...]
    sent_at: str = ""
    order_json: str = "{}"


@dataclass(frozen=True)
class PerformanceSample:
    operation: str
    stage: str
    elapsed_ms: float
    metadata: dict[str, Any]


class StateStore:
    """Thread-safe SQLite facade with short-lived connections.

    Short-lived connections avoid sharing sqlite connection objects across Tk and
    worker threads.  WAL mode allows archive indexing and UI reads to coexist.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.RLock()
        self.initialize()

    @classmethod
    def for_output(cls, output_dir: Path) -> "StateStore":
        return cls(Path(output_dir).resolve() / DATABASE_NAME)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._schema_lock, self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS batches (
                    batch_key TEXT PRIMARY KEY,
                    normalized_name TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    source_path TEXT NOT NULL DEFAULT '',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_batches_name ON batches(normalized_name);

                CREATE TABLE IF NOT EXISTS orders (
                    aw_order TEXT PRIMARY KEY,
                    lifecycle_state TEXT NOT NULL,
                    batch_key TEXT NOT NULL DEFAULT '',
                    job_name TEXT NOT NULL DEFAULT '',
                    customer TEXT NOT NULL DEFAULT '',
                    process_signature TEXT NOT NULL DEFAULT '',
                    in_input INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    test_mode INTEGER NOT NULL DEFAULT 0,
                    sent_at TEXT NOT NULL DEFAULT '',
                    deleted_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(lifecycle_state);
                CREATE INDEX IF NOT EXISTS idx_orders_batch ON orders(batch_key);

                CREATE TABLE IF NOT EXISTS lifecycle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aw_order TEXT NOT NULL,
                    from_state TEXT NOT NULL DEFAULT '',
                    to_state TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lifecycle_order ON lifecycle_events(aw_order, id DESC);

                CREATE TABLE IF NOT EXISTS archive_folders (
                    archive_name TEXT PRIMARY KEY,
                    process_signature TEXT NOT NULL DEFAULT '',
                    order_signature TEXT NOT NULL DEFAULT '',
                    indexed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS archive_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    archive_name TEXT NOT NULL,
                    archive_date TEXT NOT NULL DEFAULT '',
                    batch_key TEXT NOT NULL,
                    batch_name TEXT NOT NULL,
                    aw_order TEXT NOT NULL,
                    job_name TEXT NOT NULL DEFAULT '',
                    customer TEXT NOT NULL DEFAULT '',
                    process_list_path TEXT NOT NULL DEFAULT '',
                    order_archive_dir TEXT NOT NULL DEFAULT '',
                    order_files_json TEXT NOT NULL DEFAULT '[]',
                    sent_at TEXT NOT NULL DEFAULT '',
                    order_json TEXT NOT NULL DEFAULT '{}',
                    indexed_at TEXT NOT NULL,
                    UNIQUE(archive_name, batch_key, aw_order)
                );
                CREATE INDEX IF NOT EXISTS idx_archive_date ON archive_entries(archive_date DESC);
                CREATE INDEX IF NOT EXISTS idx_archive_order ON archive_entries(aw_order);
                CREATE INDEX IF NOT EXISTS idx_archive_batch ON archive_entries(batch_key);

                CREATE TABLE IF NOT EXISTS performance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_perf_operation ON performance_events(operation, id DESC);

                CREATE TABLE IF NOT EXISTS error_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    aw_order TEXT NOT NULL DEFAULT '',
                    batch_key TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_error_code ON error_events(code, id DESC);
                """
            )
            connection.execute(
                "INSERT INTO app_metadata(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def now_text() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def normalize_batch_name(path_or_name: str | Path) -> str:
        name = Path(str(path_or_name)).name.casefold().strip()
        if name.endswith(".xlsx"):
            name = name[:-5]
        elif name.endswith(".xls"):
            name = name[:-4]
        return " ".join(name.split())

    @classmethod
    def batch_identity(cls, path: Path) -> BatchIdentity:
        source = Path(path)
        normalized = cls.normalize_batch_name(source.name)
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(block)
                digest.update(block)
        content_hash = digest.hexdigest()
        key_material = f"{normalized}\0{content_hash}".encode("utf-8", errors="ignore")
        key = hashlib.sha256(key_material).hexdigest()[:32]
        return BatchIdentity(key, normalized, content_hash, size)

    def register_batch(self, path: Path) -> BatchIdentity:
        identity = self.batch_identity(path)
        stamp = self.now_text()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO batches(batch_key, normalized_name, content_hash, file_size, source_path, first_seen, last_seen)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(batch_key) DO UPDATE SET
                    source_path=excluded.source_path,
                    last_seen=excluded.last_seen,
                    file_size=excluded.file_size
                """,
                (
                    identity.key,
                    identity.normalized_name,
                    identity.content_hash,
                    identity.file_size,
                    str(Path(path).resolve()),
                    stamp,
                    stamp,
                ),
            )
        return identity

    @staticmethod
    def derive_lifecycle_state(
        *,
        has_process_list: bool,
        in_input: bool,
        status: str = "",
        sent_at: str = "",
        deleted_at: str = "",
        archived: bool = False,
        test_mode: bool = False,
        reactivated: bool = False,
    ) -> str:
        if test_mode:
            return LifecycleState.TESTING
        if reactivated:
            return LifecycleState.REACTIVATED
        if deleted_at and not in_input:
            return LifecycleState.DELETED_LOCAL
        if archived and not in_input:
            return LifecycleState.ARCHIVED
        if sent_at:
            return LifecycleState.SENT
        if in_input and not has_process_list:
            return LifecycleState.ORPHANED_INPUT
        normalized = str(status or "").strip().upper()
        if normalized in {"FAILED", "ISSUES", "ERROR", "SKIPPED"}:
            return LifecycleState.ISSUES
        if normalized in {"OK", "PROCESSED"}:
            return LifecycleState.PROCESSED
        if normalized == "READY":
            return LifecycleState.READY
        if has_process_list or in_input:
            return LifecycleState.ACTIVE
        return LifecycleState.DISCOVERED

    def transition_order(
        self,
        aw_order: str,
        to_state: str,
        *,
        reason: str = "",
        batch_key: str = "",
        job_name: str = "",
        customer: str = "",
        process_signature: str = "",
        in_input: bool | None = None,
        archived: bool | None = None,
        test_mode: bool | None = None,
        sent_at: str | None = None,
        deleted_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if to_state not in LifecycleState.ALL:
            raise ValueError(f"Unsupported lifecycle state: {to_state}")
        aw = str(aw_order).strip()
        if not aw:
            raise ValueError("A&W order is required for a lifecycle transition.")
        stamp = self.now_text()
        with self.transaction() as connection:
            current = connection.execute("SELECT * FROM orders WHERE aw_order=?", (aw,)).fetchone()
            from_state = str(current["lifecycle_state"]) if current else ""
            current_values = dict(current) if current else {}
            values = {
                "batch_key": batch_key or str(current_values.get("batch_key", "")),
                "job_name": job_name or str(current_values.get("job_name", "")),
                "customer": customer or str(current_values.get("customer", "")),
                "process_signature": process_signature or str(current_values.get("process_signature", "")),
                "in_input": int(bool(in_input if in_input is not None else current_values.get("in_input", 0))),
                "archived": int(bool(archived if archived is not None else current_values.get("archived", 0))),
                "test_mode": int(bool(test_mode if test_mode is not None else current_values.get("test_mode", 0))),
                "sent_at": str(sent_at if sent_at is not None else current_values.get("sent_at", "")),
                "deleted_at": str(deleted_at if deleted_at is not None else current_values.get("deleted_at", "")),
            }
            connection.execute(
                """
                INSERT INTO orders(
                    aw_order, lifecycle_state, batch_key, job_name, customer, process_signature,
                    in_input, archived, test_mode, sent_at, deleted_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(aw_order) DO UPDATE SET
                    lifecycle_state=excluded.lifecycle_state,
                    batch_key=excluded.batch_key,
                    job_name=excluded.job_name,
                    customer=excluded.customer,
                    process_signature=excluded.process_signature,
                    in_input=excluded.in_input,
                    archived=excluded.archived,
                    test_mode=excluded.test_mode,
                    sent_at=excluded.sent_at,
                    deleted_at=excluded.deleted_at,
                    updated_at=excluded.updated_at
                """,
                (
                    aw,
                    to_state,
                    values["batch_key"],
                    values["job_name"],
                    values["customer"],
                    values["process_signature"],
                    values["in_input"],
                    values["archived"],
                    values["test_mode"],
                    values["sent_at"],
                    values["deleted_at"],
                    stamp,
                ),
            )
            if from_state != to_state or reason:
                connection.execute(
                    """
                    INSERT INTO lifecycle_events(aw_order, from_state, to_state, reason, metadata_json, created_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (aw, from_state, to_state, reason, json.dumps(metadata or {}, sort_keys=True), stamp),
                )

    def order_state(self, aw_order: str) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM orders WHERE aw_order=?", (str(aw_order),)).fetchone()
            return dict(row) if row else {}

    def lifecycle_events(self, aw_order: str, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM lifecycle_events WHERE aw_order=? ORDER BY id DESC LIMIT ?",
                (str(aw_order), max(1, int(limit))),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def directory_signature(path: Path) -> str:
        path = Path(path)
        if not path.exists() or not path.is_dir():
            return "missing"
        digest = hashlib.sha1()
        try:
            entries = sorted(path.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            return "unreadable"
        for entry in entries:
            try:
                stat = entry.stat()
                digest.update(entry.name.casefold().encode("utf-8", errors="ignore"))
                digest.update(str(stat.st_size).encode("ascii"))
                digest.update(str(stat.st_mtime_ns).encode("ascii"))
            except OSError:
                continue
        return digest.hexdigest()

    def archive_folder_current(self, archive_name: str, process_dir: Path, order_dir: Path) -> bool:
        process_signature = self.directory_signature(process_dir)
        order_signature = self.directory_signature(order_dir)
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT process_signature, order_signature FROM archive_folders WHERE archive_name=?",
                (str(archive_name),),
            ).fetchone()
        return bool(
            row
            and row["process_signature"] == process_signature
            and row["order_signature"] == order_signature
        )

    def replace_archive_folder(
        self,
        archive_name: str,
        process_dir: Path,
        order_dir: Path,
        records: Iterable[ArchiveRecord],
    ) -> None:
        process_signature = self.directory_signature(process_dir)
        order_signature = self.directory_signature(order_dir)
        stamp = self.now_text()
        with self.transaction() as connection:
            connection.execute("DELETE FROM archive_entries WHERE archive_name=?", (str(archive_name),))
            for record in records:
                connection.execute(
                    """
                    INSERT INTO archive_entries(
                        archive_name, archive_date, batch_key, batch_name, aw_order, job_name,
                        customer, process_list_path, order_archive_dir, order_files_json, sent_at, order_json, indexed_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.archive_name,
                        record.archive_date,
                        record.batch_key,
                        record.batch_name,
                        record.aw_order,
                        record.job_name,
                        record.customer,
                        record.process_list_path,
                        record.order_archive_dir,
                        json.dumps(list(record.order_files)),
                        record.sent_at,
                        record.order_json,
                        stamp,
                    ),
                )
            connection.execute(
                """
                INSERT INTO archive_folders(archive_name, process_signature, order_signature, indexed_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(archive_name) DO UPDATE SET
                    process_signature=excluded.process_signature,
                    order_signature=excluded.order_signature,
                    indexed_at=excluded.indexed_at
                """,
                (str(archive_name), process_signature, order_signature, stamp),
            )

    def archive_records(self, archive_names: Iterable[str]) -> list[ArchiveRecord]:
        names = [str(name) for name in archive_names if str(name)]
        if not names:
            return []
        placeholders = ",".join("?" for _ in names)
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"SELECT * FROM archive_entries WHERE archive_name IN ({placeholders}) ORDER BY archive_date DESC, batch_name, aw_order",
                names,
            ).fetchall()
        records: list[ArchiveRecord] = []
        for row in rows:
            try:
                files = tuple(str(value) for value in json.loads(row["order_files_json"] or "[]"))
            except Exception:
                files = ()
            records.append(
                ArchiveRecord(
                    archive_name=str(row["archive_name"]),
                    archive_date=str(row["archive_date"]),
                    batch_key=str(row["batch_key"]),
                    batch_name=str(row["batch_name"]),
                    aw_order=str(row["aw_order"]),
                    job_name=str(row["job_name"]),
                    customer=str(row["customer"]),
                    process_list_path=str(row["process_list_path"]),
                    order_archive_dir=str(row["order_archive_dir"]),
                    order_files=files,
                    sent_at=str(row["sent_at"]),
                    order_json=str(row["order_json"] or "{}"),
                )
            )
        return records

    def record_performance(
        self,
        operation: str,
        stage: str,
        elapsed_ms: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            with self.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO performance_events(operation, stage, elapsed_ms, metadata_json, created_at)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        str(operation),
                        str(stage),
                        float(elapsed_ms),
                        json.dumps(metadata or {}, sort_keys=True, default=str),
                        self.now_text(),
                    ),
                )
        except Exception:
            return

    @contextmanager
    def measure(self, operation: str, stage: str, metadata: dict[str, Any] | None = None) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record_performance(operation, stage, (time.perf_counter() - started) * 1000.0, metadata)

    def recent_performance(self, limit: int = 200) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM performance_events ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def record_error(
        self,
        code: str,
        title: str,
        message: str,
        *,
        aw_order: str = "",
        batch_key: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            with self.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO error_events(code, title, message, aw_order, batch_key, metadata_json, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(code),
                        str(title),
                        str(message),
                        str(aw_order),
                        str(batch_key),
                        json.dumps(metadata or {}, sort_keys=True, default=str),
                        self.now_text(),
                    ),
                )
        except Exception:
            return

    def migrate_processing_history(self, history_path: Path) -> int:
        """Import legacy JSON receipts once without deleting or rewriting them."""
        path = Path(history_path)
        if not path.exists():
            return 0
        marker_key = "legacy_processing_history_migrated"
        with closing(self.connect()) as connection:
            marker = connection.execute("SELECT value FROM app_metadata WHERE key=?", (marker_key,)).fetchone()
            if marker and str(marker["value"]) == str(path.resolve()):
                return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        orders = data.get("orders", {}) if isinstance(data, dict) else {}
        if not isinstance(orders, dict):
            return 0
        migrated = 0
        for aw_order, raw in orders.items():
            if not isinstance(raw, dict):
                continue
            sent_at = str(raw.get("sent_at", "") or "")
            deleted_at = str(raw.get("deleted_at", "") or "")
            if deleted_at:
                state = LifecycleState.DELETED_LOCAL
            elif sent_at:
                state = LifecycleState.SENT
            elif raw.get("processed_at") or raw.get("last_processed"):
                state = LifecycleState.PROCESSED
            else:
                state = LifecycleState.DISCOVERED
            self.transition_order(
                str(aw_order),
                state,
                reason="Imported legacy processing history",
                sent_at=sent_at,
                deleted_at=deleted_at,
                metadata={"legacy": True},
            )
            migrated += 1
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO app_metadata(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (marker_key, str(path.resolve())),
            )
        return migrated
