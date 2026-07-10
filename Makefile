PYTHON ?= .venv/bin/python
ALEMBIC ?= .venv/bin/alembic
NPM ?= npm
POSTGRES_URL ?= postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
POSTGRES_TEST_URL ?= $(POSTGRES_URL)
POSTGRES_COPY_URL ?=
IMPORT_ARCHIVE_ROOT ?= $(HOME)/.local/state/bayesianqc/import-archive
DB_IMPORT_ARCHIVE_ROOT ?= $(IMPORT_ARCHIVE_ROOT)
JOSH_DEMO_REMOTE_ROOT ?= /home/geoff/services/bayesianqc-josh-demo
JOSH_DEMO_STABILITY_SECONDS ?= 900

DEMO_VPS_HOST ?=
DEMO_VPS_DOMAIN ?= qc.geoffsmiscellany.com
DEMO_VPS_REMOTE_ROOT ?= /srv/bayesianqc
DEMO_VPS_SSH_KEY ?=
DEMO_VPS_SKIP_PUBLIC_SMOKE ?= 0
DEMO_VPS_SSH_KEY_ARG := $(if $(DEMO_VPS_SSH_KEY),--ssh-key "$(DEMO_VPS_SSH_KEY)",)
DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG := $(if $(filter 1 true yes,$(DEMO_VPS_SKIP_PUBLIC_SMOKE)),--skip-public-smoke,)

.PHONY: lint typecheck test frontend-test build check postgres-up postgres-upgrade test-postgres migration-upgrade migration-rehearse migration-rehearse-postgres migration-rehearse-postgres-copy import-restore-proof check-postgres demo-vps-bootstrap demo-vps-deploy demo-vps-reset-data demo-vps-rotate-password demo-vps-smoke demo-vps-rollback josh-demo-bootstrap josh-demo-deploy josh-demo-reset josh-demo-smoke josh-demo-status josh-demo-start-tunnel josh-demo-stop josh-demo-teardown josh-demo-rotate-password

lint:
	$(PYTHON) -m ruff check app tests scripts

typecheck:
	$(PYTHON) -m pyright

test:
	$(PYTHON) -m pytest

frontend-test:
	$(NPM) --prefix frontend test

build:
	$(NPM) --prefix frontend run check

check: lint typecheck test frontend-test build

postgres-up:
	docker compose up -d postgres

postgres-upgrade:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(ALEMBIC) upgrade head

test-postgres:
	BAYESIANQC_POSTGRES_TEST_URL="$(POSTGRES_TEST_URL)" $(PYTHON) -m pytest tests/test_migrations.py

migration-upgrade:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(ALEMBIC) upgrade head

migration-rehearse:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(PYTHON) scripts/rehearse_sqlite_to_postgres.py --postgres-url "$(POSTGRES_URL)"

migration-rehearse-postgres:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(PYTHON) scripts/rehearse_sqlite_to_postgres.py --postgres-url "$(POSTGRES_URL)"

migration-rehearse-postgres-copy:
	test -n "$(POSTGRES_COPY_URL)" || (echo "Set POSTGRES_COPY_URL to a disposable Postgres database URL"; exit 2)
	case "$(POSTGRES_COPY_URL)" in *disposable*|*rehearsal*|*test*) ;; *) echo "POSTGRES_COPY_URL must look disposable: include disposable, rehearsal, or test"; exit 2;; esac
	BAYESIANQC_DB_URL="$(POSTGRES_COPY_URL)" $(PYTHON) scripts/rehearse_sqlite_to_postgres.py --postgres-url "$(POSTGRES_COPY_URL)" --copy-data --truncate-target

import-restore-proof:
	BAYESIANQC_IMPORT_ARCHIVE_ROOT="$(IMPORT_ARCHIVE_ROOT)" $(PYTHON) scripts/prove_import_restore.py --source-url "$(POSTGRES_URL)" --archive-root "$(IMPORT_ARCHIVE_ROOT)" --db-archive-root "$(DB_IMPORT_ARCHIVE_ROOT)"

check-postgres: postgres-up postgres-upgrade test-postgres migration-rehearse-postgres

demo-vps-bootstrap:
	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
	scripts/demo_vps.sh bootstrap --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)

demo-vps-deploy:
	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
	scripts/demo_vps.sh deploy --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)

demo-vps-reset-data:
	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
	scripts/demo_vps.sh reset-data --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)

demo-vps-rotate-password:
	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
	scripts/demo_vps.sh rotate-password --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)

demo-vps-smoke:
	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
	scripts/demo_vps.sh smoke --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)

demo-vps-rollback:
	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
	test -n "$(DEMO_VPS_RELEASE_ID)" || (echo "Set DEMO_VPS_RELEASE_ID"; exit 2)
	scripts/demo_vps.sh rollback --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" --release-id "$(DEMO_VPS_RELEASE_ID)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)

josh-demo-bootstrap:
	scripts/josh_demo.sh bootstrap --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"

josh-demo-deploy:
	scripts/josh_demo.sh deploy --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"

josh-demo-reset:
	scripts/josh_demo.sh reset --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"

josh-demo-smoke:
	scripts/josh_demo.sh smoke --remote-root "$(JOSH_DEMO_REMOTE_ROOT)" --stability-seconds "$(JOSH_DEMO_STABILITY_SECONDS)"

josh-demo-status:
	scripts/josh_demo.sh status --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"

josh-demo-start-tunnel:
	scripts/josh_demo.sh start-tunnel --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"

josh-demo-stop:
	scripts/josh_demo.sh stop --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"

josh-demo-teardown:
	scripts/josh_demo.sh teardown --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"

josh-demo-rotate-password:
	scripts/josh_demo.sh rotate-password --remote-root "$(JOSH_DEMO_REMOTE_ROOT)"
