# Josh synthetic demo: Quick Tunnel runbook

This runbook publishes the disposable stakeholder demo through:

`Josh -> Cloudflare Quick Tunnel -> Caddy Basic Auth -> private Compose on internalserver`

It is a stakeholder demonstration, not a validated laboratory deployment. Use
only the deterministic synthetic fixture. Do not enter PHI, customer data,
instrument exports, or production laboratory data.

## Fixed topology and trust boundaries

- Control/build plane: the clean sibling worktree on the workstation.
- Origin: `internalserver`, reached only through `homeops-ssh-ubuntu`.
- Remote root: `/home/geoff/services/bayesianqc-josh-demo`.
- Compose project: `bayesianqc-josh-demo`.
- `postgres` is attached only to `db_internal`; it has no host port.
- `api` is attached to `db_internal` and `app_internal`; it has no host port.
- `web` is attached only to `app_internal`; it has no host port.
- Caddy is attached to `app_internal` and `tunnel_egress`; it has no host port.
- `cloudflared` is attached only to `tunnel_egress`, uses no account/token/config,
  and exits rather than restarting automatically.

Caddy challenges the whole site with Basic Auth, removes inbound
`Authorization` and `X-API-Key`, and injects only the stakeholder API key. It
returns 404 for API documentation, permits the stakeholder read surface and
the selected comment/resolution/alert/investigation/CAPA mutations, and returns
403 for all other API routes or methods. FastAPI's stakeholder role and stream
grants remain the primary authorization boundary.

Quick Tunnels are random-addressed, testing-only, and have no SLA. A restarted
tunnel gets a new URL. Stop the release if the URL changes unexpectedly.

## Release prerequisites

1. Work only in `/home/user/projects/BAYESIANQC-josh-demo` on
   `codex/josh-demo-hardening`.
2. Commit the intended release and confirm `git status --short` is empty.
3. Pass the full application, migration, dependency-audit, frontend, and final
   Tier-A review gates. Do not deploy with a high/critical advisory or an
   unresolved P0/P1.
4. Confirm `homeops-ssh-ubuntu hostname` reports `internalserver`.
5. Confirm all data and screenshots in the release are synthetic.

`bootstrap` and `deploy` refuse a dirty worktree. They create a deterministic
Git archive from the full 40-character release SHA, stream it through the
keyring-backed SSH wrapper, verify its SHA-256 remotely, tag built API/web
images with the exact SHA, and record image IDs and pulled-image repository
digests in `RELEASE_MANIFEST.json`. Every external build/runtime image is locked
to an immutable manifest digest in `deploy/demo/image-lock.json`; the release
manifest records those exact references and checksums the build inputs. No raw
SSH credentials or `scp` are used.

Remote preflight requires at least 10 GiB free disk and 2 GiB available RAM.
If either threshold fails, the lifecycle script stops only this Compose
project's Quick Tunnel and refuses deployment or tunnel startup.
Deployment captures host listeners before startup, rejects published container
ports, and fails if a new host listener appears.

## First bootstrap

From the clean release worktree:

```bash
make josh-demo-bootstrap
```

Bootstrap generates fresh database, bootstrap API, stakeholder API, and Basic
Auth secrets. Only the database/API secrets and bcrypt Basic password hash are
stored in remote `secrets/app.env` with mode `0600`. The username is `josh`.
The raw Basic password is printed once and is never stored on internalserver.
Capture it in a password manager; do not put it in source control, shell
history, a runbook, a review artifact, or the release manifest.

For a later committed release that should retain existing secrets:

```bash
make josh-demo-deploy
```

Both commands rebuild the database from scratch, run migrations, seed the
bootstrap/stakeholder identities and stream grants, load the deterministic
fixture, and run a private authorization smoke. They leave the public tunnel
stopped.

If the one-time password is lost, rotate it and record the newly printed value:

```bash
make josh-demo-rotate-password
```

## Pre-share acceptance sequence

Check the exact release and private services:

```bash
make josh-demo-status
```

