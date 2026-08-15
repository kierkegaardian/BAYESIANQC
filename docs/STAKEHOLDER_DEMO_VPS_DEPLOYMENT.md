# Stakeholder Demo Docker-Host Deployment

This runbook deploys BAYESIANQC as a synthetic-data stakeholder demo at
`qc.geoffsmiscellany.com`. The existing geoffsmiscellany Webhosting Hub account is
shared cPanel/static hosting, so it remains a domain/front-door asset only. The
FastAPI app, Postgres database, frontend, Caddy proxy, and import archive run on
a Docker-capable Linux host: a VPS if one is available, or an existing owned host
that can receive public HTTP/HTTPS traffic through DNS, port forwarding, or a
tunnel/static-pointer setup.

## Model

- Public URL: `https://qc.geoffsmiscellany.com`
- Browser login: HTTP Basic Auth with username `admin`
- Password: generated during bootstrap or rotation and printed once
- App auth: Caddy injects a hidden admin `X-API-Key` only for `/api/*`
- Data: deterministic synthetic demo reset; stakeholder edits are disposable
- Runtime root: `/srv/bayesianqc`
- Release source: committed Git `HEAD` only

No plaintext stakeholder password is stored in the repo or remote env files.
Caddy stores only the password hash. The hidden edge admin API key is stored in
`/srv/bayesianqc/secrets/app.env` with owner-only permissions.

## Host Prerequisites

- Ubuntu LTS or equivalent Linux host with outbound internet access.
- SSH key access for the deploy operator.
- The operator has connected once with `ssh <ssh-host>` and accepted the host key.
- Docker Engine and Docker Compose plugin installed.
- Firewall allows only SSH, HTTP, and HTTPS from the internet.
- DNS or tunnel routing sends `qc.geoffsmiscellany.com` to this host.
- Deploy operator can write `/srv/bayesianqc`.
- The BAYESIANQC worktree is clean and committed before bootstrap/deploy.

Use `DEMO_VPS_SKIP_PUBLIC_SMOKE=1` only for a private rehearsal before DNS or the
tunnel/static pointer is live. The real Josh walkthrough should leave public
smoke enabled.

## Commands

Bootstrap the first release, load synthetic demo data, and print the one-time
stakeholder password:

```bash
make demo-vps-bootstrap DEMO_VPS_HOST=<ssh-host>
```

Deploy committed code changes without resetting stakeholder edits:

```bash
make demo-vps-deploy DEMO_VPS_HOST=<ssh-host>
```

Reset remote demo data from deterministic synthetic fixtures:

```bash
make demo-vps-reset-data DEMO_VPS_HOST=<ssh-host>
```

Rotate the stakeholder password and reload Caddy:

```bash
make demo-vps-rotate-password DEMO_VPS_HOST=<ssh-host>
```

Run remote smoke checks:

```bash
make demo-vps-smoke DEMO_VPS_HOST=<ssh-host>
```

Roll back code to a previous release id:

```bash
make demo-vps-rollback DEMO_VPS_HOST=<ssh-host> DEMO_VPS_RELEASE_ID=<release-id>
```

Optional variables:

```bash
DEMO_VPS_DOMAIN=qc.geoffsmiscellany.com
DEMO_VPS_REMOTE_ROOT=/srv/bayesianqc
DEMO_VPS_SSH_KEY=/path/to/key
DEMO_VPS_SKIP_PUBLIC_SMOKE=1
```

## Release Behavior

`demo-vps-deploy` refuses dirty worktrees so the remote release matches a
committed SHA. The script uploads a `git archive` bundle, builds API/UI images
on the remote host, runs Alembic explicitly, ensures the hidden edge admin API
key is present in the database, restarts the stack, and runs smoke checks.

`demo-vps-bootstrap` uses the same deploy path, then loads the deterministic
synthetic demo suite. It does not load real lab/customer data.

`demo-vps-reset-data` creates a timestamped Postgres dump before destructive
reset, recreates the database, clears the demo import archive, re-runs
migrations, re-seeds the edge admin API key, and reloads the synthetic demo
suite.

`demo-vps-rotate-password` prints a fresh one-time stakeholder password and
force-recreates Caddy so the new password hash is active immediately.

`demo-vps-rollback` switches code/images back to a prior release id but does not
run Alembic downgrade or upgrade steps from the older release. If the rollback
crosses database migrations, run `make demo-vps-reset-data DEMO_VPS_HOST=<ssh-host>`
immediately after rollback to recreate the disposable synthetic schema and
fixtures under the rolled-back code.

Smoke checks are split intentionally: the remote helper verifies Postgres, the
API container, and Caddy's internal Basic Auth challenge; the local wrapper then
checks public `https://qc.geoffsmiscellany.com/api/me` from the operator machine
so the result matches the stakeholder path instead of a host hairpin path.

## Acceptance Checks

- Unauthenticated browser access returns a Basic Auth prompt.
- `admin` plus the generated password opens the UI.
- Internal `/me` resolves as role `admin` through the hidden edge API key.
- Public `/api/me` returns a Basic Auth challenge when unauthenticated.
- Direct API and Postgres ports are not exposed publicly.
- `/kiosk/demo`, `/charts`, `/imports`, and `/audit` load after reset.
- FastAPI `/docs`, `/redoc`, `/openapi.json`, and their `/api/*` proxy forms
  are intentionally not exposed through the public demo proxy; the demo is a UI
  walkthrough, not an API sandbox.
- `make import-restore-proof` passes when pointed at the remote DB/archive
  during a production-readiness rehearsal.

## Josh Walkthrough Runbook

1. Commit the deploy slice and confirm the target host routes
   `qc.geoffsmiscellany.com` over HTTPS.
2. Run `make demo-vps-bootstrap DEMO_VPS_HOST=<ssh-host>` for first setup, or
   `make demo-vps-deploy DEMO_VPS_HOST=<ssh-host>` for committed code updates.
3. Run `make demo-vps-reset-data DEMO_VPS_HOST=<ssh-host>` the morning of the
   walkthrough so screenshots, edits, imports, and comments start from known
   synthetic data.
4. Run `make demo-vps-smoke DEMO_VPS_HOST=<ssh-host>` and keep the output with
   the demo notes.
5. Share only `https://qc.geoffsmiscellany.com`, username `admin`, and the
   current generated password. Do not share the hidden edge API key.
6. After the walkthrough, run `make demo-vps-rotate-password
   DEMO_VPS_HOST=<ssh-host>` or shut down the host/tunnel.

All stakeholder actions in this demo are attributed to one shared edge-admin API
key in the backend audit log. That is acceptable for the Josh walkthrough only;
it is not a multi-user production auth model.

## Boundaries

This is not a shared-lab production deployment. It is a stakeholder demo using
synthetic data and a shared admin credential. Rotate the stakeholder password
after the demo, prune old release images when disk pressure appears, and do not
load real lab/customer data without the production validation package and SME
expected-row signoff.
