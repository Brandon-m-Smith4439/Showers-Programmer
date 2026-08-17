# Shower Programmer

Shower Programmer is a Windows desktop application that reads A&W shower process lists and glass-order files, classifies each glass piece for Denver or Waterjet programming, marks production sketches, prepares machine DXFs, supports visual review and manual corrections, and sends approved output to the shop production folders.

Current release: **Version 1.19 - REMAKE Location Variant Detection**

Version 1.19 REMAKE Location detection recognizes `REMAK`, `REMAKE`, `REMAKES`, `REMAKED`, `REMAKING`, and other `REMAK...` forms when they appear in the parsed A+W Location field, including reverse-extracted forms such as `REMAKESLocation:`. Matching remains Location-scoped so unrelated REMAKE notes do not alter routing.


Version 1.17 makes the **DXF Rotation** reference value adaptive: whole-number rotations show no decimal, concise values keep only meaningful decimals, and detailed values can use up to six decimal places with rounding at the sixth. The formatting is display-only; geometry/CNC calculations keep full precision.

Version 1.16 hardens multi-revision Archive Test Mode by resolving each logical order's PDF/DXF across all known archive revisions and refusing to activate Test Mode if the required archived source files were not actually restored.

Version 1.15 speeds legacy `.xls` normalization by suppressing Excel link/event/update work and reusing a converted XLSX when a network recopy has identical content. Archive batches with multiple revisions now enter Restore/Test Mode through one consolidated synthetic `.xlsx`, avoiding competing revision files and legacy-XLS conversion inside the isolated workspace. DXF Reference values are also simplified: **DXF Units** shows only the unit value and **DXF Rotation** shows only the degree value. Version 1.17 supersedes the fixed four-decimal display with adaptive precision up to six decimals. Programming-evidence text keeps its established compact degree formatting.

Version 1.14 makes isolated Test Mode unmistakable with a persistent warning banner, a **TEST MODE** window title, and visible Exit Test Mode controls. Closing the application while Test Mode is active restores production paths/state first without starting a new scan.

Version 1.13 fixes delete startup against the real list-valued order-to-batch mapping used by the Orders tree. Delete scope now evaluates each mapped batch id individually, eliminating the `unhashable type: 'list'` failure while preserving Version 1.12 frozen context-menu selection handling. Input-only child orders continue to expose **Delete Local + Network Input Files** directly, and Version 1.11 DXF-proven irregular-dimension reconciliation remains included.

Version 1.09 changes local deletion to refresh only the local Input/Process List view after cleanup. It does not immediately touch shared network input, so a deleted order stays gone locally. A later operator-initiated **Scan Orders** can deliberately re-import that order from shared input when the required PDF/DXF is still available. Delete scope remains recorded for audit history.

Version 1.08 added batch-level **Sent** and **In Input** summaries and numeric dimension-mismatch diagnostics. Its automatic post-delete network rescan and single-order re-import blocking behavior are superseded by Version 1.09, which refreshes locally after deletion and reserves network re-import for an explicit Scan Orders action.

### Archive revision and Action History polish

Version 1.07 keeps the Action History progress/status strip visible while moving the detailed diagnostic log and its Retry Load, Open History Folder, and Copy Diagnostics controls into a collapsed-by-default **Diagnostics** expander. The expander opens automatically when a load/render error occurs, leaving substantially more vertical space for normal history review.

Archived Orders/Sketches consolidate repeated process-list revisions by the numeric batch number embedded in the process-list filename. The newest revision supplies authoritative batch metadata and wins when the same A&W order appears in more than one revision; orders found only in an older revision remain represented so the logical batch is historically complete. Starting with Version 1.15, any batch with multiple archived revisions uses one consolidated synthetic `.xlsx` for Restore/Test Mode, even when the newest revision already contains the full order union. This avoids restoring competing revision files or forcing a legacy `.xls` conversion inside Test Mode.


## Main Workflow

1. Place or import order PDFs and source DXFs into `Input\Orders`.
2. Place supported process-list exports into `Input\Process List`.
3. Start the application with `GUI.bat` or the packaged `Shower Programmer.exe`.
4. Scan the process lists and review detected orders, pieces, machine choices, warnings, sketches, and DXFs.
5. Process selected orders.
6. Mark reviewed orders checked.
7. Use **Review / Send** to send sketches and programs to the production folders and archive completed input files.

