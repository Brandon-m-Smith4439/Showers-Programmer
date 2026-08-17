# Shower Programmer Changelog

All user-facing releases are tracked here. The current version is stored in `Backend/version.json`, displayed by the application, and written into update-package metadata by the rebuild script.

## [Version 1.19] - 2026-08-17

### Changed
- Location-based REMAKE routing now accepts the common Location forms **REMAK**, **REMAKE**, **REMAKES**, **REMAKED**, **REMAKING**, and other Location tokens beginning with the `REMAK` stem. The same variants are recognized in reverse-extracted A+W text such as `REMAKESLocation:`.
- Variant matching remains scoped strictly to parsed **Location** values. REMAKE wording in project names, customer notes, hardware notes, or other PDF text does not automatically route an order as a remake.

### Regression Coverage
- Added executable coverage for all supported REMAKE Location variants in both conventional and reverse-extracted field layouts, plus false-positive guards for unrelated REMAKE notes and normal Location values.

## [Version 1.18] - 2026-08-17

### Fixed
- Sent-input cleanup performs a lightweight late-arrival sweep before completed process-list retirement and keeps the process list active when a matching sent input still cannot be archived, preventing a sent local file from becoming **Input Without Process List**.
- Location-based REMAKE detection now handles reverse-extracted A+W fields such as `REMAKELocation:` as well as conventional `Location: REMAKE`.
- **Process All** automatically routes a PDF-proven REMAKE through remake processing without requiring the manual REMAKE batch selection.

### Regression Coverage
- Added coverage for late local inputs during sent cleanup, locked sent inputs preventing process-list retirement, reverse Location extraction, and automatic Process All REMAKE routing.

## [Version 1.17] - 2026-08-17

### Changed
- **DXF Rotation** in the DXF Reference card now uses adaptive precision instead of a fixed decimal count. Whole-number rotations display as whole numbers (`90 deg`), concise fractional rotations keep only meaningful trailing digits (`89.85 deg`), and detailed rotations can display up to six decimal places (`-90.154436 deg`). Values longer than six decimal places are rounded at the sixth decimal.
- Adaptive formatting remains display-only. DXF geometry, manual rotation overrides, OOS correction math, and generated CNC coordinates retain their original full internal precision.
- Programming-evidence rotation/correction text keeps its established compact formatting so historical evidence output remains stable.

### Regression Coverage
- Added executable coverage for whole-number display, trailing-zero removal, six-decimal preservation, sixth-decimal rounding, negative near-zero normalization, panel rotation summaries, and preservation of compact programming-evidence formatting.

## [Version 1.16] - 2026-08-17

### Fixed
- Multi-revision Archive Test Mode now restores each logical order's PDF/DXF from the newest revision that actually contains the corresponding source file, falling back through older revisions when a newer process-list revision did not re-archive the physical order files. PDF and DXF fallback are resolved independently.
- Batch Test Mode no longer activates merely because a consolidated process list was created. It validates that archived source files were restored for every logical order and reports the missing A&W order(s) instead of entering an apparently populated Test Mode with an empty Orders list.
- Archive file lookup prefers filename/job correlations across revision folders before opening PDFs, reducing unnecessary PDF reads during heavily revised batch restoration.

### Regression Coverage
- Added a five-revision archive regression where three logical orders have their physical PDF/DXF files only in older revision folders, proving the isolated Test Workspace receives all source files plus one consolidated process list.

## [Version 1.15] - 2026-08-17

### Performance
- Legacy binary `.xls` process-list normalization now opens Excel read-only with link updates, events, screen updating, and compatibility prompts disabled. This removes unnecessary Excel work during the one-time XLS-to-XLSX normalization path.
- Converted XLSX files now retain a source-content SHA-256 sidecar. If Network Input recopies the same `.xls` with a newer timestamp but identical bytes, Shower Programmer reuses the existing conversion instead of launching Excel again. Conversion progress now reports whether Excel was skipped and, when conversion is required, its elapsed time.

### Fixed
- Logical archive batches containing multiple revisions now always use one synthetic consolidated `.xlsx` process list for Restore Batch and Batch Test Mode. The newest duplicate A&W record still wins and older-only orders remain in the union, but competing archived process-list revisions (including legacy `.xls` copies) are no longer restored together or selected as an arbitrary authoritative file. This makes heavily revised batches such as a five-revision batch deterministic in Test Mode.

### Changed
- The DXF Reference card no longer repeats `DXF units:` beneath the **DXF Units** heading; it displays only the value such as `inches`.
- The DXF Reference card no longer repeats `DXF rotation:` beneath the **DXF Rotation** heading. Degree values now display four decimal places while all underlying geometry continues using full precision. Programming-evidence rotation/correction text intentionally keeps its established compact formatting so the DXF Reference display change does not alter historical evidence contracts.

### Regression Coverage
- Added coverage for content-identical XLS conversion reuse, low-overhead Excel COM options, five-revision archive consolidation to one synthetic XLSX, concise four-decimal DXF reference text, and preservation of compact programming-evidence degree formatting.

## [Version 1.14] - 2026-08-14

### Changed
- DXF Reference rotation and correction values are now formatted to at most two decimal places for operator readability. Programming evidence/report rotation values use the same concise display formatting; all geometry and CNC calculations retain full internal precision.
- Test Mode now shows a persistent full-width warning banner stating that the workspace is isolated and production Send is disabled. The application title also begins with **TEST MODE** while active, and the existing bottom **Exit Test Mode** control remains visible.

### Safety
- Closing Shower Programmer while Test Mode is active now restores the production Input/Process List/Output paths, cache, and production lifecycle store before the Tk application shuts down. Close-time Test Mode exit deliberately does not start a new production scan.
- If Test Mode restoration unexpectedly fails during shutdown, the operator is warned and can choose to keep the application open rather than silently closing in an unresolved Test Mode state.

### Regression Coverage
- Added executable coverage for two-decimal DXF display formatting, the persistent Test Mode visual state, close-time Test Mode restoration without a rescan, and shutdown ordering.

## [Version 1.13] - 2026-08-14

### Fixed
- Fixed **Delete Local Input Files** and **Delete Local + Network Input Files** failing before the cleanup worker started with `unhashable type: 'list'`. `order_batch_ids` stores a list of batch ids per A&W order, and the Version 1.12 scope calculation incorrectly tested that whole list directly against a set.
- Delete scope now checks each mapped batch id individually. A single-order delete remains `order` scope, while a fully selected batch is recorded as `batch` scope even when an order is represented in more than one batch/revision mapping.

### Regression Coverage
- Updated the Version 1.12 context-selection fixture to use the real list-valued `order_batch_ids` structure.
- Added executable coverage for single-order deletion, multi-batch/revision mappings, and correct order-versus-batch deletion-scope resolution.

## [Version 1.12] - 2026-08-14

### Fixed
- Orders context-menu delete actions now capture the exact selected order(s) and batch ids before the themed popup is retired. **Delete Local Input Files** and **Delete Local + Network** no longer reread Treeview selection after popup focus/teardown, preventing a destructive action from silently becoming a no-op.
- Context-menu commands now execute immediately after the popup is hidden; fragile CustomTkinter popup destruction is deferred until afterward. Any command exception is surfaced through the main status/error UI instead of disappearing inside a Tk callback.
- Delete startup now updates the main status immediately with the targeted order count and cleanup scope before background file discovery begins.

