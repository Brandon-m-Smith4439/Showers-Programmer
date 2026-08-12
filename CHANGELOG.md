# Shower Programmer Changelog

All user-facing releases are tracked here. The current version is stored in `Backend/version.json`, displayed by the application, and written into update-package metadata by the rebuild script.

## [Version 0.91] - 2026-08-12

### Fixed
- Review Order is built while hidden and presented once after layout, preventing it from dropping behind the main window or visibly oscillating between panel widths.
- Canvas resize redraws and control-state updates are deduplicated to keep the review workspace stable.
- Dragging a text mark no longer treats its text lines as geometric line segments, fixing the `too many values to unpack` sketch-preview failure.
- Automatic indicators now avoid nearby source text and local cutout geometry while preserving manual positions.
- DIAMON FUSION is anchored to the detected glass outline and fitted between the glass top and its nearest full-width top measurement.

## [Version 0.90] - 2026-08-12

### Added
- Review Order now starts with the sketch cover page as a read-only Order Overview when the cover is separate from all piece pages.
- The overview summarizes process-list descriptions, item counts, generated sketch/program readiness, processing state, issues, review state, and sent state.

### Fixed
- Refresh Sketch now reopens the saved PDF from disk, invalidates its prior raster, and explicitly renders annotations saved from Microsoft Edge.
- Automatic sketch indicators make a small bounded move when their marker would cover extracted corner text such as the tempering `BUG` mark.
- Manual indicator positions, corner choices, and DXF orientation remain untouched by corner-text avoidance.

## [Version 0.89] - 2026-08-12

### Added
- Preferences now includes an Open Diagnostics Folder button.
- The Diagnostics folder is created automatically before Windows Explorer opens it.

## [Version 0.88] - 2026-08-12

### Added
- Local order and process-list deletion now uses a seven-day recovery quarantine with restore and permanent-delete controls in Settings.
- A separate Why Programmed This Way window exposes panel-level machine, geometry, hinge, rotation, OOS, warning, and override evidence.
- The main order context menu can create a diagnostic ZIP for one selected order.
- A non-blocking network-health indicator monitors the configured import, shop sketch, and shop program folders.
- Settings can export and import configuration backups, with an automatic safety copy before import.

### Reliability
- Recovery manifests validate approved local roots and avoid overwriting files during restore.
- Diagnostic packages are order-scoped, size-bounded, and redact credential-like configuration values.
- Network health checks time out independently and do not block scanning or review.

## [Version 0.87] - 2026-08-11

### Added
- The Input Without Process List batch now offers a separate Delete Local + Network Batch action.
- The confirmation identifies the exact local and configured-network PDF/DXF files that will be removed.

### Reliability
- Shared deletion is restricted to input-only batches and validated root-level matches.
- If network correlation or deletion cannot complete safely, local files are retained so the order remains visible and cleanup can be retried.

## [Version 0.86] - 2026-08-11

### Added
- Opening Review Order for an unprocessed order now displays a centered warning with Cancel and Review Anyway choices.
- Orders with persisted processing history or an existing generated sketch continue opening immediately without an extra prompt.

## [Version 0.85] - 2026-08-11

### Fixed
- Configured hinge directions now preserve the hinge side confirmed from sketch geometry instead of reversing it during the later configuration pass.
- Repeated orientation enforcement is stable, preventing correctly calculated hinges-down doors from toggling back to hinges up in the generated DXF.
- Programming reports replace stale hinge-code reasons with the final side and direction so orientation evidence is no longer contradictory.

## [Version 0.84] - 2026-08-11

### Added
- Input PDFs without a matching current process-list order remain visible as blocked rows instead of disappearing from the scan.
- Hinge Detection settings now support adding, editing, removing, and assigning a default hinges-up or hinges-down orientation to every code.

### Interface
- General prompts are smaller, centered on their owning window, and use a clear two-choice Save or Don't Save layout where applicable.
- Settings now opens as a large centered window with larger tabs instead of maximizing, and returns to the foreground after child notices close.
- Hinge-code changes save immediately when confirmed; the separate Save Changes button and required-code labels were removed.

### Reliability
- Hinge-code matching now tolerates the common letter-O/zero variation, allowing configured `COL037` to match sketch text such as `C0L037`.
- Real cut-in/FP-S geometry and manual overrides continue to take priority over each hinge code's configurable default orientation.

