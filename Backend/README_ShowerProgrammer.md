# Shower Programmer

This folder now has a first-pass automation for shower programming:

- `GUI.bat` - double-click launcher.
- `Input\Orders` - put order PDFs and DXFs here.
- `Input\Process List` - put process-list `.xlsx` files here.
- `Input\Tools` - shop reference files such as `ANGLE CALCULATOR.xlsx`.
- `Output` - generated marked sketches, programs, and reports.
- `Backend` - Python scripts, config, and support launchers.

The batch script still defaults to **dry run**. A dry run is a preview: it scans the orders, checks matching PDFs/DXFs, and writes reports, but it does not create marked sketch PDFs or adjusted DXF programs.

## Easiest Use

Double-click:

```text
GUI.bat
```

Then:

1. Click `Scan Orders`.
2. Review the order table.
3. Click `Process Selected` or `Process All` when ready.
4. Click `Open Last Report` to inspect the final HTML report.

The table shows every A&W order from `Process List Per Machine.xlsx`, the matching job, PDF, status, and issues.
It also shows the delivery date, whether the order has been processed, and the last processed time recorded by the GUI.
The `Process Lists` path can be either one workbook or a folder. When it is a folder, every immediate `.xlsx` file in that folder is loaded together, so split lists such as `6.4.26.xlsx`, `6.4.26A.xlsx`, `6.4.26B.xlsx`, and `6.4.26C.xlsx` can be used at the same time.
Use `Open Config` when you want to adjust global label or marker placement.
To process a remake, select the order, check `REMAKE`, enter the remake pieces like `2` or `1,3`, then click `Process Selected`. Remake processing overwrites that selected order so the sketch on disk cannot stay in the old non-remake format.
Use `Open Sketches` and `Open Programs` to jump directly to the latest run's generated output folders.
Double-click a scanned order, or use `Review Order`, to open a one-order review window with the source sketch and matching DXF side-by-side. The review window can scroll the sketch, switch pieces with `Prev P`/`Next P` or Ctrl+mouse wheel, rotate the sketch view for visual checking, show the exact DXF rotation amount, highlight long angled DXF edges in orange, save dragged blue marks, and then `Process DXF` to regenerate the saved sketch/program and refresh the DXF preview.
In `Review Order`, `Delete Mark` hides the selected generated label/indicator/DIAMON FUSION/REMAKE mark, `Edit Text` changes selected generated blue text, and `Add Indicator` restores an indicator for the selected piece. Denver indicators are constrained to bottom-left or top-right; if an old saved edit used top-left or bottom-right, the program coerces it back to an allowed Denver position.
Use `Mark Checked` on the main screen to mark selected orders as reviewed in the Review column.
Use `Clear Sketch Memory` when testing new placement rules. It deletes generated sketch/review files and removes saved sketch-edit positions from `Output\manual_overrides.json`, while keeping machine/config overrides and process-list data.

The GUI writes applied runs to indexed folders under `Output\Runs` by default:

- `Output\Runs\N\Sketches` - marked PDFs for run `N`.
- `Output\Runs\N\Programs` - adjusted DXFs for run `N`.
- `Output\Runs\N\Reports` - per-order and batch reports for run `N`.
- `Output\Runs\N\manifest.json` - run metadata.
- `Output\Reviews` - temporary sketch/DXF review files from the GUI.
- `Output\manual_overrides.json` - optional per-output-folder corrections from the GUI.
- `Output\processing_history.json` - last processed time, status, remake item state, and latest run folder for the GUI table.

If selected outputs already exist and overwrite is enabled or confirmed, the GUI clears the selected order's old sketch, program DXFs, and per-order report before regenerating them. This prevents old DXF files from staying behind when the selected set changes.

## Batch Use

Preview all workbook orders and PDF matches. By default, this reads every immediate `.xlsx` file in `Input\Process List`:

```bat
Backend\run_shower_batch.bat --preview
```

Dry-run every order and write end-of-run reports:

```bat
Backend\run_shower_batch.bat
```

