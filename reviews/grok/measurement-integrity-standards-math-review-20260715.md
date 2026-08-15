# Measurement Integrity Gate — Statistical & Standards Audit

**Repository:** BAYESIANQC (`codex/measurement-integrity`, uncommitted correctness slice)  
**Reviewer:** Grok 4.5  
**Reviewer role:** statistical QC methodologist / laboratory metrologist / numerical software auditor  
**Mode:** read-only (no code changes)  
**Licensed standard text:** not in packet — clause numbers and proprietary formulas are **not** asserted  
**Inference label:** items marked **[Inference]** are engineering judgments from catalog facts + code, not licensed-standard quotations

**Verification note:** The primary agent removed transient wrapper narration and corrected two factual errors in the generated review: an in-control two-sided 3σ rule has a small nonzero false-alarm probability, not a zero long-run expectation; and `ChartView.vue` already renders predictive and credible intervals as chart overlays, so the contrary P3 finding was removed. The standards verdict and P0–P2 findings were not changed.

---

## 1. Executive verdict and claim boundary

### Verdict

**Approve as a strengthened mathematical prototype slice, with hard claim boundaries.**

The Measurement Integrity Gate correctly hardens the **Normal–Inverse–Gamma (NIG) posterior predictive risk layer** and **Student-t tail arithmetic**, and tightens finite/threshold validation around stream/prior configuration. Acceptance evidence (Ruff, Pyright, 143 backend tests, Vitest, frontend build, migration/API/browser smokes) supports **software quality of this slice**, not standards compliance.

The product remains a **hybrid single-stream laboratory QC prototype**:

| Layer | What it is | What it is not |
| --- | --- | --- |
| Frequentist | Westgard-**like** multirules on individual results with fixed or baseline mean/SD | Certified ISO 7870-2 Shewhart family; I-MR; Western Electric complete rule set |
| Bayesian | Supplemental NIG posterior predictive exceedance risk + streak policy | Standards-mandated control chart; replacement for D6299 / 7870 workflows |
| Display | Individual-value chart with configured ±k·σ bands (Levey–Jennings **style**) | Defensible I chart with MR-based σ; MR chart; EWMA; Q-chart; ILCP module |

### Explicit claim boundary

**Safe product claim (this code base):**  
“Evaluates single-level QC result streams with configurable Westgard-like rules and a Bayesian Normal–Inverse–Gamma predictive risk score against configured warning/action limits.”

**Unsafe claims (do not make):**  
“ISO 7870-2 compliant Shewhart chart,” “I-MR chart,” “ASTM D6299 Q-chart,” “ISO 7870-6 EWMA,” “ISO 7870-8 short-run Q charts,” “ILCP / D6299 site-precision workflow,” “ISO/IEC 17025 validated measurement control,” or “standards-compliant control charting suite.”

**Catalog facts used (primary URLs only):**

- ASTM D6299-26 — statistical QA/control charting for analytical measurement systems: https://store.astm.org/d6299-26.html  
- ISO 7870-2:2023 Shewhart: https://www.iso.org/standard/78859.html  
- ISO 7870-6:2024 EWMA: https://www.iso.org/standard/83852.html  
- ISO 7870-8:2017 short runs / sample-size-one: https://www.iso.org/standard/67410.html  
- ISO 7870-9:2020 stationary processes: https://www.iso.org/standard/69641.html  
- ISO 7870-4:2021 CUSUM: https://www.iso.org/standard/74101.html  
- ISO/IEC 17025:2017: https://www.iso.org/standard/66912.html  
- ASTM training (ILCP, R′, ARV, control charts as D6299 concerns): https://store.astm.org/astm-tpt-141.html  

**D6299 “Q chart” note:** Catalog text does **not** define the exact D6299 Q-statistic. Do **not** conflate D6299 Q charts with **Q–Q plots**, nor with generic short-run standardized charts from ISO 7870-8 without licensed verification. **Exact D6299 Q definition cannot be verified from supplied official catalog facts.**

