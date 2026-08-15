I'll review the full change packet as a strict Tier-B reviewer—findings first with severity, evidence, failure scenarios, and minimal fixes. Loading the complete review input and the relevant implementation.Reviewing core evaluation, provenance, replay, migration, and alert paths against the integrity criteria.## Verdict

**Blockers remain: yes — at least one P1.**  
No **P0** found. Automated green gates are necessary but not sufficient for this integrity surface.

Primary blocker: **`fixed_baseline` limits are not frozen on the config version**; every replay recomputes mean/σ from live `include_in_stats` membership in the baseline window. That violates fixed/shared limit integrity for rules, Student-t risk, and subsequent chart provenance after OOO ingest or baseline-point resolution.

---

## Findings (severity order)

### P1 — Fixed baseline is recomputed from live membership (control-limit integrity)

| | |
|---|---|
| **Evidence** | `app/evaluation_replay.py` `_limits_by_config` ~L67–87; `app/math/control_limits.py` L34–43; `app/services/ingestion.py` L247–270 (OOO → full reprocess); `app/main.py` L638–645 (resolution → full reprocess) |
| **Failure scenario** | Stream has `control_limit_source=fixed_baseline` with window W and many post-effective evaluations/alerts. Operator (1) backdates a point into W, or (2) excludes/reinstates a baseline point. Full replay rebuilds centerline/σ from current included values. All current evaluations under that config version get new action/warning bounds; dispositions/alerts can mass-supersede **without** a new config version, admin preview, or explicit re-baseline reason about limits. |
| **Why it is integrity-critical** | Evaluation snapshots store applied limits, but the *basis* for a fixed config version is not immutable. Rules, Bayesian outside-limit risk, and new chart provenance all share that recomputed basis — so “shared limits” hold for a single replay, then silently change on the next. |
| **Minimal fix** | At fixed-baseline **config create**, freeze `applied_centerline`, `applied_sigma`, and `baseline_count` (and optionally a membership fingerprint) on `StreamConfig`. Replay must use frozen values, not re-`stdev` live rows. Optionally reject later inserts into the baseline window / baseline-membership changes unless a new config version is created. |

---

### P1 — No admin/fingerprint gate when baseline membership changes rewrite limits

| | |
|---|---|
| **Evidence** | `app/services/evaluation_pending.py` only gates **config/prior** effective-dating (`historical_reprocess_required`); OOO ingest and resolution call `reprocess_stream_evaluations` directly |
| **Failure scenario** | Same as above: limit basis shifts inside a path that only audits “out-of-order ingestion” / resolution, not “control limits changed.” Preview/apply + reason is bypassed for the highest-impact limit change. |
| **Minimal fix** | If frozen limits (P1 above) are implemented, this collapses. If recomputation is kept, treat baseline-membership deltas like backdated config: block + require admin preview/apply with fingerprint and reason. |

---

### P2 — Supersede + replacement path under-tested for CAPA/investigation retention

| | |
|---|---|
| **Evidence** | `app/services/evaluation_persistence.py` L183–225 (no alert deletes; reconciliation + optional replacement); links in `InvestigationAlertLink` / `CapaLink` use `AlertRecord.id`; only test is supersede-without-replacement ack (`tests/test_evaluation_provenance_api.py` L209–254) |
| **Failure scenario** | Semantic change creates replacement alert; investigations/CAPA remain on superseded row (correct if retained), but UI/workflows that only show non-superseded alerts can look like history disappeared. Untested regression could later hard-delete or re-key alerts. |
| **Minimal fix** | Add API test: ack + assign + investigation + CAPA on alert A → supersede with replacement B → A status/ack/links retained, A `evaluation_status=superseded`, B linked via `replacement_alert_id`. |

---

### P2 — Multiple non-superseded alerts per record: last write wins

| | |
|---|---|
| **Evidence** | `app/services/evaluation_state.py` `alert_plan` L197–205: `active_by_record[qc_record_id] = alert` |
| **Failure scenario** | Legacy or manual duplicates leave two non-superseded alerts on one record; only the latest is confirmed/superseded; older stays `current`/`legacy_unverified` forever. |
| **Minimal fix** | Treat all non-superseded alerts for the record in the plan (or fail reprocess with a conflict requiring cleanup). |

---

### P2 — Prior β derivation uses configured `sigma`, not fixed-baseline σ

| | |
|---|---|
| **Evidence** | `app/main.py` ~L1018–1031 `prior_beta_from_sigma(..., effective_config.sigma)`; fixed baseline test expects β from configured σ (`tests/test_fixed_baseline_api.py` L98) while limits use sample SD |
| **Failure scenario** | Limits σ ≈ 0.28 from baseline; prior scale uses config σ = 0.5. Student-t risk still uses shared **limit bounds**, but predictive scale is inconsistent with the charted process SD — surprising “shared basis” semantics. |
| **Minimal fix** | Document explicitly, or derive omitted β from resolved fixed-baseline σ at prior effective time. |

---

### P2 — `baseline_end == effective_from` can put evaluation-time points into the baseline set

| | |
|---|---|
| **Evidence** | Validation allows `baseline_end <= effective_from` (`app/models.py` L486–492); baseline filter is inclusive on both ends (`evaluation_replay.py` L76) |
| **Failure scenario** | Points at `effective_from` help define the limits that evaluate them (circular for that timestamp cluster). |
| **Minimal fix** | Require `baseline_end < effective_from` (strict), or exclude records with `timestamp >= effective_from` from baseline membership. |