### Changed
- Individual orders in **Input Without Process List** now expose **Delete Local + Network Input Files** directly. Shared deletion remains restricted to input-only orders; normal process-list orders remain local-delete only.
- Existing Version 1.09 local-only post-delete refresh remains unchanged: deleting locally does not automatically re-import from shared input, while a later deliberate **Scan Orders** can re-import a local-only deletion.

### Regression Coverage
- Added executable coverage proving context-snapshot deletion never rereads the Treeview, context commands run before deferred popup teardown, callback exceptions are surfaced, and a single input-only order is eligible for validated local+network deletion.

## [Version 1.11] - 2026-08-14

### Fixed
- Added a second strict DXF-backed dimension reconciliation path for irregular/out-of-square pieces where the sketch dimensions match the source DXF envelope but A+W reports a nearby process-size representation instead of the raw DXF bounds.
- A&W 236465 / `89183226 KINSDALE 132` now reconciles automatically from `15.96875 x 46.34375` to the sketch/DXF envelope `15.75 x 46.375` because the supplied source DXF proves a `0.125 in` out-of-square shift. The manual **Allow Dimension Mismatch** override is no longer required for this geometry.

### Safety
- The new path does not raise the normal `0.2000 in` PDF tolerance. It requires the sketch to match the source DXF envelope within the existing strict DXF tolerance, requires genuine non-axis-aligned/OOS geometry, and limits the A+W-to-DXF variance to `0.2500 in` per dimension.
- Rectangular DXFs, unrelated sketch dimensions, and process-list dimensions beyond the guarded variance remain rejected. Duplicate-job PDF selection remains strict and does not use the OOS fallback.

### Diagnostics
- Successful reconciliation records whether the match came from the original A+W/DXF-bounds rule or from the new sketch/DXF-envelope rule, including the proven OOS shift and A+W-to-DXF deltas.

## [Version 1.10] - 2026-08-14

### Fixed
- Fixed themed Orders context-menu actions being able to disappear without executing when CustomTkinter popup destruction raised during teardown. Context actions are now hidden/unregistered first, dispatched on the Tk event loop, and only then cleaned up. This restores **Delete Local Inputs** and **Delete Local + Network Batch** execution and their normal loading-bar workflow.
- Added executable regression coverage for both local-delete entry points so future releases must prove they actually schedule the cleanup worker rather than only containing the expected source text.

### Added
- Diagnostic-package completion now includes an **Open Folder** button that immediately opens the folder containing the generated diagnostic ZIP while leaving the completion popup available.
- The shared themed notice component now supports an optional secondary action button for future operator workflows.

### Dimension Investigation
- The supplied A&W 236465 / KINSDALE 132 evidence confirms a real irregular/OOS dimension representation: the process list reports `15.9688 x 46.3438`, while the sketch contains multiple edge dimensions (`15-3/4`, `15-1/2`, `46-1/8`, `46-3/8`) and repeated `1/8` offsets. Version 1.10 does not loosen the global dimension tolerance; the actual source DXF is still required before adding another automatic geometry exception.

## [Version 1.09] - 2026-08-14

### Changed
- Successful local or local+network order cleanup now refreshes the Orders workspace strictly from the local `Input\Orders` and `Input\Process List` folders instead of immediately running a shared-network Scan Orders synchronization.
- Local deletion scope (`order` versus `batch`) remains in processing history for audit purposes, but it no longer permanently blocks a later deliberate re-import.

### Fixed
- Corrected the Version 1.09 release-marker entry in `Backend/shower_v4_features.py` so the metadata-driven rebuild validator recognizes the release consistently.
- Corrected the Version 1.09 upgrade package to include the Version 1.08 `Backend/shower_batch.py` dimension-difference diagnostics dependency, so the focused KINSDALE regression does not depend on an earlier partial overlay having installed that file.
- A later operator-initiated **Scan Orders** can reactivate a locally deleted order when its current-signature process-list entry remains active and the required PDF/DXF files are still available in shared input. Reactivation happens before completed-batch retirement so a stale deletion receipt cannot retire the process list first.
- Local-only refresh skips shared process-list import, shared PDF/DXF synchronization, Production Sketches reconciliation, and automatic network cleanup, preventing a just-deleted local order from immediately returning.

### Safety
- Valid current-signature Sent receipts remain terminal and are not reactivated merely because a stale shared input copy exists.
- Local deletion and later manual re-import remain separately auditable in Action History/SQLite lifecycle state.

## [Version 1.08] - 2026-08-14

### Changed
- Consolidated archive batch parent rows now show their own **Sent** summary and **In Input** summary. Fully sent batches show one sent date or a date range; partially sent batches show a partial count plus the applicable sent-date range. Input state shows Yes, No, or a partial count.
- Successful **Delete Local Inputs** and **Delete Local + Network Inputs** operations now automatically rescan the current workspace after the completion dialog closes so the Orders tree is rebuilt from current process-list/input evidence instead of relying on manual row surgery alone.
- Dimension-mismatch messages now include the closest per-item numeric width/height differences, the normal tolerance, and how far a dimension exceeded that tolerance.

### Fixed
- Individual-order deletion receipts are now marked separately from full-batch deletions. Re-importing a shared process-list batch can reactivate a deliberately deleted full batch, but it will not silently restore a single order that the operator intentionally deleted. Legacy deletion receipts remain compatible when every current order in a re-imported batch carries the old deletion pattern.

### Safety
- Archive batch status is calculated from the complete logical batch, even when archive filters temporarily hide some child orders.
- Generic dimension tolerance remains unchanged; Version 1.08 adds diagnostics only. DXF-proven reconciliation still controls geometry exceptions.

## [Version 1.07] - 2026-08-14

### Changed
- Action History keeps its compact live progress/status strip visible, while the detailed diagnostics log and **Retry Load**, **Open History Folder**, and **Copy Diagnostics** controls now live inside a collapsed-by-default **Diagnostics** expander. The expander opens automatically when loading or rendering fails.
- Settings > Archives now shows one logical archived batch per normalized numeric batch number instead of separate parent rows for every dated copy/revision of the same process-list batch.

### Archive Revision Handling
- The newest archived revision is authoritative for the batch label/process-list metadata and for duplicate A&W orders that appear in multiple revisions.
- Orders that exist only in an older revision remain in the consolidated logical batch so an updated batch does not erase historical orders from the archive browser.
- Batch Restore/Test Mode uses the newest process list when it already represents the complete order union. If older-only orders must be preserved, Shower Programmer creates one scoped synthetic process list containing the consolidated order set instead of restoring multiple competing revisions of the same batch.
- Consolidated batch parents show their revision count so operators can tell when several archived copies were folded into one logical batch.

### Safety
- Individual archived-order actions still use that order's selected archived revision. Consolidation changes only whole-batch presentation/action scope and does not delete or rewrite dated archive files.

## [Version 1.06] - 2026-08-14

### Fixed
- Fixed Settings > Action History stopping during tab construction before its loader/progress/table controls were created. The Order actions only checkbox now uses supported CustomTkinter checkbox styling instead of an invalid progress-color option.
- Settings lazy-tab construction now surfaces any future builder exception directly inside the affected tab and records a Settings Tab Build Failure audit entry instead of leaving a mysterious partial page.

### Added
- Added a dedicated Action History diagnostic panel with a live progress bar, stage messages, candidate/history file paths, file sizes, records read, matching records, invalid JSON-line warnings, elapsed time, and render status.
- Added **Retry Load**, **Open History Folder**, and **Copy Diagnostics** controls so Action History failures can be investigated from the workstation without guessing.
- Background-task error events now include the captured Python traceback; the Action History diagnostics panel displays it when a worker fails.