Roadmap features (EWMA, CUSUM, full Shewhart/I-MR, PT/ILCP, robust baselines) in `docs/STANDARDS_FEATURE_ROADMAP.md` and SRS **REQ-FREQ-*** remain **roadmap/requirements**, not implemented behavior.

**Slice caveat:** “Existing evaluations are not reprocessed” — historical stored signals/risk/dispositions are **not** automatically rewritten by this correctness work until an explicit reprocess path runs.

---

## 2. Audited equations and numerical findings

### 2.1 NIG parameterization (implemented)

Prior/state: \((\mu,\kappa,\alpha,\beta)\) with sequential conjugate update for one observation \(y\) (`app/bayesian.py::_update_posterior`):

\[
\begin{aligned}
\kappa_n &= \kappa_0 + 1 \\
\mu_n &= \frac{\kappa_0\mu_0 + y}{\kappa_n} \\
\alpha_n &= \alpha_0 + \tfrac12 \\
\beta_n &= \beta_0 + \frac{\kappa_0}{2\kappa_n}(y-\mu_0)^2
\end{aligned}
\]

**Finding:** Matches the standard single-observation NIG update (Murphy / conjugate Normal–Inverse-Gamma textbooks). **[Inference]** No algebraic defect found in the recurrence itself.

### 2.2 Omitted-β derivation

`app/math/prior.py::prior_beta_from_sigma`:

\[
\beta_0 = (\alpha_0 - 1)\,\sigma^2 \quad (\alpha_0 > 1,\;\sigma > 0)
\]

Under the common Inv-Gamma-on-variance convention with \(E[\sigma^2]=\beta/(\alpha-1)\) for \(\alpha>1\), this sets **prior mean variance** to the configured \(\sigma^2\).

**Finding:** Correct for **mean-variance matching**. It is **not** the same as matching a mode, a high-density interval, or a process-capability SD estimator. Docs/UI should say “prior mean variance = σ²,” not “prior SD is locked to σ.”

API wiring: omitted `beta0` resolved from effective stream `sigma` in `app/main.py::create_prior` and stream setup (`app/services/stream_setups.py`). Explicit `beta0` preserved. Tests cover this (`tests/test_measurement_integrity_api.py`, `tests/test_statistical_math.py`).

Seed prior (`app/storage.py`): \(\alpha_0=2\), \(\beta_0=0.25^2\) with \(\sigma=0.25\) equals \((\alpha_0-1)\sigma^2\). Consistent for that special case.

### 2.3 Posterior summaries and predictive Student-t

From `_risk_from_posterior`:

| Quantity | Formula | Assessment |
| --- | --- | --- |
| Posterior mean | \(\mu_n\) | Correct location for µ |
| Posterior SD of σ (mean scale) | \(\sqrt{\beta_n/(\alpha_n-1)}\) if \(\alpha_n>1\) | Mean of Inv-Gamma variance → SD; not a full posterior for σ |
| µ scale (cred. interval) | \(\sqrt{\beta_n/(\alpha_n\kappa_n)}\) | Correct Student-t scale for µ under NIG |
| Predictive scale | \(\sqrt{\beta_n(\kappa_n+1)/(\alpha_n\kappa_n)}\) | Correct posterior predictive scale for next observation |
| df | \(2\alpha_n\) | Correct for this parameterization |
| Intervals | \(\mu_n \pm t_{1-\alpha/2,df}\cdot\text{scale}\) at 95% | Symmetric equal-tail Student-t; fine for unimodal t |

**Timing semantics (important):** Risk is computed **after** absorbing the current \(y\) into the posterior, then evaluating \(P(Y_{\text{next}} \notin [L,U] \mid \text{data through } y)\). That is a valid **one-step-ahead predictive** risk for the *next* point, **not**:

- the pre-update surprise of the current point, nor  
- a Shewhart “point outside limits” indicator for the current observation.

