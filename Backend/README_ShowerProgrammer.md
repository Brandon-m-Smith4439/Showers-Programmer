# Shower Programmer Technical Reference

This document is the detailed operating and development reference for Shower Programmer. Start with the repository-level `README.md` for the general overview.

## Entry Points

The stable release entry point is:

```text
Backend\shower_programmer_v4.py
```

It installs the current release integration layer and then routes to the existing GUI, batch, or single-order implementation.

```bat
py -3 Backend\shower_programmer_v4.py
py -3 Backend\shower_programmer_v4.py --batch --preview
py -3 Backend\shower_programmer_v4.py --single --aw-order 234675 --pdf "Input\Orders\order.pdf"
```

Use the included batch launchers for normal shop operation.

## Input

- `Input\Orders`: Glass-order PDFs and matching source DXFs.
- `Input\Process List`: `.xlsx`, `.xls`, `.xml`, and `.rtf` process-list exports supported by `shower_batch.py`.
- `Input\Tools`: Shop reference files.

The process-list path may be one file or a directory. The integration layer merges pieces sharing the same A&W order across all loaded process-list batches while retaining the source-batch records used for archive completion checks.

## Output

Applied runs are normally written under:

```text
Output\Runs\<run number>\Sketches
Output\Runs\<run number>\Programs
Output\Runs\<run number>\Reports
```

Local state includes:

- `Output\processing_history.json`
- `Output\manual_overrides.json`
- review preview caches
- update audit folders
- archived local input files

## Review and Send

The application performs a production conflict preflight before the worker thread begins.

- An identical production file is accepted as already satisfied.
- **Keep Existing & Continue** leaves all different production conflicts unchanged and sends non-conflicting files.
- **Replace Existing & Continue** atomically replaces different conflicts and sends non-conflicting files.
- **Cancel Send** returns to Review / Send before copy work begins.

Each file is copied independently. A failed copy is added to the completion report and the worker continues. The existing sent-order reconciliation then prevents an incomplete order from being archived.

## Production Validation Rules

### Long-glass SE edgework

When the longer dimension is at least 113 inches, the two short end edges require `SE` labels. The validator first attempts to map label coordinates to the detected glass outline. When the PDF does not expose usable text coordinates, two explicit standalone `SE` labels are used as the fallback.

### Waterjet envelope

When both dimensions exceed 75 inches, the piece is outside the configured Waterjet envelope. A clear warning is added and DXF output is skipped for review. A long, narrow piece can still fit when one dimension is 75 inches or less.

### Mirror glass

Any individual glass type containing the configured `MIRROR` keyword is assigned to Water Jet. The rule reads the piece sketch and its process-list material text, overrides automatic Denver hints, and does not trigger from project, customer, location, or address names containing the word `Mirror`. Manual machine overrides remain available for operator corrections.

Mirror-only process-list batches are scoped to items with an actual Waterjet machine route. Mirror entries routed only to Packing/Shipping are not displayed or programmed and do not prevent the completed batch, including a legacy `.xls` source, from being archived and removed from shared input staging.

### Waterjet internal radius

The validator extracts glass thickness from the sketch/process text, reads internal ARC and polyline-bulge radii from the source DXF, converts DXF units to inches, and compares every detected radius with the thickness. Equality passes. A tolerance of 0.002 inch is used for CAD rounding.

The built-in defaults are:

```text
SE length threshold: 113 inches
Waterjet envelope: 75 x 75 inches
Minimum internal radius: glass thickness
Radius comparison tolerance: 0.002 inch
```

### DXF preview callouts

Waterjet and PPH previews use the same detected radius samples as the validator. Each selected sample is circled and connected to a radius label with a leader line. Version 0.5 adds a clear gap between the label and leader line, stops the line at the radius circle, avoids OOS text and other radius labels, and removes the redundant radius summary from the top of the DXF preview. Undersized Waterjet radii and incorrect PPH radii use the danger color; confirmed 5/16-inch PPH radii use the success color.

### FP-S full-edge rakes

