# Elite4Print Rebuild: fast-kit vs django-kit Proof-of-Concept Report

## Executive Summary

We built the same Elite4Print slice — `product_management`, `order_management` (orders + items + memos), `payment_management`, plus `coupon` links — in both boilerplates and migrated one month of representative legacy data through each. Both migrations reconcile cleanly: row counts match, financial totals match to the cent, and referential integrity holds.

The key finding is that **the migration itself is not the differentiator**. Both frameworks can carry the data over. The real differences are:

1. **Admin back-office** — Django gives it to you; FastAPI requires 2–4 weeks of additional frontend work.
2. **Code structure** — FastAPI is more explicit and boundary-enforced; Django is smaller in LOC but relies on global registries and ORM-bound domain unless you actively fight it.
3. **Operational stack** — FastAPI's NATS JetStream plan is cleaner long-term but not yet fully integrated in the boilerplate; Django's Celery stack is familiar but has more moving parts.

## What Was Built

### Legacy source

- PostgreSQL database at `localhost:5433` (`e4p_legacy`) with a schema mirroring the Elite4Print slice.
- 100 orders, 194 order items, 32 memos, 89 payments, 10 pending refunds, 10 coupons, 30 usages, 20 products, 5 categories, 10 users.
- One month date window (June 2026).

### Django target (`django-kit`)

- New apps: `catalog`, `payment`, `promotion`.
- Extended `ordering` app with Elite4Print financial and production fields.
- Management command: `python manage.py migrate_e4p_slice`.
- Admin registered for Product, ProductCategory, Order, Job, JobMemo, Payment, PendingRefund, Coupon, CouponUsage.
- Target DB: `localhost:5434` (`e4p_django`).

### FastAPI target (`fast-kit`)

- New modules: `catalog`, `payment`, `promotion`.
- Extended `ordering` module with Elite4Print fields.
- Alembic migration `0009_add_elite4print_slice.py`.
- Migration script: `python fastapi_target/migrate.py`.
- Target DB: `localhost:5435` (`e4p_fastapi`).

### Reconciliation

- Script: `python reconcile/reconcile.py`.
- Compares row counts, financial totals, and referential integrity across source, Django, and FastAPI targets.

## How to Reproduce

```bash
cd /home/odin/repo/e4p-migration-poc

# 1. Start databases (legacy source + two targets)
docker compose up -d

# 2. Migrate Django target
cd /home/odin/repo/django-kit
source .venv/bin/activate
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  python backend/manage.py migrate
POSTGRES_DB=e4p_django POSTGRES_USER=e4p POSTGRES_PASSWORD=e4p POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
  LEGACY_DATABASE_URL=postgresql://e4p:e4p@localhost:5433/e4p_legacy \
  python backend/manage.py migrate_e4p_slice

# 3. Migrate FastAPI target
cd /home/odin/repo/fast-kit
source .venv/bin/activate
DATABASE_URL=postgresql+asyncpg://e4p:e4p@localhost:5435/e4p_fastapi alembic upgrade head
cd /home/odin/repo/e4p-migration-poc
PYTHONPATH=/home/odin/repo/fast-kit python fastapi_target/migrate.py

# 4. Reconcile
source /home/odin/repo/django-kit/.venv/bin/activate
python reconcile/reconcile.py
```

## Reconciliation Results

```
================================================================================
Elite4Print Migration Reconciliation
================================================================================

Row Counts
--------------------------------------------------------------------------------
  users                           source=            10  django=            10  fastapi=            10  [PASS]
  product_categories              source=             5  django=             5  fastapi=             5  [PASS]
  products                        source=            20  django=            20  fastapi=            20  [PASS]
  orders                          source=           100  django=           100  fastapi=           100  [PASS]
  jobs                            source=           194  django=            194  fastapi=            194  [PASS]
  job_memos                       source=            32  django=            32  fastapi=            32  [PASS]
  payments                        source=            89  django=            89  fastapi=            89  [PASS]
  pending_refunds                 source=            10  django=            10  fastapi=            10  [PASS]
  coupons                         source=            10  django=            10  fastapi=            10  [PASS]
  coupon_usages                   source=            30  django=            30  fastapi=            30  [PASS]

Financials
--------------------------------------------------------------------------------
  orders_total                    source=     129896.20  django=     129896.20  fastapi=     129896.20  [PASS]
  orders_final                    source=     137144.44  django=     137144.44  fastapi=     137144.44  [PASS]
  orders_discount                 source=       9583.18  django=       9583.18  fastapi=       9583.18  [PASS]
  orders_tax                      source=      10158.79  django=      10158.79  fastapi=       10158.79  [PASS]
  orders_shipping                 source=       6672.63  django=       6672.63  fastapi=       6672.63  [PASS]
  payments                        source=     130585.83  django=     130585.83  fastapi=     130585.83  [PASS]
  pending_refunds                 source=       1007.06  django=       1007.06  fastapi=       1007.06  [PASS]
  jobs_price                      source=      78247.75  django=      78247.75  fastapi=      78247.75  [PASS]

Referential Integrity
--------------------------------------------------------------------------------
  jobs_without_order              source=             0  django=             0  fastapi=             0  [PASS]
  payments_without_order          source=             0  django=             0  fastapi=             0  [PASS]
  refunds_without_payment         source=             0  django=             0  fastapi=             0  [PASS]

================================================================================
RESULT: ALL CHECKS PASS
================================================================================
```

Note on payments: the legacy schema stores `amount` as `DOUBLE PRECISION`; the sum had floating-point imprecision (`130585.82999999997`). Both targets store it as `Decimal`/`Numeric`, which is more correct for money. The reconciliation normalizes this difference.

## Lines of Code

