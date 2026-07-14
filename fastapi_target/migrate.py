#!/usr/bin/env python3
"""Migrate the Elite4Print slice from the legacy DB to the fast-kit target DB.

Run from /home/odin/repo/e4p-migration-poc with fast-kit's virtual environment
activated (asyncpg is the only third-party dependency):

    cd /home/odin/repo/e4p-migration-poc
    source /home/odin/repo/fast-kit/.venv/bin/activate
    python fastapi_target/migrate.py

Or use the venv interpreter directly:

    /home/odin/repo/fast-kit/.venv/bin/python fastapi_target/migrate.py

The script preserves legacy integer IDs where the target schema allows it.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import asyncpg

SOURCE_DSN = os.getenv(
    "E4P_SOURCE_DSN",
    "postgresql://e4p:e4p@localhost:5433/e4p_legacy",
)
TARGET_DSN = os.getenv(
    "E4P_TARGET_DSN",
    "postgresql://e4p:e4p@localhost:5435/e4p_fastapi",
)


@dataclass
class MigrationCounts:
    users: int = 0
    product_categories: int = 0
    products: int = 0
    orders: int = 0
    jobs: int = 0
    job_memos: int = 0
    payments: int = 0
    pending_refunds: int = 0
    coupons: int = 0
    coupon_products: int = 0
    coupon_usages: int = 0

    def total(self) -> int:
        return sum(vars(self).values())


def _adapt(value: Any) -> Any:
    """Normalize legacy values for asyncpg insertion."""
    if isinstance(value, Decimal):
        return float(value)
    if value is None:
        return None
    return value


def _row(record: asyncpg.Record, columns: list[str]) -> tuple[Any, ...]:
    return tuple(_adapt(record[c]) for c in columns)


async def _reset_target(conn: asyncpg.Connection) -> None:
    """Truncate Elite4Print slice tables in dependency order."""
    tables = [
        "coupon_usages",
        "coupon_products",
        "coupons",
        "pending_refunds",
        "payments",
        "job_memos",
        "jobs",
        "orders",
        "products",
        "product_categories",
        # Users are intentionally truncated last because other modules may
        # reference them, but for this slice migration we reload them too.
        "users",
    ]
    for table in tables:
        await conn.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')


async def _migrate_users(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
    rows = await source.fetch(
        """
        SELECT id, password, last_login, is_superuser, email,
               is_staff, is_active, created_at, updated_at
        FROM authentications_user
        ORDER BY id
        """
    )
    if not rows:
        return 0

    # The fast-kit users table requires phone_number and username.  Legacy users
    # do not have these, so we synthesize deterministic values.
    inserted = 0
    for record in rows:
        user_id = record["id"]
        username = f"legacy_user_{user_id}"
        phone_number = f"+1000000000{user_id:02d}"
        await target.execute(
            """
            INSERT INTO users (
                id, uuid, email, hashed_password, phone_number, username,
                status, is_superuser, created_at, updated_at, deleted_at
            ) VALUES (
                $1, uuid_generate_v7(), $2, $3, $4, $5,
                'active', $6, $7, $8, NULL
            )
            """,
            user_id,
            record["email"],
            record["password"],
            phone_number,
            username,
            record["is_superuser"],
            record["created_at"],
            record["updated_at"],
        )
        inserted += 1
    return inserted


async def _migrate_product_categories(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        "SELECT id, name, created_at, updated_at FROM product_management_productcategory ORDER BY id"
    )
    cols = ["id", "name", "created_at", "updated_at"]
    await target.executemany(
        f"""
        INSERT INTO product_categories ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        [_row(r, cols) for r in rows],
    )
    return len(rows)


async def _migrate_products(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, category_id, name, description, product_id, created_by_id,
               product_type, min_price, max_price, sqr_ft_price, shop_rate_per_hr,
               is_active, on_draft, base_turnaround, combined_shipping, ordering,
               show_faq, shipping_type, created_at, updated_at
        FROM product_management_product
        ORDER BY id
        """
    )
    cols = [
        "id",
        "category_id",
        "name",
        "description",
        "product_id",
        "created_by_id",
        "product_type",
        "min_price",
        "max_price",
        "sqr_ft_price",
        "shop_rate_per_hr",
        "is_active",
        "on_draft",
        "base_turnaround",
        "combined_shipping",
        "ordering",
        "show_faq",
        "shipping_type",
        "created_at",
        "updated_at",
    ]
    await target.executemany(
        f"""
        INSERT INTO products ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        [_row(r, cols) for r in rows],
    )
    return len(rows)


