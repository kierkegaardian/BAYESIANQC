Here is the review of the import-ingestion readiness patch based on your requested focus areas.

There are **blocking issues remaining** that must be addressed before this feature is production-ready.

### 🔴 P0: Multiprocessing Queue Deadlock (Process Timeout Behavior)
In `app/services/import_parse_timeout.py`, the timeout mechanism will consistently fail and reject perfectly valid, fast-parsing files if their resulting payload is larger than the OS pipe buffer (typically 64KB).
```python
    process.start()
    process.join(timeout_seconds)  # <--- Deadlock trigger
    if process.is_alive():
        process.terminate()
```
**Why it fails:** If `read_source_rows` generates a large list of `SourceRow` objects, the child process's `queue.put()` will block once the underlying pipe buffer fills up. The child process cannot exit until the parent reads the data. However, the parent is blocked on `process.join()`, waiting for the child to exit. The timeout expires, the parent wrongly assumes parsing is hung, terminates the child, and raises `ImportParseTimeout`.
**Fix:** The parent must wait on the `queue` for the result with a timeout, rather than waiting on the `process` to exit.
```python
    from queue import Empty
    process.start()
    try:
        status, *payload = queue.get(timeout=timeout_seconds)
    except Empty:
        process.terminate()
        process.join()
        raise ImportParseTimeout(...)
    process.join()
```

### 🔴 P1: Race Condition & Partial Writes in Archive Writes (Data Safety)
In `app/services/imports.py`, the archive file writing strategy is unsafe against crashes and concurrent uploads.
```python
    try:
        with target.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        pass
```
**Why it fails:** `open("xb")` creates the file atomically, but does not write its contents atomically.
1. **Crash Risk:** If the server or disk fails mid-write, a 0-byte or partially written file is left behind. Future uploads of the same file will hit `FileExistsError` and incorrectly assume the file was safely archived.
2. **Race Condition:** If two users concurrently upload the same file, the second thread hits `FileExistsError` and returns immediately. If a downstream process attempts to read the archive file before the first thread finishes `handle.write(data)`, it will read truncated data.
**Fix:** Write to a temporary file first, then perform an atomic rename using `os.replace` or `Path.replace()`.
```python
    if target.exists():
        return digest, str(target)

    tmp_target = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    tmp_target.write_bytes(data)
    tmp_target.replace(target) # Atomic rename overrides any concurrent writers safely
```

### 🔴 P1: OOM Vulnerability in Restore-Proof Tooling
In `app/services/import_restore_checks.py`, the verification scripts execute unbounded `.all()` queries against the database's largest tables.
```python
    for row in session.exec(select(ImportRow).order_by(col(ImportRow.id))).all():
```
**Why it fails:** SQLModel's `.all()` fetches all rows and instantiates them into memory simultaneously. Because `ImportRow` contains raw file representations and parsed JSON blobs, running this script against a production database will rapidly exhaust memory and crash with an Out-of-Memory (OOM) error, rendering the restore-proof capability broken in production.
**Fix:** Either use `.yield_per(1000)` to stream the results iteratively, or constrain the query to select only the lightweight columns it actually needs (e.g., `select(ImportRow.id, ImportRow.batch_id, ...)`). The same issue applies to the `ImportBatch` query in `_archive_rows`.

---

### 🟡 Minor: Sticky Run/Backlog Warnings (Run/Backlog Policy)
In `app/services/import_apply.py` and `app/services/import_mapping.py`, a `RUN_CONTEXT_REQUIRED_WARNING` is correctly appended to `row.warnings` if a run/backlog association is missing. However, if a user manually resolves this by providing the missing `run_id` via the update endpoint, `update_row()` (in `imports.py`) validates the fields but **does not clear the warning**.
While this won't block the row's `READY_TO_APPLY` status (since `errors` are cleared), the row will permanently display a confusing "run/backlog association is required" warning in the UI even after the user has satisfied the requirement.

### Conclusion
**Blocking issues remain.** The multiprocessing deadlock (P0) and archive write data-safety race conditions (P1) must be patched before rollout.
