# Elite4Print Migration Comparison Harness

This repository contains a side-by-side proof-of-concept for rebuilding the Elite4Print backend. It compares two boilerplates:

- **fast-kit** — FastAPI + SQLAlchemy + Alembic (clean architecture / modular monolith)
- **django-init** — Django + DRF + Celery (modular monolith)

The harness migrates the same real-world slice of Elite4Print data — orders, order items, job memos, payments, pending refunds, coupons, products, and categories — into both targets and reconciles the results.

## What this harness proves

1. **Migration feasibility** — Can both frameworks carry over the Elite4Print schema and data cleanly?
2. **Financial reconciliation** — Do order totals, payments, refunds, discounts, taxes, and shipping reconcile to the cent?
3. **Row-count integrity** — Do all entities migrate without loss?
4. **Referential integrity** — Do foreign-key relationships hold after migration?
5. **Admin gap** — Django admin works out of the box; FastAPI has no built-in admin. `FASTAPI_ADMIN.md` documents the honest options and effort.

## What is *not* proved

- Full production performance under load.
- All 21 Elite4Print apps (only the order + payment slice).
- End-to-end API parity (only data migration + admin registration).

## Repository layout

```
.
├── docker-compose.yml              # PostgreSQL source + two target DBs
├── legacy_source/
│   ├── schema.sql                  # Elite4Print slice schema
│   ├── generate_seed.py            # Seed-data generator
│   └── seed.sql                    # Generated seed data (100 orders, ...)
├── fastapi_target/
│   └── migrate.py                  # FastAPI migration script
├── reconcile/
│   └── reconcile.py                # Cross-database reconciliation
├── METHODOLOGY.md                  # Scoring criteria and methodology
├── FASTAPI_ADMIN.md                # Honest FastAPI admin assessment
├── REPORT.md                       # Full findings and recommendation
└── README.md                       # This file
```

Companion code lives in:

- `/home/odin/repo/django-init` — branch `poc/e4p-migration-comparison`
- `/home/odin/repo/fast-kit` — branch `poc/e4p-migration-comparison`

## Prerequisites

- Docker + Docker Compose
- Python 3.13+ with `psycopg` (the django-init venv already has it)
- The two boilerplate repos checked out at the paths above

## Quick start

### 1. Start the databases

```bash
cd /home/odin/repo/e4p-migration-poc
docker compose up -d
```

This starts three PostgreSQL containers:

| Service | Host port | Database | Purpose |
|---------|-----------|----------|---------|
| `legacy_db` | `5433` | `e4p_legacy` | Source data |
| `django_target_db` | `5434` | `e4p_django` | django-init target |
| `fastapi_target_db` | `5435` | `e4p_fastapi` | fast-kit target |

The legacy DB is automatically initialized with `schema.sql` and `seed.sql`.

### 2. Regenerate seed data (optional)

```bash
python legacy_source/generate_seed.py
```

Then restart the legacy DB to reload:

```bash
docker compose down -v && docker compose up -d
```

### 3. Migrate the Django target

```bash
cd /home/odin/repo/django-init
source .venv/bin/activate

# Apply migrations to the Django target DB
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py migrate

# Run the migration command
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  LEGACY_DATABASE_URL=postgresql://e4p:e4p@localhost:5433/e4p_legacy \
  python backend/manage.py migrate_e4p_slice
```

### 4. Migrate the FastAPI target

```bash
cd /home/odin/repo/fast-kit
source .venv/bin/activate

# Apply Alembic migrations to the FastAPI target DB
DATABASE_URL=postgresql+asyncpg://e4p:e4p@localhost:5435/e4p_fastapi \
  alembic upgrade head

# Run the migration script
cd /home/odin/repo/e4p-migration-poc
PYTHONPATH=/home/odin/repo/fast-kit python fastapi_target/migrate.py
```

### 5. Reconcile

```bash
cd /home/odin/repo/e4p-migration-poc
source /home/odin/repo/django-init/.venv/bin/activate
python reconcile/reconcile.py
```

Expected output: `RESULT: ALL CHECKS PASS` with matching row counts and financial totals.

## What the reconciliation checks

The `reconcile.py` script compares three databases side by side:

- **Row counts** — users, product categories, products, orders, jobs, job memos, payments, pending refunds, coupons, coupon usages.
- **Financial totals** — orders total/final/discount/tax/shipping, payments, pending refunds, jobs price.
- **Referential integrity** — jobs without orders, payments without orders, refunds without payments.

## Inspecting the Django admin

The django-init POC registers admin classes for the slice. To verify:

```bash
cd /home/odin/repo/django-init
source .venv/bin/activate

# Promote an existing migrated user to superuser
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py shell -c "
from backend.apps.identity.domain.models import User
u = User.objects.get(id=1)
u.is_superuser = True
u.is_staff = True
u.set_password('admin')
u.save()
print('superuser set')
"

# Run Django checks
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py check
```

Then run the dev server and visit `http://localhost:8000/admin/`:

```bash
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py runserver
```

Registered admin models include `Product`, `ProductCategory`, `Order`, `Job`, `JobMemo`, `Payment`, `PendingRefund`, `Coupon`, and `CouponUsage`.

## Evaluating the results

Read the detailed reports:

- `REPORT.md` — full findings, LOC comparison, scoring, and recommendation.
- `FASTAPI_ADMIN.md` — honest assessment of what it takes to get FastAPI admin coverage equivalent to Django.
- `METHODOLOGY.md` — scoring criteria and how the POC was kept fair.

The short version:

- **Django** wins on migration familiarity and admin coverage.
- **FastAPI** wins on explicit boundaries, testability, and long-term maintainability.
- The **migration itself reconciles cleanly in both frameworks**.

## Stopping / resetting

Stop all databases:

```bash
docker compose down
```

Destroy all data and start fresh:

```bash
docker compose down -v && docker compose up -d
```

## Notes

- The legacy schema is a simplified but representative slice of Elite4Print. It is not the full production schema.
- `seed.sql` is generated by `generate_seed.py`. Do not edit `seed.sql` by hand; edit the generator instead.
- The FastAPI migration script assumes the fast-kit repo is at `/home/odin/repo/fast-kit`. If your path differs, adjust `PYTHONPATH` accordingly.