## Settings Window Lifecycle and Responsiveness (Versions 1.03-1.07)

Settings uses a persistent hide/show lifecycle so Windows and CustomTkinter do not recursively destroy the complex Settings widget tree on every close:

- Opening Settings on Preferences does not start archive or Action History I/O. Data-heavy tabs begin loading only when selected.
- Archive and Action History browsing use Settings-owned cancellable task runners, so their disk/index work does not mark the production application globally busy.
- Closing Settings requests cancellation of Settings-owned data work, releases any descendant Tk grab, withdraws the intact Settings window, and restores focus to the main program. Reopening Settings reuses that healthy window and maximizes it.
- Background archive workers communicate through queues only and do not touch Tk widgets from worker threads.

## Operator Audit and Test Mode Polish (Version 1.00)

Version 1.00 hardens the operator-facing workflow introduced in 0.98/0.99:

- Table column headers again have visible borders/dividers for easier scanning.
- Whole-batch Archive Test Mode is fully isolated. Its automatic scan reads only the Test Workspace and does not synchronize the shared network input or run production cleanup/reconciliation.
- Archive batch actions always use the full loaded batch, even when filters temporarily hide some child orders.
- Action History records delete, archive restore/return, Test Mode, reactivation, Import EDI, processing/review/send, and other order-affecting actions with A&W identities.
- Action History can be filtered by exact action, result, and order-only activity in addition to text search and time scope.
- Settings > Preferences now includes direct **Open Network Input** access.

## Visual Polish and Batch Archive Actions (Version 0.99)

Version 0.99 builds on the professional 0.98 core with faster operator access and full-batch archive testing:

- **Network Input quick access:** The Production Dashboard now has Local Input and Network Input buttons together in the top-right quick-access surface. Settings > Folder Setup includes the same Network Input action plus Local Input and Output shortcuts.
- **Batch archive actions:** Select a collapsed archive batch to restore the complete batch to active Input, return the complete batch to its dated archive, or open every order in that batch in one isolated Test Mode workspace.
- **Batch Test Mode:** The archived process list is restored as a batch whenever available, all matching order inputs share one isolated workspace, each order receives a TESTING lifecycle record in that workspace SQLite database, and production Send remains blocked.
- **Context-aware archive controls:** Archive action buttons change their labels and scope according to whether an order or batch is selected. Archive Sent Inputs uses the selected scope when present.
- **Visual polish:** Main-header quick actions, archive controls, table spacing, section surfaces, and Folder Setup were refined for a cleaner production-dashboard appearance without changing programming rules.

## Professional Workflow Core (Version 0.98)

Version 0.98 moves Shower Programmer from inferred file state toward an explicit operational model suitable for a long-running production workstation:

- **SQLite operational state:** `Output/shower_programmer.sqlite3` stores lifecycle state, lifecycle transitions, stable batch revisions, archive-index records, performance timings, and structured error history. Existing JSON histories are retained for backward compatibility.
- **Order lifecycle:** Each A&W order has an authoritative current state such as ACTIVE, READY, ISSUES, PROCESSED, SENT, DELETED_LOCAL, ARCHIVED, TESTING, REACTIVATED, or ORPHANED_INPUT, with transitions recorded for auditability.
- **Stable batch identity:** A process-list batch revision is identified from its normalized batch name plus content hash. `.xls` and `.xlsx` companions with identical content resolve to the same identity, while changed content becomes a new revision.
- **Central task manager:** Scan, Import EDI, Process Orders, Validate Selected, Send Output, cleanup, and archive loads share one progress/cancellation contract instead of each inventing its own foreground/background behavior.
- **Safe cancellation:** The main progress area exposes Cancel for managed long-running operations. Cancellation is cooperative at known safe boundaries rather than interrupting a file write in the middle.
- **Persistent archive index:** Recent archive browsing normally comes from SQLite. Only archive dates whose folder signatures changed need their process lists parsed again.
- **Performance evidence:** Major operations and stages record elapsed times so future slowdowns can be diagnosed from measured evidence instead of guesswork.
- **Structured errors and diagnostics:** Common failures have stable error codes. Failed-order diagnostics can include the order's lifecycle, recent performance samples, structured error context, configuration evidence, and relevant files.
- **Isolated archive Test Mode:** Archived production orders can be opened into a dedicated `Test Workspace` with isolated Input/Output/cache/state. Production sending is disabled while Test Mode is active.
- **Smaller release patch layer:** Mature split-batch merging now lives directly in `shower_batch.py`; the v4 feature module remains only for integrations that still benefit from isolation.

