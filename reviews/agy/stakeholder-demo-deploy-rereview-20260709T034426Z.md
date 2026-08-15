### Findings & Blockers First

Here are the remaining P0/P1 blockers identified in the reviewed deployment configuration:

#### 🚨 P0: Caddy Internal Health Check Host Matching & Redirect Loop Failure
* **Location:** [deploy/demo-vps/remote.sh#L227-L246](file:///home/user/bayesianqc/deploy/demo-vps/remote.sh#L227-L246) (`wait_for_caddy_basic_auth` function) and [deploy/demo-vps/Caddyfile](file:///home/user/bayesianqc/deploy/demo-vps/Caddyfile)
* **Problem:** The internal health check queries `http://caddy/api/me`, sending `Host: caddy`. However, [Caddyfile](file:///home/user/bayesianqc/deploy/demo-vps/Caddyfile) is strictly configured for `{$BAYESIANQC_DOMAIN}` (`qc.geoffsmiscellany.com`). Caddy will reject requests matching the host `caddy` (returning `404`), causing the deployment script to hang and fail during `smoke_release`.
* **Why Host-Header Overrides Fail:** Overriding the `Host` header to `qc.geoffsmiscellany.com` in Python will cause Caddy to trigger its automatic HTTPS middleware and return a `308 Permanent Redirect` to `https://qc.geoffsmiscellany.com/api/me`. If DNS is not yet live (e.g. during bootstrap), the redirect will fail to resolve, causing the smoke check to crash.
* **Fix:** Update [Caddyfile](file:///home/user/bayesianqc/deploy/demo-vps/Caddyfile) to explicitly permit internal HTTP traffic on the Caddy container alias so that the internal health check can hit Basic Auth without redirecting:
  ```caddy
  {$BAYESIANQC_DOMAIN}, http://caddy {
      encode zstd gzip

      basic_auth {
          admin {$BAYESIANQC_BASIC_AUTH_HASH}
      }
      # ...
  }
  ```

#### 🚨 P1: Alembic Migrations Crash on Rollback
* **Location:** [deploy/demo-vps/remote.sh#L256-L276](file:///home/user/bayesianqc/deploy/demo-vps/remote.sh#L256-L276) (`rollback` function)
* **Problem:** During a rollback, `rollback()` executes `run_migrations "$release"`, which invokes `alembic upgrade head` using the code of the older release. If the release being rolled back *from* introduced a database migration, the database will already be at a migration version that the older Alembic release code cannot recognize. Alembic will crash with `Can't locate revision identifier...`, causing the rollback script to abort.
* **Fix:** Update the operator runbook ([docs/STAKEHOLDER_DEMO_VPS_DEPLOYMENT.md](file:///home/user/bayesianqc/docs/STAKEHOLDER_DEMO_VPS_DEPLOYMENT.md)) to instruct operators that if a rollback crosses database migrations, they must run `make demo-vps-reset-data` immediately after the rollback command to re-align the schema and fixtures at the older head revision.

#### 🚨 P1: API Interactive Documentation `/docs` and `/redoc` Inaccessibility
* **Location:** [deploy/demo-vps/Caddyfile](file:///home/user/bayesianqc/deploy/demo-vps/Caddyfile) and [deploy/demo-vps/docker-compose.yml](file:///home/user/bayesianqc/deploy/demo-vps/docker-compose.yml)
* **Problem:** The API container's port `8010` is kept private (which is correct). However, Caddy only routes `/api/*` requests to the `api` container. FastAPI's interactive documentation (`/docs`, `/redoc`) and its schema `/openapi.json` are served at the root path of the `api` container. Currently, visiting `https://qc.geoffsmiscellany.com/docs` will hit the catch-all `handle` block and route to the static Vue SPA, rendering a frontend 404.
* **Fix:** If Swagger documentation must be visible to stakeholders, add routing rules to [Caddyfile](file:///home/user/bayesianqc/deploy/demo-vps/Caddyfile):
  ```caddy
  handle /docs {
      reverse_proxy api:8010
  }
  handle /openapi.json {
      reverse_proxy api:8010
  }
  ```
  *(Otherwise, document that interactive API documentation is intentionally disabled in the demo environment).*

---

### P2 Notes

1. **Docker Image Accumulation & Disk Expiration:** 
   The deployment script builds unique release-tagged images (`bayesianqc-demo-api:<release-id>`) on the remote host. Over time, multiple deployments will exhaust disk space. Consider adding `docker image prune -f` to the deployment flow.
2. **Shared Audit Log Attribution:**
   Caddy injects a single `BAYESIANQC_EDGE_ADMIN_API_KEY` for all backend requests. All operations will appear in the audit logs under a single shared administrator entity. This should be explicitly noted in the walkthrough runbook.
3. **SSH Known Hosts Verification:**
   The `scripts/demo_vps.sh` script runs SSH with `BatchMode=yes`. If the operator has never connected to the target host before, the command will abort. The runbook should mention performing a manual SSH connection to accept the host key prior to bootstrapping.

---

### Summary of Work
I performed a security and reliability review of the provided VPS deployment package. I analyzed potential shell quoting pitfalls, Caddy host-header matching constraints, Alembic version rollback limits, port exposures, and API documentation routing. The findings have been formatted into P0/P1 blockers and P2 notes for immediate action.
