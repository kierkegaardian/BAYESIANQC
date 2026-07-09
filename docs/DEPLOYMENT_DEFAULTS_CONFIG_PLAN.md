# Deployment Defaults Configuration Plan

Date: 2026-07-04
Status: planning artifact only. Do not implement DB changes, startup seeding, or
production data mutation from this plan until a later approved implementation
slice.

## Goal

Build a governed default configuration catalog for new BAYESIANQC deployments so
fresh databases can eventually start with safe, useful onboarding defaults:

- Human user group templates and inactive copyable user templates.
- Service app templates for collectors, instrument gateways, LIMS connectors,
  and notification workers.
- Industry-filterable instrument templates.
- Method/analyte templates for standards-driven QC workflows.
- Native compatibility links between industries, instruments, methods, analytes,
  parser profiles, backlog schedule templates, and datastream setup defaults.

The catalog should accelerate setup without implying that BAYESIANQC has
validated a customer's SOP, instrument installation, control limits, or
regulatory compliance state.

## Current Baseline

Existing implementation surfaces to reuse later:

- `Role` and `Permission` in `app/models.py`.
- `ROLE_PERMISSIONS` in `app/rbac.py`.
- Service-key storage in `ApiKey`.
- Scoped service-key grants in `AccessGrant`.
- Master data tables: `Instrument`, `Method`, `Analyte`, `ControlMaterial`,
  `StreamConfig`, `PriorConfig`, `KioskLayout`, and `KioskPanel`.
- Operational surfaces: QC records, comments, backlog items, alerts,
  quarantine, import batches, parser profiles, and collector transfer events.
- Datastream setup accepts instrument, method, parameter/analyte, control
  material, stream config, prior, and optional kiosk assignment in one reviewed
  payload.
- Demo fixtures already prove generator-first multi-industry catalog data can
  be rendered without hand-maintained toy rows.

## Non-Goals

- No implementation in this slice.
- No real customer users, credentials, API keys, or production secrets.
- No browser-shipped API key for the web frontend.
- No copyrighted standards text, procedure bodies, tables, or figures.
- No claim that catalog defaults are validated ASTM, ISO, AASHTO, GPA, UOP,
  EPA, clinical, pharma, or regulatory reference data.
- No automatic activation of stream limits, priors, or schedules without
  customer review.

## Principles

1. Defaults are templates until copied or applied.
2. Templates must not authenticate or appear as audit actors.
3. Human users authenticate through local accounts or OIDC/SAML in production;
   API keys belong to service apps.
4. Fresh DB seeding must be idempotent, deterministic, and versioned.
5. Standards metadata must cite source/catalog provenance but avoid protected
   content.
6. Applying a template should produce reviewed, auditable customer config.
7. Customer SOP confirmation is required before QC limits, priors, parser
   mappings, or schedule templates become active operational defaults.

## Default Security Catalog

### Human Groups

Seed these as group templates, not active shared users:

- `system_admin`: bootstrap group with all permissions; one bootstrap account
  may be enabled on first install.
- `admin_template`: copyable inactive group/user template with admin role.
- `tech_template`: copyable inactive group/user template mapped to read,
  ingest QC, log runs/events, and comment on QC points/runs/alerts; no config
  edit.
- `supervisor_qa_template`: copyable inactive group/user template mapped to
  read, ingest QC, approve, manage imports, and investigation/CAPA actions as
  supported.
- `data_steward_template`: copyable inactive group/user template mapped to
  read plus configuration edit, without result approval authority.
- `customer_readonly_template`: copyable inactive group/user template mapped to
  read only and requiring scope grants before use.

Each copied human user must get a new identity, invite/session state, audit
actor id, and authentication method. Credentials are never copied from a
template.

### Service Apps

Seed service app templates as inactive/copyable:

- `file_collector_template`: upload files, create import batches, log collector
  transfer events, and read required parser/profile status.
- `instrument_gateway_template`: submit QC records and non-result QC events
  from middleware or instrument interfaces.
- `lims_connector_template`: read charts/status and exchange scoped results or
  work orders with LIMS/LIS.
- `notification_worker_template`: read routing events and send outbound
  notifications or webhooks.
- `report_export_worker_template`: generate/export scoped reports if that
  worker exists later.

When copied, a service app receives generated credentials, explicit scopes, and
an owner/contact. Audit should record `actor_type=service_app` and
`actor_id`. If a service action is user-initiated, also preserve
`on_behalf_of_user_id` when available.

## Default Operational Catalog

### Industry Taxonomy

Start with a small reviewed taxonomy:

- `fuel_petroleum`
- `environmental`
- `clinical`
- `pharma_qc`
- `metals_steel`
- `asphalt_geotech`
- `natural_gas`
- `general_lab`

Each catalog item can carry multiple industries.

### Instrument Templates

Instrument templates should include:

- Stable template id, label, vendor, model family, instrument class, and
  technique.
- Industry tags.
- Typical data outputs and likely parser profile families.
- Compatible method template ids.
- Default site/bench placeholders, never customer-specific installed assets.
- Status: `draft`, `reviewed`, `deprecated`, or `retired`.
- Provenance note and reviewer.

### Method And Analyte Templates

Method templates should include:

- Publisher family: ASTM, ISO, AASHTO, GPA, UOP, EPA, USP, customer internal,
  or other. Keep `UOM` unresolved until clarified; it may mean UOP or unit of
  measure in prior notes.