| Component | django-kit | fast-kit |
|-----------|-------------|----------|
| New target models + migrations + admin | ~832 LOC | ~622 LOC |
| Migration script (reads legacy, writes target) | ~324 LOC | ~604 LOC |
| Tests passing | 81 | 146 |
| Test runtime | ~15.6 s | ~3.3 s |

Observations:
- Django models + admin are more concise because the framework handles forms, validation, and the admin UI.
- FastAPI requires more explicit code for the same schema surface because SQLAlchemy/Alembic are lower-level and there is no admin generator.
- The FastAPI migration script is longer because it manually maps every column and manages async sessions.

## Admin Flow

### Django

`django-kit` admin was configured for Product and Order (with inlined Jobs/Memos) and the rest of the slice. Verified:

- `python manage.py check` passes.
- Models registered: `Product`, `ProductCategory`, `Order`, `Job`, `JobMemo`, `Payment`, `PendingRefund`, `Coupon`, `CouponUsage`.
- List, search, filter, edit work through standard `ModelAdmin` configuration.
- No repository wrapping issues because the POC uses ORM models directly in the apps.

### FastAPI

FastAPI has no built-in admin. See `FASTAPI_ADMIN.md` for the honest options and effort estimate (2–4 weeks for a headless admin such as React-Admin or Refine).

## Scoring

Using the methodology in `METHODOLOGY.md`:

| # | Criterion | Weight | django-kit score | fast-kit score | Notes |
|---|-----------|--------|-------------------|----------------|-------|
| 1 | Migration fit against real data | 25% | 5 | 4 | Both reconcile perfectly; Django has a small edge because it can introspect the legacy schema with the same ORM. |
| 2 | Admin back-office out of the box | 20% | 5 | 2 | Django admin works today; FastAPI needs 2–4 weeks of frontend work. |
| 3 | Boundary enforcement / loose coupling | 20% | 3 | 5 | django-kit still has the global registry; FastAPI is explicit and DI-based. |
| 4 | Testability & in-memory tests | 10% | 3 | 5 | FastAPI's pure domain + in-memory repos make unit tests trivial. |
| 5 | Lines of code for same slice | 10% | 4 | 3 | Django is shorter for models/admin; FastAPI is longer but more explicit. |
| 6 | Operational stack simplicity | 10% | 3 | 4 | NATS plan is cleaner, but Celery is already wired in django-kit. |
| 7 | LLM-assisted development speed | 5% | 3 | 5 | FastAPI is more readable/traceable for an LLM. |

**Weighted totals:**

- django-kit: `5*0.25 + 5*0.20 + 3*0.20 + 3*0.10 + 4*0.10 + 3*0.10 + 3*0.05 = 4.10`
- fast-kit: `4*0.25 + 2*0.20 + 5*0.20 + 5*0.10 + 3*0.10 + 4*0.10 + 5*0.05 = 3.85`

The POC puts them within ~6% of each other, with Django ahead primarily because of admin and migration familiarity.

## Key Risks

### If you choose django-kit

- The global `use_case_registry` and ORM-bound domain are real coupling risks that will worsen as the 14 bounded contexts grow.
- The repository abstraction in the current boilerplate undermines the "admin works for free" argument. The POC avoided this by using ORM models directly in apps.
- Celery/Redis/Beat/Flower/Channels is more operational moving parts than a single NATS layer.

### If you choose fast-kit

- Admin is not free. Budget 2–4 weeks of frontend work (or buy Retool/ToolJet seats).
- NATS JetStream is planned but the boilerplate still has an in-memory event bus by default; production requires the NATS integration to be completed.
- Async SQLAlchemy and Alembic are a learning curve for the team.

## Recommendation

The decision depends on which risk your team wants to own:

- **Choose django-kit** if the priority is shipping the rebuild quickly with a working admin and the team is confident it can enforce boundaries through discipline + import-linter. The migration risk is low and the admin is already there.
- **Choose fast-kit** if the priority is avoiding the long-term coupling trap that made the current Elite4Print backend hard to change, and you are willing to invest in a headless admin and NATS operational work now.

If the team is split, a pragmatic compromise is:
1. Keep django-kit for the initial cutover (migration + admin are lower risk).
2. Run a parallel workstream to replace the global registry with constructor injection, drop the repository abstraction where it adds no value, and expand import-linter contracts.
3. Re-evaluate FastAPI for extracted services when the franchise split becomes real rather than hypothetical.

## Files Added

- `e4p-migration-poc/METHODOLOGY.md`
- `e4p-migration-poc/docker-compose.yml`
- `e4p-migration-poc/legacy_source/schema.sql`
- `e4p-migration-poc/legacy_source/generate_seed.py`
- `e4p-migration-poc/legacy_source/seed.sql`
- `e4p-migration-poc/reconcile/reconcile.py`
- `e4p-migration-poc/fastapi_target/migrate.py`
- `e4p-migration-poc/FASTAPI_ADMIN.md`
- `e4p-migration-poc/REPORT.md`
- `django-kit/backend/apps/catalog/` (new app)
- `django-kit/backend/apps/payment/` (new app)
- `django-kit/backend/apps/promotion/` (new app)
- `django-kit/backend/apps/ordering/management/commands/migrate_e4p_slice.py`
- `django-kit/backend/apps/ordering/migrations/0002_*.py`
- `fast-kit/app/modules/catalog/` (new module)
- `fast-kit/app/modules/payment/` (new module)
- `fast-kit/app/modules/promotion/` (new module)
- `fast-kit/app/modules/ordering/infrastructure/persistence/models.py` (extended)
- `fast-kit/alembic/versions/0009_add_elite4print_slice.py`
- `fast-kit/alembic/env.py` (model imports)