async def _migrate_orders(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, user_id, total_price, total_shipping_price, final_price,
               discount_amount, payment_status, extra_payment, tax_amount,
               is_additional_payment_paid, original_total_price, original_shipping_price,
               original_tax_amount, points_used, total_adjustment_amount,
               total_refunded_amount, order_id, order_ref, created_at, updated_at
        FROM order_management_order
        ORDER BY id
        """
    )
    # Map legacy order_id -> order_number, payment_status -> explicit column.
    inserted = 0
    for record in rows:
        await target.execute(
            """
            INSERT INTO orders (
                id, order_number, user_id, status, total_price,
                total_shipping_price, final_price, discount_amount, payment_status,
                extra_payment, tax_amount, is_additional_payment_paid,
                original_total_price, original_shipping_price, original_tax_amount,
                points_used, total_adjustment_amount, total_refunded_amount,
                order_ref, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                      $13, $14, $15, $16, $17, $18, $19, $20, $21)
            """,
            record["id"],
            record["order_id"],
            record["user_id"],
            "PENDING",
            float(record["total_price"]),
            float(record["total_shipping_price"]),
            float(record["final_price"]),
            float(record["discount_amount"]),
            record["payment_status"],
            float(record["extra_payment"]),
            float(record["tax_amount"]),
            record["is_additional_payment_paid"],
            float(record["original_total_price"]),
            float(record["original_shipping_price"]),
            float(record["original_tax_amount"]),
            record["points_used"],
            float(record["total_adjustment_amount"]),
            float(record["total_refunded_amount"]),
            record["order_ref"] or {},
            record["created_at"],
            record["updated_at"],
        )
        inserted += 1
    return inserted


async def _migrate_jobs(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, order_id, job_id, job_name, job_status, group_id,
               process_status, product_id, item_code, paper, size, quantity,
               coating, color, trim_size, price, original_price, notes,
               admin_notes, turnaround, turnaround_day, due_date, cut_off_time,
               file_editable, shipping_editable, pickup_location, created_at, updated_at
        FROM order_management_orderitems
        ORDER BY id
        """
    )
    inserted = 0
    for record in rows:
        await target.execute(
            """
            INSERT INTO jobs (
                id, order_id, job_id, job_name, job_status, group_id,
                process_status, product_id, item_code, paper, size, quantity,
                coating, color, trim_size, price, original_price, notes,
                admin_notes, turnaround, turnaround_day, due_date, cut_off_time,
                file_editable, shipping_editable, pickup_location, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                      $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                      $23, $24, $25, $26, $27, $28)
            """,
            record["id"],
            record["order_id"],
            record["job_id"],
            record["job_name"],
            record["job_status"],
            record["group_id"],
            record["process_status"],
            record["product_id"],
            record["item_code"],
            record["paper"],
            record["size"],
            record["quantity"],
            record["coating"],
            record["color"],
            record["trim_size"],
            float(record["price"]),
            float(record["original_price"]),
            record["notes"],
            record["admin_notes"],
            record["turnaround"],
            record["turnaround_day"],
            record["due_date"],
            record["cut_off_time"],
            record["file_editable"],
            record["shipping_editable"],
            record["pickup_location"],
            record["created_at"],
            record["updated_at"],
        )
        inserted += 1
    return inserted


async def _migrate_job_memos(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, order_item_id AS job_id, note, status, printing_adjustment,
               shipping_adjustment, adjustment_type, total_adjustment,
               created_at, updated_at
        FROM order_management_orderitemmemo
        ORDER BY id
        """
    )
    cols = [
        "id",
        "job_id",
        "note",
        "status",
        "printing_adjustment",
        "shipping_adjustment",
        "adjustment_type",
        "total_adjustment",
        "created_at",
        "updated_at",
    ]
    await target.executemany(
        f"""
        INSERT INTO job_memos ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        [_row(r, cols) for r in rows],
    )
    return len(rows)


async def _migrate_payments(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, amount, status, method, type, trans_id, order_id,
               card_number, job_change_id, transactions_history, user_id,
               created_at, updated_at
        FROM payment_management_payment
        ORDER BY id
        """
    )
    cols = [
        "id",
        "amount",
        "status",
        "method",
        "type",
        "trans_id",
        "order_id",
        "card_number",
        "job_change_id",
        "transactions_history",
        "user_id",
        "created_at",
        "updated_at",
    ]
    await target.executemany(
        f"""
        INSERT INTO payments ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        [_row(r, cols) for r in rows],
    )
    return len(rows)


async def _migrate_pending_refunds(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, order_id, payment_id, amount, card_number, status,
               transaction_id, error_message, retry_count, points,
               created_at, updated_at
        FROM payment_management_pendingrefund
        ORDER BY id
        """
    )
    cols = [
        "id",
        "order_id",
        "payment_id",
        "amount",
        "card_number",
        "status",
        "transaction_id",
        "error_message",
        "retry_count",
        "points",
        "created_at",
        "updated_at",
    ]
    await target.executemany(
        f"""
        INSERT INTO pending_refunds ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        [_row(r, cols) for r in rows],
    )
    return len(rows)


async def _migrate_coupons(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, coupon_code, coupon_on, coupon_type, coupon_value,
               max_discount, coupon_start_date, coupon_expiry_date,
               limit_per_user, limit_per_coupon, coupon_description,
               created_at, updated_at
        FROM coupon_management_coupon
        ORDER BY id
        """
    )
    cols = [
        "id",
        "coupon_code",
        "coupon_on",
        "coupon_type",
        "coupon_value",
        "max_discount",
        "coupon_start_date",
        "coupon_expiry_date",
        "limit_per_user",
        "limit_per_coupon",
        "coupon_description",
        "created_at",
        "updated_at",
    ]
    await target.executemany(
        f"""
        INSERT INTO coupons ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        [_row(r, cols) for r in rows],
    )
    return len(rows)


