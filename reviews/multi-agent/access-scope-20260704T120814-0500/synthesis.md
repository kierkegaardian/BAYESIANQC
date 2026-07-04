# Enterprise Scope Access Review Synthesis

Date: 2026-07-04

Plan reviewed: `docs/ENTERPRISE_SCOPE_ACCESS_PRODUCTION_PLAN.md`

Reviewers:

- AGY: `agy.md`
- Grok build: `grok-build.md`
- Codex backend explorer: completed in-thread, read-only
- Codex frontend explorer: completed in-thread, read-only
- Gemini: attempted, failed auth/client eligibility; see `gemini.md` and
  `gemini.stderr.log`

## Blocking Findings Folded Into The Plan

- The enforcement flag must be a global bypass while grants are seeded. Partial
  enforcement as soon as a grant row exists would break service keys during
  rollout.
- The first grant model should be API-key scoped. User/group/OIDC mapping should
  be a later migration after the service-key path is proven.
- Idempotency receipts must carry stream/principal context and be checked before
  replay to avoid cross-scope response leakage.
- Backlog update authorization must validate both current item access and target
  state, especially `assignment_group` and `lab_bench`.
- Comments, alerts, audit rows, saved kiosks, and import details must fail
  closed. They cannot rely on UI filters or current global list behavior.
- Mixed-scope import rows must become clear terminal failures or be blocked.
  Hidden ready rows would leave stuck batches.

## Plan Adjustments Made

- Reduced `docs/ENTERPRISE_SCOPE_ACCESS_PRODUCTION_PLAN.md` to 296 lines.
- Replaced broad `principal_type/user/group` grants with a smaller
  API-key-only `AccessGrant` table for the first slice.
- Added receipt scope hardening as mandatory data-model work.
- Added `/audit` and `/kiosks` to Wave 1 enforcement.
- Added explicit flag behavior and rollout verification before cutover.
- Added negative tests for idempotency, target-state backlog updates, kiosk
  panels, audit, comments, alerts, and mixed-scope imports.

## Residual Decisions For Implementation

- Whether Wave 2 import enforcement lands in the same implementation PR or a
  separate follow-up depends on diff size after Wave 1.
- Whether to snapshot `site` and `lab_bench` on historical fact tables should be
  revisited after stream-id enforcement lands.
- Exact 403 versus 404 behavior should be centralized in access helper tests so
  endpoint implementations stay consistent.
