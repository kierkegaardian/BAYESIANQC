# Import Ingestion Readiness Report

## Verdict
Not ready for production/shared-lab use yet.

Ready for continued controlled synthetic pilot testing on the local canonical demo stack after the UI fixes in this branch. Production readiness remains blocked by open workflow and operations gaps listed below.

## Environment
- Branch: `codex/import-readiness-production-test`
- Baseline commit before readiness additions: `608ab9c` (`docs: add import ingestion readiness test plan`)
- DB URL class: local Compose Postgres on `127.0.0.1:54329`
- API/UI: canonical `127.0.0.1:8010` and `127.0.0.1:5177`
- API key: seeded local admin key `local-dev-key`
- Archive root for final live smoke: `/home/user/projects/BAYESIANQC/reviews/import-readiness/20260704T125348-0500/live-archive-root`
- Synthetic fixtures: `samples/import_readiness/`
- Evidence packet: `reviews/import-readiness/20260704T125348-0500/`

## Source Examples Used
The fixture files are synthetic. They were shaped from public export/report patterns, not copied from vendor examples.

- Thermo Chromeleon export docs: reports can be exported for injections, sequences, or multiple sequences using templates and channels.
  <https://docs.thermofisher.com/r/Chromeleon-7.2.10-MUi-Quick-Start-Guide/1561513995v2en-US1561603211>
- Benchling OpenLabs CDS connector docs: converted OpenLabs outputs include injection CSV, peak CSV, and datacube CSV shapes.
  <https://help.benchling.com/hc/en-us/articles/33919939015437-Agilent-OpenLabs-CDS-Configuration-Guide>
- Benchling Chromeleon connector docs: Chromeleon concepts include sequences, injections, channels, and LC ASM converted into injection/peak/datacube CSV files.
  <https://help.benchling.com/hc/en-us/articles/29545115046925-Thermo-Fisher-Scientific-Chromeleon-Configuration-Guide>
- ASTM D86 automated distillation references: results are typically reported as percent recovered versus temperature in a table or graph.
  <https://koehlerinstrument.com/wp-content/uploads/2019/10/105_Distillation-GCC-2019.pdf>
- CARB automated distillation SOP: automated D86-style workflows measure vapor temperature and condensate volume periodically.
  <https://ww2.arb.ca.gov/sites/default/files/classic/testmeth/slb/sop128v2_1.pdf>
- Shimadzu LabSolutions reporting docs: reports can include summary tables, chromatograms, calibration curves, audit trail logs, and peak integration/quantitation result information.
  <https://www.shimadzu.com/an/ivd/O/225-45486.pdf>

## Results
| Phase | Result | Evidence |
| --- | --- | --- |
| 0 Preflight | Pass | `git-status.before.txt`, `git-log.txt`, `postgres-status.txt` |
| 1 Static and contract checks | Pass | `ruff.txt`, `pyright.txt`, `gen-api.txt`, `frontend-check.txt`, `frontend-check-after-ui-fix.txt`, `diff-check.txt`, `generated-schema-diff.txt` |
| 2 Migration and data safety | Pass | `test-migrations.txt` (`9 passed`), `migration-rehearsal.txt` (`20260704_0006`, posterior and sequence checks OK) |
| 3 Backend regression | Pass with expected readiness gaps | `test-import-focused.txt` (`9 passed, 2 xfailed`), `test-all.txt` (`61 passed, 2 xfailed`) |
| 4 Parser matrix | Pass for synthetic CSV, DAT, XML, peak table, bad file, path traversal, and XXE checks | `tests/test_import_readiness.py`, `samples/import_readiness/` |
| 5 Run/backlog association | Partial | Ambiguous backlog remains manual in existing tests; no-run/no-backlog policy is open as `IMP-P1-002` |
| 6 Apply, quarantine, audit, idempotency | Pass with policy caveat | Existing import tests plus readiness CSV duplicate apply check |
| 7 Security/RBAC/scope | Pass with upload-limit gap | RBAC, invalid key, path traversal, XXE, and scoped import tests passed; upload limit is `IMP-P1-001` |
| 8 UI end to end | Pass after fix | `playwright/ui-smoke-after-ui-fix.txt`, screenshots, console/page-error JSON |
| 9 Operational readiness | Not complete | Final archive root was explicit and reconcilable; backup/restore, retention, monitoring, and startup fail-fast policy are not proven |
| 10 Production-like pilot | Not complete | Synthetic online-shaped files only; no sanitized real instrument files or lab SME sign-off |

