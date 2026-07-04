Here is the strict review of the BayesianQC remediation packet.

### 🚨 P0 (Blocking) - Critical Security & Performance Regression

**O(N) Authentication Latency and Denial of Service (DoS) via PBKDF2 Loop**
* **Location:** `app/rbac.py` -> `get_current_user()` and `app/storage.py`
* **Issue:** Because the API keys are just random strings, they lack an identifier. To support randomly-salted PBKDF2 hashes, `get_current_user` falls back to fetching **all** active API keys (`active_keys = session.exec(...).all()`) and running `verify_api_key()` on each one if the legacy lookup fails.
* **Impact:**
  1. **Trivial DoS Attack:** An unauthenticated user sending an invalid API key forces the server to compute `N` PBKDF2 hashes (210,000 iterations taking ~100ms each). If there are 50 active keys, a single invalid request ties up an API thread for 5 seconds. A handful of requests will completely DDoS the application.
  2. **Severe Performance Regression:** Once a user successfully authenticates and their key is migrated, the legacy SHA-256 hash lookup will fail forever. Every subsequent API request they make will be forced into the `O(N)` PBKDF2 loop.
* **Remediation:** API key lookups must be `O(1)`. You have two primary options:
  1. **(Recommended) Update API Key Format:** Change `scripts/create_api_key.py` to generate prefixed keys (e.g., `key_id.random_secret` like `1.xYz...`). Use `key_id` to query the exact record in `O(1)` time, then run PBKDF2 exactly once.
  2. **Deterministic Lookup Hash:** Store a fast, deterministic HMAC-SHA256 hash (using a global backend pepper environment variable) in an indexed column for the `O(1)` database lookup, while retaining the PBKDF2 hash for validation.

### 🚨 P1 (Blocking) - Concurrency Race Condition

**Ingestion Lock Fails on Initial Stream Creation (Postgres)**
* **Location:** `app/services/locks.py` -> `_lock_stream_row()` and `app/main.py` -> `create_stream()`
* **Issue:** The Postgres lock implementation uses `SELECT ... FOR UPDATE` filtered by `stream_id`. However, in `create_stream` (`POST /streams`), the `StreamConfig` row being targeted **does not exist yet**.
* **Impact:** `FOR UPDATE` only locks rows that are returned by the query. An empty result set acquires no locks. If two concurrent requests attempt to create the same stream, both will bypass the lock and attempt to create version 1, resulting in unhandled constraint violations or duplicate streams.
* **Remediation:** Use session-level Postgres advisory locks (`pg_advisory_xact_lock` using a hashed 64-bit integer of the `stream_id` string). This safely serializes execution based on the stream identifier regardless of whether a row exists in the database.

---

### ⚠️ Additional Observations (Non-Blocking / Technical Debt)

1. **Unintentional SQLite Migration Crash Risk:** In `app/migrations.py`, adding `CREATE UNIQUE INDEX IF NOT EXISTS ix_posteriorstate_stream_id_unique` will cause the application to crash on startup if an older local demo database already contains duplicate posterior states (from bugs in older branches). You may want to either clear duplicates in the migration script before creating the index or wrap it in a `try/except`.
2. **Synchronous DB calls in `async def`:** While pre-existing, `ingest_qc_record` and other endpoints are declared as `async def` but heavily utilize synchronous `Session` methods. FastAPI runs `async def` endpoints on the main event loop. Blocking the event loop with synchronous DB calls destroys concurrent throughput capability. These endpoints should ideally be declared as `def` so FastAPI safely delegates them to a threadpool.
3. **Idempotency Lock Fix (Praise):** Moving the idempotency check inside `process_ingestion` under the protection of `stream_write_lock` beautifully patches a prior race condition where concurrent idempotent requests could both bypass the receipt check before the first one committed its receipt.