README language and `frontend/src/pages/chartRisk.ts` tooltip/help text correctly say “the next included QC result.” Compact labels such as “Risk” and “Bayesian risk” in ingestion and point-detail views can still be read as current-point risk when that explanatory text is not visible; exports and CAPA evidence should preserve the next-result meaning. **[Inference]**

### 2.4 Outside-limit risk and Student-t CDF/PPF

`app/math/student_t.py::student_t_probability_outside_bounds`:

\[
P(Y < L) + P(Y > U) = F_t\!\left(\frac{L-\mu}{s}\right) + F_t\!\left(-\frac{U-\mu}{s}\right)
\]

with clamping to \([0,1]\). Avoids \(1-(F(U)-F(L))\), which is better in extreme tails.

**Numerical checks (this environment):**

- Nested warn (±2) vs action (±3) → \(P_{\text{warn}} \ge P_{\text{action}}\) across sampled means/scales/df (0 violations in a grid).  
- Independent R `pt`/`qt` references in tests (`REFERENCE_VALUES`) + round-trips + no df=30 discontinuity: **appropriate regression design**.  
- Example: prior \(\mu=10,\kappa=1,\alpha=5,\beta=1\) (mean var 0.25), action ±3·0.5 around 10 → \(P_{\text{out}}\approx 0.039\) (risk score 4). After outlier \(y=13\), predictive mass outside action jumps (~0.50) as expected from mean shift + variance inflation.

**Limit construction for risk** always uses:

\[
\text{target} \pm k\cdot\sigma_{\text{config}}
\]

from `StreamConfig` (`target_value`, `sigma`, `warning_limit_sd`, `action_limit_sd`) — **not** baseline recomputed mean/SD, **not** posterior predictive center as chart centerline.

### 2.5 Finite validation and threshold ordering

| Control | Status |
| --- | --- |
| `FiniteFloat` on QC results, targets, σ, limits, bayes probs | Good |
| `sigma > 0`, limit SDs > 0, `action_limit_sd ≥ warning_limit_sd` | Good |
| `risk_threshold_hold ≥ risk_threshold_warn` (0–100) | Good |
| `alpha0 > 1`, `kappa0 > 0`, `beta0 > 0` | Good |
| Student-t finite / df>0 / p∈(0,1) | Good |
| **`bayes_hold_prob_threshold ≥ bayes_warn_prob_threshold`** when both set | **Not enforced** (`app/models.py::validate_limits_and_thresholds`) |
| Policy fallback: warn uses \(P_{\text{action}}\) when `bayes_warn_prob_threshold is None` | Intentional back-compat; **semantically confuses warn vs action** (`_update_policy_streaks`) |

### 2.6 Sequential update, timestamps, config/prior boundaries

Strengths:

- Prior/config effective dates advanced in timestamp order in `infer_risk_as_of`, `rebuild_posterior_state`, `reprocess_stream_evaluations`.  
- Prior change **resets** NIG parameters and streaks; config change **resets streaks only** (does not reseed NIG — correct if prior unchanged).  
- Out-of-order ingest triggers full reprocess (`app/services/ingestion.py`).  
- Same-timestamp handling for frequentist “recent” window in reprocess (pending batch) is more careful than live `get_recent_records` alone.

Limitations:

- Live path (`infer_risk`) vs batch reprocess are **two implementations** of the same intent; drift risk remains.  
- Autocorrelation, nonstationarity, irregular sampling, and seasonal effects are **not modeled** (i.i.d. Gaussian NIG).  
- Outliers fully enter the conjugate update unless `include_in_stats=False`; no robust/t-outlier mixture.  
- No model-health fallback when posterior degenerates (roadmap REQ-BAYES-31).

### 2.7 Does this support a standards-compliant control chart?

**No.** Correct NIG predictive risk supports only a **supplemental predictive-risk layer** beside rule/chart decisions. It does not:

- estimate σ via moving range / subgroup range,  
- maintain Phase I vs Phase II,  
- produce ARL-designed EWMA/CUSUM,  
- implement D6299 Q or ILCP evidence separation,  
- certify Gaussian adequacy or stability.