## [Version 0.83] - 2026-08-11

### Interface
- Settings now opens maximized on the same display as the main Shower Programmer window.

## [Version 0.82] - 2026-08-10

### Added
- Added a consolidated Settings workspace with Preferences, Folder Setup, Hinge Detection, and Action History tabs.
- Source sketches whose Location field contains `REMAKE` now automatically use the established REMAKE processing workflow and retain that status in processing history.

### Interface
- Removed the duplicate Folder Setup card from the dashboard and consolidated Hinge Detection, Action History, and update/configuration tools under Settings.
- Reduced the footprint of general notice, success, warning, and failure dialogs while preserving readable details and controls.

### Reliability
- REMAKE detection is restricted to the PDF Location field so unrelated notes containing the word do not change processing behavior.

## [Version 0.81] - 2026-08-10

### Interface
- Simplified the shop handoff card to only Select All Orders and Review / Send.
- Restored the original full-size Workflow buttons and moved the Tools group lower for clearer sidebar rhythm.
- Enlarged the Orders, Ready, Issues, Processed, and Checked badges and placed them between order search and the column-resize hint.
- Added responsive toolbar and sidebar layouts so smaller windows retain every action without overlap or clipping.

## [Version 0.80] - 2026-08-10

### Added
- Orders table headers now sort their column ascending or descending while keeping each process-list batch grouped.
- A compact order-number search highlights and scrolls directly to matching orders; repeated searches cycle through partial matches.
- Action History keeps the latest seven days of major scan, processing, review-status, validation, send, and memory-cleanup activity in a searchable local viewer. Older entries move into monthly local archives.
- Validate Selected performs a read-only input, output, processing, issue, checked-state, and machine-routing review for the selected orders.

### Reliability
- Active sorting is reapplied after scans and state changes so the table remains organized while work progresses.
- Packaged self-tests now verify the new search, sorting, validation, and history feature set.

## [Version 0.79] - 2026-08-10

### Interface
- Removed the obsolete Install Shortcut button from the Tools sidebar now that the application is distributed as a directly runnable folder-based executable.

## [Version 0.78] - 2026-08-10

### Interface
- Centered the Orders, Ready, Issues, Processed, and Checked summary group within the Orders header.
- Increased the summary badge dimensions, icons, counts, and labels slightly for clearer at-a-glance status reading.

## [Version 0.77] - 2026-08-10

### Added
- Review Order now has a dedicated Change Machine button with explicit Denver 1, Denver 2, and Water Jet choices.
- Hinge Detection now uses a selectable code list with Add New, Confirm Add, and confirmed removal controls. Required PPH identifiers are labeled and protected from removal.

### Fixed
- Refreshing the sketch preview now reloads the current review model and returns immediately to the editable overlay view. Operators can continue moving and changing marks without closing and reopening the order.

### Interface
- Orders, Ready, Issues, Processed, and Checked totals were reduced to compact badges and moved into the Orders section header, giving the order table more vertical workspace.

## [Version 0.76] - 2026-08-10

### Fixed
- Saving a manual Denver-to-Waterjet machine change now immediately rewrites that piece's generated DXF in millimeters with metric DXF headers. The sketch, preview, processing history, and shop program can no longer disagree about the selected machine units.
- Hinge Detection now includes the core `PPH` and `SRPPH01` identifiers. Existing editable configurations are migrated when the settings window opens, while preserving operator-added hinge codes.
- Mirror process-list batches continue to ignore Packing/Shipping-only rows when deciding whether the programming work is complete, allowing the local process list to archive after its Waterjet mirror pieces are sent.

### Validation
- Added regression coverage for manual Waterjet DXF conversion and mirror-batch local process-list archival.

## [Version 0.75] - 2026-08-10

### Fixed
- Startup scanning now imports files required by active orders before clearing validated files for previously sent orders, preventing stale shared-folder snapshot paths from raising `[WinError 2]`.
- Shared files that also match an unsent order are protected from sent-order cleanup. This is especially important when two A&W orders use the same Job Nr.
- A shared source file removed by another workstation between indexing and copying is now skipped safely; the affected order remains missing/flagged instead of aborting the complete scan.
- File-not-found scan errors now include the processing stage that encountered the missing path.

