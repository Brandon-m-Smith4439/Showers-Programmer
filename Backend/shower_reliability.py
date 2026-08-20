"""Operational reliability services for Shower Programmer.

The GUI should coordinate workflows, not own their durable recovery semantics.
This module provides transaction journals, post-send verification, database
migration backups, stable operator error codes, startup recovery discovery, and
persistent runtime rollback support using only standard-library facilities.
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


SEND_JOURNAL_SCHEMA = 1
SEND_TERMINAL_STAGES = {"COMPLETE", "FAILED_RESOLVED", "CANCELLED_RESOLVED"}


class SendStage:
    PREPARED = "PREPARED"
    OUTPUTS_COPIED = "OUTPUTS_COPIED"
    INPUTS_ARCHIVED = "INPUTS_ARCHIVED"
    NETWORK_CLEARED = "NETWORK_CLEARED"
    POST_SEND_VERIFIED = "POST_SEND_VERIFIED"
    RECEIPT_WRITTEN = "RECEIPT_WRITTEN"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED_RESOLVED = "CANCELLED_RESOLVED"
    FAILED_RESOLVED = "FAILED_RESOLVED"


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return "Post-send integrity verified."
        lines = ["Post-send integrity " + ("verified with warnings." if self.ok else "needs attention.")]
        lines.extend(f"ERROR: {item}" for item in self.errors)
        lines.extend(f"Warning: {item}" for item in self.warnings)
        return "\n".join(lines)


class SendJournal:
    """Atomic JSON journal for one production Send transaction."""

    def __init__(self, output_dir: Path) -> None:
        self.root = Path(output_dir).resolve() / "Transactions" / "Send"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def now_text() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def begin(
        self,
        *,
        aw_orders: Iterable[str],
        output_sources: Iterable[Path],
        archive_inputs: bool,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        transaction_id = f"send-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        payload: dict[str, Any] = {
            "schema": SEND_JOURNAL_SCHEMA,
            "transaction_id": transaction_id,
            "stage": SendStage.PREPARED,
            "created_at": self.now_text(),
            "updated_at": self.now_text(),
            "aw_orders": sorted({str(value) for value in aw_orders if str(value).strip()}),
            "output_sources": [str(Path(path)) for path in output_sources],
            "archive_inputs": bool(archive_inputs),
            "history": [],
            "metadata": dict(metadata or {}),
        }
        self._append_history(payload, SendStage.PREPARED, "Send transaction prepared.", {})
        self._write(transaction_id, payload)
        return transaction_id

    def update(
        self,
        transaction_id: str,
        stage: str,
        message: str,
        **details: Any,
    ) -> dict[str, Any]:
        payload = self.read(transaction_id)
        if not payload:
            payload = {
                "schema": SEND_JOURNAL_SCHEMA,
                "transaction_id": transaction_id,
                "created_at": self.now_text(),
                "history": [],
            }
        payload["stage"] = str(stage)
        payload["updated_at"] = self.now_text()
        payload.update({key: value for key, value in details.items() if key != "history"})
        self._append_history(payload, str(stage), message, details)
        self._write(transaction_id, payload)
        return payload

    def complete(self, transaction_id: str, message: str = "Send transaction complete.", **details: Any) -> None:
        self.update(transaction_id, SendStage.COMPLETE, message, completed_at=self.now_text(), **details)

    def fail(self, transaction_id: str, error: BaseException | str, **details: Any) -> None:
        self.update(
            transaction_id,
            SendStage.FAILED,
            "Send transaction stopped before completion.",
            error=f"{error.__class__.__name__}: {error}" if isinstance(error, BaseException) else str(error),
            **details,
        )

    def read(self, transaction_id: str) -> dict[str, Any]:
        path = self.root / f"{transaction_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def incomplete(self, *, max_age_days: int = 45) -> list[dict[str, Any]]:
        cutoff = datetime.now().astimezone() - timedelta(days=max_age_days)
        rows: list[dict[str, Any]] = []
        try:
            files = list(self.root.glob("send-*.json"))
        except OSError:
            return []
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("stage", "")) in SEND_TERMINAL_STAGES or str(payload.get("stage", "")) == SendStage.COMPLETE:
                    continue
                updated = datetime.fromisoformat(str(payload.get("updated_at", payload.get("created_at", ""))))
                if updated.tzinfo is None:
                    updated = updated.astimezone()
                if updated < cutoff:
                    continue
                payload["journal_path"] = str(path)
                rows.append(payload)
            except Exception:
                continue
        rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
        return rows

    @staticmethod
    def _append_history(payload: dict[str, Any], stage: str, message: str, details: dict[str, Any]) -> None:
        history = payload.setdefault("history", [])
        if not isinstance(history, list):
            history = []
            payload["history"] = history
        history.append(
            {
                "at": SendJournal.now_text(),
                "stage": stage,
                "message": message,
                "details": {key: _json_safe(value) for key, value in details.items()},
            }
        )

    def _write(self, transaction_id: str, payload: dict[str, Any]) -> None:
        target = self.root / f"{transaction_id}.json"
        temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
        temporary.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, target)


@dataclass
class SendRollbackEntry:
    target: Path
    existed_before: bool
    backup: Path | None = None
    copied_sha256: str = ""
    copied_size: int = 0


class SendRollbackTracker:
    """Restore only production files written by one cancellable Send."""

    def __init__(self, output_dir: Path, transaction_id: str) -> None:
        self.root = (
            Path(output_dir).resolve()
            / "Transactions"
            / "Send Rollback"
            / str(transaction_id)
        )
        self.entries: list[SendRollbackEntry] = []

    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def copy_atomically(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.rollback")
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass

    def prepare_target(self, target: Path) -> SendRollbackEntry:
        target = Path(target)
        existed_before = target.is_file()
        backup: Path | None = None
        if existed_before:
            self.root.mkdir(parents=True, exist_ok=True)
            backup = self.root / f"{len(self.entries) + 1:04d}-{target.name}"
            shutil.copy2(target, backup)
        entry = SendRollbackEntry(target=target, existed_before=existed_before, backup=backup)
        self.entries.append(entry)
        return entry

    def record_copy(self, entry: SendRollbackEntry) -> None:
        if not entry.target.is_file():
            raise FileNotFoundError(f"Copied production output is missing: {entry.target}")
        entry.copied_size = entry.target.stat().st_size
        entry.copied_sha256 = self.sha256_file(entry.target)

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "target": str(entry.target),
                "existed_before": entry.existed_before,
                "backup": str(entry.backup or ""),
                "copied_sha256": entry.copied_sha256,
                "copied_size": entry.copied_size,
            }
            for entry in self.entries
        ]

    def rollback(self) -> tuple[list[Path], list[str]]:
        rolled_back: list[Path] = []
        warnings: list[str] = []
        for entry in reversed(self.entries):
            if not entry.copied_sha256:
                continue
            try:
                if entry.target.is_file():
                    current_size = entry.target.stat().st_size
                    current_sha256 = self.sha256_file(entry.target)
                    if current_size != entry.copied_size or current_sha256 != entry.copied_sha256:
                        warnings.append(
                            f"Kept {entry.target.name} because it changed after this Send copied it."
                        )
                        continue
                if entry.existed_before:
                    if entry.backup is None or not entry.backup.is_file():
                        warnings.append(f"Could not restore the previous {entry.target.name}; its rollback copy is missing.")
                        continue
                    self.copy_atomically(entry.backup, entry.target)
                elif entry.target.exists():
                    entry.target.unlink()
                rolled_back.append(entry.target)
            except OSError as exc:
                warnings.append(f"Could not roll back {entry.target.name}: {exc}")
        if not warnings:
            self.commit()
        return rolled_back, warnings

    def commit(self) -> None:
        try:
            if self.root.exists():
                shutil.rmtree(self.root)
        except OSError:
            pass


def verify_post_send(
    *,
    copied_targets: Iterable[Path],
    remaining_local_inputs: Iterable[Path] = (),
    expected_network_sources: Iterable[Path] = (),
    cleanup_warnings: Iterable[str] = (),
) -> IntegrityResult:
    """Verify production copies and exact known cleanup targets without broad rescans."""
    errors: list[str] = []
    warnings: list[str] = [str(value) for value in cleanup_warnings if str(value).strip()]
    copied = [Path(path) for path in copied_targets]
    missing_outputs = [path for path in copied if not path.exists() or not path.is_file()]
    if missing_outputs:
        errors.append("Copied production output is missing: " + ", ".join(path.name for path in missing_outputs[:8]))
    local_leftovers = [Path(path) for path in remaining_local_inputs if Path(path).exists()]
    if local_leftovers:
        errors.append("Sent input still exists locally: " + ", ".join(path.name for path in local_leftovers[:8]))
    network_leftovers = [Path(path) for path in expected_network_sources if Path(path).exists()]
    if network_leftovers:
        errors.append("Sent input still exists in Network Input: " + ", ".join(path.name for path in network_leftovers[:8]))
    return IntegrityResult(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))


class DatabaseSafetyManager:
    """Back up SQLite before a schema transition and record migration outcomes."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir).resolve()
        self.database = self.output_dir / "shower_programmer.sqlite3"
        self.backup_dir = self.output_dir / "Database Backups"
        self.audit_path = self.backup_dir / "migration_history.jsonl"

    def existing_schema_version(self) -> int | None:
        if not self.database.is_file():
            return None
        try:
            with closing(sqlite3.connect(str(self.database), timeout=5.0)) as connection:
                row = connection.execute(
                    "SELECT value FROM app_metadata WHERE key='schema_version'"
                ).fetchone()
            if not row:
                return 0
            return int(row[0])
        except sqlite3.DatabaseError:
            return 0
        except Exception:
            return None

    def prepare_for_schema(self, target_schema: int) -> Path | None:
        current = self.existing_schema_version()
        if current is None or current == int(target_schema):
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup = self.backup_dir / (
            f"shower_programmer-before-schema-{current}-to-{int(target_schema)}-"
            f"{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
        )
        with closing(sqlite3.connect(str(self.database), timeout=15.0)) as source:
            with closing(sqlite3.connect(str(backup), timeout=15.0)) as destination:
                source.backup(destination)
        self._audit("backup_created", current, int(target_schema), backup=str(backup))
        return backup

    def record_schema_result(self, target_schema: int, *, backup: Path | None = None) -> None:
        current = self.existing_schema_version()
        target = int(target_schema)
        # Normal startups where the schema is already current should not create
        # migration-history noise. Record only an actual transition attempt or
        # an unexpected post-initialization mismatch that deserves attention.
        if backup is None and current == target:
            return
        self._audit(
            "migration_verified" if current == target else "migration_unverified",
            current,
            target,
            backup=str(backup or ""),
        )

    def _audit(self, action: str, from_schema: int | None, to_schema: int, **details: Any) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "action": action,
            "from_schema": from_schema,
            "to_schema": to_schema,
            **details,
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


