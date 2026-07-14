# Elite4Print Rebuild: Migration & Admin Proof-of-Concept Methodology

## Goal
Give the team empirical, side-by-side data to decide between `fast-kit` (FastAPI) and `django-init` (Django) for rebuilding Elite4Print.

## Scope (the slice Murad defined)

1. **Modules:** `product_management`, `order_management` (orders + items), `payment_management`, plus `customer` and `coupon` links.
2. **Data:** one recent month of orders from a sanitized copy of the legacy DB.
3. **Checks:**
   - Effort / LOC to model the schema and read legacy data.
   - Financial reconciliation to the cent (order totals, payments, refunds, coupons).
   - Row counts match.
   - Referential integrity holds.

## Scoring Criteria

| # | Criterion | Weight | Why it matters |
|---|-----------|--------|----------------|
| 1 | Migration fit against real Elite4Print data | 25% | Highest-risk cutover activity. |
| 2 | Admin back-office out of the box | 20% | Team size makes hand-building admin expensive. |
| 3 | Boundary enforcement / loose coupling | 20% | Primary reason for the rebuild. |
| 4 | Testability & in-memory tests | 10% | Speed and safety of future changes. |
| 5 | Lines of code for the same slice | 10% | Proxy for maintenance cost. |
| 6 | Operational stack simplicity | 10% | Day-2 running cost. |
| 7 | LLM-assisted development speed | 5% | How the team plans to work. |

### Scoring Rubric

- **5** — Clear advantage, low risk, minimal compromise.
- **4** — Good fit, minor concerns.
- **3** — Acceptable but requires trade-offs or extra work.
- **2** — Significant extra effort or risk.
- **1** — Major blocker or mismatch.

## Test Harness

This directory contains:

- `legacy_source/` — Minimal Django project that recreates the Elite4Print slice schema and seeds representative data.
- `django_target/` — Extension of `django-init` with product/payment/coupon modules and a management command to migrate from the legacy DB.
- `fastapi_target/` — Extension of `fast-kit` with product/payment/coupon modules and a script to migrate from the legacy DB.
- `reconcile/` — Shared reconciliation scripts that compare source and target financials, row counts, and referential integrity.
- `docker-compose.yml` — PostgreSQL source and target databases.
- `Makefile` — Commands to seed, migrate, reconcile, and report.

## Keeping It Fair

- Compare against the clean Django pattern (ORM-direct / managers-as-repository), not the old codebase.
- Use the same legacy data for both targets.
- Measure the same artifacts in both kits.
- For FastAPI admin, document honestly what must be hand-built or bought.