---

## 3. Standards-suitability matrix

| Standard / method | Current support | Evidence | Gap | Licensed-copy verification needed |
| --- | --- | --- | --- | --- |
| **ASTM D6299-26** (ongoing stability, precision, bias; continuous results; Gaussian adequacy) | **Partial prototype only** | Individual stream QC + mean/SD-style limits; roadmap W4 | No precision/bias packages, no ARV workflow, no R′, no Q-chart, no formal stability phase logic | **Yes** — practice body text for Q-charts, precision estimators, ILCP linkage |
| **ISO 7870-2:2023 Shewhart** | **Not supported as certified Shewhart** | LJ-style bands + multirules; SRS REQ-FREQ-01 language is aspirational | No chart-family model, no MR/R/S, no Phase I/II, no ARL documentation | **Yes** — limit construction, rules, constants |
| **I / I-MR (individuals & moving range)** | **Not I-MR** | Chart uses fixed `target`/`sigma` (`ChartView.vue`); no MR series | Missing \(\overline{\mathrm{MR}}/d_2\) σ, MR chart, MR rules, initialization | **Yes** — constants \(d_2,D_3,D_4\) and practice |
| **Westgard-like multirules** | **Implemented (single-level sequential)** | `app/frequentist.py`, `DEFAULT_RULE_SET` | Multi-level-within-run, configurable windows/severity incomplete | Lab SOP / Westgard literature; not ISO text alone |
| **ISO 7870-6:2024 EWMA** | **None (roadmap)** | Roadmap F1.2 / W3 | No λ, warm-up, limits, ARL | **Yes** |
| **ISO 7870-8:2017 short-run / n=1** | **None** | Catalog only | No standardized short-run statistics | **Yes** — distinguish from D6299 Q |
| **ISO 7870-9:2020 stationary-process charts** | **None** | i.i.d. assumption only | No stationarity diagnostics / dependent-process charts | **Yes** |
| **ISO 7870-4:2021 CUSUM** | **None (roadmap)** | Roadmap only | No CUSUM parameters/reset | **Yes** |
| **ILCP / PT (interlaboratory crosscheck)** | **None as evidence module** | Roadmap F2.7 / W5; training URL only | No ARV, peer precision, z-score policy, separation from posterior updates | **Yes** (D6299 + lab PT scheme docs) |
| **ISO/IEC 17025:2017** | **Partial platform scaffolding only** | Auth, audit, CAPA shells, quarantine | Competence system ≠ validated chart method; no full measurement-traceability package for control limits | **Yes** for how SQC evidence is expected in assessment |
| **Bayesian predictive risk (product-specific)** | **Implemented & math-hardened** | `bayesian.py`, `student_t.py`, tests | Supplemental only; not a standard control chart | N/A (not a substitute standard) |

---

## 4. Detailed method assessments

### 4.1 Shewhart / I-MR / display honesty

**Is it honest to call the current display a Shewhart individual chart or I-MR chart?**

| Claim | Honest? | Why |
| --- | --- | --- |
| “Levey–Jennings-style chart of individuals with configured mean and ±kσ bands” | **Yes** | `ChartView.vue` centers on `stream.target_value`, bands from `stream.sigma` and warn/action SD multipliers |
| “Shewhart individuals (I) chart per ISO 7870-2” | **No** | No standards-aligned σ estimation, Phase I/II, or full Shewhart rule family with documented ARL |
| “I-MR chart” | **No** | **No moving-range calculation, no MR chart, no MR control limits, no \(\overline{MR}/d_2\)** |

**Missing for defensible I / I-MR (engineering checklist; verify against licensed ISO 7870-2):**

