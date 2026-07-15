# Elite4Print Migration Comparison — Real Dev DB (V2)

**Prepared for:** Murad / Potential team  
**Date:** July 15, 2026  
**Slice:** product_management, order_management (orders + items), payment_management, plus customer and coupon links  
**Data source:** real `e4p_dev_from_prod` PostgreSQL dump (not synthetic seed data)

---

## 1. What changed vs. the first POC

The first POC used a hand-written `schema.sql` + `seed.sql` with ~100 orders. This run uses the actual dev database:

| | POC (seed) | V2 (real DB) |
|---|---|---|
| Orders | 100 | 278,057 |
| Order items | 194 | 346,528 |
| Payments | 89 | 10,760 |
| Users | 10 | 13,624 |
| Source | synthetic | `e4p_dev_from_prod` dump |

The dump file is stored in `backups/e4p_dev_from_prod_real.dump` (tracked in git) and restored into the local `legacy_db` container with `make restore-real`.

---

## 2. Realities we had to adapt to

### 2.1 Users are UUIDs, not integers
`authentications_user.id` in the real DB is `uuid`, while the target boilerplates use integer user PKs. Rather than remapping UUIDs to synthetic integers (which would break the “1:1 of the real dump” requirement), we:

- Added a `legacy_id` UUID column to the target `users` table.
- Changed all user-facing FKs in the slice (`orders.user_id`, `products.created_by_id`, `payments.user_id`, `coupon_usages.user_id`) to reference `users.legacy_id`.
- Migrated the source UUID straight into `legacy_id` so relationships are preserved exactly.

### 2.2 Bulk inserts required
The row counts are too large for row-by-row `INSERT` or `update_or_create`. Both targets were switched to bulk insert:

- **Django:** `bulk_create(..., batch_size=5000)`.
- **FastAPI:** `asyncpg.executemany(...)` with 5,000-row chunks.
- FK trigger checks were disabled during the FastAPI load (`session_replication_role = replica`) to keep the insert fast; the data is internally consistent.

### 2.3 Data quality issues
`pg_restore` logged ~129 FK errors on non-slice tables (orphan records, type mismatches in Django admin log, etc.). This is exactly the contamination Isaac described in the client follow-up. The slice tables themselves restored cleanly and reconciled.

### 2.4 Minor source/target type mismatches
- `payment_management_payment.amount` is `DOUBLE PRECISION`; targets store `Numeric` — we round to 2 decimals.
- `order_management_orderitemmemo.note` exceeded 255 chars in some rows; truncated on import.

---

## 3. Migration results

### 3.1 Row counts — all match

| Table | Source | Django | FastAPI |
|---|---:|---:|---:|
| users | 13,624 | 13,624 | 13,624 |
| product_categories | 45 | 45 | 45 |
| products | 43 | 43 | 43 |
| orders | 278,057 | 278,057 | 278,057 |
| jobs | 346,528 | 346,528 | 346,528 |
| job_memos | 3,892 | 3,892 | 3,892 |
| payments | 10,760 | 10,760 | 10,760 |
| pending_refunds | 238 | 238 | 238 |
| coupons | 9 | 9 | 9 |
| coupon_products | 222 | 222 | 222 |
| coupon_usages | 4 | 4 | 4 |

### 3.2 Financial reconciliation — all match to the cent

| Check | Source | Django | FastAPI |
|---|---:|---:|---:|
| orders_total | 67,987,560.38 | 67,987,560.38 | 67,987,560.38 |
| orders_final | 69,872,971.77 | 69,872,971.77 | 69,872,971.77 |
| orders_discount | 26,034.67 | 26,034.67 | 26,034.67 |
| orders_tax | 9,187.02 | 9,187.02 | 9,187.02 |
| orders_shipping | 798,824.84 | 798,824.84 | 798,824.84 |
| payments | 29,344,616.27 | 29,344,616.27 | 29,344,616.27 |
| pending_refunds | 18,803.06 | 18,803.06 | 18,803.06 |
| jobs_price | 65,032,422.03 | 65,032,422.03 | 65,032,422.03 |

### 3.3 Referential integrity — all pass

- jobs without order: 0 in all three DBs
- payments without order: 0 in all three DBs
- refunds without payment: 0 in all three DBs

**Reconciliation output:** `RESULT: ALL CHECKS PASS`

### 3.4 Model vs. real-data consistency verdict

We compared the source legacy schema against the django-kit and fast-kit target models to confirm the migrated data actually fits.

**Field coverage:** both targets cover every field imported by the migration scripts. The following legacy fields were intentionally omitted because they are not needed for the slice:

- `product_management_productcategory`: `category_code`, `thumbnail`, `created_by_id`, `parent_id`, `is_active`, `description`
- `product_management_product`: `thumbnail`, `large_format_production_method`
- `order_management_orderitems`: `json_file`, `round_corner_selection`, `catalog_base_price`
- `payment_management_pendingrefund`: `order_item_id`

**Data-shape checks:** the real data fits the target column widths and types:

| Field | Source max | Target width | Result |
|---|---|---|---|
| `order_id` / `order_number` | 15 chars | 32 chars | fits |
| `job_id` | 15 chars | 32 chars | fits |
| `username` | 36 chars | 50 chars (fast-kit) / 150 chars (django-kit) | fits |
| `email` | 53 chars | 255 chars | fits |
| `phone_number` | 31 chars | 32 chars (django-kit) / generated 20-char (fast-kit) | fits |
| `product_id` / `product_code` | 13 chars | 255 chars | fits |
| `coupon_code` | 13 chars | 50 chars | fits |

**Nullability:** all source rows provide the non-null values the targets require (`orders.user_id`, `products.created_by_id`, `coupon_usages.user_id`, etc.). Nullable source columns that are mostly null (e.g. `orderitems.product_id` has 329,879 nulls, `pendingrefund.order_item_id` has 234 nulls) map to nullable target columns.

**Known truncation:** `order_management_orderitemmemo.note` is unbounded in the source; the longest value is 318 characters. Both targets store it as `varchar(255)`, and the migration scripts truncate on import. This is the only data-shape loss in the slice, and it does not affect reconciliation.

**UUID bridge pattern:** the real `authentications_user.id` is `uuid`. Both targets keep an internal integer PK and store the legacy UUID in `users.legacy_id`. All user-facing FKs in the slice (`orders.user_id`, `products.created_by_id`, `payments.user_id`, `coupon_usages.user_id`) reference `users.legacy_id`, preserving the original relationships exactly.

**Verdict:** both django-kit and fast-kit models are sufficient to accommodate the real migrated data. The reconciliation passes, and the only intentional data loss is the `note` truncation described above.

---

## 4. Performance comparison

| Kit | Total rows migrated | Elapsed time |
|---|---|---:|
| Django | 653,422 | ~61 s |
| FastAPI | 653,422 | ~26 s |

FastAPI is roughly **2.3–2.6x faster** for the bulk load, largely because `asyncpg.executemany` and disabling FK triggers are very efficient for this shape. Django is still comfortably fast for a one-off migration.

---

## 5. Code/effort comparison

### 5.1 Migration script LOC

| Surface | Django | FastAPI |
|---|---:|---:|
| Migration script (final) | 413 | 722 |
| Schema/model changes for UUID mapping | 33 lines changed | 75 lines changed |

The Django script is shorter because Django ORM `bulk_create` handles batching, SQL generation, and type coercion. The FastAPI script is longer because it builds raw SQL `executemany` calls, chunking, and explicit value normalization.

### 5.2 What each side needed

| Requirement | Django | FastAPI |
|---|---|---|
| Preserve UUID users | Add `legacy_id` to `User`; change `user_id` fields to `UUIDField` | Add `legacy_id` to `UserModel`; change FK columns to `UUID` |
| Bulk load | `bulk_create(batch_size=5000)` | `asyncpg.executemany` + chunking |
| Coupon-product M2M | Added `CouponProduct` model | Already existed |
| Run time | ~61 s | ~26 s |

---

## 6. Implications for the architecture decision

### 6.1 Migration risk
Both frameworks cleanly migrated the full real-data slice. The risk is not the migration itself; it is the **schema mapping effort** and the **legacy data quality** (orphan FKs, type mismatches, stale data). Both kits require similar schema adaptation work.

### 6.2 Admin remains a differentiator
This test did not change the admin finding from the first POC: Django admin works out of the box; FastAPI still needs a hand-built or third-party back-office.

### 6.3 Performance
FastAPI is materially faster at bulk data loading. For a one-time migration this is not a blocker, but it matters if we plan to run incremental syncs or large ETL pipelines in V2.

### 6.4 UUID handling
The real dump confirmed that **user IDs are UUIDs**. Whichever stack is chosen needs a clean pattern for legacy UUIDs. We solved it with a `legacy_id` bridge column, which keeps the internal integer PK and avoids rewriting RBAC/permissions internals.

---

## 7. Recommendation

The real-data migration does not change the original recommendation: it is still a **trade-off between speed of delivery (Django) and long-term decoupling (FastAPI)**.

- If the priority is **shipping the rebuild quickly with a working back-office**, Django remains lower risk.
- If the priority is **long-term maintainability, explicit boundaries, and faster bulk operations**, FastAPI is the stronger foundation.

The migration itself is not the deciding factor — both handle it cleanly.

---

## 8. Reproducing this run

```bash
cd e4p-migration-poc

# Start databases
make up

# Restore the real dump
make restore-real

# FastAPI target
make migrate-fa

# Django target
make migrate-dj

# Reconcile
make reconcile
```

The dump file is at `backups/e4p_dev_from_prod_real.dump` and is tracked in the repo.

---

## 9. Attachments / artifacts

- `backups/e4p_dev_from_prod_real.dump` — full dev DB dump
- `fastapi_target/migrate.py` — updated FastAPI bulk migration script
- `django-kit/backend/apps/ordering/management/commands/migrate_e4p_slice.py` — updated Django bulk migration command
- `reconcile/reconcile.py` — updated reconciliation script (includes `coupon_products`)
- `Makefile` — added `restore-real` target

(End of report)