OPERATOR_ERROR_CODES = {
    "DIMENSION_MISMATCH": "DIM-001",
    "MISSING_PROCESS_ORDER": "PROC-001",
    "AMBIGUOUS_PDF": "PDF-002",
    "PDF_NOT_FOUND": "PDF-001",
    "DXF_NOT_FOUND": "DXF-001",
    "NETWORK_TIMEOUT": "NET-001",
    "NETWORK_IO": "NET-002",
    "PROCESS_LIST_READ": "PROC-002",
    "FILE_LOCKED": "FILE-001",
    "CANCELLED": "OPS-001",
    "INTERNAL": "SYS-001",
}


def operator_error_code(internal_code: str) -> str:
    return OPERATOR_ERROR_CODES.get(str(internal_code or "").upper(), "SYS-001")


def diagnostic_text(
    *,
    app_version: str,
    title: str,
    internal_code: str,
    message: str,
    aw_order: str = "",
    batch_key: str = "",
    details: dict[str, Any] | None = None,
) -> str:
    operator_code = operator_error_code(internal_code)
    lines = [
        f"Shower Programmer {app_version}",
        f"Error Code: {operator_code}",
        f"Internal Code: {internal_code}",
        f"Stage: {title}",
        f"Time: {datetime.now().astimezone().isoformat(timespec='seconds')}",
    ]
    if aw_order:
        lines.append(f"A&W: {aw_order}")
    if batch_key:
        lines.append(f"Batch: {batch_key}")
    lines.extend(["", str(message).strip()])
    if details:
        lines.extend(["", "Details:", json.dumps(_json_safe(details), indent=2, sort_keys=True)])
    return "\n".join(lines).strip()