1. **Initialization / Phase I:** stable baseline selection, outlier screening, frozen limits.  
2. **σ provenance:** MR-based (or explicit lab-chosen) estimator with constants and sample size; audit which formula applied.  
3. **MR chart:** consecutive \(|x_t-x_{t-1}|\), UCL/LCL, rule handling.  
4. **Resets:** lot change, calibration, CAPA, prior/config effective dates mapped to chart restarts.  
5. **Missing / irregular observations:** time-aware or sequence-aware policy (MR definition under gaps).  
6. **One- vs two-sided limits:** product is two-sided only.  
7. **ARL / false-alarm:** design and document multirule combined Type I error; current stack has none.  
8. **UI:** show centerline source, σ source, baseline version on every point (SRS REQ-UI-02 gap).

### 4.2 Frequentist rules (precise audit)

Implementation: `app/frequentist.py::evaluate_rules_for_values` with \(z=(x-\text{target})/\sigma\).

| Rule | Implemented condition | Severity | Lab-usage notes |
| --- | --- | --- | --- |
| **1-3s** | \(|z| \ge\) `action_limit_sd` (default 3) | ACTION | Sensible single-level “beyond action” |
| **2-2s** | Current and previous both \(\ge\) warn or both \(\le\) −warn | WARN | Sequential same-side 2s — common single-level interpretation |
| **R-4s** | Consecutive points on **opposite** sides of warn limit | ACTION | **Not** general \(|z_t-z_{t-1}|\ge 4\); evidence string says “4 SD range” but logic is opposite-side 2s crosses. Classic multi-level **within-run** R-4s is **not** implemented |
| **4-1s** | Last 4 all \(z\ge 1\) or all \(z\le -1\) | WARN | Hard-coded **1 SD**, not tied to `warning_limit_sd` |
| **10x** | Last 10 all \(z>0\) or all \(z<0\) | WARN | Strict inequality; mean-exact points break runs |

**Single-level vs multi-level:** streams are one `qc_level`. There is **no** Westgard multi-rule across L1/L2/L3 within a run, no N2 “one of two” across levels, no within-run pairing. **[Inference]** Likely mismatch for clinical multi-level QC and for many ASTM multi-level check schemes.

**Baseline duality (P1):**  
`baseline_stats` / `_baseline_target_sigma` can replace **(target, σ)** for rules with sample mean/SD from a date window, while:

- chart bands use config target/σ,  
- Bayesian limits use config target/σ.

A lab that “baselines” can see **rules fire on one scale while the plot and risk use another**.

### 4.3 D6299 Q-chart

**Not implemented.**  
**Exact D6299 Q definition cannot be verified from catalog facts.**  
**[Inference]** In petroleum/lab D6299 practice, “Q chart” usually means a **standardized short-run control statistic**, not a Q–Q plot and not automatically identical to ISO 7870-8 sample-size-one charts.

**Defensible Q-chart workflow would need (pending licensed text):** formal Q transform, target/precision schedules when they vary, initialization, resets, missing data policy, one/two-sided limits, and validation fixtures — plus clear UI naming that is **not** “Q-Q plot.”

### 4.4 ILCP (interlaboratory crosscheck program)

**Not implemented as a separate evidence class.**  
Roadmap correctly states PT/ILCP must not casually update routine posteriors.

**Defensible ILCP needs:**

- Round metadata, provider, sample IDs, **accepted reference value (ARV)** + uncertainty provenance  
- Peer/site precision (e.g. training material’s R′) and qualification rules  
- Performance metrics under **lab SOP** (z-score, En, etc.) — formulas not inventable here  
- Links to alerts/investigations/CAPA  
- **Hard separation** from `include_in_stats` posterior updates unless policy-approved  
- Audit trail independent of routine QC chart reprocessing  

### 4.5 EWMA (ISO 7870-6:2024)

**Not implemented** (roadmap only).  
Required for defensible EWMA: λ, target, variance source, warm-up, time-varying limits, reset after OOC/special cause, missing data, one/two-sided, ARL tables/simulation under lab sampling rates, disposition integration distinct from Shewhart rules.

CUSUM (7870-4) same status: roadmap, not code.

### 4.6 Bayesian layer suitability