For a Denver piece with `FP-S`, a full raked edge is corrected from the matched source DXF so the selected CNC bottom is flat. The panel report records the detected source edge and signed correction. This does not broaden manual review: only `FP-S` with a cut-in or cut-out is flagged for manual DXF review.

When the hinge-side profile contains both an angled run and a shorter square run, the `FP-S` short-transition fallback treats it as a cut even when the square run is below the general 20% segment threshold. Hinges orient up, the opposite square edge becomes the CNC bottom, and the piece is flagged for manual DXF review.

## Existing Programming Rules

The existing core continues to provide:

- A&W order/item sketch labels.
- Denver 1 door and hinge orientation.
- Denver 2 panel fabrication handling.
- Waterjet selection for small sides, notches, radii, and irregular shapes.
- transom reconciliation.
- PPH radius-based hinge-side confirmation.
- sketch edit history and manual overrides.
- output skip controls.
- source DXF matching, rotation, unit conversion, and reporting.
- production sketch reconciliation across workstations.

The current release behavior is intentionally isolated in `shower_v4_features.py`; the large existing GUI, batch, and programming modules remain the established core.

## Manual Overrides

Manual sketch and machine corrections remain stored in:

```text
Output\manual_overrides.json
```

Supported values include machine, indicator corner, rotation, hinge side, label/indicator position, text edits, output skipping, and angle correction. Use one-off overrides for unusual jobs rather than changing general production rules.

## Source Tests

Run the focused release tests:

```bat
py -3 -m unittest discover -s tests -v
```

Run the integrated application self-test:

```bat
py -3 Backend\shower_programmer_v4.py --self-test Output\release_self_test.json
```

A successful integrated report includes the existing core checks and the current release checks:

- `v4_conflict_safe_send`
- `v4_existing_file_keep_or_replace`
- `v4_per_file_send_failure_continuation`
- `v4_radius_preview_callouts`
- `v4_long_glass_se_validation`
- `v4_waterjet_oversize_flag`
- `v4_waterjet_thickness_radius_validation`
- `v4_split_batch_order_merge`
- `version_0_5_radius_label_spacing`
- `version_0_5_oos_callout_avoidance`
- `version_0_5_radius_header_removed`
- `version_0_6_fps_rake_orientation`
- `version_0_6_dynamic_release_self_test`
- `version_0_61_fps_short_cut_hinges_up`
- `version_0_62_mirror_glass_waterjet`
- `version_0_63_machine_decision_inspector`
- `version_0_63_process_list_normalization`
- `version_0_63_known_order_regressions`
- `version_0_63_incremental_scan_cache`
- `version_0_64_dxf_first_review_layout`
- `version_0_65_smart_network_import`
- `version_0_66_mirror_waterjet_batch_scope`
- `version_0_67_duplicate_job_order_identity`
- `version_0_68_hidden_xls_conversion`
- `version_0_69_fast_accurate_scanning`

Run the data-driven known-order regression library by itself:

```bat
py -3 -m unittest tests.test_known_order_regressions -v
```

## Troubleshooting

### A generated file already exists in production

Use the production conflict dialog. Keep the existing production file when it is intentionally authoritative; replace it when the newly reviewed output should become authoritative.

### One file cannot be copied

Close the affected PDF/DXF, NCEditor, AutoCAD, or File Explorer preview. The rest of the send continues and the failed filename appears in the completion summary.

### A split order is missing a piece

Confirm both process-list files are in the configured process-list folder and rescan. The integration layer merges same-A&W pieces after loading the visible batch records.

### Thickness cannot be determined

Confirm the sketch or process text contains a recognized thickness such as `3/8 CLEAR TEMPERED` or `Glass Thickness: 3/8`. The order is flagged for review rather than silently passing the internal-radius check.

### Rebuild validation fails

Read the first `ERROR:` line in the rebuild terminal. The script checks required files, release metadata, changelog agreement, package dependencies, Python syntax, source self-test output, packaged self-test output, Tcl/Tk data, PDFium, and update-package integrity.