---

### P2 — Stream write lock is a no-op off PostgreSQL

| | |
|---|---|
| **Evidence** | `app/services/locks.py` L29–34 |
| **Failure scenario** | Any non-Postgres session loses fingerprint/stream serialization guarantees (TOCTOU races). Runtime is Postgres-first; residual risk for mistaken SQLite use. |
| **Minimal fix** | Fail closed if dialect ≠ postgresql for write paths, or document hard runtime requirement in lock helper. |

---

### P3 — Full reprocess always appends snapshots for every selected record

| | |
|---|---|
| **Evidence** | `evaluation_persistence.persist_replay` L169–181 updates all `selected`, not only `changed_records` |
| **Failure scenario** | Large streams grow `qcrecordevaluation` rapidly; `current_evaluation_id` churn even when disposition unchanged (confirm path still works). |
| **Minimal fix** | Write new snapshots only for changed records (and always when pointer null); still reconcile alerts against full replay. |

---

### P3 — Alert semantic signature ignores risk magnitude within tier

| | |
|---|---|
| **Evidence** | `evaluation_state._semantic_signature` / `_bayesian_tier` L157–186 |
| **Failure scenario** | Risk 51→99 both “warn” → confirm, no replacement; ops may expect a new alert. |
| **Minimal fix** | Document policy, or include coarse risk buckets in signature. |

---

### P3 — Dead `baseline_stats` and write-only `PosteriorState`

| | |
|---|---|
| **Evidence** | `storage.baseline_stats` unused by evaluation path; `PosteriorState` only written in `_sync_posterior_state` |
| **Failure scenario** | Misleading secondary “truth” for future callers; not current live/replay divergence (evaluation is pure replay). |
| **Minimal fix** | Remove or mark non-authoritative; never reintroduce dual evaluation paths. |

---

## Audit checklist (requested surfaces)

| Surface | Assessment |
|---|---|
| **Replay / live equivalence** | **Pass** for a fixed record/config/prior set: ingest, OOO, resolution, and admin apply all go through `replay_evaluations` → `evaluate_point` (no separate live kernel). **Fails under fixed-baseline membership drift** (P1). |
| **Shared limit basis (rules / Student-t / charts)** | **Pass** within one evaluation: `ResolvedControlLimits` feeds rules, `risk_from_posterior`, and chart provenance. Broken across time if baseline recomputes (P1). |
| **Immutable snapshot / cache / pointer** | **Pass** for written rows: new `QCRecordEvaluation`, pointer + JSON cache set together in one transaction. Legacy null provenance allowed and surfaced. |
| **Alert confirm / supersede / replace + history** | **Mostly pass**: no deletes; reconciliations; replacement optional; ack retained in tested path. CAPA/investigation retention relies on FK to old alert id — **undertested** (P2). |
| **Preview read-only + fingerprint TOCTOU** | **Pass**: preview does not write; apply reloads state under lock and 409s on fingerprint mismatch (`evaluations.py` L103–109; tests cover stale + read-only). |
| **Admin RBAC + audit reason** | **Pass**: admin-only reprocess; nonblank reason on apply; audit `apply_evaluation_reprocess`. QA Manager OVERRIDE denied. |
| **Alembic up/down + legacy null provenance** | **Pass**: `control_limit_source` backfill; nullable pointers; partial baseline aborts upgrade; downgrade drops in safe order; migration tests present. |
| **Same-timestamp + effective-dating** | **Pass**: same-ts batching in replay; config/prior `_active_version`; backdated config/prior blocked until manual apply. |
| **R-4s / 4-1s / threshold modes** | **Pass**: new configs reject R-4s; legacy variant tagged; 4-1s fixed 1σ tested; threshold modes recorded; new configs force paired explicit probs. |
| **No fabricated historical bands** | **Pass**: frontend gaps + warning when `evaluation` null; no stream-config backfill of history. |
| **Standards-claim boundaries** | **Pass**: README / SRS / roadmap language is prototype / Westgard-like / non-claim for ASTM/ISO conformance. |

---

## Missing tests (high value)

1. **Fixed-baseline freeze**: after config create, exclude/backdate a baseline member → limits for post-effective points **unchanged** (or admin gate if recompute is intentional).  
2. **Append-only vs full reprocess** identity for the latest record (and posterior end-state).  
3. **Supersede + replacement** with investigation + CAPA + assignment retained on original.  
4. **Stale fingerprint under concurrent ingest** (second apply 409 after first apply).  
5. **Mixed_legacy threshold mode** disposition behavior on a legacy fixture.  
6. **Chart API**: legacy null provenance → `evaluation: null`, no inferred bands (backend + existing Vitest).  
7. **Migration downgrade** smoke (upgrade head → down one → schema absence).  
8. **Same-timestamp posterior order** vs rules non-observation (rules covered; bayesian risk ordering less explicit).

---

## Explicit blocker conclusion

| Severity | Remaining? |
|---|---|
| **P0** | **None identified** |
| **P1** | **Yes — blockers remain** (unfrozen `fixed_baseline` recomputation; limit rewrites outside admin preview/apply) |

Until fixed-baseline values are version-frozen (or membership changes are admin-gated like backdated config), this packet should **not** be treated as closed for the Evaluation Provenance and Control-Limit Integrity Gate, regardless of green Ruff/Pyright/pytest/Vitest/Docker/migration smoke.