**Suitable as:** supplemental predictive-risk and persistence policy (`warn_streak` / `hold_streak`) feeding hybrid disposition (`determine_disposition` / `reprocess_stream_evaluations`).

**Not suitable as:** sole release criterion replacing mandated control charts; estimator of process σ for Shewhart limits; ILCP scorer; nonstationary/autocorrelated process model without further work.

Disposition hybrid (implemented): ACTION frequentist → REJECT; else Bayesian hold streak → HOLD; else any signal or Bayesian warn streak → MONITOR; else ACCEPT. Bayesian cannot alone REJECT without frequentist ACTION (except HOLD_FOR_REVIEW path). That is a **product policy**, not a standards mandate.

---

## 5. Ranked findings (P0–P3)

**Defect classes:** **C** = correctness / semantic defect in implemented behavior; **M** = missing feature (not a bug in existing math).

### P0 — none for pure NIG/Student-t algebra of this slice

No P0 algebraic failure found in update equations, predictive df/scale, or two-tail Student-t construction under the stated NIG model. Finite validation is substantially improved.

### P1 — correctness / claim / lab-safety semantics

| ID | Type | Location | Finding | Consequence |
| --- | --- | --- | --- | --- |
| **P1-1** | **C** | `app/storage.py::baseline_stats`, `app/evaluations.py::_baseline_target_sigma`, `app/bayesian.py::_risk_from_posterior`, `frontend/src/pages/ChartView.vue::buildControlSeries` | **Three-way centerline/σ provenance:** rules may use baseline mean/SD; chart and Bayesian limits use config target/σ | Analysts can accept/reject on a different scale than the chart/risk they show auditors |
| **P1-2** | **C** | `app/frequentist.py` R-4s + evidence string | R-4s is opposite-side warn crosses, not general 4σ range; multi-level within-run R-4s absent | False confidence in “Westgard R-4s” coverage; misses or mislabels lab-expected events |
| **P1-3** | **C**/claim | `_risk_from_posterior`; compact labels in `Ingestion.vue` / `ChartRiskBadge.vue`; accurate helper copy in `chartRisk.ts` | Risk is **post-update next-step** predictive mass; the detailed help is accurate, but compact labels can still be read as “this point’s risk” | Residual ambiguity in screenshots/exports/CAPA evidence when helper text is absent; not an algebra defect |
| **P1-4** | **M**/claim | Product language / SRS REQ-FREQ-01 | Calling the system Shewhart/I-MR/D6299-compliant without method modules | Regulatory/commercial overclaim risk |
| **P1-5** | **C** | Acceptance note: evaluations not reprocessed | Stored historical evaluations may predate Student-t / finite / β-derivation fixes | Audit packets can mix math generations until forced reprocess |

### P2 — material gaps and design debts

| ID | Type | Location | Finding | Consequence |
| --- | --- | --- | --- | --- |
| **P2-1** | **M** | Entire codebase | No I-MR, EWMA, CUSUM, Q-chart, ILCP modules | Cannot sell as standards chart suite |
| **P2-2** | **C** | `app/models.py` validators | No ordering between `bayes_warn_prob_threshold` and `bayes_hold_prob_threshold` | Configurable nonsensical policies (hold easier than warn) |
| **P2-3** | **C** | `_update_policy_streaks` fallback | Warn streak can key off **\(P_{\text{action}}\)** when bayes warn threshold unset | Over/under-warning depending on score thresholds |
| **P2-4** | **C** | Dual update paths: `infer_risk` vs `reprocess_stream_evaluations` | Parallel logic for Bayesian/frequentist evaluation | Future drift; harder validation |
| **P2-5** | **M** | `app/frequentist.py` | Multi-level multirules not supported | Clinical/multi-level lab SOPs incomplete |
| **P2-6** | **M** | Bayesian model | No autocorrelation/nonstationarity diagnostics; no robust outlier model | Silent miscalibration under real lab dependence |
| **P2-7** | **M** | Diagnostics | No PPC / model-health / frequentist fallback (roadmap) | Degenerate posteriors can still score |
| **P2-8** | **C** | `4-1s` hardcoded 1 SD | Inconsistent with configurable warn/action SD philosophy | Surprising behavior if labs set nonstandard 1s |