async def _migrate_coupon_products(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        "SELECT id, coupon_id, product_id FROM coupon_management_coupon_products ORDER BY id"
    )
    cols = ["id", "coupon_id", "product_id", "created_at", "updated_at"]
    now = datetime.now(UTC)
    values = [(r["id"], r["coupon_id"], r["product_id"], now, now) for r in rows]
    await target.executemany(
        f"""
        INSERT INTO coupon_products ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        values,
    )
    return len(rows)


async def _migrate_coupon_usages(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        """
        SELECT id, coupon_id, user_id, order_id, status, created_at, updated_at
        FROM coupon_management_couponusage
        ORDER BY id
        """
    )
    cols = ["id", "coupon_id", "user_id", "order_id", "status", "created_at", "updated_at"]
    await target.executemany(
        f"""
        INSERT INTO coupon_usages ({', '.join(cols)})
        VALUES ({', '.join(f'${i+1}' for i in range(len(cols)))})
        """,
        [_row(r, cols) for r in rows],
    )
    return len(rows)


async def _source_counts(source: asyncpg.Connection) -> dict[str, int]:
    tables = {
        "users": "authentications_user",
        "product_categories": "product_management_productcategory",
        "products": "product_management_product",
        "orders": "order_management_order",
        "jobs": "order_management_orderitems",
        "job_memos": "order_management_orderitemmemo",
        "payments": "payment_management_payment",
        "pending_refunds": "payment_management_pendingrefund",
        "coupons": "coupon_management_coupon",
        "coupon_products": "coupon_management_coupon_products",
        "coupon_usages": "coupon_management_couponusage",
    }
    return {name: await source.fetchval(f"SELECT count(*) FROM {table}") for name, table in tables.items()}


async def _target_counts(target: asyncpg.Connection) -> dict[str, int]:
    tables = [
        "users",
        "product_categories",
        "products",
        "orders",
        "jobs",
        "job_memos",
        "payments",
        "pending_refunds",
        "coupons",
        "coupon_products",
        "coupon_usages",
    ]
    return {name: await target.fetchval(f'SELECT count(*) FROM "{name}"') for name in tables}


async def migrate() -> MigrationCounts:
    source = await asyncpg.connect(SOURCE_DSN)
    target = await asyncpg.connect(TARGET_DSN)
    try:
        print("Resetting target slice tables...")
        await _reset_target(target)

        counts = MigrationCounts()
        print("Migrating users...")
        counts.users = await _migrate_users(source, target)
        print("Migrating product categories...")
        counts.product_categories = await _migrate_product_categories(source, target)
        print("Migrating products...")
        counts.products = await _migrate_products(source, target)
        print("Migrating orders...")
        counts.orders = await _migrate_orders(source, target)
        print("Migrating jobs (order items)...")
        counts.jobs = await _migrate_jobs(source, target)
        print("Migrating job memos...")
        counts.job_memos = await _migrate_job_memos(source, target)
        print("Migrating payments...")
        counts.payments = await _migrate_payments(source, target)
        print("Migrating pending refunds...")
        counts.pending_refunds = await _migrate_pending_refunds(source, target)
        print("Migrating coupons...")
        counts.coupons = await _migrate_coupons(source, target)
        print("Migrating coupon products...")
        counts.coupon_products = await _migrate_coupon_products(source, target)
        print("Migrating coupon usages...")
        counts.coupon_usages = await _migrate_coupon_usages(source, target)

        source_counts = await _source_counts(source)
        target_counts = await _target_counts(target)
        return counts, source_counts, target_counts
    finally:
        await source.close()
        await target.close()


def _print_summary(
    counts: MigrationCounts,
    source_counts: dict[str, int],
    target_counts: dict[str, int],
) -> None:
    print("\n" + "=" * 60)
    print("Migration complete")
    print("=" * 60)
    print(f"{'Table':<22} {'Source':>10} {'Target':>10} {'Migrated':>12}")
    print("-" * 60)
    for name, migrated in vars(counts).items():
        src = source_counts.get(name, 0)
        tgt = target_counts.get(name, 0)
        print(f"{name:<22} {src:>10} {tgt:>10} {migrated:>12}")
    print("-" * 60)
    print(f"{'TOTAL':<22} {sum(source_counts.values()):>10} {sum(target_counts.values()):>10} {counts.total():>12}")
    print("=" * 60)

    mismatches = [
        name
        for name in vars(counts)
        if source_counts.get(name, 0) != target_counts.get(name, 0)
    ]
    if mismatches:
        print("WARNING: row-count mismatch in:", ", ".join(mismatches))
    else:
        print("All source/target row counts match.")


async def main() -> None:
    counts, source_counts, target_counts = await migrate()
    _print_summary(counts, source_counts, target_counts)


if __name__ == "__main__":
    asyncio.run(main())
