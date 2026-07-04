# BAYESIANQC Import Ingestion Requirements

Date: 2026-07-04

Provenance:
- Source questionnaire export: `/home/user/.codex/attachments/44231415-b236-4e2c-81f9-e8b4b9c78a60/pasted-text.txt`
- Related planning tool: [Import Requirements Questionnaire](IMPORT_REQUIREMENTS_QUESTIONNAIRE.html)

This document turns the filled questionnaire into implementation requirements for petrochemical instrument-file ingestion. It is a requirements baseline, not a completed design or validation package.

## Product Intent

BAYESIANQC should ingest petrochemical instrument and middleware files through a controlled parser-profile workflow. Successful file parsing must preserve file provenance, parse row-level candidates, and apply accepted rows through the existing QC ingestion service so rule evaluation, Bayesian risk, alerts, quarantine, backlog completion, and audit history remain consistent.

The system must not require an external run/sample id in the file. If a file lacks a run id, the import workflow must support manual association to a scheduled QC backlog item and may suggest matches by configurable proximity rules.

## Confirmed Decisions

- First target domain: petrochemical instruments and middleware exports.
- Supported file extensions must include `.dat` and `.txt` in addition to common structured formats.
- Initial formats: CSV, XLSX, XML, and other petrochemical export formats discovered during onboarding.
- Files may contain mixed patient/sample/QC/result/event data; the parser must classify rows rather than assume every row is a QC result.
- Delivery modes should support manual upload, watched folders, collector agent, and direct API upload.
- Parser profiles may be configured by admins and supervisors.
- Parser auto-selection should support per-instrument filename patterns; reusable pattern configurations should be possible when multiple instruments share a file shape.
- A run is primarily a scheduled QC backlog item for MVP requirements.
- If no run id exists, the app should not silently create a final run. It should require manual choice unless later product rules explicitly allow provisional runs.
- Matching window around scheduled or manually started run time should be configurable, with an initial expected range of two to three hours on either side.
- Ambiguous scheduled-run matches must stop for manual association. The system must not guess.
- Manual runs should probably carry `started_at`, `started_by`, and expected stream/QC-level context.
- Partial files should apply good rows immediately.
- Out-of-bounds or mismatched rows should be visible both as import exceptions and through QC quarantine when they reach QC validation.
- Raw files belong in a customer-controlled archive location and are subject to customer retention policy after attachment to a sample/run/import context.
- The collector should run on Windows and Ubuntu. It may be installed on a local interface server, middleware host, network-share watcher, or individual instrument-run PC.

## Parser Profile Requirements

Each parser profile must be stored as versioned configuration in the database.

Minimum profile fields:
- Profile id, display name, active status, version, author, and reason.
- Source type: instrument, middleware, LIMS, manual upload, or collector.
- Supported filename patterns and file extensions.
- Optional directory/source hints, including instrument identity from watched-folder context.
- Format settings: delimiter, quote character, encoding, header row, timezone, decimal convention, and date/time formats.
- Column mappings with aliases.
- Defaults for fields that may not appear in the file.
- Required parser fields.
- Row filters that identify QC rows, sample rows, event rows, header/footer rows, and ignored rows.
- Stream-resolution rules.
- Run/backlog matching rules and matching window.
- Archive policy and failed-file policy.

Profile changes must be auditable. Draft/active/approval semantics remain an open decision.

## File Import Requirements

Every file handled by the system must create an import batch record, even if parsing fails.

Import batch fields:
- Original filename.
- Source path or upload source.
- Archived path.
- SHA-256 file hash.
- File size.
- Parser profile id and version, when selected.
- Source instrument or source system, when known.
- Detected format and extension.
- Upload/detection actor or service account.
- Timestamps for received, archived, parsed, applied, failed, and completed states.
- File-level status.
- File-level failure reason, when applicable.

Raw file archiving:
- Archive successfully parsed files.
- Archive failed files with hash and failure reason unless customer policy explicitly forbids it.
- Store archive paths under a customer-owned retention location.
- Never rely on the source instrument export folder as the only audit copy.

File-level failure examples:
- No matching parser profile.
- Unsupported or unsafe file type.
- Corrupt/unreadable file.
- Unreadable encoding.
- Missing required headers or required data regions.
- No parseable result/event rows.

File-level failures should move or copy the file into a failed-to-ingest location and mark the import batch failed.

## Row Parsing Requirements

The parser must produce row-level candidates before QC application.

Each import row should store:
- Import batch id.
- Row number or message locator.
- Raw row payload.
- Row type: QC result, sample/result, event, ignored, parse error, or unknown.
- Parsed fields.
- Parser warnings and errors.
- Stream-resolution status.
- Run/backlog-resolution status.
- Apply status.
- Linked QC record id, quarantine id, event id, or backlog item id when available.

Minimum fields for a row to become an apply-ready QC result:
- Result value or controlled result token.
- Test method or resolvable method default.
- Instrument identity, either from file, parser profile, or source directory.
- Parameter/analyte/test code.
- Timestamp, from file content or controlled context.

