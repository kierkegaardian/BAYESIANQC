Here are the review findings for the BAYESIANQC import-ingestion readiness patch based on your requested focus areas.

### 1. Multiprocessing Queue Deadlock: **FIXED**
The worker boundary in `read_source_rows_with_timeout` now correctly reads the payload via `queue.get()` *before* invoking `process.join()`. This ensures the child process's background pipe-flushing thread can successfully drain the IPC pipe, allowing the worker process to exit gracefully without deadlocking.

### 2. Archive Partial-Write Race: **FIXED**
The implementation in `archive_file` now writes to a unique temporary file (`.{target.name}.{pid}.{uuid}.tmp`) and relies on POSIX's atomic `tmp_target.replace(target)`. This effectively prevents parallel ingestions or file readers from interacting with a partially written archive.

### 3. Run/Backlog Policy: **FIXED**
The `ImportRunContextPolicy` explicitly ensures data completeness. The default requirement correctly rejects data without a run or backlog context, while parsing profiles configured with `"run_context_policy": "allow_provisional"` allow rows to advance. The server-side patching validations are also correctly enforced via `enforce_run_context`.

### 4. Upload Limits: **FIXED**
By executing a bounded read with `file.file.read(settings.max_upload_bytes + 1)`, the server immediately evaluates whether the payload breaches the file size limitation, gracefully aborting with HTTP 413 without pulling gigabytes into memory.

### 5. Restore-Proof OOM/Copy Behavior: **P0 BLOCKERS REMAIN**
While file hashing operates efficiently with 1MB streams, there are **two critical OOM blockers** affecting the database restore checks:

**A. Whole-File Read of the Database Dump**
In `scripts/prove_import_restore.py`, `_remove_unsupported_dump_settings` reads the output of `pg_dump` entirely into memory:
```python
lines = path.read_text(encoding="utf-8").splitlines()
```
Because the SQL dump encompasses all database table data, this will rapidly consume gigabytes of RAM in a production environment and fail with an OOM.
* **Fix Required:** Refactor this to open the file as a stream. Iterate line-by-line, write non-matching lines to a temporary file, and use `.replace()` to swap it with the original dump.

**B. Unbounded Result Set Fetching**
In `app/services/import_restore_checks.py`, the database verification loops over the entire `ImportRow` and `ImportBatch` tables:
```python
for row_id, batch_id, status, qc_record_id, quarantine_id in session.execute(
    sa_select(...).order_by(col(ImportRow.id))
):
```
SQLAlchemy pulls the full result set into memory by default. Because `ImportRow` will easily grow into millions of records, caching the entire result set in Python memory is a massive OOM hazard.
* **Fix Required:** Append `.yield_per(1000)` (or an appropriate chunk size) to the `select` queries to enforce server-side cursors, allowing the script to stream database rows effectively.

***

**Summary:** The patch resolves the primary ingestion application blockers safely. However, **readiness remains blocked** until the OOM hazards in the background backup/restore proof tooling are corrected with streaming processing.