## [Version 0.74] - 2026-08-10

### Fixed
- Final sends for a partially delivered process-list batch now reuse filenames from the dated local archive for orders sent earlier. Those earlier orders no longer force a shared-drive PDF-content scan when the batch becomes complete.
- An order with a validated archive map is considered clean when none of its exact source names remain in the shared snapshot. Unrelated shared PDFs are left untouched instead of being opened to prove an already-completed cleanup.
- Startup reconciliation now passes the same local archive evidence into cleanup, allowing leftovers from a previously successful production send to be retired without repeating network PDF inspection.
- If correlation is ever still required and times out, the cleanup note now identifies the unresolved A&W order numbers.

### Performance
- Completed-batch cleanup performs prior-order correlation against the fast local archive and keeps the bounded network path limited to files that do not have validated local evidence.

## [Version 0.73] - 2026-08-10

### Fixed
- Sending an individual order now hands the exact locally validated input filenames to shared-folder cleanup. Predictable files such as order `237239` no longer trigger a 15-second scan through unrelated shared PDFs.

### Performance
- Shared cleanup uses fast A&W/Job Nr filename correlation first and opens PDF content only for orders that still lack validated filename evidence.
- Local archiving no longer rescans the entire Orders folder after moving each completed batch. A failed local move keeps the affected process list and produces a cleanup warning.
- Source-name mapping for multi-order archives uses up to four local workers while preserving the existing exact order/PDF/DXF correlation rules.

## [Version 0.72] - 2026-08-10

### Performance
- Shared input cleanup now indexes the network folder once before deletion and performs up to four independently validated deletions concurrently.
- Post-delete verification uses one lightweight directory snapshot and inspects only files that arrived during cleanup, avoiding repeated full-folder PDF reads for every completed batch.

### Safety
- Cleanup has a bounded timeout so an unavailable or stalled network share cannot hold the send workflow indefinitely.
- Process lists remain untouched when deletion times out, the shared folder changes unexpectedly, post-cleanup verification fails, or batch ownership cannot be established.
- Transient delete failures receive one retry. Remaining files and indeterminate cleanup conditions are shown in a themed warning popup after the production send completes.

## [Version 0.71] - 2026-08-10

### Fixed
- Strong radius and positive notch evidence now keeps non-door pieces on Waterjet even when a conflicting process-list row includes Denver routing. This fixes the underlying classification for archived examples `237181.2` and `237191.1` without order-specific overrides.
- DXF radius pointers now reuse the exact outline transform, correcting vertically and horizontally offset circles such as `237189.2`.
- OOS labels now render inside the piece with backed, dimension-style text and collision-aware placement around other OOS labels and detected radius cuts.

### Added
- Added `JRG037` and `GEN180` to door hinge detection.
- Added a themed **Hinge Detection** settings window so operators can add, remove, or change hinge codes while preserving the rest of the JSON configuration.
- Standard information, warning, error, confirmation, retry, and save prompts now use a consistent Shower Programmer dialog style.

### Performance
- Production destination checks and independent sketch/DXF copies now use up to four workers. Atomic targets, existing-file keep/replace choices, progress reporting, and per-file failure recovery remain intact.

## [Version 0.70] - 2026-08-07

### Added
- Ambiguous sketch rows now open an order-specific resolver with every matching PDF, an Open button for each file, and an editable A&W-specific rename suggestion.
- Exact local PDF/DXF duplicates now mark only the affected order as an issue. Double-clicking that order opens a keep/remove review with an Open button beside every candidate.
- DXF Preview now labels the top, bottom, left, and right sides in fractional inches rounded to the nearest 1/16 inch. Metric Water Jet DXFs remain millimeter files while their review dimensions are shown in inches.

### Performance
- Shared-drive scans now index filenames without opening PDF content or hashing copy candidates on the network.
- Nonstandard PDF names are copied into a local inspection cache before first-page extraction, and only confirmed matches enter the active Orders folder.
- New binary `.xls` process lists are copied local first and batch-converted through one hidden Excel session instead of repeatedly launching Excel against the shared drive.
- Independent PDF/DXF transfers use up to four atomic copy workers, reducing first-import latency while keeping each destination file all-or-nothing.
- Timestamp-only file comparisons reuse locally cached hashes on later scans, and staging progress updates once per copied network file.

