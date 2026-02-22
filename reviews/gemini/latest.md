I will start by investigating the `QCRecord` and `reprocess_stream_evaluations` implementations to ensure they support the new fields and transactional logic introduced in the diff.
I will read the `QCRecord` definition in `app/db_models.py` and the `reprocess_stream_evaluations` implementation in `app/evaluations.py` to confirm they align with the transactional requirements and the new fields used in the diff.
I will examine the `detect_duplicate` function in `app/storage.py` and verify timezone handling across the codebase to ensure transactional integrity and consistency.
I will read the `detect_duplicate` function and its surrounding context in `app/storage.py` to identify any potential hidden commits or timezone issues.
I will read `app/timeutils.py` to understand the implementation of `as_utc` and ensure it correctly handles timezone normalization.
I will read the `ingest_csv` function in `app/main.py` to determine if it calls `process_ingestion` in a loop and how it handles commits, which could impact performance during bulk out-of-order imports.
I will examine `QCRecordIn` in `app/models.py` to verify how it handles timestamps and ensure consistent timezone comparison during ingestion.
I will read `app/frequentist.py` to check the `evaluate_rules` implementation and determine if it correctly handles the current flushed but uncommitted record.
I will search for any remaining `.commit()` calls in the `app/` directory to identify potential hidden commits that could compromise transactional integrity.
I will read the `resolve_qc_record` function in `app/main.py` to check for redundant commits and ensure that `reprocess_stream_evaluations` is called correctly within the transaction.
I will read the `create_stream_version` function in `app/main.py` to confirm how the `config` is added to the session and identify any hidden or multiple commits.
I will read the `create_stream_config` function in `app/storage.py` to determine if it performs a commit, which would contribute to the multiple commits issue.
I will read the `create_stream_config` function in `app/storage.py` to check for any commit calls.
I will read the remaining part of the `create_stream_config` function in `app/storage.py` to check for a commit call at the end.
This is a critical review of the provided diff, focusing on transaction integrity, performance, and correctness. While the diff addresses some timezone and reprocessing issues, it introduces significant performance risks and fails to fully secure transactional boundaries.

### **P0: Performance Degradation ($O(N^2)$) in Bulk Ingestion**
The current implementation of `process_ingestion` is a performance trap. 
- **The Issue:** `process_ingestion` performs a `session.commit()` at the end of every call. When called within the `ingest_qc_records_csv` loop, this results in a commit per row. More critically, if any record is "out-of-order" (older than the latest record), it triggers `reprocess_stream_evaluations`, which performing a full table scan for that stream. 
- **The Impact:** A bulk upload of 1,000 historical records will execute 1,000 commits and potentially 1,000 full-stream recomputations. This will crush the database.
- **Concrete Fix:** 
    1. Add a `commit: bool = True` parameter to `process_ingestion`.
    2. In `ingest_qc_records_csv`, call `process_ingestion(..., commit=False)`.
    3. Track affected `stream_id`s in the loop.
    4. Call `reprocess_stream_evaluations(session, stream_id)` exactly once per affected stream after the loop.
    5. Perform a single `session.commit()` at the end of the bulk operation.

### **P1: Broken Atomicity in Configuration & Resolution Endpoints**
Endpoints like `create_stream_version`, `create_prior`, and `resolve_qc_record` are not atomic.
- **The Issue:** These functions call `create_stream_config` (which commits), then `record_audit` (which commits), then `reprocess_stream_evaluations` (which commits). 
- **The Impact:** If `reprocess_stream_evaluations` fails (e.g., due to a data constraint or timeout), the new configuration is already committed, but the historical evaluations remain stale. This creates a "corrupted" state where the UI shows new limits but old, incorrect violations.
- **Concrete Fix:** 
    1. Update `create_stream_config`, `create_prior_config`, and `record_audit` to support `commit=False`.
    2. Wrap these endpoints in a single transaction: perform all additions and reprocessing, then commit once at the end.

### **P1: SQL Timezone Comparison Risks**
The diff correctly introduces `as_utc` for Python-side logic but misses it in critical SQL queries.
- **The Issue:** Queries like `QCRecord.timestamp > record.timestamp` in `process_ingestion` and the alert filtering in `stream_chart` compare database values against potentially naive `datetime` objects.
- **The Impact:** If a naive datetime is passed, SQLite/PostgreSQL may interpret it using system local time, causing incorrect "out-of-order" detection or missing alerts.
- **Concrete Fix:** Wrap all datetime parameters in `as_utc()` before passing them to `session.exec()`.

### **P2: Hidden Commits in Storage Layer**
The `app/storage.py` module is riddled with side-effect commits.
- **The Issue:** Functions like `create_stream_config`, `create_prior`, and `store_receipt` (by default) execute `session.commit()`. 
- **The Impact:** This makes it impossible to compose these functions into larger atomic operations without risking partial commits.
- **Concrete Fix:** Standardize all "create/update" functions in `storage.py` to accept a `commit: bool` argument, defaulting to `True` for backward compatibility but allowing callers to opt-out for transactional safety.

---

### **Recommended Test Plan**

1.  **Concurrency/Idempotency Test:** 
    - Simulate two simultaneous `process_ingestion` calls with the same `idempotency_key`. 
    - **Expected:** One succeeds; the other returns the cached result or fails gracefully without corrupting the audit trail.
2.  **Bulk Out-of-Order Ingestion Test:** 
    - Ingest 100 records in reverse chronological order via CSV.
    - **Benchmark:** Reprocessing should happen once (or efficiently), not 100 times.
3.  **Atomic Failure Test:** 
    - Mock `reprocess_stream_evaluations` to raise an exception during `resolve_qc_record`.
    - **Expected:** The `QCRecord` resolution and the `AuditEntry` must NOT be committed to the database.
4.  **Timezone Boundary Test:** 
    - Ingest a record with a timestamp near the DST transition or with an explicit offset.
    - **Expected:** SQL comparison correctly identifies it relative to existing UTC records.

**Get these fixed immediately. I will not approve a system that allows partial configuration updates or $O(N^2)$ ingestion loops.**