Process every order into `Output\Sketches`, `Output\Programs`, and `Output\Reports`:

```bat
Backend\run_shower_batch.bat --apply
```

Process only certain A&W orders:

```bat
Backend\run_shower_batch.bat --orders 234450,234454 --apply
```

Use one specific workbook or folder:

```bat
Backend\run_shower_batch.bat --process-list "Input\Process List\6.4.26.xlsx"
Backend\run_shower_batch.bat --process-list "Input\Process List"
```

Overwrite existing outputs:

```bat
Backend\run_shower_batch.bat --apply --force
```

Batch mode writes:

- `batch_programming_report_YYYYMMDD_HHMMSS.txt`
- `batch_programming_report_YYYYMMDD_HHMMSS.csv`
- `batch_programming_report_YYYYMMDD_HHMMSS.html`
- one per-order `*_programming_report.txt`

If an order has an issue, batch mode keeps going and marks that order as `ISSUES`, `SKIPPED`, or `FAILED` in the reports.

## Basic Use

Dry run:

```bat
Backend\run_shower_programmer.bat --pdf "Input\Orders\Glass Order TRUE HOMES_87366091 EDGEWATER 768.pdf" --aw-order 234675
```

Apply:

```bat
Backend\run_shower_programmer.bat --pdf "Input\Orders\Glass Order TRUE HOMES_87366091 EDGEWATER 768.pdf" --aw-order 234675 --apply
```

Output goes to `Sketches` by default:

- `Sketches\234675.pdf`
- `Sketches\23467501.dxf`
- `Sketches\23467502.dxf`
- `Sketches\234675_programming_report.txt`

Use `--force` if you intentionally want to overwrite existing output files.

## Single Order Test

```bat
Backend\run_shower_programmer.bat --pdf "Input\Orders\234450.pdf" --aw-order 234450 --job "87793318 RIVERWALK 497"
```

Example orders are only test inputs. The default config does not contain rules for one specific old order.

## Rules Currently Automated

- Text label: `A&W order.item`, for example `234675.1`.
- Machine line:
  - `DENVER 1` for door-like pieces.
  - `DENVER 2` for panel fabrication.
  - `WJ` for notches, irregular/radius pieces, and pieces under `6-1/8`.
