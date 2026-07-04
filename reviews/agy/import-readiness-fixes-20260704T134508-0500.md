Here is the review of the import-ingestion readiness patch.

While the feature footprint hits the core requirements for bounds, context enforcement, and restore-proof tooling, there are critical P0 and P1 flaws in concurrency, data safety, transaction management, and the operational viability of the DR tooling. Production readiness is blocked until these are resolved.

### P0 Findings (Correctness & Availability)

**1. Thread Pool Exhaustion / DoS in Parse Timeout**
* **Location:** `app/services/import_parse_timeout.py` (`read_source_rows_with_timeout`)
* **Issue:** You are using `ThreadPoolExecutor(max_workers=4)` combined with `future.cancel()` to enforce `BAYESIANQC_IMPORT_PARSE_TIMEOUT_SECONDS`. In Python, thread cancellation does not interrupt a running thread. If a file is maliciously complex or triggers an infinite loop in the parser, that thread will hang indefinitely. Four such uploads will permanently exhaust the pool. Subsequent uploads will instantly time out while waiting for a thread, resulting in a total denial of service for imports.
* **Fix:** CPU-bound parsing timeouts require process isolation (`ProcessPoolExecutor` where the worker can be forcibly killed) or cooperative cancellation (passing a deadline token into `read_source_rows`).

**2. Transaction Boundary Violation in Batch Apply**
* **Location:** `app/services/import_apply.py` (`_apply_one`)
* **Issue:** `_apply_one` evaluates a single row. If the row lacks a required run context, the function mutates the row and directly calls `session.commit()`. Calling commit inside a fine-grained row-iteration loop destroys the transaction atomicity of the broader batch application, severely degrades database performance, and risks prematurely committing unrelated pending state on the session.
* **Fix:** Remove `session.commit()` from `_apply_one`. Simply `session.add(row)` and let the caller manage the transaction commit after processing the entire batch.

### P1 Findings (Data Safety & Tooling)

**3. TOCTOU Race Condition in File Archiving**
* **Location:** `app/services/imports.py` (`archive_file`)
* **Issue:** You are checking `if not target.exists(): target.write_bytes(data)`. If two users concurrently upload files with the exact same content (same SHA-256 hash), they will both pass the existence check and write to the same path simultaneously. This interleaved writing will corrupt the archive payload on disk.
* **Fix:** Open the file exclusively using `with target.open("xb") as f: f.write(data)` and catch `FileExistsError`, or write to a temporary file and atomically move it into place using `os.replace`.

**4. Restore-Proof Validation Breaks on Relocated Archives**
* **Location:** `app/services/import_restore_checks.py` (`restored_archive_path`)
* **Issue:** The validation script attempts to reconcile paths by calling `Path(stored_path).resolve().relative_to(source_root)`. Because `ImportBatch.archived_path` stores the *absolute* path of the file from the production environment, this check will crash with `outside_archive_root` on any DR environment that mounts the backup archive at a different base directory than production.
* **Fix:** Either stop storing absolute paths in the database (store paths relative to the archive root), or update the tooling to accept a `--db-archive-root` argument so it can correctly map and strip the production prefix.

**5. Restore-Proof Script OOMs / Fills Disk on Production Archives**
* **Location:** `scripts/prove_import_restore.py` (`_copy_archive`)
* **Issue:** The restore proof script uses `shutil.copytree(source_root, target_root)` to clone the entire archive before running tests. Production archives will grow to hundreds of gigabytes or terabytes. A full file-by-file copy in Python is an operational hazard that will trigger out-of-disk/OOM events during DR drills.
* **Fix:** Do not clone the archive root. The script should execute its read-only hash verifications directly against the mounted `--archive-root`.

### Test Gaps

* **Run Context on Manual Updates:** `update_row` in `imports.py` correctly calls `enforce_run_context`. However, there is no test verifying that an API request attempting to update a row while still lacking the required run context is correctly rejected (returns 422).
* **Concurrency / Timeout Efficacy:** The test `test_parse_timeout_returns_controlled_failure` uses a mocked `sleep` which yields the thread back upon completion. It masks the P0 thread exhaustion bug because it doesn't test saturation of the thread pool with runaway CPU loops.

**Recommendation:** Reject. Remediate the P0/P1 issues (specifically moving to process-based parsing timeouts, removing the errant commit, fixing the file write race, and fixing the DR pathing assumptions) before merging.
