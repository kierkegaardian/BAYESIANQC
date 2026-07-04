**Strict Lab-Readiness & Migration Review**

### 🚨 P0 / P1 Blocking Findings

**[P1 - Runtime Boundary / Split-Brain Risk] Stale Uvicorn Process on Port 8010**
*   **Observation:** The packet notes: *"Port 8010 was already occupied by an older BAYESIANQC uvicorn process with no `BAYESIANQC_DB_URL`; it was left untouched."*
*   **Risk:** This violates a strict runtime boundary. If the older process has live-reloading enabled, it may have reloaded with the new Postgres default in `app/db.py` and could be silently mutating your local Postgres database. If it hasn't reloaded, it is still writing to the SQLite `bayesianqc.db` while your new port 8011 process writes to Postgres, creating a local split-brain data state.
*   **Remediation:** The stale process on port 8010 must be terminated immediately to ensure a hard runtime boundary and guarantee no unintended SQLite fallback or rogue Postgres mutations are occurring during validation.

**[P1 - Data Integrity] Incomplete Posterior Value Parity**
*   **Observation:** *"Full Bayesian posterior value recomputation and cross-database value comparison still need automation beyond `PosteriorState.n_obs` sanity."*
*   **Risk:** While row counts and Postgres sequence values are successfully validated, the core scientific data (Bayesian posteriors) is only checked for observation counts (`n_obs`). Floating-point differences, byte-array serialization bugs, or truncation during the SQLite-to-Postgres transfer could silently corrupt the actual posterior states.
*   **Remediation:** While acceptable for an initial local dev slice, full mathematical parity (exact match or within strict epsilon) of the posterior state vectors *must* be automated and verified across the SQLite-to-Postgres boundary before this can be considered lab-ready.

**[P1 - Rollback Readiness] Undefined Local Rollback Path**
*   **Observation:** The packet notes *"Backup/restore SOP, rollback proof... remain blockers for shared lab deployment."*
*   **Risk:** Per reviewer instructions, rollback issues are blocking. Even for local/dev, if the Postgres database gets corrupted during dev work, a developer needs to know how to safely fallback to SQLite.
*   **Remediation:** Explicitly document the local rollback procedure (e.g., reverting the `app/db.py` default URL, or setting a specific ENV var overriding the Postgres URL back to SQLite) to prove the fallback capability is functional.

---

### 🟡 P2 Non-Blocking Findings & Notes

**[P2 - Migration Correctness] Concurrent Writes During Rehearsal**
*   **Observation:** The rehearsal script executes a copy with `--copy-data --truncate-target`.
*   **Note:** In local/dev, you have implicit control over writes. However, moving forward, the migration SOP must explicitly enforce a read-only lock or application downtime on the SQLite source *before* executing the copy, otherwise you risk losing in-flight data.

**[P2 - Schema Coverage] Foreign Key Enforcement**
*   **Observation:** *"Stronger foreign-key coverage and explicit future Alembic DDL deltas are still needed..."*
*   **Note:** SQLite is notoriously lax with FK constraints depending on pragmas, while Postgres is strict. Ensure that the existing SQLite schema isn't harboring orphaned rows that will cause the Postgres `COPY` or `INSERT` commands to explode during a real migration.

**[P2 - Operational] Frontend Build Warning**
*   **Observation:** *"npm --prefix frontend run check: passed with the known Vite large chunk warning."*
*   **Note:** Known technical debt. Does not block the backend database cutover, but should be tracked for resolution before shared deployment.

---

### ✅ Positive Highlights & Commendations
*   **Sequence Validation:** Explicitly checking Postgres sequence `nextval` parity after the data copy is an excellent, often-overlooked safeguard that prevents post-migration `IntegrityError`s.
*   **Concurrency Coverage:** Adding "same-stream concurrent ingestion" to the disposable Postgres tests directly addresses one of the primary motivations for moving to an RDBMS.
*   **Test Isolation:** Utilizing `BAYESIANQC_POSTGRES_TEST_URL` for disposable pytest databases ensures the primary dev database remains uncorrupted by automated test suites.
*   **Dynamic Alembic Head:** The rehearsal script dynamically deriving the Alembic head (`20260703_0002`) instead of hardcoding it prevents silent drift in future migrations.

### Final Verdict
**STATUS: CONDITIONAL APPROVAL (Requires P1 remediations)**
This is a highly structured, well-evidenced local cutover. However, to satisfy strict runtime-boundary constraints, the stale uvicorn process on port 8010 must be killed to eliminate split-brain risk. The data integrity (posterior float parity) and rollback gaps must be formally patched before this architecture progresses to a shared lab environment.
