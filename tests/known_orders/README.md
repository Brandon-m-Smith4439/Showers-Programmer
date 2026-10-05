# Known Order Regression Library

This folder stores sanitized, reproducible facts derived from real diagnostic packages. It intentionally does not store customer PDFs or production workbooks. Each JSON case preserves only the geometry/process facts needed to reproduce a previously important decision.

`Rebuild Shower Programmer EXE.bat` runs the library through `tests/release_smoke_test.py` before packaging. New diagnostic cases can be added as small JSON fixtures after the failure mode is understood and sanitized.
