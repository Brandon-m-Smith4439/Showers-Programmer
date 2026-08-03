# Shower Programmer

Shower Programmer is a Windows desktop application that reads A&W shower process lists and glass-order files, classifies each glass piece for Denver or Waterjet programming, marks production sketches, prepares machine DXFs, supports visual review and manual corrections, and sends approved output to the shop production folders.

Current release: **Version 0.62 — Mirror Glass Waterjet Detection**

## Main Workflow

1. Place or import order PDFs and source DXFs into `Input\Orders`.
2. Place supported process-list exports into `Input\Process List`.
3. Start the application with `GUI.bat` or the packaged `Shower Programmer.exe`.
4. Scan the process lists and review detected orders, pieces, machine choices, warnings, sketches, and DXFs.
5. Process selected orders.
6. Mark reviewed orders checked.
7. Use **Review / Send** to send sketches and programs to the production folders and archive completed input files.

## Production Checks

- **Existing production files:** Before sending, the application identifies generated filenames that already exist in the production folders. Identical files are accepted automatically. Different files open a clear dialog where the operator can keep the existing production files, replace them, or cancel the send. Non-conflicting files continue normally.
- **Per-file send recovery:** A locked or inaccessible file is reported without stopping unrelated files. An order with an unsent required file is not archived as fully sent.
- **Radius callouts:** Waterjet and PPH DXF previews circle each detected internal radius and place a spaced leader label beside it. Radius labels avoid OOS annotations and nearby radius labels.
- **Long glass:** Glass with either dimension at least 113 inches must show `SE` on both short end edges. Missing or unclear end-edge labels create a review warning.
- **Waterjet envelope:** A Waterjet piece larger than 75 inches in both dimensions is flagged and its DXF is skipped for review.
- **Waterjet radius versus thickness:** Detected internal radii must be at least the glass thickness. For example, 3/8-inch glass with a 1/4-inch internal radius is flagged; a 3/8-inch radius passes.
- **Split process-list batches:** Pieces for the same A&W order are merged even when different thicknesses or glass types place them in separate batch files.
- **FP-S raked edges:** Full-edge rakes use matched DXF geometry for a signed angle correction that leaves the CNC bottom flat. `FP-S` cut-ins and cut-outs remain flagged for manual review.
- **FP-S short cut transitions:** A confirmed hinge-side profile with an angled run and a shorter square run orients hinges up and keeps the square opposite edge on the CNC bottom.

## Project Structure

```text
Assets/
  ShowersProgrammer.ico
  ShowersProgrammer.png
Backend/
  shower_programmer_v4.py       Stable release application entry point
  shower_v4_features.py         Production-safety and validation integration
  shower_programmer_gui.py      Existing GUI and workflow implementation
  shower_batch.py               Process-list and batch implementation
  shower_programmer.py          PDF/DXF programming engine
  shower_programmer_config.json Shop rules and visual settings
  build_update_package.py       Clean update-package builder
  version.json                  Current release metadata
Input/
  Orders/                       Local order PDFs and source DXFs
  Process List/                 Process-list exports
  Tools/                        Shop reference tools
Output/                         Generated runs, history, reviews, and local state
CHANGELOG.md                    User-facing release history
GUI.bat                         Source launcher
Rebuild Shower Programmer EXE.bat
```

## Source and Generated Files

Authoritative source files live under `Backend`, `Assets`, and the project root. The following locations are generated or machine-local and should not be manually treated as source:

- `build`
- `release`
- `Shower Programmer\_internal`
- `Input`
- `Output`
- `tmp`
- Python `__pycache__` folders

The rebuild script replaces application runtime files while preserving local `Input`, `Output`, settings, histories, archives, and manual overrides.

## Running from Source

Double-click:

```text
GUI.bat
```

Or run:

```bat
py -3 Backend\shower_programmer_v4.py
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
Backend\run_shower_batch.bat --preview
Backend\run_shower_batch.bat --apply
```

Single-order mode:

```bat
Backend\run_shower_programmer.bat --aw-order 234675 --pdf "Input\Orders\order.pdf"
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

The project uses a pre-1.0 release series. The current release is **Version 0.62**. Each revision advances by `0.01`:

```text
Version 0.63
Version 0.64
Version 0.65
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

See `Backend\README_ShowerProgrammer.md` for command-line details, output behavior, configuration notes, and troubleshooting guidance.