### Safety
- Existing A&W, Job Nr, dimension, DXF-item, machine, orientation, and manual-override rules remain authoritative.
- Copy-suffixed files are not declared exact duplicates until their contents are compared locally.
- OOS labels render inside the outline, side dimensions render outside it, and radius callouts retain their existing collision avoidance.

## [Version 0.69] - 2026-08-05

### Changed
- Each scan enumerates local sketch PDFs once, then reuses that candidate list for every active order instead of recursively searching the Orders tree per order.
- Unchanged sketch piece dimensions are cached and reused for duplicate Job Nr validation, avoiding repeated PDF page extraction without removing the dimension check.
- Local PDF filenames are checked across the full candidate set before any PDF content is opened.
- Exact duplicate-file hashes are cached so unchanged shared-drive copy candidates are not reread on every scan.

### Performance
- On the current 24-active-order local benchmark, measured process-list loading, local input checks, filtering, and preview validation improved from approximately 2.10 seconds to 0.29 seconds on a repeat scan.

### Safety
- A&W order identity, Job Nr matching, process-list dimensions, duplicate-sketch disambiguation, DXF matching, and missing-file recovery rules are unchanged.
- Cache entries are invalidated using file path, size, timestamp, and content verification when a timestamp changes.

## [Version 0.68] - 2026-08-05

### Changed
- Legacy `.xls` to `.xlsx` conversion now launches PowerShell in hidden, non-interactive mode.
- The Excel conversion, Excel process check, and timeout cleanup subprocesses all use the Windows `CREATE_NO_WINDOW` flag and hidden startup settings.

### Safety
- The application still displays conversion progress, retries, and actionable conversion errors in its own interface.
- Excel remains invisible with alerts disabled; process-list parsing and normalized workbook output are unchanged.

## [Version 0.67] - 2026-08-05

### Fixed
- A&W orders `237008` and `237009` remain separate even though both use Job Nr `89420398.4 2089 HOLBROOK`; the process-list order-item field is now explicitly protected as the production identity.
- PDF selection validates process-list dimensions and uses them to distinguish separate copy-suffixed sketches sharing one Job Nr.
- A missing second sketch is reported instead of silently relabeling a piece from the other A&W order.
- DXF selection prefers the candidate whose outline dimensions match the process-list piece when same-Job/item filenames collide.

### Safety
- Copy-suffixed PDFs and DXFs are suggested as duplicates only when their file content is identical. Different source files are preserved even when Windows gave one an `_1` suffix.
- Existing Job Nr, item remapping, machine classification, orientation, and manual overrides are unchanged when source identity is unambiguous.

## [Version 0.66] - 2026-08-05

### Fixed
- Mirror-only process-list batches now load only orders and items carrying an actual Waterjet machine route. Packing/Shipping-only mirror entries no longer appear as work to program or prevent the batch from completing.
- Completed legacy `.xls` batches now match their converted/local process-list companion by batch name and remove the original export from the shared Showers Programmer Input folder after verified archival.

### Safety
- Mirror-batch detection is based on mirror glass material descriptions, not customer, project, or job names containing `Mirror`.
- Mixed-material process lists retain all machine sections. Ordinary shower batches, DXF orientation, and manual overrides are unchanged.

## [Version 0.65] - 2026-08-04

### Added
- Added one-pass indexing of the shared Showers Programmer Input folder so process lists, order files, duplicate review, and missing-file recovery reuse the same network snapshot.
- Added a duplicate-file review dialog for PDF/DXF copy variants such as `_1_1.dxf` and `_2_1.dxf`, with individual file selection and conservative suggested removals.
- Added per-order input coverage checks so a newly supplied PDF is imported even when that order already has local DXFs, and missing process-list DXF items are recovered independently.

### Changed
- Unchanged process-list exports remain local and are not recopied or reparsed. Timestamp-only upstream refreshes are verified by content once, then their local timestamps are aligned for fast future scans.
- Network matching now copies only the PDF or DXF items that are missing locally.

### Safety
- Duplicate detection only flags a copy-suffixed PDF/DXF when the corresponding unsuffixed sibling exists. Nothing is deleted without an operator selection.
- Existing machine classification, DXF orientation, manual overrides, and send/archive rules are unchanged.