### Safety
- Action History still defaults to the most recent seven days and reads only the current history file plus monthly archive files intersecting the selected date range. Read/inspection failures now surface explicitly instead of being silently treated as an empty history.

## [Version 1.05] - 2026-08-13

### Fixed
- Action History no longer attempts to hydrate all historical JSONL archives before showing the normal operator view. The Settings tab now loads only the requested calendar window, defaulting to the most recent seven days.
- Action History loading now runs on a Settings-owned background task runner with visible progress/error state, so a large history file cannot make the tab appear permanently blank or frozen. Search, Action, Result, and Order-only filters operate against the already-loaded date window instead of rereading disk on every filter change.
- Reopening the persistent Settings window refreshes the selected Action History date range without rebuilding the Settings widget tree.

### Changed
- Added From/To date controls to Action History with **Apply Range**, **Last 7 Days**, and **Cancel Load**. A single supplied date loads that one day. Only monthly archive files intersecting the requested range are opened.
- Simplified the Archives tab: the archive/run selector is now a two-state segmented control, **Load 7 More Days** lives beside the date controls, and the duplicate **Refresh Range** footer button was removed. The lower action card now focuses on Archive Sent Inputs, Return, Restore, and Test Mode for the current order/batch selection.
- Settings now opens maximized on first launch and when reopened, while retaining the persistent hide/show close behavior introduced in Version 1.03.

### Performance
- Date-windowed Action History avoids reading unrelated monthly history archives and keeps history disk I/O off the Tk UI thread.
- Archive filtering/paging remains seven-day and SQLite-index backed; the GUI cleanup does not weaken the existing archive batching, sorting, or Test Mode behavior.

## [Version 1.04] - 2026-08-13

### Fixed
- Fixed the persistent Settings window leaving the Archives tab unable to reload after Settings was hidden while archive work was active. The archive event poll now remains alive long enough to consume cancellation/completion events, so `refresh_inflight` cannot remain permanently stuck.
- Reopening the persistent Settings window now explicitly reactivates the selected data tab. Archives refreshes its current date range when needed, and Action History reloads whenever its tab is selected again.
- Archive load failures no longer apply an empty result as though the requested date range loaded successfully. Failed ranges remain retryable and display the actual error in the Archives tab.
- Action History now shows a visible loading/error state and refreshes from disk when revisited instead of relying only on its one-time lazy-build callback.

### Added
- Added an Archives-tab progress surface with a determinate/indeterminate loading bar, current stage text, item/date counts, completion timing, Cancel, and Retry controls.
- Archive progress now distinguishes loading, completed, completed-with-notes, cancelled, and failed states without using the main production progress bar.

### Safety
- Archive browsing remains on its Settings-owned background task manager and never blocks the production workspace. Closing Settings requests safe cancellation but keeps the lightweight queue lifecycle intact so background completion cannot orphan the tab state.
- The Version 1.03 persistent hide/show Settings lifecycle remains unchanged.

## [Version 1.03] - 2026-08-13

### Fixed
- Replaced ordinary Settings-window destruction with a persistent hide/show lifecycle. Clicking the Windows X button or pressing Escape now withdraws the intact Settings Toplevel instead of recursively destroying its CustomTkinter descendants, eliminating the blank native Settings shell that could remain after its contents disappeared.
- A hidden Settings window is reused with its controls intact; a genuinely damaged or childless shell is retired from reuse and hidden without attempting the same fragile recursive destroy path again.
- Application shutdown now quits the Tk main loop before attempting final root destruction so a descendant cleanup exception cannot strand the process during exit.

### Changed
- Settings tabs are now built lazily. Opening Preferences constructs only the Preferences content; Folder Setup, Hinge Detection, Archives, Recovery, Backup & Restore, and Action History are built the first time each tab is selected. This reduces Settings startup work and avoids creating complex hidden widget trees unnecessarily.
- The existing lazy Archives I/O behavior remains: archive disk/index work still begins only when Archives is selected.

### Safety
- Closing Settings continues to cancel Settings-owned archive work, release descendant grabs, clear temporary topmost state, and restore focus to the main window, but no normal Settings close issues a widget-tree `destroy`.

## [Version 1.02] - 2026-08-13

### Fixed
- Fixed the Settings window being able to turn into an empty, reusable shell when CustomTkinter child-widget cleanup raised before the parent Toplevel itself was destroyed.
- Settings now unregisters and hides itself immediately, attempts normal CustomTkinter cleanup, verifies the actual Tcl/Tk Toplevel no longer exists, and falls back to a direct Tcl `destroy` of the parent shell if recursive widget destruction aborted.
- The Settings button now refuses to reuse a window that is already closing or has lost all of its child content, preventing a stranded blank shell from being brought back to the front.

### Safety
- A failed first native-window teardown no longer permanently locks the close handler. The shell stays hidden/unregistered, an idle forced-destroy retry is scheduled, and another Settings window can be opened normally instead of reusing the damaged one.
- Settings tab references are cleared only when they belong to the window being destroyed, so a delayed destroy event from an older Settings window cannot clear a newly opened Settings workspace.

## [Version 1.01] - 2026-08-13

### Fixed
- Fixed Settings being able to leave the application inaccessible or visually blank after the Settings window was closed while its archive browser was loading.
- Closing Settings now explicitly cancels Settings-owned archive work, releases any Tk grab held by the Settings window or one of its descendants, destroys the window, and returns focus to the main application.

### Changed
- Opening Settings on Preferences no longer automatically starts archive discovery. The archive browser now loads its default seven-day window only when the Archives tab is actually selected.
- Archive browsing now uses a Settings-owned instance of the shared background-task framework instead of the production task runner, so loading archive history does not disable the main production workspace.
- Archive worker callbacks communicate through a thread-safe queue; the worker never calls Tk widgets directly.

### Safety
- Closing Settings during an archive load is safe and immediate from the operator's perspective. Cancellation remains cooperative in the worker, but the production UI is no longer held disabled while that Settings-only task finishes its current safe filesystem step.

## [Version 1.00] - 2026-08-13

### Fixed
- Restored clear borders/dividers around table column headers across the Orders, Archives, Action History, and other ttk Treeview surfaces.
- Fixed whole-batch Archive Test Mode so the scan that runs after activation stays inside the isolated Test Workspace. Test Mode no longer indexes/copies shared-network input, reconciles Production Sketches, retires production process lists, or performs automatic production/shared cleanup.
- Batch archive actions now resolve the full loaded batch even when the archive browser is currently filtered, so Batch Test Mode/Restore/Return do not silently operate on only the visible filtered children.

### Added
- Action History now records successful local deletion, local+network deletion, incomplete shared deletion attempts, archived-order/batch restore, archived-order/batch return, Archive Sent Inputs cleanup, Test Mode entry/exit, deleted-order reactivation, and Import EDI activity in addition to the processing/review/send actions already recorded.
- Action History now has exact **Action** and **Result** filters plus an **Order actions only** filter in both the standalone history window and Settings > Action History. Search and Last 7 Days/Archive/All scope controls remain available.
- Added **Open Network Input** directly to Settings > Preferences > Application, in addition to the existing Production Dashboard and Folder Setup quick access.

### Safety
- Shared-network Import EDI is blocked while Test Mode is active so an archived test workspace cannot accidentally pull current production network input into the isolated batch.
- Delete activity remains auditable at the A&W order level while the existing SQLite lifecycle DELETED_LOCAL transition and seven-day recovery behavior are preserved.

