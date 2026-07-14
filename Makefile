.PHONY: help up down reset seed migrate-dj migrate-fa reconcile admin-check

help:
	@echo "Elite4Print Migration Comparison Harness"
	@echo ""
	@echo "Available commands:"
	@echo "  make up          - Start PostgreSQL databases"
	@echo "  make down        - Stop PostgreSQL databases"
	@echo "  make reset       - Destroy all data and start fresh"
	@echo "  make seed        - Regenerate seed.sql"
	@echo "  make migrate-dj  - Migrate the Django target"
	@echo "  make migrate-fa  - Migrate the FastAPI target"
	@echo "  make reconcile   - Run reconciliation checks"
	@echo "  make admin-check - Verify Django admin registration"

up:
	docker compose up -d

down:
	docker compose down

reset:
	docker compose down -v && docker compose up -d

seed:
	python legacy_source/generate_seed.py

migrate-dj:
	cd ../django-init && source .venv/bin/activate && \
	POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
	POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
	python backend/manage.py migrate && \
	POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
	POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
	LEGACY_DATABASE_URL=postgresql://e4p:e4p@localhost:5433/e4p_legacy \
	python backend/manage.py migrate_e4p_slice

migrate-fa:
	cd ../fast-kit && source .venv/bin/activate && \
	DATABASE_URL=postgresql+asyncpg://e4p:e4p@localhost:5435/e4p_fastapi \
	alembic upgrade head && \
	cd ../e4p-migration-poc && \
	../fast-kit/.venv/bin/python fastapi_target/migrate.py

reconcile:
	source ../django-init/.venv/bin/activate && \
	python reconcile/reconcile.py

admin-check:
	cd ../django-init && source .venv/bin/activate && \
	POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
	POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
	python backend/manage.py check
