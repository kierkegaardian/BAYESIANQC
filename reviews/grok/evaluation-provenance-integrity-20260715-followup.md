I'll review the remediation against the prior P1 fixed-baseline and P2 alert-history findings. First I'll load the full prompt and the relevant code changes.Next I'll inspect the prior P1 findings and the fixed-baseline freeze, migration, and alert-reconciliation paths.I have the prior P1s; next I'll verify freeze, migration, replay, and alert-reconciliation code against those findings.## Verdict

**No P0/P1 blockers remain.** Both prior fixed-baseline **P1s** are closed by version-frozen centerline/sample-SD/count plus fail-closed migration/replay. The multi-active and replacement-alert **P2s** are addressed in code/tests without introducing a new migration or replay integrity defect. Omitted prior β from submitted config σ is accepted as product intent (not flagged).

Focused suite: **16 passed** (`test_fixed_baseline_api`, `test_alert_reconciliation_history`, `test_evaluation_migration`, `test_evaluation_kernel` baseline cases, `test_evaluation_provenance_api`).

---

## Findings (severity order)

### No P0

None identified on this remediation slice.

### No P1

Prior blockers are closed (detail below). No new migration/replay P1 found.

### Residual non-blockers

| Sev | Item | Notes |
|---|---|---|
| **P3** | Multi-active confirm does not collapse duplicates | `alert_plan` now processes **all** non-superseded alerts. If two match the new signature, both **confirm** and both stay active. Orphan-forever is fixed; optional cleanup (keep one, supersede extras) is still absent. No dedicated multi-active test. |
| **P3** | Frozen baseline fields not on `StreamConfigOut` | DB freezes `baseline_centerline` / `baseline_sigma` / `baseline_count`, but the config API drops them. Integrity is enforced via evaluation provenance + replay; ops cannot inspect frozen stats on the config resource alone. |
| **P3** | Dead `storage.baseline_stats` still live-recomputes membership | Unused by evaluation/replay (fail-closed frozen path is authoritative). Trap for a future caller only. |

---

## Prior P1 closure check

### P1-1 — Fixed baseline recomputed from live membership

**Closed.**

| Gate | Evidence |
|---|---|
| Freeze at config create | `create_stream_config` → `validate_stream_control_limits` (live window **once**) → stores `baseline_centerline` / `baseline_sigma` / `baseline_count` for `fixed_baseline` |
| Replay uses frozen only | `_limits_by_config` passes frozen fields; **does not** load live baseline rows |
| Fail-closed if incomplete | Partial freeze → error; all-null freeze with empty `baseline_values` → error (no silent recompute) |
| Behavioral tests | Backdate into baseline window + exclude baseline member → post-effective evaluation limits **identical** (`tests/test_fixed_baseline_api.py`) |

### P1-2 — Membership change rewrites limits outside admin preview/apply

**Closed by collapse into freeze.**  
OOO ingest / resolution may still full-reprocess (history/posterior can change), but **limit basis for a config version does not**. That was the integrity requirement.

---

## Migration / replay bug review

| Concern | Result |
|---|---|
| Backfill of legacy `fixed_baseline` | `20260715_0008` freezes from current included membership; incomplete partial freeze aborts; insufficient finite values / non-positive SD aborts |
| Upgrade validation | Migration test asserts centerline=10, sample SD=\(\sqrt{2}\), count=2; head schema includes frozen columns |
| Create vs migration mean | `sum/n` vs `fmean` — equivalent for these values; not a defect |
| Replay divergence | Frozen path preferred whenever any frozen field is present; evaluation snapshots still store applied limits independently |
| Create-time only recomputation | Intentional: only `validate_stream_control_limits` at version create uses live membership |

No migration or replay integrity bug found that would re-open the P1s.

---

## Multi-active alert reconciliation

**Prior P2 fixed in substance.**

- Was: last write wins → older active alert never confirmed/superseded.  
- Now: `active_by_record: dict[int, list[AlertRecord]]`; every active alert planned.

Observed outcomes:

| Case | Behavior |
|---|---|
| Both match | Both `confirm` (no create) |
| Both mismatch | Both `supersede` + one `create` (shared replacement) |
| Mixed | Matching confirmed; mismatch superseded **without** create (confirmed sibling remains) |

Residual P3 only: dual-confirm multi-current and missing unit coverage.

---

## Replacement alert investigation/CAPA/ack/assignment test

**Prior P2 closed.** `tests/test_alert_reconciliation_history.py` covers:

1. Ack + assign original  
2. Investigation + CAPA links  
3. Semantic config change → preview supersede/create → apply  
4. Original stays `acknowledged` / `assigned_to=qc-lead` / `evaluation_status=superseded`  
5. Replacement is `current` via `replacement_alert_id`  
6. `InvestigationAlertLink` / `CapaLink` still point at original row id  

Persistence still does not delete alerts or rewrite ack/assignment; reconciliations are append-only. Implementation matches the test contract.

---

## Explicit product non-finding

Omitted prior β from **submitted config σ** (not baseline sample SD) is **not** a defect per product requirement. Fixed-baseline test still expects β from config σ (`0.5² × (α−1)`).

---

## Blocker conclusion

| Severity | Remaining? |
|---|---|
| **P0** | **No** |
| **P1** | **No** — both fixed-baseline P1s closed without new migration/replay integrity bugs |
| **P2 (targeted)** | Multi-active reconciliation and replacement history retention are addressed; only P3 hygiene remains |

This narrow remediation is **acceptable to treat as closed** for the prior P1 fixed-baseline findings and the reviewed P2 alert-history gaps.