## [Version 0.99] - 2026-08-13

### Added
- Added **Network Input** quick access beside Local Input on the Production Dashboard. The same shared-folder action is available from Settings > Folder Setup and always uses the currently configured Import From path.
- Archive batch rows are now first-class action targets. Selecting a collapsed batch can restore the full batch to Input, return the full batch to its dated archive, or open the entire batch in one isolated Test Mode workspace.
- **Archive Sent Inputs** scopes itself to the selected order or batch when one is selected; with no selection it continues to operate on the loaded archive range.
- Batch Test Mode restores the archived process list as a batch whenever possible, copies all matching order PDF/DXF inputs into one isolated workspace, records every order as TESTING in the workspace SQLite database, and keeps production Send disabled.
- Whole-batch Restore, Return to Archive, Batch Test Mode preparation, and already-sent archive cleanup run through the shared background task manager with live progress and safe cancellation boundaries so large archive actions do not freeze Settings.

### Visual Polish
- Refined the main dashboard header into a compact quick-access surface, strengthened the title hierarchy, added a purpose-built network-folder icon, and increased Orders/Archive table row and header spacing for easier scanning.
- Refined the Archive Browser with a polished header card, clearer selection guidance, and action buttons whose labels change between order-level and batch-level operations.
- Added a Quick Folder Access surface to Settings > Folder Setup for Local Input, Network Input, and Output.

### Safety
- Batch restore/Test Mode preserves the original dated archive. Conflicting active filenames receive unique targets rather than silently overwriting different content.
- Returning a restored batch reuses the existing per-order archive correlation safeguards and also cleans up any synthetic fallback batch process list.
- Existing Version 0.98 lifecycle, SQLite, structured-error, and production-send protections remain intact; batch archive work now extends the same centralized task/progress/cancellation contract.

## [Version 0.98] - 2026-08-13

### Added
- Added a durable SQLite operational database at `Output/shower_programmer.sqlite3` for authoritative order lifecycle state, stable process-list batch identities, archive indexing, performance timings, and structured error history. Existing JSON histories remain supported and are migrated non-destructively for backward compatibility.
- Added explicit lifecycle states for discovered, active, ready, issues, processed, sent, deleted-local, archived, isolated testing, reactivated, and input-without-process-list orders. Lifecycle transitions are retained as an audit trail.
- Added a reusable background task manager with one production-affecting task at a time, common progress reporting, safe cancellation boundaries, Tk-thread completion callbacks, and elapsed-time recording. Scan, Import EDI, Process Orders, Validate Selected, Send Output, local/shared cleanup, and Archive Browser loads now use this common task contract.
- Added a persistent SQLite archive index. Unchanged dated archive folders are served from the database instead of reparsing process-list workbooks, while new or modified archive dates are refreshed automatically.
- Added structured internal error codes such as dimension mismatch, missing process order, ambiguous PDF, network timeout/I/O, locked file, cancellation, and internal error. Error history is stored in SQLite so tests and diagnostics no longer depend on exact popup wording.
- Failed order dialogs can create a one-click diagnostic package containing the selected order files plus lifecycle events, recent performance data, configuration evidence, and structured error context.
- Added isolated **Test Mode** for archived orders. It creates a dedicated `Test Workspace` with its own Input, Process List, Output, cache, and SQLite state database; production Send actions are disabled until Test Mode is exited.
- Added regression coverage for lifecycle transitions, stable batch identity, task cancellation, SQLite archive reuse, archive cancellation, structured errors, performance instrumentation, isolated Test Mode, idempotency, and the representative multi-state “bad day” workflow.

### Changed
- Stable split-batch A&W merging now lives in `shower_batch.py` core instead of being installed as release-time monkey patches. The v4 integration layer retains only compatibility delegates and the remaining isolated production-safety integrations.
- Re-imported-batch `REACTIVATED` is now an audited transition rather than a sticky final state; the next normal scan resolves the order to its current ACTIVE/READY/PROCESSED/SENT state from real evidence.
- Archive searches now use the same central progress/cancellation system and expose safe cancellation between archive-date indexing steps.
- SQLite read connections are explicitly closed after each operation while retaining WAL mode and short-lived worker-safe connections.

### Safety
- The SQLite database supplements rather than deletes the existing processing-history/action-history files, allowing a gradual migration with existing installations.
- Test Mode never repoints production shop destinations and blocks all production Send entry points.
- Cancellation is cooperative and occurs only at safe boundaries; completed file copies/deletions are not rolled back blindly.
- Archive index validity is based on dated-folder signatures, so edited archive contents automatically invalidate and rebuild only the affected date.

## [Version 0.97] - 2026-08-13

### Fixed
- Re-scanning a process-list batch that was explicitly deleted locally no longer immediately retires the freshly re-imported process list and leaves its network PDF/DXF files under **Input Without Process List**.
- When a process list is genuinely copied back from the shared input folder, Shower Programmer now clears only matching explicit-deletion receipts for orders in that re-imported batch before completed-batch retirement runs.
- Manual **Import EDI Orders** also reloads process-list state when a shared process list was restored, avoiding stale in-memory order context.

### Safety
- Sent receipts are never cleared by batch reactivation, so previously sent production work remains protected by the existing sent-history rules.
- Reactivation is limited to process-list batches that were actually copied from the shared input folder during the current synchronization; merely seeing old PDFs/DXFs does not bypass process-list identity.
- Reactivation is recorded in processing history with the source process-list name and prior deletion timestamp for auditability.

## [Version 0.96] - 2026-08-13

### Added
- Settings > Archives now starts with only the most recent seven calendar days instead of scanning the entire archive history. **Load 7 More Days** appends the next older seven-day window without reloading records that are already visible.
- Archive date filters support From/To ranges or a single date, plus quick **Last 7 Days** reset behavior.
- Archived inputs are grouped under their original process-list batch and batches start collapsed.
- Archive columns are sortable like the main Orders table. The initial sort is Archive Date descending; clicking A&W, Job, Customer, Files, Sent, In Input, or the batch heading reorders the applicable rows.
- The Archives tab can switch between **Orders / Sketch Archives** and **Processing Runs**. Run history is grouped by run/batch and correlated with processing-history A&W records.
- Search, Sent-state, and In-Input filters operate on the currently loaded archived-input rows without rescanning disk.

### Performance
- Archive browsing now limits filesystem and workbook work to the requested date range, parses independent archived process lists concurrently, and indexes each dated order folder once.
- The initial archive browser uses filename-based PDF/DXF correlation and defers expensive PDF text inspection until an operator actually chooses **Restore for Testing** for a specific order.
- Switching to Processing Runs does not scan run history until that view is requested.

### Safety
- Restore for Testing still performs exact PDF/DXF correlation for the selected order before copying files, so the faster browser index does not weaken archive restore accuracy.
- Existing Version 0.95 background loading remains in place; all archive range loads continue on a worker thread.

## [Version 0.95] - 2026-08-13

### Fixed
- Large local/shared order deletion now runs its file discovery, shared cleanup, recovery moves, verification, history updates, and process-list retirement off the Tk UI thread while reporting progress instead of freezing the application.
- Settings opens immediately while the Archives inventory loads in the background; Recovery and Action History also defer their initial disk refreshes until after the window is visible.
- Archive inventory enrichment reuses one active-input candidate list instead of repeatedly enumerating Input for each archived order.
- Main progress messages were updated where older wording no longer matched the current scan/synchronization workflow.

## [Version 0.94] - 2026-08-13