Confirm the SHA and archive checksum match the workstation release. Confirm
all services are healthy, all image records have IDs, and Postgres/Caddy/
cloudflared have repository digests.

Exercise the allowed Josh workflow before publishing: add a comment,
exclude/reinstate a point, update an alert, and create/update linked
investigation and CAPA evidence. Confirm raw ingestion, imports, configuration,
administration, and docs remain inaccessible. Then discard those acceptance
mutations with a full reset:

```bash
make josh-demo-reset
make josh-demo-status
```

Reset stops any active tunnel first, creates a timestamped Postgres/import
archive snapshot with SHA-256 checksums, drops and recreates the entire demo
database, clears the demo archive, reruns migrations, and reloads fixtures. It
never selectively deletes test rows.

Start the tunnel last:

```bash
make josh-demo-start-tunnel
```

The command prints one `https://...trycloudflare.com` URL and proves an
unauthenticated request receives a Basic challenge. Next run the authenticated
public gate. Passing the password via an environment variable is acceptable for
the short-lived process; it is not written remotely or printed:

```bash
read -r -s JOSH_DEMO_BASIC_PASSWORD
export JOSH_DEMO_BASIC_PASSWORD
make josh-demo-smoke
unset JOSH_DEMO_BASIC_PASSWORD
```

The default smoke holds the same URL for at least 900 seconds, rechecking every
30 seconds. It verifies:

- unauthenticated `/api/me` receives the Basic challenge;
- authenticated `/api/me` reports `role=stakeholder`;
- stakeholder pages and the scoped `/api/stream-catalog` read succeed while the
  full `/api/streams` configuration list remains denied;
- a real alert status mutation succeeds, is read back, and is restored to its
  original open state before the check completes;
- docs/OpenAPI return 404;
- raw ingestion, import, configuration, and admin writes return 403;
- encoded and normalized forbidden-path probes remain denied.

Also open the URL from an off-LAN/cellular browser at desktop size and at a
basic phone viewport. Verify kiosk, charts, alerts, investigations, and CAPAs;
check for failed requests, console errors, clipping, and stale error states.
Do not share until the URL has remained unchanged for 15 minutes.
The smoke command refuses values below 900 seconds and the remote host will not
record `public-smoke=pass` without the same minimum.

## Sharing with Josh

Share the random URL and password through separate channels. Give Josh:

- username `josh`;
- the synthetic/nonvalidated disclaimer;
- the guided sequence: overview kiosk; fuel outlier with frequentist rejection
  separated from low predictive risk; pharma predictive warning; steel
  alternating variability without an R-4s claim; unit-mismatch quarantine; and
  the comment/resolution/alert/investigation/CAPA workflow.

Stop immediately for real/customer data, an incorrect role or scope, an
unexpected published port/listener, migration failure, unresolved high/critical
advisory, changed URL, public failure, or host resources below the minimum.

## Operations

```bash
make josh-demo-status
make josh-demo-stop
```

`stop` removes the project-labeled cloudflared container first, then stops this
Compose project's remaining services. It does not affect other containers and
never uses `killall`, Docker prune, or a global Compose command.

To restart after `stop`, run `make josh-demo-reset` and then
`make josh-demo-start-tunnel`; expect a new random URL and repeat the full
public smoke before sharing.

## Teardown and retention

```bash
make josh-demo-teardown
```

Teardown performs these project-scoped actions:

1. records the release SHA, URL, start/end times, and nonsecret smoke results;
2. stops and removes this project's cloudflared container first;
3. captures a custom-format Postgres dump, import archive, release manifest,
   and SHA-256 checksums;
4. runs Compose down without deleting the persistent database bind;
5. removes the remote secret environment file;
6. verifies no `bayesianqc-josh-demo` containers or new listeners remain;
7. polls the former public URL from the workstation until its Basic challenge
   is gone.

The stopped snapshot and backup remain under the fixed remote root for seven
days. Purging them, deleting the persistent database bind, or deleting backups
requires separate explicit approval.