### P3 — polish / validation debt

| ID | Type | Location | Finding |
| --- | --- | --- | --- |
| **P3-1** | **M** | Tests | Strong Student-t constants; weak **end-to-end NIG sequential goldens** and ARL studies |
| **P3-2** | **M** | Docs | SRS claims ahead of implementation (Shewhart/EWMA/CUSUM) without “not implemented” banners on UI |
| **P3-3** | **C** minor | Seed prior comment style | \(\beta_0=\sigma^2\) without \((\alpha-1)\) is coincidentally correct only for \(\alpha=2\); derivation helper is the durable rule |

---

## 6. Test and validation recommendations

### 6.1 Independent constants

| Constant / function | Source | Use |
| --- | --- | --- |
| Student-t CDF/PPF | R `pt`/`qt`, scipy, or Boost — already partially done | Keep multi-library golden vectors |
| NIG sequential states | Hand-derived + second independent implementation | Small integer sequences |
| \(d_2,D_3,D_4\) (when I-MR added) | Licensed ISO / ASTM tables only | Never invent |
| EWMA limit factors / ARL | Licensed ISO 7870-6 + simulation | After EWMA slice |

### 6.2 Reference datasets

1. **In-control Gaussian** stream: known σ, fixed target — verify a stand-alone two-sided 1-3s false-alarm probability near \(2\Phi(-3) \approx 0.0027\) per independent observation (ARL near 370), then measure the combined multirule rate separately.  
2. **Known shift** (+1σ, +2σ sustained): rule detection order 10x / 4-1s / 2-2s / 1-3s.  
3. **Opposite-side pair** at ±2.1σ: assert R-4s policy matches **documented** definition (fix definition first).  
4. **Baseline window** vs config σ deliberately different: assert **documented** which source rules/chart/Bayes use (today: assert failure until unified).  
5. **Prior omit-β** matrix over \(\alpha_0,\sigma\).  
6. **Out-of-order + exclude-from-stats** reconstruction equality of posterior state.  
7. **ILCP (future):** ARV/peer fixtures never touch NIG unless flag set.

### 6.3 Simulation / ARL / OC

- Combined multirule **in-control ARL** under independence (current product default assumption).  
- Sensitivity of Bayesian hold/warn ARL under prior strength \((\kappa_0,\alpha_0)\).  
- Contaminated outliers: effect on posterior risk vs robust alternatives (future).  
- Do **not** claim ISO ARL tables until method matches standard definition.

### 6.4 Traceability matrix (starter)

| Requirement / claim | Code | Test | Status |
| --- | --- | --- | --- |
| NIG update | `bayesian._update_posterior` | Need golden sequence tests | Math OK; tests thin |
| Predictive Student-t tails | `student_t.*`, `_risk_from_posterior` | `test_statistical_math.py` | Strong |
| Omit-β | `prior_beta_from_sigma`, main/setup | API + unit tests | Strong |
| Finite config | `StreamConfigBase`, `PriorConfigIn` | unit + API 422 | Strong |
| Westgard-like rules | `frequentist.evaluate_rules_for_values` | partial via ingestion/kiosk | Need definition tests |
| Baseline vs config σ | storage + evaluations + ChartView | **Missing** | P1 |
| I-MR / EWMA / Q / ILCP | — | — | Not implemented |
| 17025 evidence pack | audit/CAPA shells | process tests | Not SQC-method validation |

---

## 7. Smallest coherent next implementation slice

**Do not start with EWMA/Q/ILCP.** First close the **σ/centerline provenance + claim honesty** loop so the hybrid product is auditable.

### Recommended slice: “Control-limit provenance & reprocess honesty”

