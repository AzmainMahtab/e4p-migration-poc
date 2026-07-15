# Elite4Print Migration Comparison Harness

A reproducible, side-by-side proof-of-concept for rebuilding the Elite4Print backend. It migrates the same real-world data slice into two boilerplates and reconciles the results.

- **fast-kit** — FastAPI + SQLAlchemy + Alembic (clean architecture / modular monolith)
- **django-kit** — Django + DRF + Celery (modular monolith)

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
├── django-kit/                     # branch: poc/e4p-migration-comparison
├── fast-kit/                       # branch: poc/e4p-migration-comparison
└── e4p-migration-poc/              # this repo
```

## Prerequisites

- Docker + Docker Compose
- **[uv](https://docs.astral.sh/uv/)** package manager (installs the right Python version automatically)
- Access to the three repositories:
  - `https://github.com/AzmainMahtab/e4p-migration-poc.git`
  - `https://github.com/AzmainMahtab/django-kit.git`
  - `https://github.com/AzmainMahtab/fast-kit.git`

## Setup

### 1. Clone the three repositories side by side

> **Important:** the POC changes in `django-kit` and `fast-kit` live on the branch `poc/e4p-migration-comparison`, not on `main`. Clone that branch directly.

```bash
mkdir elite4print-rebuild && cd elite4print-rebuild
git clone https://github.com/AzmainMahtab/e4p-migration-poc.git
git clone --branch poc/e4p-migration-comparison https://github.com/AzmainMahtab/django-kit.git
git clone --branch poc/e4p-migration-comparison https://github.com/AzmainMahtab/fast-kit.git
```

If you already cloned without the branch flag, switch branches:

```bash
cd django-kit && git checkout poc/e4p-migration-comparison && cd ..
cd fast-kit && git checkout poc/e4p-migration-comparison && cd ..
```

### 2. Install uv

Both boilerplates use **[uv](https://docs.astral.sh/uv/)** for reproducible dependency management. If you don't have it yet, install it:

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then verify:
```bash
uv --version
```

### 3. Set up the boilerplate virtual environments

```bash
cd django-kit && uv sync && cd ..
cd fast-kit && uv sync && cd ..
```

This creates `.venv/` in each repo and installs the exact locked versions from their `uv.lock` files. The locks include binary wheels where available (e.g. `psycopg[binary]`, `asyncpg`), so no system PostgreSQL development libraries are required.

> The commands below assume the recommended directory structure. If you cloned to different paths, replace `../django-kit` and `../fast-kit` accordingly.

## Quick start

All commands below are run from inside `e4p-migration-poc/`.

> **Dockerization note:** the three PostgreSQL databases are Dockerized via `docker-compose.yml`. The migration and reconciliation scripts run on the host using `uv` (they connect to the exposed container ports `5433`, `5434`, and `5435`).

### 1. Start the databases

```bash
cd e4p-migration-poc
docker compose up -d
```

This starts three PostgreSQL containers on localhost:

| Service | Port | Database | Purpose |
|---------|------|----------|---------|
| `legacy_db` | `5433` | `e4p_legacy` | Source data |
| `django_target_db` | `5434` | `e4p_django` | django-kit target |
| `fastapi_target_db` | `5435` | `e4p_fastapi` | fast-kit target |

The legacy DB starts empty. For the real-data workflow, restore the bundled dump next. For the old synthetic workflow, use `legacy_source/schema.sql` + `seed.sql` instead.

### 2. Restore the real dev dump

```bash
make restore-real
```

This restores `backups/e4p_dev_from_prod_real.dump` (tracked in the repo) into the `legacy_db` container.

### 3. (Optional) Regenerate seed data

```bash
python legacy_source/generate_seed.py
```

Then restart the legacy DB to reload:

```bash
docker compose down -v && docker compose up -d
```

### 4. Migrate the Django target

```bash
cd ../django-kit

# Apply migrations
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  uv run python backend/manage.py migrate

# Migrate the Elite4Print slice
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  LEGACY_DATABASE_URL=postgresql://e4p:e4p@localhost:5433/e4p_legacy \
  uv run python backend/manage.py migrate_e4p_slice
```

### 5. Migrate the FastAPI target

```bash
cd ../fast-kit

# Apply Alembic migrations
DATABASE_URL=postgresql+asyncpg://e4p:e4p@localhost:5435/e4p_fastapi \
  uv run alembic upgrade head

# Run the migration script
cd ../e4p-migration-poc
uv run --project ../fast-kit python fastapi_target/migrate.py
```

### 6. Reconcile

```bash
cd ../e4p-migration-poc
uv run --project ../django-kit python reconcile/reconcile.py
```

Expected output: `RESULT: ALL CHECKS PASS` with matching row counts and financial totals.

## Using the Makefile

A `Makefile` is provided for convenience. From `e4p-migration-poc/`:

```bash
make up            # docker compose up -d
make down          # docker compose down
make reset         # destroy volumes and start fresh
make restore-real  # restore real dev dump into legacy_db
make seed          # regenerate seed.sql
make migrate-dj    # migrate Django target
make migrate-fa    # migrate FastAPI target
make reconcile     # run reconciliation
```

Run `make help` for the full list.

## What the reconciliation checks

`reconcile/reconcile.py` compares the source, Django, and FastAPI databases:

- **Row counts** — users, product categories, products, orders, jobs, job memos, payments, pending refunds, coupons, coupon usages.
- **Financial totals** — orders total/final/discount/tax/shipping, payments, pending refunds, jobs price.
- **Referential integrity** — jobs without orders, payments without orders, refunds without payments.

## Inspecting the Django admin

The django-kit POC registers admin classes for the slice.

```bash
cd ../django-kit

# Promote an existing migrated user to superuser
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  uv run python backend/manage.py shell -c "
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
  uv run python backend/manage.py check
```

Then run the dev server:

```bash
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p \
  POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  uv run python backend/manage.py runserver
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

Make sure both boilerplate environments are synced with uv:

```bash
cd ../django-kit && uv sync   # provides psycopg[binary] for reconcile.py
cd ../fast-kit && uv sync      # provides asyncpg for fastapi_target/migrate.py
```

### Django migration complains about missing dependencies

Make sure you are on the `poc/e4p-migration-comparison` branch in `django-kit` and have run `uv sync`.

### FastAPI Alembic migration fails

Make sure you are on the `poc/e4p-migration-comparison` branch in `fast-kit`, have run `uv sync`, and that `DATABASE_URL` points to the target DB on port `5435`.

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
- The real Elite4Print dev dump is bundled at `backups/e4p_dev_from_prod_real.dump` (tracked in git). Use `make restore-real` to load it.
- The harness is intentionally self-contained so anyone with access to the three repos can reproduce it.
