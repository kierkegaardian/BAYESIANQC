Here is the infrastructure and deployment review for the proposed Docker network patch and rollout plan. A detailed report with a step-by-step safe rollout procedure and rollback strategy has been compiled in the artifact: [infrastructure_review.md](file:///home/user/.gemini/antigravity-cli/brain/859bdbdd-5809-42a0-a5bd-292f4fa65468/infrastructure_review.md).

### 🚨 Critical Findings (P0/P1)

*   **P0: Automated Data Loss on Deployment**
    The `deploy` command in [remote.sh](file:///home/user/projects/BAYESIANQC-josh-demo/deploy/demo/remote.sh#L12-L55) calls `reset_data` which executes `dropdb` and wipes the host-mounted `/var/lib/bayesianqc/import-archive` directory. Even though a pre-reset backup is generated, executing the script as-is for the rollout will wipe all existing demo state and custom data, replacing them with default fixtures.
*   **P0: Outage and Lockout due to Secrets Deletion**
    The `teardown` command in [remote.sh](file:///home/user/projects/BAYESIANQC-josh-demo/deploy/demo/remote.sh#L133-L172) deletes the `app.env` secrets file (`rm -f "$ENV_FILE"`). A subsequent bootstrap will rotate all tokens (including the Postgres password and API keys), locking out the container from the existing bind-mounted database data and breaking external client integrations.
*   **P1: Failure to Restore the VPN Path (Bridge Persistence)**
    Stopping containers via `remote.sh stop` does not remove the Docker network bridge. Host route tables will continue to route `172.22.0.0/16` traffic into the local Docker interface until the network is explicitly removed (e.g., via `compose down` or `docker network rm`).
*   **P1: Weak/Incorrect Test Assertion**
    The test `test_demo_networks_do_not_overlap_roadtrip_vpn` in [test_deployment_shell.py](file:///home/user/projects/BAYESIANQC-josh-demo/tests/test_deployment_shell.py#L47-L52) only checks for overlaps against `172.22.0.0/24`. Since the actual VPN client block is `172.22.0.0/16`, any subnet in the `172.22.1.0/24` to `172.22.255.0/24` range would pass the test but still hijack VPN traffic.

---

### Key Decisions / Actions Needed

Please review the proposed manual rollout procedure in the artifact [infrastructure_review.md](file:///home/user/.gemini/antigravity-cli/brain/859bdbdd-5809-42a0-a5bd-292f4fa65468/infrastructure_review.md) to safely recreate the networks and containers.

1. Would you like to proceed with the manual rollout steps to bypass the destructive parts of the existing scripts?
2. Should we update the deployment scripts to fix these data loss and secrets deletion behaviors for future rollouts? (Note: No files have been edited in this pass).