### Added
- Settings now includes an **Archives** workspace that inventories dated order/process-list archives by A&W order, job, customer, source process list, file count, sent state, and whether a copy is currently back in Input.
- Archived orders can be **restored for testing** without disturbing the dated archive. Shower Programmer copies the archived order files into Input and creates a scoped one-order `Archive Test ...xlsx` process list so regression testing does not reactivate the entire original batch.
- **Return to Archive** removes or returns active test/manual copies to the original dated archive, while **Archive Sent Inputs** cleans up active Input copies for orders that history already marks as sent.
- Order Overview text boxes now support **Increase Size** and **Decrease Size** while remaining isolated from per-piece machine/programming overrides.

### Fixed
- DXF-proven dimension reconciliation now supports raked/trapezoid geometry as well as the Version 0.93 parallelogram case. A&W still has to match the DXF overall bounds, while the sketch may match a proven outer edge span or true sloped-edge length. This handles legitimate cases such as A&W `28.4062 x 94.1875` versus sketch `28 x 94.3125` without loosening the generic PDF dimension tolerance.
- Dimension-mismatch and other long operator dialogs are larger, use larger body text, and present mismatch evidence in labeled sections instead of one dense paragraph.
- REMAKE detection now tolerates A&W PDF extraction forms such as `MASTERLocation:` and multiline `Location:` values and checks the Location field on every PDF page. Unrelated REMAKE notes outside the Location field remain ignored.
- REMAKE banners now use the same fixed-large, glass-anchored placement approach as DIAMON FUSION, including the same large default font and allowance to cross top measurement graphics when needed.
- Rebuild validation now checks the new sectioned, multi-line dimension-mismatch message without assuming the error is a single line, preventing the duplicate-job regression test from falsely failing a valid Version 0.94 build.

### Safety
- Archive testing copies the dated archive instead of moving it. Returning a test order preserves the original archived file; a changed active copy is archived under a unique name rather than overwriting the original.
- Duplicate-Job PDF selection remains strict. DXF-assisted geometry reconciliation is still used only after the order/sketch context has been selected and the DXF proves A&W's overall geometry.
- **Allow Dimension Mismatch** remains available as an explicit operator fallback when neither the normal dimension match nor DXF geometry can prove the order automatically.

## [Version 0.93] - 2026-08-12

### Added
- Automatic out-of-square dimension reconciliation: when normal process-list/PDF dimensions disagree, the order can continue only when the matching source DXF proves that A+W's overall bounding size and the sketch's smaller edge size describe the same OOS geometry.
- Right-click order action **Allow Dimension Mismatch** provides a persistent per-order operator override for exceptional cases that cannot be proven automatically. The override can be cleared from the same menu and never changes machine routing or DXF geometry.

### Fixed
- Mirror and other parallelogram/OOS glass no longer fail PDF identity validation solely because A+W reports overall extents while the sketch labels physical edge lengths.
- Scan preview and actual processing now use the same dimension-override configuration, so an approved exception behaves consistently before and during processing.

### Safety
- DXF-assisted reconciliation is validation-only and is not used to choose between ambiguous duplicate-Job PDFs. Existing duplicate-job safeguards remain strict.
- Manual dimension overrides remain visible as a processing warning so operator-approved exceptions are auditable.

## [Version 0.92] - 2026-08-12

### Added
- Order Overview now supports text-only sketch annotations with move, edit, delete, undo/redo, and Save Sketch Edits. Machine, indicator, flip, DXF, and X controls remain disabled on the overview.
- Refresh Sketch now exposes a visible **Resume Editing** action so externally refreshed PDF annotations can be inspected and editing can continue immediately.

### Fixed
- Review Order now uses a native maximized window state with normal Windows minimize/restore/maximize controls and taskbar-aware sizing instead of any fullscreen fallback.
- The overview sketch and right-side information columns use the same stable sizing contract as piece pages.
- DIAMON FUSION keeps its configured large font size; automatic placement may cross top measurement graphics but remains outside the detected glass.
- Automatic Denver indicator avoidance now keeps the complete painted marker inside the detected glass while avoiding BUG text and local cutout geometry.
- Waterjet indicators are no longer moved by the Denver corner-text/cutout avoidance pass, restoring their independent configured placement.

### Safety
- Overview annotations are stored separately from per-piece machine overrides so cover-page text cannot affect machine classification, indicator selection, hinge orientation, or DXF output.
- Manual indicator coordinates and manual machine/orientation overrides remain authoritative.

## [Version 0.91] - 2026-08-12

### Fixed
\- Review Order is built while hidden and presented once after layout, preventing it from dropping behind the main window or visibly oscillating between panel widths.
\- Canvas resize redraws and control-state updates are deduplicated to keep the review workspace stable.
\- Dragging a text mark no longer treats its text lines as geometric line segments, fixing the `too many values to unpack` sketch-preview failure.
\- Automatic indicators now avoid nearby source text and local cutout geometry while preserving manual positions.
\- DIAMON FUSION is anchored to the detected glass outline and fitted between the glass top and its nearest full-width top measurement.

## [Version 0.90] - 2026-08-12

### Added
\- Review Order now starts with the sketch cover page as a read-only Order Overview when the cover is separate from all piece pages.
\- The overview summarizes process-list descriptions, item counts, generated sketch/program readiness, processing state, issues, review state, and sent state.

### Fixed
\- Refresh Sketch now reopens the saved PDF from disk, invalidates its prior raster, and explicitly renders annotations saved from Microsoft Edge.
\- Automatic sketch indicators make a small bounded move when their marker would cover extracted corner text such as the tempering `BUG` mark.
\- Manual indicator positions, corner choices, and DXF orientation remain untouched by corner-text avoidance.

## [Version 0.89] - 2026-08-12

### Added
\- Preferences now includes an Open Diagnostics Folder button.
\- The Diagnostics folder is created automatically before Windows Explorer opens it.

## [Version 0.88] - 2026-08-12

### Added
\- Local order and process-list deletion now uses a seven-day recovery quarantine with restore and permanent-delete controls in Settings.
\- A separate Why Programmed This Way window exposes panel-level machine, geometry, hinge, rotation, OOS, warning, and override evidence.
\- The main order context menu can create a diagnostic ZIP for one selected order.
\- A non-blocking network-health indicator monitors the configured import, shop sketch, and shop program folders.
\- Settings can export and import configuration backups, with an automatic safety copy before import.

### Reliability
\- Recovery manifests validate approved local roots and avoid overwriting files during restore.
\- Diagnostic packages are order-scoped, size-bounded, and redact credential-like configuration values.
\- Network health checks time out independently and do not block scanning or review.

## [Version 0.87] - 2026-08-11

### Added
\- The Input Without Process List batch now offers a separate Delete Local + Network Batch action.
\- The confirmation identifies the exact local and configured-network PDF/DXF files that will be removed.

### Reliability
\- Shared deletion is restricted to input-only batches and validated root-level matches.
\- If network correlation or deletion cannot complete safely, local files are retained so the order remains visible and cleanup can be retried.

## [Version 0.86] - 2026-08-11

### Added
\- Opening Review Order for an unprocessed order now displays a centered warning with Cancel and Review Anyway choices.
\- Orders with persisted processing history or an existing generated sketch continue opening immediately without an extra prompt.

## [Version 0.85] - 2026-08-11

