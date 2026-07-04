I have reviewed the patch. **No P0/P1 blockers remain.** The implementation is production-ready.

Here is the breakdown of how the blockers and critical areas were successfully addressed:

**1. Restore-proof N+1/OOM (`verify_import_links`) - FIXED**
* **OOM/Memory Issue:** You successfully delegated the mismatch detection to the database using `outerjoin` and `.is_(None)`. Using `yield_per=1000` combined with `stream_results=True` ensures Python streams the results efficiently using server-side cursors.
* **Capped Growth:** You enforced a hard memory cap via `_MISMATCH_SAMPLE_LIMIT`, ensuring that even a massively corrupted database won't blow up the script's memory.

**2. Parser-profile N+1 (`apply_ready_rows`) - FIXED**
* By swapping `session.commit()` out for `session.flush()` inside `_apply_one`, the SQLAlchemy `Session` retains objects in its identity map. When `profile_for_batch` uses `session.get(ParserProfile, ...)`, it correctly hits the local identity cache rather than querying the database for every row. This thoroughly resolves the N+1 issue.

**3. Parser Timeout - SOLID**
* The use of `multiprocessing.get_context("spawn")` perfectly isolates the parser. If the worker hangs or loops indefinitely, `queue.get(timeout=...)` correctly catches it, cleanly terminates the worker process, and correctly records `FAILED_TO_INGEST` and `408 Request Timeout` without threatening the main web server process.

**4. Archive Atomicity - SOLID**
* The file archiving logic successfully writes to a unique `.tmp` file (seeded with `uuid4` and PID) and utilizes `Path.replace()`, which translates to an atomic POSIX `rename()`. This guarantees that readers and backup tools will never capture partially written files.

**5. Upload Bounds - SOLID**
* `file.file.read(settings.max_upload_bytes + 1)` correctly halts memory consumption right at the boundary limit, preventing application OOM. It gracefully returns a standard `413 Payload Too Large` error before parsing is ever attempted.

**6. Run/Backlog Policy - SOLID**
* The `run_context_policy` is correctly structured and enforced across all entry points: initial ingestion mapping, manual user patching (`update_row`), and strictly gated inside `_apply_one`. Rows successfully revert to `needs_review` if they lack the required context, with no loopholes for bypassing the check.

***

**Minor Non-Blocking Observation (P3/P4)**
In `prove_import_restore.py`, `verify_archive_hashes` appends to its `mismatches` list without using `_MISMATCH_SAMPLE_LIMIT`. If an operator runs this script against a database expecting 5 million files, but the mounted `archive_root` is completely empty, the script will build a 5-million element list in memory. Because this is an operator-run maintenance script and not an application endpoint, it is strictly a low-priority note rather than a blocker.
