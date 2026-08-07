# Shower Programmer Changelog

All user-facing releases are tracked here. The current version is stored in `Backend/version.json`, displayed by the application, and written into update-package metadata by the rebuild script.

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
