# Release procedure

1. Refresh the official source ledger and review upstream compatibility.
2. Run `python -m unittest discover -s tests -v` and
   `python scripts/check_release.py --root .`.
3. Build with `python -m build`. Install the wheel in a fresh environment
   outside the source checkout. Check the console command, offline doctor,
   resources and every knowledge-pack hash.
4. Run the same artifact on Windows, macOS and Linux. Keep mocked writes,
   authenticated reads and any separately authorized paid tests distinct.
5. Exercise the knowledge pack against the supported Empire engine in a
   temporary vault using `scripts/verify_knowledge_attachment.py`.
6. Record measured results in `docs/VALIDATION.md`. Inspect source archives,
   wheel contents, generated metadata and Git history for private material.
7. Publish the immutable version tag, wheel, source distribution and
   `SHA256SUMS`. Never replace published bytes under the same version.
8. Admit the released commit and exact codeload ZIP checksum to the
   `cto-legends` catalog. Verify discovery, preview, clean installation,
   handoff, runtime and update status before shipping the catalog change.

The provider CLI remains an external prerequisite. Installing this package
must not install provider credentials, modify a vault or create cloud resources.