## Out-of-Square Dimension Matching

A&W may report the overall bounding width/height of an out-of-square or raked piece while the glass sketch labels a physical edge span or true sloped-edge length. Shower Programmer first uses the normal PDF/process-list dimension check. If that fails, Version 0.94 can reconcile the order only when the matching source DXF proves all of the following:

- the DXF overall bounding size matches the A&W process-list dimensions;
- the DXF contains measurable non-axis-aligned outer geometry; and
- the sketch-reported piece size agrees with a real outer-edge span or physical edge length from that same DXF.

This fallback validates an already-selected PDF; it does not weaken duplicate-Job PDF selection. For an unusual order that still cannot be proven automatically, right-click the order and choose **Allow Dimension Mismatch** after manually verifying the sketch and DXF. The saved override is per A&W order, remains auditable as a warning, and can be removed with **Clear Dimension Override**.

## Production Checks

\- **Re-imported batch reactivation:** If a local batch was explicitly deleted but its process list still exists in the shared input folder, scanning that batch again clears only the matching local deletion receipt after the shared process list is copied back. The batch remains active and its PDF/DXF files are matched normally instead of being shown as Input Without Process List. Sent receipts are preserved.
\- **Fast archive browser:** Settings > Archives initially loads only the newest seven days and keeps batch groups collapsed. Use From/To dates (or one date), **Last 7 Days**, **Load 7 More Days**, search, Sent/In Input filters, and sortable headings to narrow the view without rescanning everything. Switch between **Orders / Sketch Archives** and **Processing Runs**. Archived-input rows are consolidated by logical process-list batch number, with repeated archived revisions shown as one batch; run history remains grouped by run/batch.
\- **Archive testing workspace:** Select either an archived order or a collapsed batch. Order-level restore creates a scoped one-order test process list; batch-level restore/Test Mode brings the complete archived batch together using its archived process list whenever possible. **Return to Archive** works at either scope, and **Archive Sent Inputs** uses the selected order/batch when present. Whole-batch archive actions use the shared background task manager, progress bar, and safe cancellation contract.
\- **Responsive cleanup/settings:** Large local/shared deletes and archive loading run in background workers with live progress, avoiding the long UI freezes that occurred when filesystem work ran directly on Tk's main thread.
\- **Readable operator dialogs:** Error/warning dialogs use larger text and wider layouts. Dimension-mismatch failures are split into Process List, Sketch, validation, and Next Step sections instead of one dense paragraph.
\- **REMAKE detection and banner:** REMAKE is detected from the A&W Location field on the overview or piece pages even when PDF extraction joins `Location:` to preceding text or breaks the value onto another line. The REMAKE banner uses the same fixed-large, glass-anchored placement contract as DIAMON FUSION.
\- **Seven-day file recovery:** Explicit local input deletion moves order and completed process-list files into a manifest-backed Recovery area for seven days. Restore or permanently remove a recovery bundle from Settings.
\- **Programming evidence:** Right-click an order and choose **Why Programmed This Way** to inspect machine, geometry, hinge, rotation, OOS correction, warnings, and manual-override evidence in a separate window.
\- **Diagnostic packages:** Right-click one order to create an order-scoped ZIP containing its matched inputs, process list, generated files, processing evidence, action history, and a redacted configuration snapshot.
\- **Diagnostics folder access:** Open the local Diagnostics folder directly from the Preferences tab. The folder is created automatically on a fresh installation.
\- **Order overview:** Review Order includes the sketch cover page with process descriptions, item/output counts, processing status, issues, checked state, sent state, and text-only sketch editing. Machine and indicator controls remain disabled on the cover page.
\- **Overview text sizing:** Right-click an overview text box to increase or decrease its font size; the size remains stored separately from piece machine/programming overrides.
\- **DIAMON FUSION banner:** DIAMON FUSION keeps its configured large font size and stays outside the detected glass even when it crosses top measurement graphics.
\- **External PDF annotations:** Refresh Sketch reopens the saved PDF and displays annotations saved from Microsoft Edge. Use **Resume Editing** to return immediately to movable sketch overlays.
\- **Indicator placement:** Automatic Denver indicators avoid nearby source text/cutouts while keeping the full marker inside the detected glass. Waterjet placement remains independent from that Denver-only avoidance; manual indicator positions are preserved.
\- **Network health:** The main status area checks the import, shop sketch, and shop program folders asynchronously and shows Online, Partial, or Offline without delaying normal scans.
\- **Configuration backup:** Settings can export or import shop rules, hinge settings, and UI preferences. Import automatically preserves the current configuration first.
\- **Existing production files:** Before sending, the application identifies generated filenames that already exist in the production folders. Identical files are accepted automatically. Different files open a clear dialog where the operator can keep the existing production files, replace them, or cancel the send. Non-conflicting files continue normally.
\- **Per-file send recovery:** A locked or inaccessible file is reported without stopping unrelated files. An order with an unsent required file is not archived as fully sent.
\- **Fast production sending:** Independent sketch and DXF copies, plus existing-file checks, run concurrently while preserving atomic targets and keep/replace decisions.
\- **Radius callouts:** Waterjet and PPH DXF previews circle each detected internal radius and place a spaced leader label beside it. Radius labels avoid OOS annotations and nearby radius labels.
\- **Hinge detection settings:** Use **Hinge Detection** under Tools to add or change hinge codes such as `JRG037` and `GEN180` without editing source code. Core PPH identifiers `PPH` and `SRPPH01` remain available in the editable list.
\- **Manual machine changes:** Saving a review edit after changing a piece from Denver to Waterjet rewrites its program DXF in millimeters, including the metric DXF header expected by Waterjet.
\- **Review workflow controls:** Review Order includes an explicit machine selector, and refreshing a sketch returns directly to the editable overlay view without requiring the order window to be reopened.
\- **Sortable order list:** Click an Orders table heading to sort that column ascending or descending without separating orders from their process-list batch.
\- **Order search:** Use the order-number search above the table to highlight and scroll to an exact or partial A&W order match.
\- **Action History:** Search the last seven days of major workflow activity by action, A&W order, Job Nr, job name, result, or detail. Older entries are retained in monthly local archives.
\- **Validate Selected:** Run a non-destructive readiness review of selected orders without generating or changing production output.
\- **Guarded hinge settings:** Hinge codes are managed through a selectable list with confirmed add/remove actions. Required `PPH` and `SRPPH01` identifiers are visibly protected.
\- **Compact order summary:** Live Orders, Ready, Issues, Processed, and Checked totals sit inside the Orders header so the table has more vertical room.
\- **Long glass:** Glass with either dimension at least 113 inches must show `SE` on both short end edges. Missing or unclear end-edge labels create a review warning.
\- **Waterjet envelope:** A Waterjet piece larger than 75 inches in both dimensions is flagged and its DXF is skipped for review.
\- **Waterjet radius versus thickness:** Detected internal radii must be at least the glass thickness. For example, 3/8-inch glass with a 1/4-inch internal radius is flagged; a 3/8-inch radius passes.
\- **Split process-list batches:** Pieces for the same A&W order are merged even when different thicknesses or glass types place them in separate batch files.
\- **Mirror process-list batches:** Only items carrying a Waterjet route are treated as programming work; Packing/Shipping-only mirror entries do not block completion or archival.
\- **Duplicate Job Nrs:** A&W order-item values remain the production identity when two orders share one Job Nr. Distinct copy-suffixed source files are preserved and matched by piece dimensions.
\- **FP-S raked edges:** Full-edge rakes use matched DXF geometry for a signed angle correction that leaves the CNC bottom flat. `FP-S` cut-ins and cut-outs remain flagged for manual review.
\- **FP-S short cut transitions:** A confirmed hinge-side profile with an angled run and a shorter square run orients hinges up and keeps the square opposite edge on the CNC bottom.
\- **Machine Decision inspector:** Review Order shows the evidence behind each machine, indicator, orientation, and OOS decision without altering established processing rules.
\- **Incremental scan cache:** Unchanged PDF text, piece-dimension evidence, process-list rows, DXF preview geometry, and duplicate-file hashes are reused between scans and application sessions. Local PDFs are enumerated once per scan and filename matches are exhausted before PDF content is opened.
\- **Legacy XLS conversion:** Excel 97-2003 process lists are converted through a hidden, non-interactive PowerShell/Excel helper while normal scan progress and error reporting remain visible in the application.
\- **Smart network import:** Each scan indexes the shared input folder once, reuses unchanged local process lists, offers selective cleanup for copy-suffixed PDF/DXF duplicates, and retrieves only missing order PDFs or DXF items.

