Shower Programmer V39 - Atomic Runtime Swap

This update fixes a V38 installer defect that could remove the live _internal folder before a slow OneDrive copy completed.

Key changes:
- Copies the complete replacement app beside the installation while the old app remains intact.
- Validates EXE, _internal, Tcl data, Tk data, and pdfium.dll.
- Runs the copied EXE self-test before touching the live runtime.
- Moves the old runtime into a rollback folder before activating the new runtime.
- Places the new EXE last, so users cannot launch a half-installed program.
- Automatically rolls back if the new app fails to remain open.
- Shows visible progress and writes apply_update.log.
- Rebuild BAT and update-ZIP builder reject packages missing Tcl/Tk runtime data.

Recovery for a computer already broken by V38:
1. Close Shower Programmer and the updater terminal.
2. Preserve the broken folder as a backup.
3. Copy a complete freshly built Shower Programmer folder into place.
4. Restore only Input, Output, and local settings/history from the backup.
5. Do not copy the broken _internal folder back.