- Plain panels with no detected cutouts/fabrication get only the order/item label and no DXF output.
- `DIAMON FUSION` is added when the PDF text contains `Diamon` or `Diamond Fusion`.
- `DIAMON FUSION` is bold blue at the original banner size and is placed above the glass where `REMAKE` would normally go. When possible it avoids top measurements and WJ indicators.
- Batch mode also picks up `Diamon Fusion` from `Process List Per Machine.xlsx`.
- Batch mode uses the process list's machine hints, such as `Waterjet`, `Denver 1 (CNC)`, and `Denver 2 (CNC)`, as a helper reference.
- Process-list `Waterjet` is treated as a hint, not a command. If the PDF looks like a Denver panel, the tool keeps the Denver classification unless an item override says otherwise.
- Process-list fabrication wording can fill in missed Denver 1 or Denver 2 fabrication, but it does not force an unconfirmed WJ classification by itself.
- Slot/macro fabrication wording such as `SCU4 Slot MACRO` is treated as real fabrication, so those pieces are not left as label-only when the PDF text is sparse.
- Process-list notch wording is not used by itself to force `WJ`.
- K cuts are Denver-allowed fabrication by default, so a K-cut panel can stay on Denver instead of being forced to WJ.
- Denver 1 doors estimate the hinge side from hinge labels/cutout geometry. Normal doors orient hinges down; doors with cut-in, K-cut, PPH, SRPPH01, or AV1E037 wording orient hinges up. Plain V1E037 is treated as a hinge label, not a hinges-up trigger.
- Denver 1 doors with clear cut-in, kick-in, or K-cut/jut-out evidence in the matched DXF can use that DXF shape to correct the hinge side and orient hinges up before the program is rotated. The DXF detector checks for either an angled hinge-side kick or parallel offset side runs, which covers stepped jut-outs like `234584.2`.
- Denver 2 panels prefer the square long side from the matched DXF when choosing the bottom side. This keeps panels off the out-of-square side when a square long side is available.
- Tall WJ DXFs follow the selected WJ marker corner. WJ indicators are constrained to `top_left` or `bottom_right`; top-left rotates `90` and bottom-right rotates `-90`, which keeps the program aligned with the reviewed sketch.
- WJ pieces are flagged if neither side can fit under the 75-inch limit. The sketch can still be written, but the DXF is skipped and reported.
- DXFs are matched from names like `SO JOB_1__P1.dxf`.
- If both a plain DXF like `SO JOB_1.dxf` and a detailed weighted DXF like `SO JOB_1__... (67.1lb).dxf` exist, the weighted DXF is used.
- DXFs are rotated so tall programmed pieces put the long side along the bottom.
- Mirror orders are hidden from the GUI unless the process list shows fabrication. Mirror fabrication is programmed as `WJ`.
- Remake orders mark selected remake pieces with `REMAKE`; non-remake pages in that order get a giant X and skip DXF output.
- Denver 1 angle correction is based on the matched DXF edge that will sit flat on the Denver. Out-of-square text alone does not apply the angle calculator; the source DXF must show that the hinge/bottom side needs correction. Raked-edge text by itself is not a manual-review issue.
- Manual DXF review is flagged only when an FP-S piece also has cut-in/cut-out evidence. Manual-review pieces still generate DXFs so the program can be inspected and corrected.
- Sketch indicators are blue. Denver pieces get a blue dot. WJ pieces get two blue lines meeting at the chosen water-jet table corner.
- Indicator placement uses the connected glass outline from the PDF when it can find one, so markers are based on the piece edge instead of dimension lines.
- WJ markers are larger than Denver dots by default.
- Sketch labels are bold blue text.
- REMAKE text and X-out marks are bold blue.
- Sketch labels check for drawing/text collisions. They try the detected glass center first, shrink slightly on tight pieces, and only fall back to other open space when the center is not readable.

## Placement Calibration

Edit `shower_programmer_config.json` to move markings globally:

```json
"label_position": {
  "denver_y_ratio": 0.74,
  "waterjet_y_ratio": 0.82,
  "denver_nudge_y": 0,
  "waterjet_nudge_y": 0
},
"indicator_nudge": {
  "waterjet_y": 0
}
```

The config has `_notes` sections above the main visual and rule groups. Those notes are safe to leave in place and are there so the placement controls are easier to tune without reading the Python.

Useful rules of thumb:

- Set `label_position.center_first` to `true` to try the piece center before the configured ratio positions.
- Increase `denver_y_ratio` or `waterjet_y_ratio` to aim labels higher inside the glass.
- Use `denver_nudge_x`, `denver_nudge_y`, `waterjet_nudge_x`, and `waterjet_nudge_y` for small final label moves in PDF points. Positive `y` moves up.
- Use `indicator_nudge.waterjet_x` and `indicator_nudge.waterjet_y` for WJ corner marker calibration after the program selects the corner. Positive values move inward from the selected WJ corner, so top-left, top-right, bottom-left, and bottom-right all stay on-page.
- When the glass outline is detected, WJ markers use the outline corner directly. Use `indicator_nudge.waterjet_outline_x` and `indicator_nudge.waterjet_outline_y` for small outline-based movement; positive `x` moves right and positive `y` moves up.
- Use `indicator_nudge.denver_x` and `indicator_nudge.denver_y` for Denver dot calibration after the program selects the corner. Positive `x` moves right; positive `y` moves up.
- Use `indicator_offset` to set the maximum Denver dot distance from the selected corner. The program automatically reduces this on narrow pieces so dots do not land in the middle of the glass.
- Use `indicator_size` for Denver dot size. Use `waterjet_indicator_size`, `waterjet_indicator_line_width`, and `waterjet_indicator_length_ratio` for the WJ two-line marker size.
- Use `diamon_fusion_above_remake_gap` to change the gap between `DIAMON FUSION` and `REMAKE`.
- Keep per-item overrides for unusual one-off jobs, not for teaching the general rules.

