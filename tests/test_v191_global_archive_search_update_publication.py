from __future__ import annotations

import json
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui
import shower_state


class Version191GlobalArchiveSearchUpdatePublicationTests(unittest.TestCase):
    def _indexed_archive(self, root: Path) -> tuple[shower_state.StateStore, Path, Path]:
        output_dir = root / "Output"
        process_root = root / "Process List" / "Archive"
        order_root = root / "Orders" / "Archive"
        process_date = process_root / "09.30.26"
        order_date = order_root / "09.30.26"
        process_date.mkdir(parents=True)
        order_date.mkdir(parents=True)
        process_file = process_date / "Batch 44001.xlsx"
        process_file.write_bytes(b"archive fixture")

        first = shower_batch.ProcessOrder("239465", "SMITH SHOWER ENCLOSURE", "ACME GLASS")
        first.items[1] = shower_batch.ProcessItem(1, width_text='48-5/8"', height_text='40"', delivery_date="10/01/2026")
        second = shower_batch.ProcessOrder("239466", "JONES MASTER BATH", "BUILDERS SOURCE")
        second.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='72"', delivery_date="10/02/2026")
        cached = {row["aw_order"]: row for row in shower_batch.process_orders_to_cache([first, second])}

        store = shower_state.StateStore.for_output(output_dir)
        store.replace_archive_folder(
            "09.30.26",
            process_date,
            order_date,
            [
                shower_state.ArchiveRecord(
                    archive_name="09.30.26",
                    archive_date="2026-09-30",
                    batch_key="batch-44001",
                    batch_name=process_file.name,
                    aw_order=first.aw_order,
                    job_name=first.job_name,
                    customer=first.customer,
                    process_list_path=str(process_file),
                    order_archive_dir=str(order_date),
                    order_files=(),
                    order_json=json.dumps(cached[first.aw_order], sort_keys=True),
                ),
                shower_state.ArchiveRecord(
                    archive_name="09.30.26",
                    archive_date="2026-09-30",
                    batch_key="batch-44001",
                    batch_name=process_file.name,
                    aw_order=second.aw_order,
                    job_name=second.job_name,
                    customer=second.customer,
                    process_list_path=str(process_file),
                    order_archive_dir=str(order_date),
                    order_files=(),
                    order_json=json.dumps(cached[second.aw_order], sort_keys=True),
                ),
            ],
        )
        return store, order_root, process_root

    def test_sqlite_archive_search_supports_aw_job_customer_batch_date_and_multiple_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, _order_root, _process_root = self._indexed_archive(Path(temp_dir))
            for query in ("239465", "smith", "acme", "10/01/2026", "smith 239465"):
                self.assertEqual([row.aw_order for row in store.search_archive_records(query)], ["239465"], query)
            for query in ("44001", "09.30.26"):
                self.assertEqual(
                    [row.aw_order for row in store.search_archive_records(query)],
                    ["239465", "239466"],
                    query,
                )
            self.assertEqual([row.aw_order for row in store.search_archive_records("builders 239466")], ["239466"])
            self.assertEqual(store.search_archive_records("not-a-real-order"), [])

    def test_archived_inventory_can_search_all_cached_dates_without_date_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, order_root, process_root = self._indexed_archive(Path(temp_dir))
            found, warnings = gui.ShowerProgrammerApp.archived_order_inventory(
                order_root,
                process_root,
                state_store=store,
                search_query="ACME 239465",
            )
            self.assertEqual(warnings, [])
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["order"].aw_order, "239465")
            missing, warnings = gui.ShowerProgrammerApp.archived_order_inventory(
                order_root,
                process_root,
                state_store=store,
                search_query="no-match",
            )
            self.assertEqual(warnings, [])
            self.assertEqual(missing, [])

    def test_archive_search_helper_matches_tokens_across_different_fields(self) -> None:
        self.assertTrue(gui.ShowerProgrammerApp.archive_search_matches("smith 239465", "239465", "Smith Shower", "Acme"))
        self.assertTrue(gui.ShowerProgrammerApp.archive_search_matches("44001 acme", "Batch 44001.xlsx", "ACME GLASS"))
        self.assertFalse(gui.ShowerProgrammerApp.archive_search_matches("smith 239999", "239465", "Smith Shower"))

    def test_archive_ui_exposes_full_history_search_and_enter_shortcut(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = source.index("    def build_archive_settings_tab")
        body = source[start:]
        self.assertIn('"Search All Archives"', body)
        self.assertIn('placeholder_text="Search Job, Customer, A&W order, Batch, or archive date..."', body)
        self.assertIn('search_entry.bind("<Return>"', body)
        self.assertIn("def search_all_archives()", body)
        self.assertIn("search_query=query_text", body)
        self.assertIn("date_from=None", body)
        self.assertIn("date_to=None", body)

    def test_package_descriptor_exposes_release_commit_as_update_authority(self) -> None:
        metadata = {
            "zip_path": "release/Shower-Programmer-Windows.zip",
            "sha256": "abc",
            "size": 123,
            "version": "Version 1.91",
            "version_number": 191,
            "marker": "VERSION_1_91_GLOBAL_ARCHIVE_SEARCH_UPDATE_PUBLICATION",
            "release_name": "Global Archive Search and Update Publication Reliability",
            "release_date": "2026-09-30",
            "built_at": "2026-09-30T17:00:00+00:00",
            "commit": "published-package-sha",
        }
        with mock.patch.object(gui.ShowerProgrammerApp, "download_text", return_value=json.dumps(metadata)):
            descriptor = gui.ShowerProgrammerApp.github_update_package_descriptor("owner", "repo", "main")
        self.assertEqual(descriptor["commit"], "published-package-sha")
        self.assertEqual(descriptor["version_number"], 191)
        self.assertEqual(descriptor["marker"], metadata["marker"])

    def test_packaged_update_check_ignores_newer_source_only_branch_commit(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.worker_queue = queue.Queue()
        app.github_update_repo = lambda _repo: ("owner", "repo")
        app.github_latest_commit = lambda *_args: ("newer-source-only-sha", "2026-09-30T18:00:00Z")
        app.github_update_package_descriptor = lambda *_args: {
            "version": "Version 1.90",
            "release_name": "Published 1.90",
            "commit": "published-package-sha",
            "built_at": "2026-09-30T17:00:00Z",
        }
        app.current_update_revision = lambda _repo: "published-package-sha"
        app.current_packaged_exe_hash = lambda: "local-hash"
        with mock.patch.object(gui.sys, "frozen", True, create=True):
            app.worker_check_for_updates(Path("."), "", False, True)
        kind, payload = app.worker_queue.get_nowait()
        self.assertEqual(kind, "update_no_updates")
        self.assertEqual(payload["latest_sha"], "published-package-sha")
        self.assertEqual(payload["latest_version"], "Version 1.90")

    def test_corrupt_local_update_metadata_falls_back_without_send_rollback_state(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            app_dir = root / "app"
            (repo / "Output").mkdir(parents=True)
            app_dir.mkdir(parents=True)
            (repo / "Output" / "update_metadata.json").write_text("{broken", encoding="utf-8")
            (app_dir / ".shower_update.json").write_text("{also-broken", encoding="utf-8")
            app.frozen_app_dir = lambda: app_dir
            app.git_head_without_git = lambda _repo: "fallback-sha"
            with mock.patch.dict("os.environ", {"APPDATA": ""}, clear=False):
                self.assertEqual(app.current_update_revision(repo), "fallback-sha")

    def test_rebuild_script_warns_that_build_is_not_published_automatically(self) -> None:
        script = (ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        self.assertIn("IMPORTANT - PUBLISHING REQUIRED", script)
        self.assertIn("does NOT upload it to GitHub", script)
        self.assertIn("release\\Shower-Programmer-Windows.json", script)
        self.assertIn("release\\Shower-Programmer-Windows.zip", script)

    def test_version_191_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 191)
        self.assertTrue(str(version["marker"]).startswith("VERSION_1_"))
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_91_GLOBAL_ARCHIVE_SEARCH_UPDATE_PUBLICATION", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self_test = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        required = (
            "global_archive_metadata_search",
            "published_package_update_authority",
            "explicit_update_publish_handoff",
            "safe_update_metadata_fallback",
            "version_1_91_global_archive_search_update_publication",
        )
        for flag in required:
            self.assertIn(flag, flags)
            self.assertIn(f'"{flag}": True', self_test)


if __name__ == "__main__":
    unittest.main()
