Here is a strict implementation and rollout review of the BAYESIANQC access control plan, focusing on edge cases, safety, and potential bypasses.

### Findings & Recommendations

**P0: Rollout Safety Hazard (Feature Flag Semantics)**
*   **Issue:** The plan states: *"Non-admin roles with no grants initially remain unrestricted behind a feature flag... Any role with at least one grant is restricted."* If enforcement applies immediately to any key that *has* a grant regardless of the flag, then during Step 6 of rollout ("Seed grants for intended service keys"), those service accounts will immediately experience restricted access the moment their first grant is inserted. If a key requires multiple grants, it will have broken/partial access until the seeding script finishes.
*   **Minimal Change:** The feature flag `BAYESIANQC_ENFORCE_ACCESS_GRANTS` must act as a **global bypass** (i.e., when `0`, all users get an `unrestricted` scope, and `accessgrant` rows are completely ignored in production). Seed all grants while the flag is `0`, verify via dry-run/audit logs if possible, and then flip to `1` to enforce everything atomically. Tests can explicitly set the flag to `1`.

**P1: Backlog Target-State Bypass (Scope Escalation)**
*   **Issue:** For `PATCH /qc/backlog/{id}`, the plan states *"require backlog item access"*. Checking the item's *current* scope is necessary but insufficient. If a user has access to a backlog item, they could potentially update its `assignment_group`, `lab_bench`, or `stream_id` to a value *outside* their allowed scope, effectively throwing it over the wall or hijacking items.
*   **Minimal Change:** Update `require_backlog_access` (or add a separate check for mutations) to validate both the **current state** of the item (to allow the read/edit) AND the **target state** of the mutation. A user must not be able to assign an item to a group or bench they cannot access. 

**P1: Import Batch Dangling State (Silent Failures)**
*   **Issue:** For imports, the plan dictates leaving out-of-scope ready rows untouched during `POST /qc/imports/{batch_id}/apply`, while `GET /qc/imports/{batch_id}` hides out-of-scope rows. If a user uploads a batch with mixed scopes, the out-of-scope rows will remain in `ready_to_apply` indefinitely because the original uploader cannot see them to delete them, and applying the batch skips them. This will lead to stuck batch states and database bloat.
*   **Minimal Change:** Do not silently hide out-of-scope import rows. Either (A) reject the file entirely during parsing if it contains out-of-scope streams, or (B) automatically mark out-of-scope rows as `failed` / `ignored` with a clear "out of scope" reason during parsing, so the batch can cleanly reach a terminal state.

**P1: Kiosk Layout Information Leak / UI Crashes**
*   **Issue:** The plan states *"saved kiosk layouts should not leak out-of-scope stream names"* but relies on *"backend stream checks"*. If a user does `GET /kiosk/layouts/{id}` and the backend attempts to dynamically scrub out-of-scope streams from the saved JSON blob, it risks returning a structurally invalid layout that crashes the frontend. 
*   **Minimal Change:** Do not dynamically filter the contents of a saved layout JSON. Instead, enforce at the route level: if a user requests a kiosk layout that contains *any* stream outside their scope, return `403 Forbidden`. 

**P2: Missing Test Coverage**
*   **Issue:** The test plan covers the happy paths and basic denials but misses the edge cases identified above. 
*   **Minimal Change:** Add the following to the backend focused tests:
    *   Scoped key gets 403 when attempting to `PATCH` a backlog item to an out-of-scope `assignment_group`.
    *   `GET /kiosk/layouts/{id}` returns 403 if the layout references an out-of-scope stream.
    *   Feature flag toggling (verify that flag=`0` truly grants `unrestricted` access even when grants exist in the DB, and flag=`1` enforces them).
    *   Comments/Alerts attached to global or null streams (ensure they fail closed).

### Praise / Strong Points in the Plan
*   **Idempotency:** Explicitly calling out idempotency receipts as a potential leakage vector and checking scope *before* idempotent replay is an excellent catch.
*   **Anti-Scope Creep:** Deferring OIDC, advanced UI grant management, and separating Wave 2 (Imports) if it gets too complex are great decisions that keep this slice achievable. 
*   **Direct-Object Reads:** The distinction between using 404 to hide existence on reads and 403 on mutations of known parents is exactly the right security posture. (Just ensure all read endpoints, like `GET /qc/records/{id}`, follow this).
