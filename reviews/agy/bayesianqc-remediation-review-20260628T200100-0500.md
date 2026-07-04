## Findings

### P1 Blocker: Stale Read / Race Condition in `resolve_qc_record`
In `app/main.py`, the `resolve_qc_record` endpoint fetches the `QCRecord` *before* acquiring the `stream_write_lock`.
```python
    record = session.exec(select(QCRecord).where(QCRecord.id == record_id)).first()
    if not record:
        raise HTTPException(status_code=404, detail="QC record not found")
    with stream_write_lock(session, record.stream_id):
        try:
            before = record.model_dump(mode="json")
            reason = payload.resolved_reason
            if payload.include_in_stats != record.include_in_stats:
```
**Impact:** If two concurrent requests attempt to update the same record (or if one overlaps with another operation holding the stream lock), the second request will operate on a stale `record` object since it was fetched outside the lock. This defeats the lock's purpose. It will incorrectly evaluate `payload.include_in_stats != record.include_in_stats` and write the stale object state back to the database, skipping the required reason validation and potentially corrupting the Bayesian stream state which relies on accurate inclusion statuses.

**Remediation:** Add `session.refresh(record)` immediately inside the `with stream_write_lock(session, record.stream_id):` block so that the record's current database state is loaded before comparing and modifying `include_in_stats`.

---

## Confirmation of Previous Blockers

All requested previous blockers have been thoroughly addressed in this remediation, provided the stale read above is fixed:

1. **Auth Lookup DoS: RESOLVED**
   - The addition of `key_lookup_hash` provides a fast, constant-time `O(1)` index lookup for API keys. It successfully bypasses the expensive PBKDF2 hashing phase (`verify_api_key`) on arbitrary incoming keys. Legacy keys are properly checked against `legacy_sha256_hash` and dynamically migrated upon successful authentication.

2. **SQLite Locking / Threadpool Behavior: RESOLVED**
   - Endpoints were successfully converted from `async def` to `def`, which offloads them to FastAPI's external threadpool (preventing event loop starvation).
   - The introduction of `stream_write_lock` successfully guards the critical read-modify-write stream evaluation logic against SQLite's concurrent writer overlaps, which would otherwise throw `OperationalError: database is locked`. *(Assuming `process_ingestion` internally acquires this lock as implied by the passing `asyncio.gather` test).*

3. **Stream / Prior Version Race Handling: RESOLVED**
   - The `uq_streamconfig_stream_version` and `uq_priorconfig_stream_version` database-level `UniqueConstraint`s definitively close the race condition. Combined with the `except IntegrityError` blocks bubbling up as `409 Conflict`, clients can safely retry without corrupting config history.

4. **Chart Resolution UI: RESOLVED**
   - The UI correctly guards resolution actions behind the `canApprove` flag.
   - The interactive chart correctly prompts for a mandatory reason when *excluding* and *reinstating* a point, correctly aligning with the updated backend logic.
   - The `hasNumericChartValue` helper cleanly fixes the tooltip bug, ensuring clicks and hover logic target actual data points rather than overlapping event lines.
