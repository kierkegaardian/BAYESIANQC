I have reviewed the patch.

**Status of Prior Blockers:**
*   **OOM from whole dump reads:** **Fixed.** `_remove_unsupported_dump_settings` in `prove_import_restore.py` now streams the SQL file line-by-line (`for line in source: target.write(line)`), eliminating the memory bloat.
*   **Unchunked DB result sets:** **Fixed.** The iteration in `_archive_rows` and `verify_import_links` correctly leverages `.execution_options(yield_per=1000, stream_results=True)` to stream server-side cursors in chunks.

**Remaining P0/P1 Issues:**
There are two critical remaining issues that must be fixed before this is production-ready.

**1. Restore Proof: OOM and N+1 Queries in `verify_import_links` (P0/P1)**
While the main query in `verify_import_links` uses `yield_per=1000` to stream rows, the loop body calls `_id_exists(session, ...)` for every row.
*   `_id_exists` uses `session.get(model, row_id)`.
*   Because `session.get()` caches every fetched object in the SQLAlchemy `Session`'s identity map, looping over millions of applied rows will load millions of `QCRecord` objects into memory until the script OOMs, completely defeating the `yield_per` strategy.
*   Furthermore, because this is an iterative loop, it executes a sequential `SELECT` query for every single unique `QCRecord` and `ImportBatch`. 10 million rows will result in 10 million synchronous DB queries, turning this script into a multi-hour process.
*   **Fix:** Replace the iterative loop with bulk referential integrity queries on the database side (e.g., using `outerjoin` and checking for `IS NULL`).

**2. Run/Backlog Policy: N+1 Query in `apply_ready_rows` (P1)**
To enforce the new run/backlog policy, `_apply_one` now fetches the parser profile for each row by calling `profile_for_batch(session, batch)`.
*   `profile_for_batch` is implemented using `session.exec(select(ParserProfile).where(...)).first()`.
*   Unlike `session.get()`, a `select().first()` bypasses the identity map and emits a new `SELECT` query to the database *every single time*.
*   Because `apply_ready_rows` calls `_apply_one` in a tight loop, applying a moderate batch of 10,000 rows will fire 10,000 synchronous `SELECT` queries during the web request, likely causing the HTTP request to time out.
*   **Fix:** Either resolve the `profile` once in `apply_ready_rows` and pass it down to `_apply_one`, or rewrite `profile_for_batch` to use `session.get(ParserProfile, batch.parser_profile_id)` so it only queries the database once and hits the local identity map cache for subsequent rows.

**Other Areas Reviewed (No P0/P1s Found):**
*   **Multiprocessing Timeout:** Solid. The use of `context.Queue` with `queue.get(timeout)` cleanly guarantees process halting and prevents queue deadlocks if the parser process stalls.
*   **Archive Atomicity:** Solid. Writing to a `.tmp` file using the PID + UUID and moving it via `Path.replace()` provides strong cross-platform atomicity.
*   **Upload Bounds:** Solid. Explicitly calling `file.file.read(settings.max_upload_bytes + 1)` successfully prevents memory exhaustion from unbounded file streams before raising the 413 error.