## Manual Edits

When the automatic guess is wrong on one order, use the GUI `Edit Sketch` button. Dragging markings saves corrections to:

```text
Output\manual_overrides.json
```

The override file follows the same format as config overrides, but it is local to that output folder and is merged automatically by the GUI and batch runner:

```json
"item_overrides": {
  "234675": {
    "1": {
      "machine": "DENVER 2",
      "indicator_corner": "bottom_left",
      "rotation_degrees": 90
    },
    "2": {
      "machine": "",
      "skip_dxf": true
    }
  }
}
```

Supported override fields:

- `machine`: `DENVER 1`, `DENVER 2`, `WJ`, or blank for label-only.
- `indicator_corner`: `bottom_left`, `bottom_right`, `top_left`, or `top_right`.
- `rotation_degrees`: usually `0`, `90`, `-90`, or `180`.
- `skip_dxf`: `true` or `false`.
- `hinge_side`: `left` or `right`.
- `hinges_up`: `true` or `false`.
- `angle_correction_degrees`: direct extra DXF rotation for out-of-square hinge-side correction.
- `label_nudge_x` and `label_nudge_y`: one-item label movement in PDF points.
- `indicator_nudge_x` and `indicator_nudge_y`: one-item marker movement in PDF points.
- `diamon_fusion`: `true` or `false`.
- `diamon_fusion_font_size`: one-item DIAMON FUSION text size.
- `diamon_fusion_nudge_x` and `diamon_fusion_nudge_y`: one-item DIAMON FUSION movement in PDF points.
- `label_x` and `label_y`: absolute one-item label position saved by `Edit Sketch`.
- `indicator_x` and `indicator_y`: absolute one-item indicator position saved by `Edit Sketch`.
- `diamon_fusion_x` and `diamon_fusion_y`: absolute one-item DIAMON FUSION position saved by `Edit Sketch`.
- `out_of_square` and `out_of_square_length`: calculates the same small-angle correction used by the Angle Calculator workbook.
- `angle_direction`: `1` or `-1` to flip the correction direction.

Use these overrides for manual review corrections after checking a generated sketch or DXF. Rerun the order and the sketch/DXF/report will be regenerated from the corrected settings.

## Global Overrides

For permanent shop-wide behavior changes, edit `shower_programmer_config.json`. Keep global `item_overrides` for unusual one-off jobs that must always be handled the same way, not for normal manual review corrections.

For Denver 1 doors, the program also checks the matched source DXF after hinge-side orientation is chosen. If the hinge edge is slightly off-axis, it uses the same Angle Calculator math and applies the signed correction needed to make that hinge edge square after rotation.

Out-of-square door example:

```json
"item_overrides": {
  "234675": {
    "1": {
      "machine": "DENVER 1",
      "rotation_degrees": 90,
      "out_of_square": "1/8",
      "out_of_square_length": "78",
      "angle_direction": 1
    }
  }
}
```

If the PDF mentions out-of-square and no angle override is set, the order is flagged in the report for review.

## Current Limits

This is a strong first pass, not a fully trusted lights-out production system yet.

- Hinge-side detection is heuristic. Door-like pieces are detected from words like `PPH`, `HINGE`, `PULL`, and `HANDLE`.
- Out-of-square hinge straightening is automatic for clear raked/out-of-square Denver 1 doors and for matched Denver 1 DXFs whose hinge edge is slightly off-axis. Item overrides can still be used when the drawing is ambiguous.
- Square-corner preference is still mostly handled by the chosen default/override corner. Exact square-corner detection from the drawing is not fully automatic yet.
- PDF label/dot placement is based on the sample layout and estimated panel geometry. Check the generated PDF before using it in production.
- DXF output should be opened once in CAD/machine software during testing to confirm the machine accepts the rotated files.