def startup_recovery_issues(runtime_root: Path, output_dir: Path) -> list[dict[str, str]]:
    """Discover interrupted durable operations without changing production data."""
    runtime = Path(runtime_root).resolve()
    output = Path(output_dir).resolve()
    issues: list[dict[str, str]] = []
    journal = SendJournal(output)
    for item in journal.incomplete():
        issues.append(
            {
                "type": "send",
                "severity": "WARN",
                "title": "Interrupted Send transaction",
                "detail": f"{item.get('transaction_id', '')} stopped at {item.get('stage', 'unknown')} for {', '.join(item.get('aw_orders', [])) or 'unknown order' }.",
                "path": str(item.get("journal_path", "")),
            }
        )

    test_root = runtime / "Test Workspace"
    if test_root.is_dir():
        try:
            workspaces = [path for path in test_root.iterdir() if path.is_dir()]
        except OSError:
            workspaces = []
        for workspace in sorted(workspaces, key=lambda path: path.name, reverse=True)[:8]:
            manifest = workspace / "TestModeProvenance.json"
            if manifest.is_file():
                issues.append(
                    {
                        "type": "test_workspace",
                        "severity": "INFO",
                        "title": "Previous Test Mode workspace",
                        "detail": workspace.name,
                        "path": str(workspace),
                    }
                )

    for pattern in (".__sp_new_*", ".__sp_old_*"):
        try:
            paths = list(runtime.glob(pattern))
        except OSError:
            paths = []
        for path in paths:
            issues.append(
                {
                    "type": "update",
                    "severity": "WARN",
                    "title": "Interrupted update staging folder",
                    "detail": path.name,
                    "path": str(path),
                }
            )

    rollback_journal = output / "shower_programmer.sqlite3-journal"
    if rollback_journal.is_file() and rollback_journal.stat().st_size > 0:
        issues.append(
            {
                "type": "database",
                "severity": "WARN",
                "title": "SQLite rollback journal present",
                "detail": "Database recovery may be needed; run System Health before production work.",
                "path": str(rollback_journal),
            }
        )
    return issues