## Defects
| Severity | ID | Description | Repro | Recommendation |
| --- | --- | --- | --- | --- |
| P1 | IMP-P1-001 | No configured maximum upload size or parse timeout is enforced for import uploads. | `tests/test_import_readiness.py::test_oversized_import_is_rejected_by_configured_limit` is `xfail`. | Add explicit upload-size and parse-time limits, return `413` or a controlled failure, and document customer config. |
| P1 | IMP-P1-002 | A row with no run/backlog context can become `ready_to_apply` when stream defaults resolve. This conflicts with the stricter MVP reading that no-run/no-backlog rows require manual association. | `tests/test_import_readiness.py::test_import_without_run_or_backlog_requires_manual_association` is `xfail`. | Decide policy. If manual association is required, mark these rows `needs_review` unless profile config explicitly allows provisional/import-run creation. |
| P1 | IMP-P1-003 | Production restore readiness is not proven. DB migration rehearsal passed, but a database plus archive-root restore was not executed. | Phase 9 not run against a real backup target. | Add a disposable backup/restore drill that restores DB plus archive files and reconciles import hashes/QC record evidence. |
| P1 | IMP-P1-004 | No sanitized real-instrument pilot files or lab SME expected-row sign-off were available. | Phase 10 used synthetic fixtures only. | Run at least two real sanitized instrument families with hand-reviewed expected rows before production claims. |
| P2 | IMP-P2-001 | If `BAYESIANQC_IMPORT_ARCHIVE_ROOT` is omitted, demo imports default to `data/import-archive` under the repo. This was observed during the first UI smoke and then corrected for final evidence. | `wrong-default-archive/` preserves the files from the mistaken first run. | Make deployment/run scripts require or default to an external archive root; document local-dev-only behavior. |

## Fixed During Run
| Severity | ID | Description | Evidence |
| --- | --- | --- | --- |
| P2 | IMP-FIXED-001 | Imports and Parser Profiles had horizontal overflow at 390px mobile width. | Failed `playwright/ui-smoke-archive-root.txt`; fixed in `frontend/src/components/AppLayout.vue`; passed `playwright/ui-smoke-after-ui-fix.txt`. |
| P3 | IMP-FIXED-002 | Browser console showed a 404 resource error from the missing favicon. | Fixed with `frontend/public/favicon.svg` and link in `frontend/index.html`; final smoke had `severeConsoleCount: 0`. |

## Residual Risk
- Synthetic fixture coverage is broad enough to exercise parser mechanics, but it does not validate any vendor-specific export contract.
- The current import profile model can parse the tested CSV/DAT/TXT/XML shapes, but customer onboarding will still need profile review and expected-row comparison per instrument.
- Access-scope behavior passed automated checks, but enterprise human-user auth, OIDC/SAML, MFA, and user/group administration remain outside this import-readiness run.
- The live canonical dev database now contains synthetic readiness import/profile rows from the UI smoke.

## Production Conditions
Before production/shared-lab deployment:
- Resolve `IMP-P1-001` and `IMP-P1-002`.
- Prove DB plus archive-root backup/restore with hash reconciliation.
- Set and verify a durable, backed-up, non-repo archive root.
- Define retention policy for raw files, failed files, artifacts, and collector logs.
- Define upload size, parse timeout, and future collector file-stability policy.
- Run sanitized real-instrument pilots with lab SME expected-row sign-off.
- Decide whether profiles can ever auto-apply rows without run/backlog context.

## Sign-Off
Agent readiness run completed with synthetic fixtures and local canonical services. No lab SME or operations owner sign-off was performed.
