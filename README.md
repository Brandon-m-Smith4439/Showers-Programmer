**# Shower Programmer**

Shower Programmer is a Windows desktop application that reads A&W shower process lists and glass-order files, classifies each glass piece for Denver or Waterjet programming, marks production sketches, prepares machine DXFs, supports visual review and manual corrections, and sends approved output to the shop production folders.

Current release: **\*\*Version 0.97 - Re-imported Batch Reactivation\*\***

**## Main Workflow**

1\. Place or import order PDFs and source DXFs into \`Input\Orders\`.
2\. Place supported process-list exports into \`Input\Process List\`.
3\. Start the application with \`GUI.bat\` or the packaged \`Shower Programmer.exe\`.
4\. Scan the process lists and review detected orders, pieces, machine choices, warnings, sketches, and DXFs.
5\. Process selected orders.
6\. Mark reviewed orders checked.
7\. Use **\*\*Review / Send\*\*** to send sketches and programs to the production folders and archive completed input files.

**## Out-of-Square Dimension Matching**

A&W may report the overall bounding width/height of an out-of-square or raked piece while the glass sketch labels a physical edge span or true sloped-edge length. Shower Programmer first uses the normal PDF/process-list dimension check. If that fails, Version 0.94 can reconcile the order only when the matching source DXF proves all of the following:

- the DXF overall bounding size matches the A&W process-list dimensions;
- the DXF contains measurable non-axis-aligned outer geometry; and
- the sketch-reported piece size agrees with a real outer-edge span or physical edge length from that same DXF.

This fallback validates an already-selected PDF; it does not weaken duplicate-Job PDF selection. For an unusual order that still cannot be proven automatically, right-click the order and choose **Allow Dimension Mismatch** after manually verifying the sketch and DXF. The saved override is per A&W order, remains auditable as a warning, and can be removed with **Clear Dimension Override**.

**## Production Checks**

\- **\*\*Re-imported batch reactivation:\*\*** If a local batch was explicitly deleted but its process list still exists in the shared input folder, scanning that batch again clears only the matching local deletion receipt after the shared process list is copied back. The batch remains active and its PDF/DXF files are matched normally instead of being shown as Input Without Process List. Sent receipts are preserved.
\- **\*\*Fast archive browser:\*\*** Settings > Archives initially loads only the newest seven days and keeps batch groups collapsed. Use From/To dates (or one date), **Last 7 Days**, **Load 7 More Days**, search, Sent/In Input filters, and sortable headings to narrow the view without rescanning everything. Switch between **Orders / Sketch Archives** and **Processing Runs**. Archived-input rows remain grouped by process-list batch; run history is grouped by run/batch.
\- **\*\*Archive testing workspace:\*\*** **Restore for Testing** performs exact correlation for the selected archived order, copies its PDF/DXF back to Input, and creates a one-order test process list without modifying the original archive. **Return to Archive** removes the active test copies, and **Archive Sent Inputs** cleans up already-sent archive orders that were manually moved back into Input.
\- **\*\*Responsive cleanup/settings:\*\*** Large local/shared deletes and archive loading run in background workers with live progress, avoiding the long UI freezes that occurred when filesystem work ran directly on Tk's main thread.
\- **\*\*Readable operator dialogs:\*\*** Error/warning dialogs use larger text and wider layouts. Dimension-mismatch failures are split into Process List, Sketch, validation, and Next Step sections instead of one dense paragraph.
\- **\*\*REMAKE detection and banner:\*\*** REMAKE is detected from the A&W Location field on the overview or piece pages even when PDF extraction joins `Location:` to preceding text or breaks the value onto another line. The REMAKE banner uses the same fixed-large, glass-anchored placement contract as DIAMON FUSION.
\- **\*\*Seven-day file recovery:\*\*** Explicit local input deletion moves order and completed process-list files into a manifest-backed Recovery area for seven days. Restore or permanently remove a recovery bundle from Settings.
\- **\*\*Programming evidence:\*\*** Right-click an order and choose **\*\*Why Programmed This Way\*\*** to inspect machine, geometry, hinge, rotation, OOS correction, warnings, and manual-override evidence in a separate window.
\- **\*\*Diagnostic packages:\*\*** Right-click one order to create an order-scoped ZIP containing its matched inputs, process list, generated files, processing evidence, action history, and a redacted configuration snapshot.
\- **\*\*Diagnostics folder access:\*\*** Open the local Diagnostics folder directly from the Preferences tab. The folder is created automatically on a fresh installation.
\- **\*\*Order overview:\*\*** Review Order includes the sketch cover page with process descriptions, item/output counts, processing status, issues, checked state, sent state, and text-only sketch editing. Machine and indicator controls remain disabled on the cover page.
\- **\*\*Overview text sizing:\*\*** Right-click an overview text box to increase or decrease its font size; the size remains stored separately from piece machine/programming overrides.
\- **\*\*DIAMON FUSION banner:\*\*** DIAMON FUSION keeps its configured large font size and stays outside the detected glass even when it crosses top measurement graphics.
\- **\*\*External PDF annotations:\*\*** Refresh Sketch reopens the saved PDF and displays annotations saved from Microsoft Edge. Use **\*\*Resume Editing\*\*** to return immediately to movable sketch overlays.
\- **\*\*Indicator placement:\*\*** Automatic Denver indicators avoid nearby source text/cutouts while keeping the full marker inside the detected glass. Waterjet placement remains independent from that Denver-only avoidance; manual indicator positions are preserved.
\- **\*\*Network health:\*\*** The main status area checks the import, shop sketch, and shop program folders asynchronously and shows Online, Partial, or Offline without delaying normal scans.
\- **\*\*Configuration backup:\*\*** Settings can export or import shop rules, hinge settings, and UI preferences. Import automatically preserves the current configuration first.
\- **\*\*Existing production files:\*\*** Before sending, the application identifies generated filenames that already exist in the production folders. Identical files are accepted automatically. Different files open a clear dialog where the operator can keep the existing production files, replace them, or cancel the send. Non-conflicting files continue normally.
\- **\*\*Per-file send recovery:\*\*** A locked or inaccessible file is reported without stopping unrelated files. An order with an unsent required file is not archived as fully sent.
\- **\*\*Fast production sending:\*\*** Independent sketch and DXF copies, plus existing-file checks, run concurrently while preserving atomic targets and keep/replace decisions.
\- **\*\*Radius callouts:\*\*** Waterjet and PPH DXF previews circle each detected internal radius and place a spaced leader label beside it. Radius labels avoid OOS annotations and nearby radius labels.
\- **\*\*Hinge detection settings:\*\*** Use **\*\*Hinge Detection\*\*** under Tools to add or change hinge codes such as \`JRG037\` and \`GEN180\` without editing source code. Core PPH identifiers \`PPH\` and \`SRPPH01\` remain available in the editable list.
\- **\*\*Manual machine changes:\*\*** Saving a review edit after changing a piece from Denver to Waterjet rewrites its program DXF in millimeters, including the metric DXF header expected by Waterjet.
\- **\*\*Review workflow controls:\*\*** Review Order includes an explicit machine selector, and refreshing a sketch returns directly to the editable overlay view without requiring the order window to be reopened.
\- **\*\*Sortable order list:\*\*** Click an Orders table heading to sort that column ascending or descending without separating orders from their process-list batch.
\- **\*\*Order search:\*\*** Use the order-number search above the table to highlight and scroll to an exact or partial A&W order match.
\- **\*\*Action History:\*\*** Search the last seven days of major workflow activity by action, A&W order, Job Nr, job name, result, or detail. Older entries are retained in monthly local archives.
\- **\*\*Validate Selected:\*\*** Run a non-destructive readiness review of selected orders without generating or changing production output.
\- **\*\*Guarded hinge settings:\*\*** Hinge codes are managed through a selectable list with confirmed add/remove actions. Required \`PPH\` and \`SRPPH01\` identifiers are visibly protected.
\- **\*\*Compact order summary:\*\*** Live Orders, Ready, Issues, Processed, and Checked totals sit inside the Orders header so the table has more vertical room.
\- **\*\*Long glass:\*\*** Glass with either dimension at least 113 inches must show \`SE\` on both short end edges. Missing or unclear end-edge labels create a review warning.
\- **\*\*Waterjet envelope:\*\*** A Waterjet piece larger than 75 inches in both dimensions is flagged and its DXF is skipped for review.
\- **\*\*Waterjet radius versus thickness:\*\*** Detected internal radii must be at least the glass thickness. For example, 3/8-inch glass with a 1/4-inch internal radius is flagged; a 3/8-inch radius passes.
\- **\*\*Split process-list batches:\*\*** Pieces for the same A&W order are merged even when different thicknesses or glass types place them in separate batch files.
\- **\*\*Mirror process-list batches:\*\*** Only items carrying a Waterjet route are treated as programming work; Packing/Shipping-only mirror entries do not block completion or archival.
\- **\*\*Duplicate Job Nrs:\*\*** A&W order-item values remain the production identity when two orders share one Job Nr. Distinct copy-suffixed source files are preserved and matched by piece dimensions.
\- **\*\*FP-S raked edges:\*\*** Full-edge rakes use matched DXF geometry for a signed angle correction that leaves the CNC bottom flat. \`FP-S\` cut-ins and cut-outs remain flagged for manual review.
\- **\*\*FP-S short cut transitions:\*\*** A confirmed hinge-side profile with an angled run and a shorter square run orients hinges up and keeps the square opposite edge on the CNC bottom.
\- **\*\*Machine Decision inspector:\*\*** Review Order shows the evidence behind each machine, indicator, orientation, and OOS decision without altering established processing rules.
\- **\*\*Incremental scan cache:\*\*** Unchanged PDF text, piece-dimension evidence, process-list rows, DXF preview geometry, and duplicate-file hashes are reused between scans and application sessions. Local PDFs are enumerated once per scan and filename matches are exhausted before PDF content is opened.
\- **\*\*Legacy XLS conversion:\*\*** Excel 97-2003 process lists are converted through a hidden, non-interactive PowerShell/Excel helper while normal scan progress and error reporting remain visible in the application.
\- **\*\*Smart network import:\*\*** Each scan indexes the shared input folder once, reuses unchanged local process lists, offers selective cleanup for copy-suffixed PDF/DXF duplicates, and retrieves only missing order PDFs or DXF items.

**## Project Structure**

\`\`\`text
Assets/
  ShowersProgrammer.ico
  ShowersProgrammer.png
Backend/
  shower\_programmer\_v4.py       Stable release application entry point
  shower\_v4\_features.py         Production-safety and validation integration
  shower\_programmer\_gui.py      Existing GUI and workflow implementation
  shower\_batch.py               Process-list and batch implementation
  shower\_programmer.py          PDF/DXF programming engine
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
\`\`\`

**## Source and Generated Files**

Authoritative source files live under \`Backend\`, \`Assets\`, and the project root. The following locations are generated or machine-local and should not be manually treated as source:

\- \`build\`
\- \`release\`
\- \`Shower Programmer\\\_internal\`
\- \`Input\`
\- \`Output\`
\- \`tmp\`
\- Python \`\_\_pycache\_\_\` folders

The rebuild script replaces application runtime files while preserving local \`Input\`, \`Output\`, settings, histories, archives, and manual overrides.

**## Running from Source**

Double-click:

\`\`\`text
GUI.bat
\`\`\`

Or run:

\`\`\`bat
py -3 Backend\shower\_programmer\_v4.py
\`\`\`

Required Python packages include:

\`\`\`text
customtkinter
openpyxl
pypdf
pypdfium2
pillow
reportlab
pyinstaller
\`\`\`

**## Command-Line Modes**

Batch mode:

\`\`\`bat
Backend\run\_shower\_batch.bat --preview
Backend\run\_shower\_batch.bat --apply
\`\`\`

Single-order mode:

\`\`\`bat
Backend\run\_shower\_programmer.bat --aw-order 234675 --pdf "Input\Orders\order.pdf"
\`\`\`

Both launchers load the same current-release rules as the GUI.

**## Building the Windows Application**

Run:

\`\`\`text
Rebuild Shower Programmer EXE.bat
\`\`\`

The rebuild performs source validation, Python compilation, the source self-test, a one-folder PyInstaller build, packaged self-testing, runtime validation, safe deployment, and clean update-package generation.

Generated release files:

\`\`\`text
Shower Programmer\Shower Programmer.exe
release\Shower-Programmer-Windows.zip
release\Shower-Programmer-Windows.json
\`\`\`

Do not publish a new source revision without rebuilding and publishing matching release artifacts. Automatic updates compare the installed revision and packaged executable metadata against the files published from the repository.

**## Versioning**

The project uses a pre-1.0 release series. The current release is **\*\*Version 0.97\*\***. Each revision advances by \`0.01\`:

\`\`\`text
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
\`\`\`

For every release:

1\. Update \`Backend\version.json\`.
2\. Add a matching heading to \`CHANGELOG.md\`.
3\. Update the release marker in the changed feature module.
4\. Run the rebuild script.
5\. Publish the matching source and update-package files together.

**## Local Data Safety**

The application stores processing history, manual overrides, review output, and update audit information under \`Output\` or the packaged application folder. These files are workstation data and should be preserved during updates. The update package intentionally excludes \`Input\`, \`Output\`, and source folders.

**## Detailed Technical Reference**

See \`Backend\README\_ShowerProgrammer.md\` for command-line details, output behavior, configuration notes, and troubleshooting guidance.