**Findings:**

*   **P0/P1 Blockers:** None found. The remediation looks very solid and addresses all the critical security, data integrity, and concurrency paths.
*   **Stale-Read Blocker:** **Confirmed Fixed.** The addition of `with stream_write_lock(session, record.stream_id):` combined with the internal `session.refresh(record)` in `resolve_qc_record` correctly serializes access to the stream and guarantees the record is up-to-date before updating its statistical inclusion state and recomputing evaluations.
*   **API Key Hashes (Auth perf/DoS):** Fixed. Moving to a deterministic `key_lookup_hash` alongside PBKDF2 allows the system to do a targeted point query (and a fallback legacy point query for unmigrated keys) without having to do full-table PBKDF2 verification scans.
*   **RBAC / Spoofing:** Fixed. Replacing client-side spoofable fields like `payload.acknowledged_by` with the authoritative `user.actor` effectively closes the actor impersonation vulnerability. Furthermore, separating `Permission.READ` for basic listing endpoints ensures users like Auditors don't need `INGEST_QC` permission to view the app, satisfying least-privilege principles.
*   **Audit Reasons:** Fixed. Backend and frontend correctly enforce reasoning inputs when changing the state of alerts, investigations, CAPAs, and resolving QC records (both exclude and reinstate).

Everything looks great to merge. Good job getting these locked down.