- Public method identifier and title/short description where allowed.
- Revision/year if known.
- Industry tags and applicable matrices.
- Compatible instrument classes and specific instrument template ids.
- Expected analyte/result templates with units, result role, and QC relevance.
- Suggested chart family, rule set family, and baseline strategy as
  `requires_customer_review`.
- Links to parser profile templates and import row classification hints.
- Provenance URL or citation pointer for public catalog metadata.

Do not store copyrighted method details. Use only public identifiers, allowed
metadata, customer-provided SOP references, and local configuration values.

### Stream Setup Defaults

Applied catalog rows should eventually feed the existing stream setup workflow:

- instrument name/manufacturer/model
- method name/technique
- parameter/analyte name and units
- control material placeholder
- QC level placeholder
- target/sigma placeholders or demo-only values
- rule set placeholder
- Bayesian prior placeholder
- optional saved kiosk assignment
- optional backlog schedule template

Freshly applied rows should default to `draft` or `needs_customer_review` until
an authorized admin/data steward confirms SOP-specific values.

## Discovery Plan

1. Inventory current internal fixtures:
   - demo kiosk generator families
   - sample D86/refinery assets
   - import readiness samples
   - stream setup XLSX fields
   - existing parser profile model
2. Define the canonical catalog schema in a docs-first draft:
   - human group template
   - human user template
   - service app template
   - industry
   - instrument template
   - method template
   - analyte/result template
   - compatibility link
   - parser profile template
   - schedule/backlog template
3. Research public catalog metadata for the first vertical:
   - start with fuel/petroleum because current demos already cover ASTM D86,
     D93, D97, D1500, D4052, D4294, D445, and D5191 style workflows.
   - record only public identifiers and allowed metadata.
   - capture source, retrieval date, and review status.
4. Expand to other verticals only after the first vertical has a clean schema
   and review workflow:
   - environmental EPA
   - asphalt/geotech AASHTO
   - natural gas GPA
   - pharma USP/ICH-adjacent lab QC metadata
   - clinical general method categories
   - metals/steel ASTM/ISO method categories
5. Validate every template against the existing datastream setup shape.
6. Produce a seed preview report before any DB writes:
   - counts by template type
   - inactive vs active objects
   - permission matrix
   - service app scope requirements
   - standards provenance coverage
   - items requiring customer review

## Implementation Plan For Later

### Wave 1: Plan And Schema Only

- Add catalog schema documentation and JSON examples.
- Add tests that validate example JSON against Pydantic models, without DB
  inserts.
- Choose `samples/default_catalog/` or `app/defaults/catalog/` for packaging.

### Wave 2: Typed Catalog Loader

- Add typed Python models for default catalog files.
- Add dry run: `python scripts/preview_default_catalog.py --catalog default`.
- Report every object that would be created, reused, deprecated, or skipped.
- Fail on duplicate ids, dangling compatibility links, missing provenance, or
  active user/service templates with credentials.

### Wave 3: Seed Into Empty DB

- Add an idempotent seed service for empty DBs or missing catalog versions.
- Use catalog version records so repeat seeds say "already applied".
- Keep migrations schema-only; keep catalog data in versioned seed files.
- Default state:
  - bootstrap system admin enabled only when configured.
  - all other user templates inactive/copyable.
  - service app templates inactive/copyable.
  - catalog templates reviewed/draft, not customer-active.

### Wave 4: Apply Templates To Customer Config

- Add UI/API for previewing and applying catalog templates through existing
  datastream setup and parser-profile flows.
- Require reason, reviewer, customer site/bench, and SOP reference before
  creating active stream configs.
- Generate audit entries for applied instrument, method, analyte, stream,
  prior, parser profile, kiosk, and schedule template rows.

### Wave 5: Fresh Build Defaults

- On fresh DB creation, run migrations, then seed the current bundled default
  catalog version.
- Add deployment checks that prove:
  - defaults are present after a clean DB build.
  - re-running seed is no-op.
  - templates cannot authenticate.
  - only bootstrap admin is enabled when requested.
  - all service app templates require explicit credential generation.

## Validation Gates

- `ruff`, `pyright`, and focused unit tests for catalog parser/loader.
- Migration rehearsal against disposable Postgres when schema is added.
- Seed dry-run output checked into a review artifact for the first catalog.
- Security review for auth, user, group, service credential, or scope changes.
- Standards/provenance review so no protected standards content is embedded.
- Frontend typecheck if any UI is added.

## Open Questions

- Confirm whether `UOM` means UOP, unit-of-measure defaults, or another body.
- Decide whether templates live in app tables with a flag or catalog tables.
- Decide whether bootstrap admin is local-account only, OIDC-mapped, or both.
- Decide whether service apps remain API-key based after OIDC lands or move to
  OAuth client credentials.
- Decide who can promote a template from `draft` to `reviewed`.
- Decide whether catalog updates are app-version-bound or independently
  packaged.

## Success Criteria

The later implementation is ready when a new deployment can be built from an
empty Postgres database and immediately show:

- enabled bootstrap admin only when configured;
- inactive copyable human user templates by group;
- inactive copyable service app templates;
- industry-filterable instrument templates;
- standards-aware method/analyte templates with provenance;
- compatibility links from methods to instruments and analytes;
- no usable non-bootstrap credentials;
- clear "requires customer review" status before operational activation.
