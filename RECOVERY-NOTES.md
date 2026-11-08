# Local source recovery — 2026-11-08

This branch preserves a previously uncommitted local UrnaPack source snapshot
before removal of the large local election-data working directory. It is a
backup branch, not a merge or software/data release. Original source history
and the pending source changes are retained; national raw/derived datasets
and build outputs are excluded.

The recovered final snapshot passed cargo fmt --check, cargo clippy
--all-targets -- -D warnings, cargo test and 147 Python unittest cases.
Python integration checks used the existing locally compiled binaries.