## Project Structure

```text
Assets/
  ShowersProgrammer.ico
  ShowersProgrammer.png
Backend/
  shower\_programmer\_v4.py       Stable release application entry point
  shower\_v4\_features.py         Production-safety and validation integration
  shower\_programmer\_gui.py      Existing GUI and workflow implementation
  shower\_batch.py               Process-list and batch implementation
  shower\_programmer.py          PDF/DXF programming engine
  shower\_state.py               SQLite lifecycle/archive/performance/error store
  shower\_tasks.py               Central cancellable background task manager
  shower\_errors.py              Structured internal/operator error model
  shower\_cache.py               Persistent file-derived scan/cache helpers
  shower\_programmer\_config.json Shop rules and visual settings
  build\_update\_package.py       Clean update-package builder
  version.json                  Current release metadata
Input/
  Orders/                       Local order PDFs and source DXFs
  Process List/                 Process-list exports
  Tools/                        Shop reference tools
Output/                         Generated runs, history, reviews, and local state
CHANGELOG.md                    User-facing release history
GUI.bat                         Source launcher
Rebuild Shower Programmer EXE.bat
```

## Source and Generated Files

Authoritative source files live under `Backend`, `Assets`, and the project root. The following locations are generated or machine-local and should not be manually treated as source:

\- `build`
\- `release`
\- `Shower Programmer\\\_internal`
\- `Input`
\- `Output`
\- `tmp`
\- Python `\_\_pycache\_\_` folders