## [Version 0.64] - 2026-08-04

### Changed
- Removed the production risk queue, Risk column, High Risk summary card, risk sorting, and Review Highest Risk action.
- Removed risk fields from processing history and batch text, CSV, and HTML reports.
- Moved the Machine Decision section below the DXF preview so the preview appears first and receives the larger workspace.
- Kept the machine decision evidence for glass type, dimensions, process hints, matched DXF, orientation, OOS correction, manual overrides, reasons, and warnings.

### Safety
- This release changes review presentation only. It does not change machine classification, DXF orientation, process-list normalization, caching, or manual overrides.

## [Version 0.63] - 2026-08-03

### Added
- Added a Machine Decision inspector to Review Order with glass type, dimensions, process hint, matched DXF, indicator, orientation, OOS correction, manual-override state, reasons, and warnings.
- Added a production Risk column, High Risk summary count, automatic within-batch risk sorting, and a Review Highest Risk action.
- Added resilient legacy `.xls` normalization with visible progress, one automatic retry, atomic output replacement, and normalized-file reuse.
- Added persistent incremental caches for first-page PDF text, parsed process lists, and DXF preview geometry. Timestamp-only copies are verified by content hash before reparsing.
- Added a data-driven known-order regression library covering mirror glass, project-name false positives, Denver minimum size, `FP-S` short transitions, and PPH hinges-up behavior.
- Added risk detail to text, CSV, and HTML batch reports.

### Changed
- Scan completion now reports how many cached resources were reused and refreshed.
- Review cache warmup now calculates production risk in the background without changing machining decisions.

### Safety
- Risk scoring and decision inspection are observational only; they do not override machine classification, orientation, or manual edits.
- Legacy workbook conversion stages to a temporary file and replaces the normalized workbook only after Excel produces a complete result.

## [Version 0.62] - 2026-08-03

### Added
- Added individual glass-type detection for mirror material, including `1/4 Mirror Annealed` and `1/4 Mirror Clear Annealed`.
- Mirror glass now always selects Water Jet, even when it has no fabrication keywords or a process-list machine hint says Denver.
- Added regression coverage for PDF mirror descriptions, process-list mirror descriptions, conflicting Denver hints, and project names containing `Mirror`.

### Changed
- Mirror detection is evaluated per piece rather than treating every piece in an order as mirror glass.
- A project or customer name containing `Mirror` does not change ordinary clear glass to Water Jet.

## [Version 0.61] - 2026-08-03

### Fixed
- Corrected order `236472.2` so its short square-to-angled `FP-S` hinge-side transition is detected from the matched DXF.
- Doors with that confirmed `FP-S` transition now orient hinges up, move the Denver indicator off the hinge side, keep the square opposite edge on the CNC bottom, and receive the existing manual-review warning.
- Added a focused regression test for a square hinge-side run that is shorter than the general 20% cut-in threshold.

### Changed
- Release revisions now advance by `0.01`: `Version 0.61`, `Version 0.62`, `Version 0.63`, and so on.
- Added editable `auto_dxf_fps_cut_min_segment_ratio` and `auto_dxf_fps_cut_min_coverage_ratio` rules for the narrowly gated `FP-S` fallback.

## [Version 0.6] - 2026-08-03

### Fixed
- Confirmed `FP-S` full-edge rakes from matched DXF geometry and now records the detected source edge and flattening correction in each panel report.
- Added a regression check based on order `236472.2`: its 1/4-inch full-height hinge-side rake receives the signed angle correction and becomes flat on the CNC bottom without being misclassified as a cut-in.
- Replaced the packaged self-test's hard-coded `V40` check with validation against the active release metadata, allowing current-version EXE builds to complete.
- Reworked release self-test scratch folders to avoid restricted Windows temporary-directory ACLs.
- Cleared production-send summary state at the start of every send so details from a previous send cannot appear in the next completion message.

### Changed
- Made the stable rebuild script read the current release metadata instead of requiring manual version-specific edits for each future release.
- Added focused tests for full-edge `FP-S` rake correction while preserving the rule that only `FP-S` cut-ins/cut-outs require manual review.

## [Version 0.5] - 2026-08-03