### Fixed
\- Configured hinge directions now preserve the hinge side confirmed from sketch geometry instead of reversing it during the later configuration pass.
\- Repeated orientation enforcement is stable, preventing correctly calculated hinges-down doors from toggling back to hinges up in the generated DXF.
\- Programming reports replace stale hinge-code reasons with the final side and direction so orientation evidence is no longer contradictory.

## [Version 0.84] - 2026-08-11

### Added
\- Input PDFs without a matching current process-list order remain visible as blocked rows instead of disappearing from the scan.
\- Hinge Detection settings now support adding, editing, removing, and assigning a default hinges-up or hinges-down orientation to every code.

### Interface
\- General prompts are smaller, centered on their owning window, and use a clear two-choice Save or Don't Save layout where applicable.
\- Settings now opens as a large centered window with larger tabs instead of maximizing, and returns to the foreground after child notices close.
\- Hinge-code changes save immediately when confirmed; the separate Save Changes button and required-code labels were removed.

### Reliability
\- Hinge-code matching now tolerates the common letter-O/zero variation, allowing configured `COL037` to match sketch text such as `C0L037`.
\- Real cut-in/FP-S geometry and manual overrides continue to take priority over each hinge code's configurable default orientation.

## [Version 0.83] - 2026-08-11

### Interface
\- Settings now opens maximized on the same display as the main Shower Programmer window.

## [Version 0.82] - 2026-08-10

### Added
\- Added a consolidated Settings workspace with Preferences, Folder Setup, Hinge Detection, and Action History tabs.
\- Source sketches whose Location field contains `REMAKE` now automatically use the established REMAKE processing workflow and retain that status in processing history.

### Interface
\- Removed the duplicate Folder Setup card from the dashboard and consolidated Hinge Detection, Action History, and update/configuration tools under Settings.
\- Reduced the footprint of general notice, success, warning, and failure dialogs while preserving readable details and controls.

### Reliability
\- REMAKE detection is restricted to the PDF Location field so unrelated notes containing the word do not change processing behavior.

## [Version 0.81] - 2026-08-10

### Interface
\- Simplified the shop handoff card to only Select All Orders and Review / Send.
\- Restored the original full-size Workflow buttons and moved the Tools group lower for clearer sidebar rhythm.
\- Enlarged the Orders, Ready, Issues, Processed, and Checked badges and placed them between order search and the column-resize hint.
\- Added responsive toolbar and sidebar layouts so smaller windows retain every action without overlap or clipping.

## [Version 0.80] - 2026-08-10

### Added
\- Orders table headers now sort their column ascending or descending while keeping each process-list batch grouped.
\- A compact order-number search highlights and scrolls directly to matching orders; repeated searches cycle through partial matches.
\- Action History keeps the latest seven days of major scan, processing, review-status, validation, send, and memory-cleanup activity in a searchable local viewer. Older entries move into monthly local archives.
\- Validate Selected performs a read-only input, output, processing, issue, checked-state, and machine-routing review for the selected orders.

### Reliability
\- Active sorting is reapplied after scans and state changes so the table remains organized while work progresses.
\- Packaged self-tests now verify the new search, sorting, validation, and history feature set.

## [Version 0.79] - 2026-08-10

### Interface
\- Removed the obsolete Install Shortcut button from the Tools sidebar now that the application is distributed as a directly runnable folder-based executable.

## [Version 0.78] - 2026-08-10

### Interface
\- Centered the Orders, Ready, Issues, Processed, and Checked summary group within the Orders header.
\- Increased the summary badge dimensions, icons, counts, and labels slightly for clearer at-a-glance status reading.

## [Version 0.77] - 2026-08-10

### Added
\- Review Order now has a dedicated Change Machine button with explicit Denver 1, Denver 2, and Water Jet choices.
\- Hinge Detection now uses a selectable code list with Add New, Confirm Add, and confirmed removal controls. Required PPH identifiers are labeled and protected from removal.

### Fixed
\- Refreshing the sketch preview now reloads the current review model and returns immediately to the editable overlay view. Operators can continue moving and changing marks without closing and reopening the order.

### Interface
\- Orders, Ready, Issues, Processed, and Checked totals were reduced to compact badges and moved into the Orders section header, giving the order table more vertical workspace.

## [Version 0.76] - 2026-08-10

### Fixed
\- Saving a manual Denver-to-Waterjet machine change now immediately rewrites that piece's generated DXF in millimeters with metric DXF headers. The sketch, preview, processing history, and shop program can no longer disagree about the selected machine units.
\- Hinge Detection now includes the core `PPH` and `SRPPH01` identifiers. Existing editable configurations are migrated when the settings window opens, while preserving operator-added hinge codes.
\- Mirror process-list batches continue to ignore Packing/Shipping-only rows when deciding whether the programming work is complete, allowing the local process list to archive after its Waterjet mirror pieces are sent.

### Validation
\- Added regression coverage for manual Waterjet DXF conversion and mirror-batch local process-list archival.

## [Version 0.75] - 2026-08-10

### Fixed
\- Startup scanning now imports files required by active orders before clearing validated files for previously sent orders, preventing stale shared-folder snapshot paths from raising `[WinError 2]`.
\- Shared files that also match an unsent order are protected from sent-order cleanup. This is especially important when two A&W orders use the same Job Nr.
\- A shared source file removed by another workstation between indexing and copying is now skipped safely; the affected order remains missing/flagged instead of aborting the complete scan.
\- File-not-found scan errors now include the processing stage that encountered the missing path.

## [Version 0.74] - 2026-08-10

### Fixed
\- Final sends for a partially delivered process-list batch now reuse filenames from the dated local archive for orders sent earlier. Those earlier orders no longer force a shared-drive PDF-content scan when the batch becomes complete.
\- An order with a validated archive map is considered clean when none of its exact source names remain in the shared snapshot. Unrelated shared PDFs are left untouched instead of being opened to prove an already-completed cleanup.
\- Startup reconciliation now passes the same local archive evidence into cleanup, allowing leftovers from a previously successful production send to be retired without repeating network PDF inspection.
\- If correlation is ever still required and times out, the cleanup note now identifies the unresolved A&W order numbers.

### Performance
\- Completed-batch cleanup performs prior-order correlation against the fast local archive and keeps the bounded network path limited to files that do not have validated local evidence.

## [Version 0.73] - 2026-08-10

### Fixed
\- Sending an individual order now hands the exact locally validated input filenames to shared-folder cleanup. Predictable files such as order `237239` no longer trigger a 15-second scan through unrelated shared PDFs.

### Performance
\- Shared cleanup uses fast A&W/Job Nr filename correlation first and opens PDF content only for orders that still lack validated filename evidence.
\- Local archiving no longer rescans the entire Orders folder after moving each completed batch. A failed local move keeps the affected process list and produces a cleanup warning.
\- Source-name mapping for multi-order archives uses up to four local workers while preserving the existing exact order/PDF/DXF correlation rules.

## [Version 0.72] - 2026-08-10

### Performance
\- Shared input cleanup now indexes the network folder once before deletion and performs up to four independently validated deletions concurrently.
\- Post-delete verification uses one lightweight directory snapshot and inspects only files that arrived during cleanup, avoiding repeated full-folder PDF reads for every completed batch.

### Safety
\- Cleanup has a bounded timeout so an unavailable or stalled network share cannot hold the send workflow indefinitely.
\- Process lists remain untouched when deletion times out, the shared folder changes unexpectedly, post-cleanup verification fails, or batch ownership cannot be established.
\- Transient delete failures receive one retry. Remaining files and indeterminate cleanup conditions are shown in a themed warning popup after the production send completes.

## [Version 0.71] - 2026-08-10