The rebuild script replaces application runtime files while preserving local `Input`, `Output`, settings, histories, archives, and manual overrides.

## Running from Source

Double-click:

```text
GUI.bat
```

Or run:

```bat
py -3 Backend\shower\_programmer\_v4.py
```

Required Python packages include:

```text
customtkinter
openpyxl
pypdf
pypdfium2
pillow
reportlab
pyinstaller
```

## Command-Line Modes

Batch mode:

```bat
Backend\run\_shower\_batch.bat --preview
Backend\run\_shower\_batch.bat --apply
```

Single-order mode:

```bat
Backend\run\_shower\_programmer.bat --aw-order 234675 --pdf "Input\Orders\order.pdf"
```

Both launchers load the same current-release rules as the GUI.

## Building the Windows Application

Run:

```text
Rebuild Shower Programmer EXE.bat
```

The rebuild performs source validation, Python compilation, the source self-test, a one-folder PyInstaller build, packaged self-testing, runtime validation, safe deployment, and clean update-package generation.

Generated release files:

```text
Shower Programmer\Shower Programmer.exe
release\Shower-Programmer-Windows.zip
release\Shower-Programmer-Windows.json
```

Do not publish a new source revision without rebuilding and publishing matching release artifacts. Automatic updates compare the installed revision and packaged executable metadata against the files published from the repository.

## Versioning

The project now uses the **Version 1.06** production series. Revisions continue to advance by `0.01`:

```text
Version 0.82
Version 0.83
Version 0.84
Version 0.85
Version 0.86
Version 0.87
Version 0.88
Version 0.89
Version 0.90
Version 0.91
Version 0.92
Version 0.93
Version 0.94
Version 0.95
Version 0.96
Version 0.97
Version 0.98
Version 0.99
Version 1.00
Version 1.01
Version 1.02
Version 1.03
Version 1.04
Version 1.05
Version 1.06
```

For every release:

1. Update `Backend\version.json`.
2. Add a matching heading to `CHANGELOG.md`.
3. Update the release marker in the changed feature module.
4. Run the rebuild script.
5. Publish the matching source and update-package files together.

## Local Data Safety

The application stores processing history, manual overrides, review output, and update audit information under `Output` or the packaged application folder. These files are workstation data and should be preserved during updates. The update package intentionally excludes `Input`, `Output`, and source folders.

## Detailed Technical Reference

See `Backend\README\_ShowerProgrammer.md` for command-line details, output behavior, configuration notes, and troubleshooting guidance.


## Version 1.15

Legacy XLS normalization is cached by content, multi-revision archive batches use one consolidated synthetic XLSX in Test Mode, and DXF Reference unit/rotation values are simplified; Version 1.17 uses adaptive degree display up to six decimals.
