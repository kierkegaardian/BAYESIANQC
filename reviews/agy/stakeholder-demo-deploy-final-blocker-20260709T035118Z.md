No remaining P0 or P1 blockers were found in this deployment path. All components, error handling, readiness loops, and rollback flows are structurally sound and verified by the pytest suite.

Below is the detailed review and reconciliation of the bcrypt escaping mechanism.

---

### 1. Reconciliation of the Bcrypt `$$` Finding

No blocker is raised for the double-dollar `$$` escaping in `remote.sh` (`hash="${hash//\$/\$\$}"`). 

* **Behavior**: In `docker compose`, environment variables declared in `.env` or `--env-file` files utilize `$` for variable interpolation. To pass a literal `$` to a container's environment, it must be escaped as `$$`.
* **Verification**: The Compose probe results (`app.env HASH=$$2a$$14$$abc$$def` delivering `$2a$14$abc$def` inside the container) confirm that this escaping operates correctly. Docker Compose successfully strips the escape characters and passes the valid single-`$` bcrypt hash directly to the Caddy environment. Caddy then reads the unescaped hash correctly for HTTP Basic Auth.

---

### 2. Remaining P0/P1 Blockers
* **None**. 

---

### 3. Brief P2 Notes / Observations
* **Host directory permissions (Non-blocking)**: In `remote.sh`, the `postgres/` and `caddy/data/` directories are created using the deploy operator's default user/group permissions. Because the official `postgres` image entrypoint initially runs as `root` to chown the data volume, and the official `caddy` image runs as `root` by default (to bind to ports 80/443), this is non-blocking. If a hardened custom Caddy image is used that runs as a non-root UID (e.g. UID 1000), file write permissions on the host `/srv/bayesianqc/caddy/data` directory may need to be adjusted.
* **`api` Container Self-Resolution (Non-blocking)**: In `wait_for_api`, the check uses `urllib.request.urlopen("http://api:8010/me")` inside the `api` container. While Docker DNS generally resolves the service name `api` to the container's IP on the default bridge network, querying `http://127.0.0.1:8010/me` would bypass DNS resolution entirely.
