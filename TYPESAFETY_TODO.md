# Typesafety TODO (BAYESIANQC)

Last updated: 2026-01-29

## Tech choices (current)
- OpenAPI is the source of truth for API shapes.
- Frontend types are generated with `openapi-typescript` into `frontend/src/api/schema.ts` (do not edit by hand).
- Frontend uses `frontend/src/api/contracts.ts` for stable, ergonomic aliases.
- Python static type checking uses `pyright` (`requirements-dev.txt`, `pyrightconfig.json`) in `basic` mode.

## Done (this pass)
- Removed frontend `any` usage and typed all pages/components against OpenAPI-generated schemas.
- Added typed response models for CSV ingest, report summary, and chart endpoints.
- Strengthened backend domain enums for QC disposition and signal severity.
- Added `col(...)` wrappers where SQLModel annotations otherwise confuse static typing.
- Made `pyright` pass with 0 errors.

## TODO (next)
### CI / automation
- Add a single “quality” command for CI/dev: run `pytest`, `pyright`, `frontend` `typecheck`, and a `gen:api` drift check.
- Add a “drift guard” that fails if `frontend/src/api/schema.ts` is not up to date with backend OpenAPI (either committed regen, or a `git diff --exit-code` check after `npm run gen:api`).

### Backend typing improvements
- Tighten DB model types to match API/domain types:
  - Store `Disposition` as an enum in `AlertRecord` (instead of `str`) so conversions aren’t needed at the API boundary.
  - Consider modeling `signals` / `bayesian_risk` as Pydantic models at the boundary where they’re written/read (to reduce `dict[str, Any]` usage).
- Reduce `Any` leakage for JSON columns by introducing a shared JSON type alias (and/or ensuring `JsonValue` is used where possible).
- Align audit models:
  - Decide if `AuditEntryOut.after` should be required. Today `AuditEntry.after` is nullable but `AuditEntryOut.after` is not.
  - If required: enforce non-null at write-time and consider backfilling legacy rows.
  - If optional: update `AuditEntryOut` to `Optional[...]` and regen OpenAPI + TS types.

### Python type-checking posture
- Decide whether `pyright` should gate merges (CI-required) or remain best-effort.
- If gating: progressively increase strictness by directory (or file) and address SQLModel/SQLAlchemy typing gaps with targeted casts/helpers rather than broad ignores.

### API/client ergonomics
- Add typed client helpers (thin wrapper around `fetch`) that:
  - centralize endpoint URLs, headers, and JSON parsing
  - return OpenAPI-typed results (and typed errors)
- Consider generating a typed client (not just types) if/when the API surface grows enough to justify it.

### UX / explainability (Bayesian outputs)
- Expose `posterior_mean`, `posterior_sigma`, and `predictive_sigma` in the UI (e.g., alert tooltip/details panel) so users can interpret *why* risk is high.
