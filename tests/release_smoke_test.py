#!/usr/bin/env python3
"""Non-destructive pre-release integration smoke test for Shower Programmer.

The test deliberately uses only temporary workspaces and sanitized fixtures.  It
covers the cross-module handoffs most likely to escape isolated unit tests:
direct legacy-XLS ingestion, the real-order regression corpus, archive revision
consolidation/Test Mode provenance, diagnostic packaging, and production-path
isolation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from contextlib import closing
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_order(shower_batch, aw: str, job: str, *, width: str, height: str):
    order = shower_batch.ProcessOrder(aw, job, "SANITIZED CUSTOMER")
    order.items[1] = shower_batch.ProcessItem(
        1,
        width_text=width,
        height_text=height,
        delivery_date="8/17/2026",
        customer="SANITIZED CUSTOMER",
        processing=["FLAT POLISH"],
        machine_hints=["DENVER 2"],
    )
    return order


def run(project_root: Path) -> dict[str, object]:
    backend = project_root / "Backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    import shower_batch
    import shower_programmer_gui as gui
    import shower_regressions
    import shower_reliability

    fixture = project_root / "tests" / "known_orders" / "legacy_process_list_sample.xls"
    if not fixture.is_file():
        raise RuntimeError(f"Missing sanitized legacy-XLS smoke fixture: {fixture}")

    legacy_orders = shower_batch.load_process_orders_from_file_uncached(fixture)
    if [order.aw_order for order in legacy_orders] != ["700001", "700002"]:
        raise AssertionError("Direct legacy-XLS smoke parse returned unexpected orders")

    known_results = shower_regressions.run_known_order_library(project_root, shower_batch)

    with tempfile.TemporaryDirectory(prefix="shower-release-smoke-") as raw_temp:
        temp = Path(raw_temp)
        production = temp / "PRODUCTION_SENTINEL"
        production.mkdir()
        production_file = production / "must_not_change.txt"
        production_file.write_text("production-data-must-remain-untouched\n", encoding="utf-8")
        production_hash = sha256(production_file)

        revision_old = temp / "Archive" / "08.10.26" / "Orders"
        revision_new = temp / "Archive" / "08.17.26" / "Orders"
        revision_old.mkdir(parents=True)
        revision_new.mkdir(parents=True)
        process_old = temp / "Archive" / "08.10.26" / "Process List" / "Batch 9900 old.xlsx"
        process_new = temp / "Archive" / "08.17.26" / "Process List" / "Batch 9900.xlsx"
        process_old.parent.mkdir(parents=True)
        process_new.parent.mkdir(parents=True)
        process_old.write_bytes(b"sanitized-old-revision")
        process_new.write_bytes(b"sanitized-new-revision")

        first = make_order(shower_batch, "700101", "90000001 SMOKE ALPHA", width="24", height="72")
        second = make_order(shower_batch, "700102", "90000002 SMOKE BETA", width="30", height="80")

        source_files: list[Path] = []
        for folder, order in ((revision_old, first), (revision_new, second)):
            pdf = folder / f"A&W {order.aw_order} {order.job_name}.pdf"
            dxf = folder / f"{order.aw_order}_P1.dxf"
            pdf.write_bytes(b"%PDF-1.4\n% sanitized smoke fixture\n")
            dxf.write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n", encoding="ascii")
            source_files.extend([pdf, dxf])

        raw_entries = [
            {
                "order": first,
                "archive_name": "08.10.26",
                "archive_date": gui.datetime(2026, 8, 10),
                "batch_name": "Batch 9900.xlsx",
                "batch_key": "old",
                "process_list_files": [process_old],
                "order_archive_dir": revision_old,
                "order_files": [source_files[0], source_files[1]],
            },
            {
                "order": first,
                "archive_name": "08.17.26",
                "archive_date": gui.datetime(2026, 8, 17),
                "batch_name": "Batch 9900.xlsx",
                "batch_key": "new",
                "process_list_files": [process_new],
                "order_archive_dir": revision_new,
                "order_files": [],
            },
            {
                "order": second,
                "archive_name": "08.17.26",
                "archive_date": gui.datetime(2026, 8, 17),
                "batch_name": "Batch 9900.xlsx",
                "batch_key": "new",
                "process_list_files": [process_new],
                "order_archive_dir": revision_new,
                "order_files": [source_files[2], source_files[3]],
            },
        ]
        groups = gui.ShowerProgrammerApp.consolidate_archive_batch_entries(raw_entries)
        if len(groups) != 1 or int(groups[0].get("revision_count", 0)) != 2:
            raise AssertionError("Archive revision consolidation smoke test failed")
        inspector = gui.ShowerProgrammerApp.archive_revision_inspector_text(groups[0])
        if "Revision 1" not in inspector or "Resolved archived file sources" not in inspector:
            raise AssertionError("Archive Revision Inspector smoke output is incomplete")

        prepared = gui.ShowerProgrammerApp.prepare_archived_batch_test_mode(
            groups[0]["children"],
            batch_name="Batch 9900.xlsx",
            archive_name="08.17.26",
            runtime_root=temp / "RUNTIME",
        )
        process_dir = Path(prepared["process_dir"])
        restored_orders = shower_batch.load_process_orders(process_dir)
        if sorted(order.aw_order for order in restored_orders) != ["700101", "700102"]:
            raise AssertionError("Consolidated Test Mode process list did not round-trip")
        manifest_path = Path(prepared["provenance_manifest"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if len(manifest.get("orders", [])) != 2:
            raise AssertionError("Test Mode provenance manifest is missing orders")
        if not any(row.get("files") for row in manifest.get("orders", [])):
            raise AssertionError("Test Mode provenance manifest is missing source-file provenance")

        reliability_output = temp / "RELIABILITY_OUTPUT"
        reliability_output.mkdir()
        journal = shower_reliability.SendJournal(reliability_output)
        transaction_id = journal.begin(
            aw_orders=["700101", "700102"],
            output_sources=[production_file],
            archive_inputs=True,
        )
        journal.update(
            transaction_id,
            shower_reliability.SendStage.POST_SEND_VERIFIED,
            "Smoke test verified Send state.",
            integrity_ok=True,
        )
        if not journal.incomplete():
            raise AssertionError("Transactional Send journal did not expose incomplete durable work")
        journal.complete(transaction_id)
        if journal.incomplete():
            raise AssertionError("Completed Send journal remained in startup recovery")

        database = reliability_output / "shower_programmer.sqlite3"
        import sqlite3
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE app_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO app_metadata(key, value) VALUES('schema_version', '1')")
            connection.commit()
        database_safety = shower_reliability.DatabaseSafetyManager(reliability_output)
        backup = database_safety.prepare_for_schema(2)
        if backup is None or not backup.is_file():
            raise AssertionError("Database migration safety smoke test did not create a pre-schema backup")

        diagnostic = shower_reliability.diagnostic_text(
            app_version="Version 1.21",
            title="Smoke",
            internal_code="NETWORK_TIMEOUT",
            message="sanitized timeout",
            aw_order="700101",
        )
        if "NET-001" not in diagnostic or "700101" not in diagnostic:
            raise AssertionError("Operator error-code diagnostics smoke test failed")

        diagnostic_source = temp / "diagnostic-source.txt"
        diagnostic_source.write_text("sanitized diagnostic smoke input", encoding="utf-8")
        diagnostic_zip = temp / "diagnostics" / "smoke.zip"
        gui.ShowerProgrammerApp.write_diagnostic_zip(
            diagnostic_zip,
            {"smoke": [diagnostic_source]},
            {"release_smoke": {"orders": [order.aw_order for order in restored_orders]}},
        )
        if not diagnostic_zip.is_file():
            raise AssertionError("Diagnostic package smoke test did not create a ZIP")

        if sha256(production_file) != production_hash:
            raise AssertionError("Release smoke test modified its production sentinel")

    return {
        "ok": True,
        "legacy_xls_orders": len(legacy_orders),
        "known_order_cases": len(known_results),
        "archive_revision_inspector": True,
        "test_mode_provenance": True,
        "diagnostic_package": True,
        "transactional_send_recovery": True,
        "database_migration_backup": True,
        "operator_error_codes": True,
        "production_paths_untouched": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--report")
    args = parser.parse_args()
    result = run(Path(args.project_root).resolve())
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print("Pre-release smoke test passed:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
