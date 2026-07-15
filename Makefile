.PHONY: help up down reset seed migrate-dj migrate-fa reconcile admin-check

help:
	@echo "Elite4Print Migration Comparison Harness"
	@echo ""
	@echo "Available commands:"
	@echo "  make up             - Start PostgreSQL databases"
	@echo "  make down           - Stop PostgreSQL databases"
	@echo "  make reset          - Destroy all data and start fresh"
	@echo "  make restore-real   - Restore backups/e4p_dev_from_prod_real.dump into legacy_db"
	@echo "  make seed           - Regenerate seed.sql (synthetic data)"
	@echo "  make migrate-dj     - Migrate the Django target"
	@echo "  make migrate-fa     - Migrate the FastAPI target"
	@echo "  make reconcile      - Run reconciliation checks"
	@echo "  make admin-check    - Verify Django admin registration"

up:
	docker compose up -d

down:
	docker compose down

reset:
	docker compose down -v && docker compose up -d

restore-real:
	docker run --rm \
		-e PGPASSWORD=e4p \
		-v $(PWD)/backups:/backups \
		--network host \
		postgres:16-alpine \
		pg_restore -h localhost -p 5433 -U e4p -d e4p_legacy \
			--no-owner --no-acl --verbose \
			/backups/e4p_dev_from_prod_real.dump

seed:
	python legacy_source/generate_seed.py

migrate-dj:
	cd ../django-kit && \
	POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
	POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
	uv run python backend/manage.py migrate && \
	POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
	POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
	LEGACY_DATABASE_URL=postgresql://e4p:e4p@localhost:5433/e4p_legacy \
	uv run python backend/manage.py migrate_e4p_slice

migrate-fa:
	cd ../fast-kit && \
	DATABASE_URL=postgresql+asyncpg://e4p:e4p@localhost:5435/e4p_fastapi \
	uv run alembic upgrade head && \
	cd ../e4p-migration-poc && \
	uv run --project ../fast-kit python fastapi_target/migrate.py

reconcile:
	cd ../e4p-migration-poc && \
	uv run --project ../django-kit python reconcile/reconcile.py

admin-check:
	cd ../django-kit && \
	POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
	POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
	uv run python backend/manage.py check