class RuntimeRollbackManager:
    """Persistent one-version runtime rollback support."""

    ROLLBACK_FOLDER = "Rollback"
    SNAPSHOT_FOLDER = "PreviousRuntime"

    @classmethod
    def snapshot_dir(cls, app_dir: Path) -> Path:
        return Path(app_dir).resolve() / cls.ROLLBACK_FOLDER / cls.SNAPSHOT_FOLDER

    @classmethod
    def snapshot_info(cls, app_dir: Path) -> dict[str, str]:
        root = cls.snapshot_dir(app_dir)
        exe = root / "Shower Programmer.exe"
        metadata = root / ".shower_update.json"
        version = "Unknown previous version"
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
            version = str(data.get("version", version))
        except Exception:
            pass
        return {
            "available": "yes" if exe.is_file() and (root / "_internal").is_dir() else "no",
            "version": version,
            "path": str(root),
        }

    @classmethod
    def stage_rollback_script(cls, app_dir: Path, updates_dir: Path, current_pid: int) -> Path:
        app = Path(app_dir).resolve()
        snapshot = cls.snapshot_dir(app)
        exe_name = "Shower Programmer.exe"
        if not (snapshot / exe_name).is_file() or not (snapshot / "_internal").is_dir():
            raise RuntimeError("No validated previous runtime snapshot is available.")
        updates = Path(updates_dir).resolve()
        updates.mkdir(parents=True, exist_ok=True)
        script = updates / f"rollback_{datetime.now():%Y%m%d_%H%M%S}.cmd"
        current_backup = app / cls.ROLLBACK_FOLDER / "ReplacedRuntime"
        body = f'''@echo off\nsetlocal EnableExtensions\nset "APP_DIR={app}"\nset "SNAPSHOT={snapshot}"\nset "CURRENT_BACKUP={current_backup}"\nset "EXE_NAME={exe_name}"\nset "PID={int(current_pid)}"\ntitle Shower Programmer Rollback\necho Waiting for Shower Programmer to close...\n:wait\ntasklist /FI "PID eq %PID%" /NH 2>nul | findstr /R /C:"[ ]%PID%[ ]" >nul\nif not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\nif exist "%CURRENT_BACKUP%" rmdir /S /Q "%CURRENT_BACKUP%"\nmkdir "%CURRENT_BACKUP%" >nul 2>nul\nfor %%N in (_internal Assets "Shower Programmer.exe" .shower_update.json) do (\n  if exist "%APP_DIR%\\%%~N" move /Y "%APP_DIR%\\%%~N" "%CURRENT_BACKUP%\\%%~N" >nul\n)\nfor %%N in (_internal Assets "Shower Programmer.exe" .shower_update.json) do (\n  if exist "%SNAPSHOT%\\%%~N" move /Y "%SNAPSHOT%\\%%~N" "%APP_DIR%\\%%~N" >nul\n)\nif not exist "%APP_DIR%\\%EXE_NAME%" goto restore_failed\nstart "" "%APP_DIR%\\%EXE_NAME%"\nexit /b 0\n:restore_failed\necho Rollback could not activate the previous runtime. Restoring the newer runtime...\nfor %%N in (_internal Assets "Shower Programmer.exe" .shower_update.json) do (\n  if exist "%CURRENT_BACKUP%\\%%~N" move /Y "%CURRENT_BACKUP%\\%%~N" "%APP_DIR%\\%%~N" >nul\n)\nif exist "%APP_DIR%\\%EXE_NAME%" start "" "%APP_DIR%\\%EXE_NAME%"\npause\nexit /b 1\n'''
        script.write_text(body, encoding="utf-8", newline="\r\n")
        return script


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