### Fixed
\- Strong radius and positive notch evidence now keeps non-door pieces on Waterjet even when a conflicting process-list row includes Denver routing. This fixes the underlying classification for archived examples `237181.2` and `237191.1` without order-specific overrides.
\- DXF radius pointers now reuse the exact outline transform, correcting vertically and horizontally offset circles such as `237189.2`.
\- OOS labels now render inside the piece with backed, dimension-style text and collision-aware placement around other OOS labels and detected radius cuts.

### Added
\- Added `JRG037` and `GEN180` to door hinge detection.
\- Added a themed **Hinge Detection** settings window so operators can add, remove, or change hinge codes while preserving the rest of the JSON configuration.
\- Standard information, warning, error, confirmation, retry, and save prompts now use a consistent Shower Programmer dialog style.

### Performance
\- Production destination checks and independent sketch/DXF copies now use up to four workers. Atomic targets, existing-file keep/replace choices, progress reporting, and per-file failure recovery remain intact.

## [Version 0.70] - 2026-08-07

### Added
\- Ambiguous sketch rows now open an order-specific resolver with every matching PDF, an Open button for each file, and an editable A&W-specific rename suggestion.
\- Exact local PDF/DXF duplicates now mark only the affected order as an issue. Double-clicking that order opens a keep/remove review with an Open button beside every candidate.
\- DXF Preview now labels the top, bottom, left, and right sides in fractional inches rounded to the nearest 1/16 inch. Metric Water Jet DXFs remain millimeter files while their review dimensions are shown in inches.

### Performance
\- Shared-drive scans now index filenames without opening PDF content or hashing copy candidates on the network.
\- Nonstandard PDF names are copied into a local inspection cache before first-page extraction, and only confirmed matches enter the active Orders folder.
\- New binary `.xls` process lists are copied local first and batch-converted through one hidden Excel session instead of repeatedly launching Excel against the shared drive.
\- Independent PDF/DXF transfers use up to four atomic copy workers, reducing first-import latency while keeping each destination file all-or-nothing.
\- Timestamp-only file comparisons reuse locally cached hashes on later scans, and staging progress updates once per copied network file.

### Safety
\- Existing A&W, Job Nr, dimension, DXF-item, machine, orientation, and manual-override rules remain authoritative.
\- Copy-suffixed files are not declared exact duplicates until their contents are compared locally.
\- OOS labels render inside the outline, side dimensions render outside it, and radius callouts retain their existing collision avoidance.

## [Version 0.69] - 2026-08-05

### Changed
\- Each scan enumerates local sketch PDFs once, then reuses that candidate list for every active order instead of recursively searching the Orders tree per order.
\- Unchanged sketch piece dimensions are cached and reused for duplicate Job Nr validation, avoiding repeated PDF page extraction without removing the dimension check.
\- Local PDF filenames are checked across the full candidate set before any PDF content is opened.
\- Exact duplicate-file hashes are cached so unchanged shared-drive copy candidates are not reread on every scan.

### Performance
\- On the current 24-active-order local benchmark, measured process-list loading, local input checks, filtering, and preview validation improved from approximately 2.10 seconds to 0.29 seconds on a repeat scan.

### Safety
\- A&W order identity, Job Nr matching, process-list dimensions, duplicate-sketch disambiguation, DXF matching, and missing-file recovery rules are unchanged.
\- Cache entries are invalidated using file path, size, timestamp, and content verification when a timestamp changes.

## [Version 0.68] - 2026-08-05

### Changed
\- Legacy `.xls` to `.xlsx` conversion now launches PowerShell in hidden, non-interactive mode.
\- The Excel conversion, Excel process check, and timeout cleanup subprocesses all use the Windows `CREATE\_NO\_WINDOW` flag and hidden startup settings.

### Safety
\- The application still displays conversion progress, retries, and actionable conversion errors in its own interface.
\- Excel remains invisible with alerts disabled; process-list parsing and normalized workbook output are unchanged.

## [Version 0.67] - 2026-08-05

### Fixed
\- A&W orders `237008` and `237009` remain separate even though both use Job Nr `89420398.4 2089 HOLBROOK`; the process-list order-item field is now explicitly protected as the production identity.
\- PDF selection validates process-list dimensions and uses them to distinguish separate copy-suffixed sketches sharing one Job Nr.
\- A missing second sketch is reported instead of silently relabeling a piece from the other A&W order.
\- DXF selection prefers the candidate whose outline dimensions match the process-list piece when same-Job/item filenames collide.

### Safety
\- Copy-suffixed PDFs and DXFs are suggested as duplicates only when their file content is identical. Different source files are preserved even when Windows gave one an `\_1` suffix.
\- Existing Job Nr, item remapping, machine classification, orientation, and manual overrides are unchanged when source identity is unambiguous.

## [Version 0.66] - 2026-08-05

### Fixed
\- Mirror-only process-list batches now load only orders and items carrying an actual Waterjet machine route. Packing/Shipping-only mirror entries no longer appear as work to program or prevent the batch from completing.
\- Completed legacy `.xls` batches now match their converted/local process-list companion by batch name and remove the original export from the shared Showers Programmer Input folder after verified archival.

### Safety
\- Mirror-batch detection is based on mirror glass material descriptions, not customer, project, or job names containing `Mirror`.
\- Mixed-material process lists retain all machine sections. Ordinary shower batches, DXF orientation, and manual overrides are unchanged.

## [Version 0.65] - 2026-08-04

### Added
\- Added one-pass indexing of the shared Showers Programmer Input folder so process lists, order files, duplicate review, and missing-file recovery reuse the same network snapshot.
\- Added a duplicate-file review dialog for PDF/DXF copy variants such as `\_1\_1.dxf` and `\_2\_1.dxf`, with individual file selection and conservative suggested removals.
\- Added per-order input coverage checks so a newly supplied PDF is imported even when that order already has local DXFs, and missing process-list DXF items are recovered independently.

### Changed
\- Unchanged process-list exports remain local and are not recopied or reparsed. Timestamp-only upstream refreshes are verified by content once, then their local timestamps are aligned for fast future scans.
\- Network matching now copies only the PDF or DXF items that are missing locally.

### Safety
\- Duplicate detection only flags a copy-suffixed PDF/DXF when the corresponding unsuffixed sibling exists. Nothing is deleted without an operator selection.
\- Existing machine classification, DXF orientation, manual overrides, and send/archive rules are unchanged.

## [Version 0.64] - 2026-08-04

### Changed
\- Removed the production risk queue, Risk column, High Risk summary card, risk sorting, and Review Highest Risk action.
\- Removed risk fields from processing history and batch text, CSV, and HTML reports.
\- Moved the Machine Decision section below the DXF preview so the preview appears first and receives the larger workspace.
\- Kept the machine decision evidence for glass type, dimensions, process hints, matched DXF, orientation, OOS correction, manual overrides, reasons, and warnings.

### Safety
\- This release changes review presentation only. It does not change machine classification, DXF orientation, process-list normalization, caching, or manual overrides.

## [Version 0.63] - 2026-08-03

### Added
\- Added a Machine Decision inspector to Review Order with glass type, dimensions, process hint, matched DXF, indicator, orientation, OOS correction, manual-override state, reasons, and warnings.
\- Added a production Risk column, High Risk summary count, automatic within-batch risk sorting, and a Review Highest Risk action.
\- Added resilient legacy `.xls` normalization with visible progress, one automatic retry, atomic output replacement, and normalized-file reuse.
\- Added persistent incremental caches for first-page PDF text, parsed process lists, and DXF preview geometry. Timestamp-only copies are verified by content hash before reparsing.
\- Added a data-driven known-order regression library covering mirror glass, project-name false positives, Denver minimum size, `FP-S` short transitions, and PPH hinges-up behavior.
\- Added risk detail to text, CSV, and HTML batch reports.

