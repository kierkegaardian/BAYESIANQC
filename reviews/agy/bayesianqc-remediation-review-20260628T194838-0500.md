Here is the review of the BayesianQC remediation implementation, prioritized by P0/P1 blocking issues.

### P0 / P1 Blocking Issues

#### 1. [P0 - Security / DoS] O(N) PBKDF2 Verification on Every Request
**Location:** `app/rbac.py` -> `get_current_user`
**Impact:** Immediate CPU exhaustion and trivial Denial of Service (DoS).
**Details:** The API key migration implementation attempts a `legacy_hash` (SHA-256) lookup first. For migrated keys, this lookup correctly fails. The code then falls back to fetching **all** active keys and running `verify_api_key` against each one sequentially. Because `verify_api_key` uses PBKDF2 with 210,000 iterations, a single request from a migrated user (or an attacker sending a dummy key) will force the server to compute `210,000 * N_active_keys` iterations. If a lab has 50 active keys, every single API request will require over 10 million hash iterations, completely killing the server.
**Remediation:** High-entropy API keys (144-bits) do not require slow KDFs like PBKDF2 because they are immune to dictionary attacks (a single SHA-256 round is perfectly secure). If PBKDF2 is strictly mandated by a compliance team, the API keys MUST be redesigned to include a public identifier prefix (e.g., `key_id:secret_string`) so the backend can look up the specific row by ID in O(1) time before performing the hash comparison.

#### 2. [P0 - UI Bug] QC Point Exclusion is Completely Broken
**Location:** `frontend/src/pages/ChartView.vue` -> `handleChartClick`
**Impact:** Technicians cannot exclude outlier QC points, breaking a critical lab workflow.
**Details:** When a user clicks a point to exclude it, they are prompted for a reason. The response is captured in a variable named `confirm`, but the submission logic attempts to read from an undefined variable named `result`:
```typescript
await updateResolution(recordId, false, result.value); // result is undefined!
```
This throws a `ReferenceError`, silently fails in the console, and prevents the API call from firing.
**Remediation:** Change `result.value` to `confirm.value`.

#### 3. [P1 - Race Condition] Stream Creation Postgres Lock Bypass
**Location:** `app/services/locks.py` -> `_lock_stream_row` & `app/main.py` -> `create_stream`
**Impact:** Potential for duplicated configuration versions and corrupted state.
**Details:** The Postgres `stream_write_lock` uses `.with_for_update()` to lock existing rows for a stream. However, when a brand-new stream is being created via `POST /streams`, there are no rows to lock. `with_for_update()` will lock 0 rows, allowing concurrent requests for the same new `stream_id` to bypass the lock entirely. Both will see no existing configuration and attempt to insert `version=1`.
**Remediation:** Enforce a composite unique constraint on `(stream_id, version)` in the `StreamConfig` table to guarantee an integrity error upon race conditions, or utilize Postgres advisory locks (`pg_advisory_xact_lock`) which can lock arbitrary string identifiers before rows exist.

#### 4. [P1 - Concurrency Flaw] SQLite RLock is Useless in Async Endpoints
**Location:** `app/services/locks.py` & `app/main.py`
**Impact:** Zero concurrency protection for SQLite and severely blocked event loops.
**Details:** `stream_write_lock` attempts to serialize SQLite writes using `threading.RLock`. However, the route handlers (`async def ingest_qc_record`, `async def resolve_qc_record`, etc.) are declared as `async def`. In FastAPI, `async def` endpoints run concurrently on the single main asyncio event loop thread. Because `RLock` checks thread identity, it is trivially reentrant for any concurrent request running on the same thread—meaning the lock provides no serialization whatsoever. Additionally, performing synchronous database operations inside `async def` endpoints starves the event loop.
**Remediation:** Change the endpoints to standard `def` (remove `async`) so FastAPI automatically dispatches them to a threadpool. This will stop them from blocking the event loop and ensure that the `threading.RLock` correctly serializes access across different threads.

---

### Non-Blocking Notes & Lab-Readiness Gaps

* **API Key DB Mutation on Startup:** `seed_defaults` attempts to migrate the `local-dev-key` to PBKDF2 on every boot. Because of the aforementioned `legacy_hash` lookup failure, it iterates all keys, re-hashes a new PBKDF2 string (with a new salt), and triggers a DB write on every single application startup.
* **Missing Instrument/Method Validation:** `process_ingestion` properly verifies that the payload's `analyte` and `qc_level` match the stream configuration, but it fails to check that `instrument_id` and `method_id` align with the stream. This allows records with mismatched metadata to slip into the stream.
* **Test Concurrency Illusion:** `test_concurrent_same_stream_ingestion_keeps_posterior_count` uses `httpx.ASGITransport` to hit `async def` endpoints that execute synchronous code. This blocks the test's event loop, forcing the requests to execute perfectly sequentially. The test passes, but it isn't actually testing concurrent execution.
