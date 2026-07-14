# Elite4Print Migration Comparison Harness

A reproducible, side-by-side proof-of-concept for rebuilding the Elite4Print backend. It migrates the same real-world data slice into two boilerplates and reconciles the results.

- **fast-kit** — FastAPI + SQLAlchemy + Alembic (clean architecture / modular monolith)
- **django-init** — Django + DRF + Celery (modular monolith)

The slice covers: orders, order items, job memos, payments, pending refunds, coupons, products, and categories.

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
e4p-migration-poc/
├── docker-compose.yml              # PostgreSQL source + two target DBs
├── legacy_source/
│   ├── schema.sql                  # Elite4Print slice schema
│   ├── generate_seed.py            # Seed-data generator
│   └── seed.sql                    # Generated seed data
├── fastapi_target/
│   └── migrate.py                  # FastAPI migration script
├── reconcile/
│   └── reconcile.py                # Cross-database reconciliation
├── Makefile                        # Common commands
├── METHODOLOGY.md                  # Scoring criteria and methodology
├── FASTAPI_ADMIN.md                # Honest FastAPI admin assessment
├── REPORT.md                       # Full findings and recommendation
└── README.md                       # This file
```

This harness is designed to sit next to the two boilerplate repos:

```
workspace/
├── django-init/                    # branch: poc/e4p-migration-comparison
├── fast-kit/                       # branch: poc/e4p-migration-comparison
└── e4p-migration-poc/              # this repo
```

## Prerequisites

- Docker + Docker Compose
- Python 3.13+
- `psycopg` and `asyncpg` (installed in the boilerplate virtual environments)
- Access to the three repositories:
  - `https://github.com/AzmainMahtab/e4p-migration-poc.git`
  - `https://github.com/AzmainMahtab/django-kit.git`
  - `https://github.com/AzmainMahtab/fast-kit.git`

## Setup

### 1. Clone the three repositories side by side

```bash
mkdir elite4print-rebuild && cd elite4print-rebuild
git clone https://github.com/AzmainMahtab/e4p-migration-poc.git
git clone https://github.com/AzmainMahtab/django-kit.git django-init
git clone https://github.com/AzmainMahtab/fast-kit.git
```

### 2. Check out the POC branches in both boilerplates

```bash
cd django-init && git checkout poc/e4p-migration-comparison && cd ..
cd fast-kit && git checkout poc/e4p-migration-comparison && cd ..
```

### 3. Set up the boilerplate virtual environments

Follow each repo's own README, or run the equivalent of:

```bash
cd django-init && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cd ..
cd fast-kit && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cd ..
```

> The commands below assume the recommended directory structure. If you cloned to different paths, replace `../django-init` and `../fast-kit` accordingly.

## Quick start

All commands below are run from inside `e4p-migration-poc/`.

### 1. Start the databases

```bash
cd e4p-migration-poc
docker compose up -d
```

This starts three PostgreSQL containers on localhost:

| Service | Port | Database | Purpose |
|---------|------|----------|---------|
| `legacy_db` | `5433` | `e4p_legacy` | Source data |
| `django_target_db` | `5434` | `e4p_django` | django-init target |
| `fastapi_target_db` | `5435` | `e4p_fastapi` | fast-kit target |

The legacy DB is automatically initialized with `schema.sql` and `seed.sql`.

### 2. (Optional) Regenerate seed data

```bash
python legacy_source/generate_seed.py
```

Then restart the legacy DB to reload:

```bash
docker compose down -v && docker compose up -d
```

### 3. Migrate the Django target

```bash
cd ../django-init
source .venv/bin/activate

# Apply migrations
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py migrate

# Migrate the Elite4Print slice
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  LEGACY_DATABASE_URL=postgresql://e4p:e4p@localhost:5433/e4p_legacy \
  python backend/manage.py migrate_e4p_slice
```

### 4. Migrate the FastAPI target

```bash
cd ../fast-kit
source .venv/bin/activate

# Apply Alembic migrations
DATABASE_URL=postgresql+asyncpg://e4p:e4p@localhost:5435/e4p_fastapi \
  alembic upgrade head

# Run the migration script
cd ../e4p-migration-poc
python fastapi_target/migrate.py
```

