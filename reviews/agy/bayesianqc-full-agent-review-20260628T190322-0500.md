**Findings Summary**
The BAYESIANQC prototype establishes a strong structural foundation, successfully bridging classical frequentist multirules with continuous Bayesian risk scoring and a full CAPA lifecycle. However, it currently suffers from critical Pydantic validation bugs, flawed RBAC on read operations, and lacks the enterprise-grade concurrency and authentication mechanisms required for a regulated production lab environment.

### 1. Current Implemented Feature Set
- **Data Ingestion**: Support for API and CSV ingestion of QC results (`/qc/records`), as well as non-result event tracking.
- **Hybrid Decision Engine**: Simultaneous evaluation of frequentist Westgard rules (1-3s, 2-2s, R-4s, 4-1s, 10x) and a Bayesian updating model (Normal-Inverse-Gamma) to calculate predictive risk scores (0-100) and warn/hold streaks.
- **Quality Workflows**: Automated generation of Alerts based on risk/signals, accompanied by Investigation routing and a structured CAPA module.
- **Master Data**: CRUD endpoints for Instruments, Methods, Analytes, Stream Configurations (with versioning), and Prior Configurations.
- **Persistence & UI**: SQLite backend with SQLAlchemy/SQLModel capturing detailed audit logs, and a Vue/Element Plus frontend for visualizing Levey-Jennings control charts.

### 2. Bugs, Regressions, Security, and Compliance Gaps
- **[P0] Ingestion Payload Rejection (Bug)**: `QCRecordIn` fields such as `operator_id`, `reagent_lot`, `calibration_status`, `run_id`, and `comments` are typed as `Optional[str]` but lack `= None` defaults. In Pydantic v2, this means the keys are still strictly required in the JSON payload, which explains why the minimal payload test returns a 422. (*`app/models.py` lines 1024-1032*)
- **[P1] RBAC Read Defect (Bug/Security)**: The `GET /streams` endpoint is hardcoded to require `Permission.INGEST_QC`. Because the `AUDITOR` and `DATA_STEWARD` roles do not possess this permission (they have `[]` and `[Permission.EDIT_CONFIG]` respectively), they receive 403 errors. The RBAC model currently lacks a generic "read" permission. (*`app/main.py` lines 4235-4237*; *`app/rbac.py` lines 1643-1649*)
- **[P1] Unresolved Merge Conflicts (Regression)**: Unresolved Git conflict markers (`<<<<<<< ours`, `=======`, `>>>>>>> theirs`) were merged into `reviews/codex/latest.md`, causing CI diff checks to fail. (*`stdin-for-agy.txt` lines 181-183*)
- **[P2] Concurrency Race Condition (Architecture)**: Due to SQLite's lack of row-level locking, concurrent QC ingestions to the same stream will currently result in a "lost-update race" on the `PosteriorState`. (*`docs/ARCHITECTURE.md` lines 805-809*)
- **[P3] Vite Build Optimization**: The `npm run check` pipeline emits a large chunk warning due to missing manual code-splitting configuration in the frontend build.

### 3. What Must Be Done Before Real Lab Use
- **Migrate to PostgreSQL & Implement Locking**: SQLite cannot safely handle concurrent lab workloads. You must migrate to Postgres and implement `SELECT FOR UPDATE` or optimistic concurrency controls (`updated_at` guards) to prevent Bayesian posterior data corruption during simultaneous high-volume updates.
- **Implement Enterprise Authentication (Compliance)**: Replace the static, hardcoded `X-API-Key` system with OIDC/OAuth2 and MFA. This is absolutely mandatory to support Part 11 compliant, non-repudiable electronic signatures for Investigations, CAPAs, and configuration changes.
- **Enforce Transaction Boundaries**: Implement the planned "True Middleware" architecture split. Database `commit()` calls must be strictly elevated to and owned by the Service layer. Currently, scattered commits risk partial state persistence (e.g., saving a QC point but failing to save the alert).
- **Audit Trail & Typesafety Hardening**: Finalize the data contract for `AuditEntryOut` (specifically reconciling whether `after` is nullable or required) and rigorously enforce reason codes for any manual QC corrections/deletions.