### Changed
\- Scan completion now reports how many cached resources were reused and refreshed.
\- Review cache warmup now calculates production risk in the background without changing machining decisions.

### Safety
\- Risk scoring and decision inspection are observational only; they do not override machine classification, orientation, or manual edits.
\- Legacy workbook conversion stages to a temporary file and replaces the normalized workbook only after Excel produces a complete result.

## [Version 0.62] - 2026-08-03

### Added
\- Added individual glass-type detection for mirror material, including `1/4 Mirror Annealed` and `1/4 Mirror Clear Annealed`.
\- Mirror glass now always selects Water Jet, even when it has no fabrication keywords or a process-list machine hint says Denver.
\- Added regression coverage for PDF mirror descriptions, process-list mirror descriptions, conflicting Denver hints, and project names containing `Mirror`.

### Changed
\- Mirror detection is evaluated per piece rather than treating every piece in an order as mirror glass.
\- A project or customer name containing `Mirror` does not change ordinary clear glass to Water Jet.

## [Version 0.61] - 2026-08-03

### Fixed
\- Corrected order `236472.2` so its short square-to-angled `FP-S` hinge-side transition is detected from the matched DXF.
\- Doors with that confirmed `FP-S` transition now orient hinges up, move the Denver indicator off the hinge side, keep the square opposite edge on the CNC bottom, and receive the existing manual-review warning.
\- Added a focused regression test for a square hinge-side run that is shorter than the general 20% cut-in threshold.

### Changed
\- Release revisions now advance by `0.01`: `Version 0.61`, `Version 0.62`, `Version 0.63`, and so on.
\- Added editable `auto\_dxf\_fps\_cut\_min\_segment\_ratio` and `auto\_dxf\_fps\_cut\_min\_coverage\_ratio` rules for the narrowly gated `FP-S` fallback.

## [Version 0.6] - 2026-08-03

### Fixed
\- Confirmed `FP-S` full-edge rakes from matched DXF geometry and now records the detected source edge and flattening correction in each panel report.
\- Added a regression check based on order `236472.2`: its 1/4-inch full-height hinge-side rake receives the signed angle correction and becomes flat on the CNC bottom without being misclassified as a cut-in.
\- Replaced the packaged self-test's hard-coded `V40` check with validation against the active release metadata, allowing current-version EXE builds to complete.
\- Reworked release self-test scratch folders to avoid restricted Windows temporary-directory ACLs.
\- Cleared production-send summary state at the start of every send so details from a previous send cannot appear in the next completion message.

### Changed
\- Made the stable rebuild script read the current release metadata instead of requiring manual version-specific edits for each future release.
\- Added focused tests for full-edge `FP-S` rake correction while preserving the rule that only `FP-S` cut-ins/cut-outs require manual review.

## [Version 0.5] - 2026-08-03

### Changed
\- Added a clear gap between each radius label and the start of its leader line so the line no longer touches or crosses the radius text.
\- Added collision-aware radius label placement that avoids existing out-of-square (`OOS`) annotations and other radius labels in the DXF preview.
\- Leader lines now stop at the edge of the radius circle instead of continuing through the highlighted radius location.
\- Removed the redundant **Internal Cut Radius** / **PPH Hinge Radii** summary from the DXF preview header now that each detected radius has an on-drawing callout.
\- Reclaimed the removed header space so the DXF drawing and OOS annotations use the normal preview layout.
\- Standardized the user-facing version format as **Version 0.5**. Future releases increment to **Version 0.6**, **Version 0.7**, and so on.

### Fixed
\- Prevented radius text backgrounds and leader lines from obscuring OOS measurements.
\- Prevented nearby radius labels from stacking on top of one another when multiple internal radii are close together.

## [Version 0.4] - 2026-08-03

### Added
\- Added a production-file conflict review before sending sketches and programs.
\- Added clear **Keep Existing & Continue**, **Replace Existing & Continue**, and **Cancel Send** choices when a different file already exists in a production folder.
\- Added per-file send error handling so one locked or inaccessible production file does not stop unrelated files from being sent.
\- Added DXF preview callouts that draw a leader line and circle around detected Waterjet and PPH internal-radius locations.
\- Added a long-glass edgework rule requiring `SE` on both short end edges when either glass dimension is 113 inches or longer.
\- Added a Waterjet envelope warning when both glass dimensions exceed 75 inches. The affected DXF is skipped for review.
\- Added glass-thickness versus internal-radius validation for Waterjet parts. Each detected internal radius must be at least the glass thickness.
\- Added split-batch order reconciliation so pieces from the same A&W order are combined when glass thickness or type places them in separate process-list files.
\- Added focused automated tests for the Version 0.4 production rules and send workflow.
\- Added a repository-level `README.md` with project, workflow, build, update, and folder guidance.
\- Added `Backend/shower\_programmer\_v4.py` as the release application entry point and `Backend/shower\_v4\_features.py` as the isolated production-safety integration layer.

### Changed
\- Introduced the pre-1.0 user-facing release series as **Version 0.4** after the historical `V40` releases.
\- Replaced the version-specific rebuild filename with the stable `Rebuild Shower Programmer EXE.bat` name.
\- Updated all source launchers to start the release entry point.
\- Reworked the detailed backend README and removed temporary test text.
\- Existing production files that are byte-for-byte identical are now accepted automatically without copying them again.
\- Orders are marked sent and archived only when every requested output is either copied successfully, intentionally kept as an existing production file, or intentionally skipped by the processing options.

### Safety
\- Choosing **Keep Existing** does not modify the conflicting production file.
\- Choosing **Replace Existing** uses the existing atomic-copy helper.
\- Choosing **Cancel Send** stops before production files are changed.
\- A failed individual copy is reported in the completion summary and prevents that incomplete order from being archived as fully sent.

## [V40] - 2026-07-27

### Added
\- Added a visible `V40` badge beside **Production Dashboard**.
\- The version badge opens this changelog on GitHub.
\- Added a **Report Bug** button to the home-page status panel.
\- Bug reports open the repository issue form with the running version and a troubleshooting template prefilled.
\- Added `Backend/version.json` as the single source for the visible version, release marker, release name, and release date.
\- Update dialogs now show installed and available version numbers when release metadata is available.

### Changed
\- The rebuild script now validates that the GUI marker, version file, changelog, packaged self-test, `.shower\_update.json`, and clean update metadata all agree.
\- The clean update metadata now records the release name and GitHub changelog URL.

## [V39] - 2026-07-27

### Fixed
\- Reworked update installation into a pre-copy, self-test, atomic runtime swap, and rollback flow.
\- Prevented a failed update from deleting the working `\_internal` runtime.
\- Added visible update-terminal progress and update logs.

## [V38] - 2026-07-27

### Added
\- Added short `C:\SPU` update staging and controlled ZIP extraction.
\- Added a clean update-only ZIP and JSON metadata generated by the rebuild script.
\- Added deep-path, Tcl/Tk runtime, PDFium, and update-package validation.

## [V37] - 2026-07-27

### Changed
\- Removed the unnecessary scrollbar from the fixed left sidebar.

## Earlier releases

Earlier release details remain documented in the version-specific README files supplied with those packages.
