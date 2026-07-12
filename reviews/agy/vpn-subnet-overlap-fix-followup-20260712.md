Here is the strict read-only follow-up review of the proposed Docker network patch and manual rollout plan.

---

### Status Summary: **ALL P0/P1 ISSUES RESOLVED**
The combination of the reviewed commit patch and the manual rollout plan successfully addresses and mitigates all critical findings without introducing any new blockers.

#### 1. **P0: Destructive deploy/reset behavior** — **CLOSED**
* **Risk**: Sourcing the deployment script runs [reset_data](file:///home/user/projects/BAYESIANQC-josh-demo/deploy/demo/remote_lib.sh#L258-L278), which executes `dropdb` and wipes the host-mounted `/var/lib/bayesianqc/import-archive` directory.
* **Resolution**: The manual rollout plan completely bypasses `remote.sh deploy` and `remote.sh reset`. Instead, the services are built, pulled, and brought up manually using raw `docker compose` commands (Step 3 & 5). This preserves all data.

#### 2. **P0: Teardown secret deletion** — **CLOSED**
* **Risk**: Sourcing the teardown script deletes `app.env`, forcing a bootstrap on subsequent starts which rotates all database passwords and API keys, locking out containers from the bind-mounted database volume.
* **Resolution**: The rollout plan explicitly avoids the teardown script and keeps `app.env` intact. In addition, Step 1 creates a secure copy (`app.env.bak`), and Step 7 verifies the SHA-256 of `app.env` matches the baseline post-rollout to ensure no secret rotation occurred.

#### 3. **P1: Old network persistence (Bridge Persistence)** — **CLOSED**
* **Risk**: Stopping containers via `./remote.sh stop` leaves the dynamically allocated Docker bridge in place on the host, maintaining the routing hijack of `172.22.0.0/16`.
* **Resolution**: Step 4 runs `docker compose down --remove-orphans` on the old release (explicitly without `-v` to preserve Docker-managed volumes), which tears down the bridge network. The operator then verifies that the host routing table is clean of any `172.22` conflicts (`ip route show | grep 172.22`).

#### 4. **P1: Weak/Incorrect Test Assertion** — **CLOSED**
* **Risk**: The old test checked for overlaps against `172.22.0.0/24`, allowing a conflicting subnet in the remainder of the `/16` range to pass.
* **Resolution**: The reviewed commit updates [test_demo_networks_do_not_overlap_roadtrip_vpn](file:///home/user/projects/BAYESIANQC-josh-demo/tests/test_deployment_shell.py#L47-L52) to check against the full `172.22.0.0/16` network. The local test run confirms that the test passes with the new subnets configuration defined in [docker-compose.yml](file:///home/user/projects/BAYESIANQC-josh-demo/deploy/demo/docker-compose.yml):
  * `db_internal`: `172.31.251.0/24`
  * `app_internal`: `172.31.252.0/24`
  * `tunnel_egress`: `172.31.253.0/24`

---

### Manual Rollout Plan Review
The manual rollout procedure is structurally sound and follows defensive deployment practices.

1. **Safety of Database Backups**: Step 2 leverages the existing, tested [backup_snapshot](file:///home/user/projects/BAYESIANQC-josh-demo/deploy/demo/remote_lib.sh#L235-L243) and [write_checksums](file:///home/user/projects/BAYESIANQC-josh-demo/deploy/demo/remote_lib.sh#L245-L249) commands, ensuring we have a restorable database dump (`database.dump`) and a compressed archive of all uploaded files (`import-archive.tar.gz`) before touching the running system.
2. **Immutable Release Isolation**: Extracting and preparing the new release in `releases/<new-sha>` before stopping the service allows the operator to execute the build/pull steps (Step 3) in isolation. Since these commands only prepare images, they present no port or runtime network conflicts with the currently running service.
3. **Subnet-by-Subnet Rollout**: Starting Postgres first (Step 5) and waiting for its health check to pass is critical. The API service depends on a running database. Bringing up API/web/caddy afterwards guarantees that Postgres is ready to receive connections, preventing connection timeout failures on API startup.
4. **Post-Rollout Validation**: Confirming the baseline row counts, archive file listings, and `app.env` SHA-256 (Step 7) provides absolute assurance that no data loss or environment modification took place.

---

### Rollback Plan Review
* **Strategy**: `compose down` the new release without `-v`, bring the old release up via compose, and restart the tunnel.
* **Safety**: Since `/var/lib/postgresql/data` (Postgres data) and `/var/lib/bayesianqc/import-archive` are stored on host bind-mounts and are never removed, rolling back preserves the database state and imported files exactly as they were prior to the maintenance window. Sourcing the original release files will recreate the dynamic bridge network, restoring the application to its exact prior state.

### Blocker Assessment
No remaining P0/P1 blockers exist. The patch is approved for manual rollout.