### Changed
- Added a clear gap between each radius label and the start of its leader line so the line no longer touches or crosses the radius text.
- Added collision-aware radius label placement that avoids existing out-of-square (`OOS`) annotations and other radius labels in the DXF preview.
- Leader lines now stop at the edge of the radius circle instead of continuing through the highlighted radius location.
- Removed the redundant **Internal Cut Radius** / **PPH Hinge Radii** summary from the DXF preview header now that each detected radius has an on-drawing callout.
- Reclaimed the removed header space so the DXF drawing and OOS annotations use the normal preview layout.
- Standardized the user-facing version format as **Version 0.5**. Future releases increment to **Version 0.6**, **Version 0.7**, and so on.

### Fixed
- Prevented radius text backgrounds and leader lines from obscuring OOS measurements.
- Prevented nearby radius labels from stacking on top of one another when multiple internal radii are close together.

## [Version 0.4] - 2026-08-03

### Added
- Added a production-file conflict review before sending sketches and programs.
- Added clear **Keep Existing & Continue**, **Replace Existing & Continue**, and **Cancel Send** choices when a different file already exists in a production folder.
- Added per-file send error handling so one locked or inaccessible production file does not stop unrelated files from being sent.
- Added DXF preview callouts that draw a leader line and circle around detected Waterjet and PPH internal-radius locations.
- Added a long-glass edgework rule requiring `SE` on both short end edges when either glass dimension is 113 inches or longer.
- Added a Waterjet envelope warning when both glass dimensions exceed 75 inches. The affected DXF is skipped for review.
- Added glass-thickness versus internal-radius validation for Waterjet parts. Each detected internal radius must be at least the glass thickness.
- Added split-batch order reconciliation so pieces from the same A&W order are combined when glass thickness or type places them in separate process-list files.
- Added focused automated tests for the Version 0.4 production rules and send workflow.
- Added a repository-level `README.md` with project, workflow, build, update, and folder guidance.
- Added `Backend/shower_programmer_v4.py` as the release application entry point and `Backend/shower_v4_features.py` as the isolated production-safety integration layer.

### Changed
- Introduced the pre-1.0 user-facing release series as **Version 0.4** after the historical `V40` releases.
- Replaced the version-specific rebuild filename with the stable `Rebuild Shower Programmer EXE.bat` name.
- Updated all source launchers to start the release entry point.
- Reworked the detailed backend README and removed temporary test text.
- Existing production files that are byte-for-byte identical are now accepted automatically without copying them again.
- Orders are marked sent and archived only when every requested output is either copied successfully, intentionally kept as an existing production file, or intentionally skipped by the processing options.

### Safety
- Choosing **Keep Existing** does not modify the conflicting production file.
- Choosing **Replace Existing** uses the existing atomic-copy helper.
- Choosing **Cancel Send** stops before production files are changed.
- A failed individual copy is reported in the completion summary and prevents that incomplete order from being archived as fully sent.

## [V40] - 2026-07-27

### Added
- Added a visible `V40` badge beside **Production Dashboard**.
- The version badge opens this changelog on GitHub.
- Added a **Report Bug** button to the home-page status panel.
- Bug reports open the repository issue form with the running version and a troubleshooting template prefilled.
- Added `Backend/version.json` as the single source for the visible version, release marker, release name, and release date.
- Update dialogs now show installed and available version numbers when release metadata is available.

### Changed
- The rebuild script now validates that the GUI marker, version file, changelog, packaged self-test, `.shower_update.json`, and clean update metadata all agree.
- The clean update metadata now records the release name and GitHub changelog URL.

## [V39] - 2026-07-27

### Fixed
- Reworked update installation into a pre-copy, self-test, atomic runtime swap, and rollback flow.
- Prevented a failed update from deleting the working `_internal` runtime.
- Added visible update-terminal progress and update logs.

## [V38] - 2026-07-27

### Added
- Added short `C:\SPU` update staging and controlled ZIP extraction.
- Added a clean update-only ZIP and JSON metadata generated by the rebuild script.
- Added deep-path, Tcl/Tk runtime, PDFium, and update-package validation.

## [V37] - 2026-07-27

### Changed
- Removed the unnecessary scrollbar from the fixed left sidebar.

## Earlier releases

Earlier release details remain documented in the version-specific README files supplied with those packages.