`migrate.py` uses `asyncpg`, which is installed in fast-kit's virtual environment. If you prefer, you can also run it with the venv interpreter directly:

```bash
../fast-kit/.venv/bin/python fastapi_target/migrate.py
```

### 5. Reconcile

```bash
cd ../e4p-migration-poc
source ../django-init/.venv/bin/activate
python reconcile/reconcile.py
```

Expected output: `RESULT: ALL CHECKS PASS` with matching row counts and financial totals.

## Using the Makefile

A `Makefile` is provided for convenience. From `e4p-migration-poc/`:

```bash
make up          # docker compose up -d
make down        # docker compose down
make reset       # destroy volumes and start fresh
make seed        # regenerate seed.sql
make migrate-dj  # migrate Django target
make migrate-fa  # migrate FastAPI target
make reconcile   # run reconciliation
```

Run `make help` for the full list.

## What the reconciliation checks

`reconcile/reconcile.py` compares the source, Django, and FastAPI databases:

- **Row counts** — users, product categories, products, orders, jobs, job memos, payments, pending refunds, coupons, coupon usages.
- **Financial totals** — orders total/final/discount/tax/shipping, payments, pending refunds, jobs price.
- **Referential integrity** — jobs without orders, payments without orders, refunds without payments.

## Inspecting the Django admin

The django-init POC registers admin classes for the slice.

```bash
cd ../django-init
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

# Verify admin registration
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py check
```

Then run the dev server:

```bash
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py runserver
```

Visit `http://localhost:8000/admin/` and log in with the superuser credentials you just set.

Registered admin models: `Product`, `ProductCategory`, `Order`, `Job`, `JobMemo`, `Payment`, `PendingRefund`, `Coupon`, `CouponUsage`.

## Evaluating the results

Read the detailed reports:

- `REPORT.md` — full findings, LOC comparison, scoring, and recommendation.
- `FASTAPI_ADMIN.md` — honest assessment of FastAPI admin options.
- `METHODOLOGY.md` — scoring criteria and fairness rules.

Short version:

- **Django** wins on migration familiarity and admin coverage.
- **FastAPI** wins on explicit boundaries, testability, and long-term maintainability.
- The **migration itself reconciles cleanly in both frameworks**.

## Environment variables

You can override database connections if you are not using the default Docker Compose setup:

| Variable | Default | Used by |
|----------|---------|---------|
| `LEGACY_DATABASE_URL` | `postgresql://e4p:e4p@localhost:5433/e4p_legacy` | Django migration, reconciliation |
| `E4P_SOURCE_DSN` | `postgresql://e4p:e4p@localhost:5433/e4p_legacy` | FastAPI migration |
| `E4P_TARGET_DSN` | `postgresql://e4p:e4p@localhost:5435/e4p_fastapi` | FastAPI migration |
| `DJANGO_DATABASE_URL` | `postgresql://e4p:e4p@localhost:5434/e4p_django` | Reconciliation |
| `FASTAPI_DATABASE_URL` | `postgresql://e4p:e4p@localhost:5435/e4p_fastapi` | Reconciliation |

## Troubleshooting

### Port already in use

If `5433`, `5434`, or `5435` are taken, edit `docker-compose.yml` to map different host ports and set the matching environment variables.

### `psycopg` or `asyncpg` not found

Use the boilerplate virtual environments:

```bash
source ../django-init/.venv/bin/activate   # for reconcile.py
source ../fast-kit/.venv/bin/activate      # for fastapi_target/migrate.py
```

### Django migration complains about missing dependencies

Make sure you are on the `poc/e4p-migration-comparison` branch in `django-init` and have run `pip install -r requirements.txt`.

### FastAPI Alembic migration fails

Make sure you are on the `poc/e4p-migration-comparison` branch in `fast-kit` and that `DATABASE_URL` points to the target DB on port `5435`.

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
- The harness is intentionally self-contained so anyone with access to the three repos can reproduce it.
