PYTHON ?= .venv/bin/python
ALEMBIC ?= .venv/bin/alembic
NPM ?= npm
POSTGRES_URL ?= postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
POSTGRES_TEST_URL ?= $(POSTGRES_URL)
POSTGRES_COPY_URL ?=
IMPORT_ARCHIVE_ROOT ?= $(HOME)/.local/state/bayesianqc/import-archive
DB_IMPORT_ARCHIVE_ROOT ?= $(IMPORT_ARCHIVE_ROOT)

.PHONY: lint typecheck test build check postgres-up postgres-upgrade test-postgres migration-upgrade migration-rehearse migration-rehearse-postgres migration-rehearse-postgres-copy import-restore-proof check-postgres

lint:
	$(PYTHON) -m ruff check app tests scripts

typecheck:
	$(PYTHON) -m pyright

test:
	$(PYTHON) -m pytest

build:
	$(NPM) --prefix frontend run check

check: lint typecheck test build

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
