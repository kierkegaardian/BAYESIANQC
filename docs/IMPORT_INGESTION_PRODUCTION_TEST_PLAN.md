# BAYESIANQC Import Ingestion Production Readiness Test Plan
## Purpose
This plan verifies whether the import ingestion system is production-ready for a controlled lab pilot. It is written as an agent handoff: execute the phases in order, collect evidence, and stop on any P0/P1 failure.
The target feature set is server-side import ingestion: parser profiles, archive-first uploads, import batches and rows, run/backlog association, apply through existing QC ingestion, artifacts/peaks, collector event contracts, and the import/profile UI. The Go collector binary is not in scope unless it has been implemented in a later branch.
## Agent Rules
- Work from `/home/user/projects/BAYESIANQC`.
- Do not test against real production data unless the user explicitly provides a sanitized production copy and approves the test window.
- Do not push or change remotes.
- If the worktree is dirty, classify the dirty files before testing. If changes are unrelated to import ingestion or access enforcement, stop and ask.
- Use a disposable archive root: `export BAYESIANQC_IMPORT_ARCHIVE_ROOT="$(mktemp -d)"`.
- Save all evidence under `reviews/import-readiness/<timestamp>/`.
- Final output must include: pass/fail table, command transcript paths, defect list with severity, residual risk, and an explicit production readiness recommendation.
## Readiness Gates
Production-ready means all of these are true:
- Fresh Postgres migrations install the schema and existing migration rehearsal passes.
- Import APIs preserve the legacy `/qc/records` path and do not duplicate QC records on repeated uploads.
- Every handled file creates an `ImportBatch`, archived file, hash, status, and collector action.
- Bad files are archived and marked `failed_to_ingest`; row-level defects remain reviewable import rows.
- Parser profiles are editable only by allowed roles and every profile mutation is audited.
- Delimited, XLSX, and XML profiles parse known-good files and reject or quarantine bad rows deterministically.
- Ambiguous run/backlog matches are never guessed.
- Applying ready rows uses existing `process_ingestion`, quarantine, audit, alert, and backlog-completion behavior.
- UI supports upload, review, manual row association, apply, artifact/peak inspection, and profile creation without console errors.
- Archive, audit, retention, backup, and restore behavior are documented and verified for the selected deployment.
## Phase 0: Preflight And Environment
Commands:
```bash
mkdir -p reviews/import-readiness
stamp="$(date +%Y%m%dT%H%M%S%z)"
packet="reviews/import-readiness/$stamp"
mkdir -p "$packet"
git status --short --branch --untracked-files=all | tee "$packet/git-status.before.txt"
git log --oneline --decorate -10 | tee "$packet/git-log.txt"
docker compose ps postgres | tee "$packet/postgres-status.txt"
```
Pass criteria:
- Current branch and dirty state are understood.
- Postgres is healthy or can be started with `docker compose up -d postgres`.
- No unrelated dirty files will be modified during testing.
P0 failure:
- Agent cannot identify which changes are under test.
- Test database cannot be created or destroyed safely.
## Phase 1: Static Quality And Contract Checks
Commands:
```bash
.venv/bin/python -m ruff check app tests scripts | tee "$packet/ruff.txt"
.venv/bin/pyright | tee "$packet/pyright.txt"
npm --prefix frontend run gen:api | tee "$packet/gen-api.txt"
npm --prefix frontend run check | tee "$packet/frontend-check.txt"
git diff --check | tee "$packet/diff-check.txt"
```
Pass criteria:
- Ruff, pyright, generated API, frontend check, and diff check pass.
- Existing Vite large-chunk warning is acceptable only if no new functional warnings appear.
- Regenerated OpenAPI and `frontend/src/api/schema.ts` are either unchanged or intentionally changed by the tested branch.
P1 failure:
- Generated API drift is unexplained.
- Any strict typing error appears in import, access, backlog, ingestion, or UI code.
## Phase 2: Migration And Data Safety
Commands:
```bash
.venv/bin/python -m pytest tests/test_migrations.py -q | tee "$packet/test-migrations.txt"
.venv/bin/python scripts/rehearse_sqlite_to_postgres.py --help | tee "$packet/rehearsal-help.txt"
```
Additional checks:
- Run Alembic upgrade on a disposable Postgres database.
- Confirm tables exist: `parserprofile`, `importbatch`, `importrow`, `instrumentrun`, `importartifact`, `instrumentpeak`, `collectortransferevent`.
- Confirm backlog columns exist: `started_at`, `started_by`.
- Confirm core indexes exist: `ix_importbatch_status_received`, `ix_importrow_batch_status`, `ix_parserprofile_status_type`.
- Confirm downgrade policy. If full downgrade is not supported, document why and verify restore-from-backup instead.
Pass criteria:
- Fresh upgrade reaches the current Alembic head.
- Existing seeded app startup still works after migration.
- No migration creates data loss in existing QC, backlog, quarantine, audit, comments, kiosk, or stream tables.
P0 failure:
- Migration fails on a fresh database.
- Migration corrupts existing QC records, backlog links, audit entries, or idempotency receipts.
## Phase 3: Backend Regression Suite
Commands:
```bash
export BAYESIANQC_IMPORT_ARCHIVE_ROOT="$(mktemp -d)"
.venv/bin/python -m pytest tests/test_imports.py -q | tee "$packet/test-imports.txt"
.venv/bin/python -m pytest -q | tee "$packet/test-all.txt"
```
Pass criteria:
- Focused import tests pass.
- Full test suite passes.
- No test writes archive files into the repo worktree.
Required coverage audit:
- Verify tests cover profile CRUD/RBAC/audit.
- Verify tests cover CSV, TXT/DAT, XLSX, and XML.
- Verify tests cover bad files and row-level errors separately.
- Verify tests cover ambiguous backlog matching.
- Verify tests cover idempotent duplicate apply.
- Verify tests cover collector transfer events.
P1 failure:
- Coverage does not distinguish file-level failure from row-level exception.
- Duplicate upload creates duplicate accepted QC records.
## Phase 4: Parser Profile Functional Matrix
Create profiles and fixtures in a disposable database. For each test, verify `ImportBatch`, `ImportRow`, archive file, audit entries, and UI display.
Test cases:
- IMP-PARSE-001: CSV direct mapping with comma delimiter, quoted values, BOM, and normal numeric result.
- IMP-PARSE-002: TXT tab-delimited mapping with `.txt` extension and explicit delimiter.
- IMP-PARSE-003: DAT table discovery with intro text, table anchor, repeated blank lines, and expected analyte aliases.
- IMP-PARSE-004: XLSX active-sheet import with header row and one valid row.
- IMP-PARSE-005: XML mapping with configured row path and child element extraction.
- IMP-PARSE-006: Non-detect token maps only when `result_token_map` contains the token; raw token is preserved.
- IMP-PARSE-007: Alphanumeric token without a map becomes row-level parse error, not accepted QC.
- IMP-PARSE-008: Missing timestamp, result, or units becomes row-level exception.
- IMP-PARSE-009: Unknown extension becomes failed-to-ingest batch with `move_to_failed`.
- IMP-PARSE-010: Expected-analyte discovery ignores unrelated sample analytes.
- IMP-PARSE-011: Peak-table profile creates `InstrumentPeak` rows but does not create QC records.
- IMP-PARSE-012: Artifact-only profile archives evidence and does not affect QC stats.
Pass criteria:
- Parsed fields match profile config exactly.
- Ignored/sample/event rows do not create QC records.
- Errors and warnings are visible in batch detail and UI.
P0 failure:
- Parser accepts an unexpected analyte as QC.
- Parser applies QC when required fields are missing.
## Phase 5: Run And Backlog Association
Set up at least three open backlog items for the same stream and instrument:
- One due within the match window.
- Two due within the same match window to force ambiguity.
- One outside the match window.
Test cases:
- IMP-RUN-001: A file with explicit `run_id` applies rows to that run key.
- IMP-RUN-002: A file without `run_id` and exactly one matching backlog associates provisionally or directly per profile rule.
- IMP-RUN-003: Two matching backlog items leave the row `needs_review`.
- IMP-RUN-004: Manual row patch with `stream_id` and `qc_backlog_item_id` changes the row to `ready_to_apply`.
- IMP-RUN-005: Applying a row linked to backlog completes that backlog item only after accepted ingestion.
- IMP-RUN-006: A quarantined row linked to backlog leaves the backlog open and links the quarantine.
Pass criteria:
- Ambiguous matches are never guessed.
- `started_at` and `started_by` are set when backlog is claimed or started.
- Proximity matching uses scheduled/started time and the configured window.
P0 failure:
- Wrong backlog item is completed.
- Ambiguous match is auto-applied.
## Phase 6: Apply, Quarantine, Audit, And Idempotency
Test cases:
- IMP-APPLY-001: Ready row applies through `process_ingestion` and creates normal QC record, evaluation, audit, and optional alert.
- IMP-APPLY-002: Out-of-bounds row applies into quarantine, not QC record.
- IMP-APPLY-003: Unit mismatch without conversion quarantines.
- IMP-APPLY-004: Future timestamp quarantines.
- IMP-APPLY-005: Repeated `/qc/imports/{id}/apply` does not create duplicates.
- IMP-APPLY-006: Reupload of same file with `auto_apply=true` does not create duplicate QC records.
- IMP-APPLY-007: Mixed batch applies good rows and leaves bad rows reviewable.
- IMP-APPLY-008: Audit log has entries for profile create/update, import create, row update, apply/ingest, quarantine, backlog completion, and collector event.
Pass criteria:
- `QCRecord.idempotency_key` and ingestion receipts prove duplicate protection.
- Batch status transitions are correct: `ready_to_apply`, `parsed_with_exceptions`, `partially_applied`, `applied`, `failed_to_ingest`.
- Quarantine detail keeps raw payload and failure context.
P0 failure:
- Accepted and quarantined rows are indistinguishable in audit.
- Applying one batch changes unrelated streams or backlog items.
## Phase 7: Security, RBAC, And Scope Controls
Run these checks for admin, supervisor, QA manager, QC analyst, data steward, auditor, and invalid key.
Test cases:
- IMP-SEC-001: Missing or invalid API key returns `401`.
- IMP-SEC-002: Read-only users can list batches but cannot upload, patch rows, apply, or post collector events.
- IMP-SEC-003: Supervisor/admin can manage import profiles; QC analyst cannot.
- IMP-SEC-004: Profile management, row association, and apply attempts are audited.
- IMP-SEC-005: If access-scope enforcement is present in the branch, mixed-scope import batches are blocked or split by explicit policy.
- IMP-SEC-006: Filename path traversal attempts archive under the configured archive root only.
- IMP-SEC-007: XML payloads with external entity or entity expansion attacks fail safely.
- IMP-SEC-008: Oversized files are rejected or handled within configured resource limits.
Pass criteria:
- Authorization behavior matches the documented role model.
- No route bypasses `X-API-Key`.
- Archive path cannot escape `BAYESIANQC_IMPORT_ARCHIVE_ROOT`.
P0 failure:
- Unauthorized user can apply QC or edit parser profiles.
- Malicious filename writes outside archive root.
## Phase 8: UI End-To-End Checks
Use the current dev server or a disposable deployment:
```bash
export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
export BAYESIANQC_SEED_LOCAL_DEV_KEY=1
export BAYESIANQC_IMPORT_ARCHIVE_ROOT="$(mktemp -d)"
.venv/bin/uvicorn app.main:app --reload --port 8010
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5177
```
Manual or Playwright scenarios:
- UI-IMP-001: Log in with `local-dev-key`; sidebar shows Imports and Configuration -> Parser Profiles.
- UI-IMP-002: Create active CSV profile from the profile page.
- UI-IMP-003: Upload a good CSV and see batch status counts, archive path, and ready row.
- UI-IMP-004: Apply ready rows and confirm status changes to applied.
- UI-IMP-005: Upload a bad file and see `failed_to_ingest` plus failure reason.
- UI-IMP-006: Upload an ambiguous backlog file, patch row stream/backlog, and apply.
- UI-IMP-007: Upload peak table and see peak table panel populated.
- UI-IMP-008: Confirm no browser console errors, no horizontal overflow at 1440, 1100, and mobile width.
Pass criteria:
- UI state matches API state after refresh.
- Long filenames, archive paths, and row errors do not break layout.
- Disabled controls reflect permissions.
P1 failure:
- UI allows an action that API rejects due to permissions without clear error display.
- Manual association cannot make a valid row ready to apply.
## Phase 9: Operational Readiness
Checks:
- Confirm archive root is durable, backed up, permission-restricted, and not inside the repo.
- Confirm archive retention policy: raw result files, failed files, artifacts, and collector logs.
- Confirm database backup/restore proof after import batches and archived files are created.
- Confirm logs do not leak API keys or protected lab data beyond configured storage.
- Confirm import archive and database records can be reconciled by file hash.
- Confirm app startup fails clearly if archive root is missing or unwritable, or document intended degraded behavior.
- Confirm timezone policy for instrument timestamps and scheduling windows.
- Confirm maximum upload size, parse timeout, and file stability policy for future collector.
Pass criteria:
- A restored database plus archive root can reproduce import evidence.
- Operators know where failed files and archived files live.
- Monitoring can detect failed imports, parse exceptions, and collector event failures.
P0 failure:
- Archive files are not backed up with the database.
- Restore loses evidence required to audit an accepted QC result.
## Phase 10: Production-Like Pilot
Run with sanitized files from at least two actual instruments:
- One routine result report.
- One export with sample rows mixed with QC rows.
- One export with an instrument event or calibration marker.
- One failed/partial export.
- One chromatogram/raw artifact.
- One peak table if the instrument emits peaks.
Procedure:
1. Create parser profiles in draft.
2. Preview each file manually.
3. Compare parsed rows to hand-reviewed expected rows.
4. Activate only profiles with exact match.
5. Re-upload and apply ready rows.
6. Reconcile QC records, quarantine rows, batch rows, archived files, audit entries, and backlog state.
7. Have a second reviewer inspect the readiness packet.
Pass criteria:
- Hand-reviewed expected rows match parsed rows exactly.
- No non-QC sample is applied as QC.
- All exceptions are explainable and reviewable.
- Lab SME signs off on parser profile behavior per instrument.
## Final Report Template
The agent should write `reviews/import-readiness/<timestamp>/REPORT.md`:
```markdown
# Import Ingestion Readiness Report
## Verdict
Ready / Ready with conditions / Not ready
## Environment
- Branch:
- Commit:
- Dirty files:
- DB URL class:
- Archive root:
## Results
| Phase | Result | Evidence |
| --- | --- | --- |
## Defects
| Severity | ID | Description | Repro | Recommendation |
| --- | --- | --- | --- | --- |
## Residual Risk
## Production Conditions
## Sign-Off
```
## Stop Conditions
Stop and report immediately if any of these occur:
- Migration failure or data loss.
- Unauthorized user can ingest/apply/edit profiles.
- Duplicate QC records from repeated upload/apply.
- Ambiguous backlog/run auto-applies.
- Archive file missing for any handled upload.
- Bad file disappears without an `ImportBatch`.
- UI action applies rows not shown as ready.
- Production-like pilot disagrees with hand-reviewed expected results.