If timestamp is not present in the row, it may be inferred only from explicit file-level metadata, run context, or manual association. If no controlled timestamp source exists, the row must require manual resolution before QC application.

The parser must support non-detect and alphanumeric result tokens such as `ND`, `<x`, `>x`, and instrument-specific qualifier strings. These must not be silently converted into ordinary numeric results. The parsed row should preserve the original token and produce a numeric value plus qualifier only when the parser profile defines that rule.

## Stream Resolution

Rows should resolve to canonical QC streams before application.

Resolution may use:
- Explicit stream id in the file.
- Instrument plus method plus parameter/analyte plus QC level plus units.
- Parser defaults.
- Directory/source context.
- Scheduled backlog context.

Unknown or conflicting stream mappings should create import exceptions. They should not be applied to QC records until resolved.

## Run And Backlog Association

Rows do not need an external run/sample id to enter the import workflow.

Run association rules:
- Prefer explicit `qc_backlog_item_id` when a user manually associates the import or row.
- Suggest scheduled/in-progress backlog matches when instrument, stream or stream tuple, QC level, lot, and timestamp proximity fit one candidate.
- Use a configurable time window, initially two to three hours before and after scheduled/manual start time.
- If exactly one high-confidence match exists, the UI may present it as a suggested association.
- If more than one match exists, manual association is required.
- If no match exists, manual choice is required for MVP. Provisional run creation is a future option, not the default.

Manual run/backlog initiation should add fields for `started_at`, `started_by`, expected stream id, expected instrument, expected QC level, and optional expected lot.

## Apply Behavior

Preview and apply are separate workflow steps.

Preview:
- Parses the file.
- Archives the file.
- Creates import batch and import row records.
- Shows accepted, apply-ready, mapping-required, run-association-required, parse-failed, and quarantine-likely rows.
- Does not update QC statistics.

Apply:
- Applies ready rows through the existing QC ingestion service.
- Good rows from partial files may apply immediately.
- Row-level failures must not block good rows from the same file.
- Existing QC validation remains authoritative for units, bounds, mappings, duplicate detection, and quarantine.

## Operator Workflow

The UI should support:
- Import batch list by instrument/source/status/date.
- Import detail with raw file metadata, parser profile version, and row status counts.
- Row review for mapping, parser error, ambiguous run association, and quarantine result.
- Manual association of rows to scheduled backlog items.
- Re-preview after parser profile changes when requested.

Open decisions:
- Which roles review import exceptions.
- Whether every import requires preview approval before apply.
- Whether users may edit parsed values, or only mappings/run associations.
- Whether parser changes automatically re-preview old failed files.

## Collector Requirements

The API must own canonical import, parse, archive, audit, and apply behavior.

A collector should be a separate installable process or service that can run near instruments or network shares. The collector should:
- Watch configured folders.
- Identify candidate files by profile/source settings.
- Avoid direct database access.
- Upload files to BAYESIANQC import endpoints.
- Retry safely.
- Keep a local sent/failed spool.
- Avoid deleting source files by default until an explicit customer policy says otherwise.

Supported collector deployment targets:
- Windows service on an instrument-run PC.
- Windows service on a local interface or middleware server.
- Ubuntu systemd service on a local interface or application-side server.
- Ubuntu systemd service watching a mounted network share.

The same collector behavior should be used in each deployment mode. The deployment location changes file access and service packaging, not parsing, audit, archive, or QC apply rules.

Open decisions:
- Whether MVP includes API upload only or includes a folder-watching collector.
- Whether collector moves, copies, or deletes source files after server acknowledgment.

## LIMS And Middleware Boundary

LIMS and middleware payloads should probably use the same import batch model as instrument files, but this remains an open decision until real payloads are available.

Outbound webhooks to notify a LIMS about accepted, held, rejected, or quarantined QC should remain a later integration feature unless a pilot requires it.

## MVP Implementation Slices

1. Add database models for parser profiles, import batches, import rows, and explicit instrument/QC runs or run associations.
2. Add backend services for parser profile lookup, file archiving, import batch creation, and row candidate parsing.
3. Implement delimited `.csv`, `.txt`, and `.dat` parsing with profile-driven delimiter/header/date/column rules.
4. Add import preview and apply endpoints that use existing QC ingestion for accepted rows.
5. Add UI for import batch review, row exceptions, and manual run/backlog association.
6. Add failed-to-ingest archive handling with file hash and failure reason.
7. Add a Windows/Ubuntu collector only after manual/API upload proves the server-side import contract.

## Validation Requirements

Tests should cover:
- Successful petrochemical delimited import.
- `.dat` and `.txt` files parsed through profile settings.
- Mixed file with QC rows, ignored sample rows, and event rows.
- Missing run id with manual backlog association.
- Proximity match suggestions inside the configured window.
- Ambiguous backlog match requiring manual association.
- Partial file with good rows applied and bad rows retained.
- File-level failure moved to failed-to-ingest state.
- Non-detect/alphanumeric result token preservation.
- Duplicate file hash/idempotency behavior.
- Audit records for file receipt, parser profile version, apply, quarantine, and manual association.
- Collector smoke tests for Windows-style paths and Ubuntu-style paths.