1. **Data model fields (versioned):** `centerline_source`, `sigma_source` ∈ {config, baseline_window, …}; store applied target/σ **on each evaluation**.  
2. **Single evaluation kernel** used by live ingest and reprocess (eliminate dual path drift for rules+risk inputs).  
3. **Chart consumes evaluated target/σ per point** (or active baseline), not only raw stream config.  
4. **Bayesian limits option:** same provenance as frequentist, or explicit “fixed release limits” mode documented.  
5. **UI copy:** “Levey–Jennings-style individual results + Westgard-like rules + Bayesian predictive risk (supplemental).” Ban “I-MR / ISO Shewhart compliant” strings.  
6. **Admin action:** bulk reprocess after math/config changes; record math-version stamp on evaluations.  
7. **Validators:** order `bayes_hold_prob_threshold ≥ bayes_warn_prob_threshold` when both set; document fallback warn uses \(P_{\text{action}}\).  
8. **Tests:** baseline-vs-config disagreement fixture; reprocess idempotency; NIG golden chain.

**Out of scope for that slice:** EWMA, CUSUM, D6299 Q, ILCP, full I-MR (follow-on after provenance).

---

## 8. Safe versus unsafe product / UI claims

### Safe

- “Prototype laboratory QC platform for single-stream individual results.”  
- “Westgard-**like** multirules (1-3s, 2-2s, R-4s, 4-1s, 10x) on sequential single-level data; R-4s means consecutive opposite warning-limit crossings as coded.”  
- “Normal–Inverse–Gamma Bayesian update with Student-t posterior predictive probability outside **configured** warning/action limits; risk score 0–100 from action exceedance probability.”  
- “Supplemental hybrid disposition: frequentist ACTION rejects; Bayesian streaks can hold/monitor.”  
- “Supports future standards-oriented workflows; not a certification against ASTM/ISO chart standards.”  
- “Demo/kiosk data are synthetic unless labeled otherwise.”

### Unsafe

- “ISO 7870-2 Shewhart compliant,” “validated I-MR,” “moving-range control.”  
- “ASTM D6299 compliant,” “D6299 Q-chart,” “site precision R′ / ARV / ILCP module.”  
- “ISO 7870-6 EWMA,” “ISO 7870-8 short-run charts,” “ISO 7870-9 stationary-process charts,” “ISO 7870-4 CUSUM.”  
- “ISO/IEC 17025 validated QC method” (platform features ≠ method validation).  
- “Bayesian control chart replaces multirules / standards charts.”  
- “False-alarm rate / ARL designed to standard tables” (no such study in product).  
- “Q-Q plot” as synonym for D6299 Q-chart (category error).

---

## Separation: correctness defects vs missing features

| Correctness / semantic defects (fix or document now) | Missing features (roadmap; not math bugs) |
| --- | --- |
| Dual centerline/σ between rules vs chart vs Bayes | I-MR, EWMA, CUSUM, Q-chart, ILCP |
| R-4s name/evidence vs multi-level lab expectation | Full Shewhart family, attribute charts |
| Keep post-update next-result risk explicit in compact labels and exported evidence | Robust baselines, model diagnostics |
| Unordered bayes warn/hold thresholds; warn fallback on \(P_{\text{action}}\) | Autocorrelation / nonstationarity models |
| Historical evaluations not re-stamped after math changes | 17025 full quality-system depth |

---

## Bottom line

The Measurement Integrity Gate **successfully hardens the Bayesian predictive-risk mathematics** (NIG update, mean-preserving \(\beta_0\), Student-t tails/intervals, finite guards) and is **fit as a supplemental risk layer** beside Westgard-like individual rules.

It is **not** yet a standards-defensible Shewhart/I-MR, D6299 Q, EWMA, or ILCP system. The highest-value integrity work is **unifying and auditing limit/σ provenance**, **reprocessing historical evaluations**, and **disciplining product claims** — not replacing mandated frequentist workflows with Bayesian scores.

**Licensed copies of D6299-26 and the ISO 7870 / 17025 texts remain required** before any clause-level compliance mapping or proprietary formula implementation.
