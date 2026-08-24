from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_reliability
from shower_temp import workspace_temporary_directory
from shower_rules import archive as archive_rules
from shower_rules import dimensions as dimension_rules
from shower_rules import machine as machine_rules
from shower_rules import orientation as orientation_rules
from shower_rules import remake as remake_rules


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, *texts: str) -> None:
        self.pages = [FakePage(text) for text in texts]


class Version121ReliabilityArchitectureTests(unittest.TestCase):
    def test_send_journal_survives_until_transaction_is_complete(self) -> None:
        with workspace_temporary_directory() as raw:
            output = Path(raw)
            journal = shower_reliability.SendJournal(output)
            transaction_id = journal.begin(
                aw_orders=["800001"],
                output_sources=[output / "800001.pdf"],
                archive_inputs=True,
            )
            journal.update(
                transaction_id,
                shower_reliability.SendStage.OUTPUTS_COPIED,
                "copied",
                copied_targets=[str(output / "800001.pdf")],
            )
            incomplete = journal.incomplete()
            self.assertEqual([row["transaction_id"] for row in incomplete], [transaction_id])
            journal.complete(transaction_id)
            self.assertEqual(journal.incomplete(), [])

    def test_resolved_noop_send_does_not_trigger_startup_recovery(self) -> None:
        with workspace_temporary_directory() as raw:
            output = Path(raw)
            journal = shower_reliability.SendJournal(output)
            transaction_id = journal.begin(aw_orders=["800001"], output_sources=[], archive_inputs=False)
            journal.update(
                transaction_id,
                shower_reliability.SendStage.CANCELLED_RESOLVED,
                "No matching generated files were found; no production Send occurred.",
            )
            self.assertEqual(journal.incomplete(), [])

    def test_post_send_integrity_checks_outputs_local_and_network_cleanup(self) -> None:
        with workspace_temporary_directory() as raw:
            root = Path(raw)
            copied = root / "production.pdf"
            copied.write_text("ok", encoding="utf-8")
            local = root / "local.pdf"
            local.write_text("leftover", encoding="utf-8")
            network = root / "network.dxf"
            network.write_text("leftover", encoding="utf-8")
            result = shower_reliability.verify_post_send(
                copied_targets=[copied],
                remaining_local_inputs=[local],
                expected_network_sources=[network],
            )
            self.assertFalse(result.ok)
            self.assertTrue(any("locally" in value for value in result.errors))
            self.assertTrue(any("Network Input" in value for value in result.errors))
            local.unlink()
            network.unlink()
            self.assertTrue(
                shower_reliability.verify_post_send(
                    copied_targets=[copied],
                    remaining_local_inputs=[local],
                    expected_network_sources=[network],
                ).ok
            )

    def test_database_safety_creates_backup_before_schema_change(self) -> None:
        with workspace_temporary_directory() as raw:
            output = Path(raw)
            database = output / "shower_programmer.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE app_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("INSERT INTO app_metadata(key, value) VALUES('schema_version', '5')")
                connection.execute("CREATE TABLE sentinel(value TEXT)")
                connection.execute("INSERT INTO sentinel(value) VALUES('preserve-me')")
                connection.commit()
            manager = shower_reliability.DatabaseSafetyManager(output)
            backup = manager.prepare_for_schema(6)
            self.assertIsNotNone(backup)
            assert backup is not None
            self.assertTrue(backup.is_file())
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(connection.execute("SELECT value FROM sentinel").fetchone()[0], "preserve-me")

    def test_database_safety_does_not_log_when_schema_is_already_current(self) -> None:
        with workspace_temporary_directory() as raw:
            output = Path(raw)
            database = output / "shower_programmer.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE app_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("INSERT INTO app_metadata(key, value) VALUES('schema_version', '6')")
                connection.commit()
            manager = shower_reliability.DatabaseSafetyManager(output)
            self.assertIsNone(manager.prepare_for_schema(6))
            manager.record_schema_result(6)
            self.assertFalse(manager.audit_path.exists())

    def test_operator_codes_are_stable_and_copyable(self) -> None:
        self.assertEqual(shower_reliability.operator_error_code("NETWORK_TIMEOUT"), "NET-001")
        self.assertEqual(shower_reliability.operator_error_code("FILE_LOCKED"), "FILE-001")
        text = shower_reliability.diagnostic_text(
            app_version="Version 1.21",
            title="Review / Send",
            internal_code="NETWORK_TIMEOUT",
            message="Timed out",
            aw_order="800001",
        )
        self.assertIn("Error Code: NET-001", text)
        self.assertIn("A&W: 800001", text)

    def test_startup_recovery_finds_incomplete_send_and_prior_test_workspace(self) -> None:
        with workspace_temporary_directory() as raw:
            root = Path(raw)
            output = root / "Output"
            output.mkdir()
            transaction = shower_reliability.SendJournal(output).begin(
                aw_orders=["800001"], output_sources=[], archive_inputs=True
            )
            workspace = root / "Test Workspace" / "old-batch"
            workspace.mkdir(parents=True)
            (workspace / "TestModeProvenance.json").write_text("{}", encoding="utf-8")
            issues = shower_reliability.startup_recovery_issues(root, output)
            self.assertTrue(any(transaction in item.get("detail", "") for item in issues))
            self.assertTrue(any(item.get("type") == "test_workspace" for item in issues))

    def test_runtime_rollback_snapshot_is_detected_and_script_is_staged(self) -> None:
        with workspace_temporary_directory() as raw:
            app = Path(raw) / "Shower Programmer"
            snapshot = shower_reliability.RuntimeRollbackManager.snapshot_dir(app)
            (snapshot / "_internal").mkdir(parents=True)
            (snapshot / "Assets").mkdir()
            (snapshot / "Shower Programmer.exe").write_bytes(b"old-exe")
            (snapshot / ".shower_update.json").write_text(json.dumps({"version": "Version 1.20"}), encoding="utf-8")
            info = shower_reliability.RuntimeRollbackManager.snapshot_info(app)
            self.assertEqual(info["available"], "yes")
            self.assertEqual(info["version"], "Version 1.20")
            script = shower_reliability.RuntimeRollbackManager.stage_rollback_script(app, Path(raw) / "updates", 12345)
            source = script.read_text(encoding="utf-8")
            self.assertIn("ReplacedRuntime", source)
            self.assertIn("PreviousRuntime", source)

    def test_business_rules_are_small_pure_modules(self) -> None:
        self.assertTrue(remake_rules.location_value_indicates_remake("REMAKES - MASTER LEFT"))
        self.assertFalse(remake_rules.location_value_indicates_remake("MASTER LEFT"))
        self.assertTrue(remake_rules.pdf_location_indicates_remake(FakeReader("REMAKELocation:")))
        self.assertTrue(machine_rules.minimum_dimension_forces_waterjet(6.0, 80.0, {"rules": {"denver_min_inches": 6.125}}))
        self.assertFalse(machine_rules.minimum_dimension_forces_waterjet(6.125, 80.0, {"rules": {"denver_min_inches": 6.125}}))
        self.assertTrue(dimension_rules.dimensions_match((24.0, 80.0), (80.0, 24.0), 0.01))
        self.assertEqual(orientation_rules.default_machine_rotation("WJ", 24.0, 80.0), -90.0)
        self.assertEqual(orientation_rules.default_machine_rotation("DENVER 1", 24.0, 80.0), 90.0)
        first = Path("C:/Archive/08.17.26")
        second = Path("C:/Archive/08.10.26")
        self.assertEqual(archive_rules.ordered_unique_paths([first, first, second]), [first, second])

    def test_release_smoke_closes_sqlite_fixture_connection(self) -> None:
        smoke_source = (PROJECT_ROOT / "tests" / "release_smoke_test.py").read_text(encoding="utf-8")
        self.assertIn("from contextlib import closing", smoke_source)
        self.assertIn("with closing(sqlite3.connect(database)) as connection:", smoke_source)
        self.assertIn("connection.commit()", smoke_source)

    def test_gui_and_batch_are_wired_to_new_reliability_services(self) -> None:
        gui_source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        batch_source = (BACKEND / "shower_batch.py").read_text(encoding="utf-8")
        rebuild = (PROJECT_ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        self.assertIn("self.send_journal.begin", gui_source)
        self.assertIn("run_startup_recovery_check", gui_source)
        self.assertIn("verify_post_send", gui_source)
        self.assertIn('"Rule Test"', gui_source)
        self.assertIn("Copy Diagnostics", gui_source)
        self.assertIn("stage_rollback_script", gui_source)
        self.assertIn("prepare_for_schema", gui_source)
        self.assertIn("from shower_rules import machine as machine_rules", batch_source)
        self.assertIn("from shower_rules.remake import", batch_source)
        self.assertIn("PreviousRuntime", rebuild)
        self.assertIn("SOURCE_RELIABILITY", rebuild)
        self.assertIn("SOURCE_RULES_REMAKE", rebuild)


if __name__ == "__main__":
    unittest.main()
