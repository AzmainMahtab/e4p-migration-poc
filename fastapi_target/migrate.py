#!/usr/bin/env python3
"""Migrate the Elite4Print slice from the real legacy DB to the fast-kit target DB.

This script is optimized for the real dev dump (~278k orders, ~346k jobs) and
preserves legacy UUIDs in user relationships by writing them into users.legacy_id
and referencing that column from orders, products, payments, and coupon_usages.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

SOURCE_DSN = os.getenv(
    "E4P_SOURCE_DSN",
    "postgresql://e4p:e4p@localhost:5433/e4p_legacy",
)
TARGET_DSN = os.getenv(
    "E4P_TARGET_DSN",
    "postgresql://e4p:e4p@localhost:5435/e4p_fastapi",
)

CHUNK_SIZE = 5_000


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
    elapsed_seconds: float = 0.0

    def total(self) -> int:
        return (
            self.users
            + self.product_categories
            + self.products
            + self.orders
            + self.jobs
            + self.job_memos
            + self.payments
            + self.pending_refunds
            + self.coupons
            + self.coupon_products
            + self.coupon_usages
        )


def _to_decimal(value: Any, places: int = 2) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal(10) ** -places)
    return Decimal(str(value)).quantize(Decimal(10) ** -places)


def _json(value: Any) -> dict | list | None:
    if value is None:
        return None
    return value


def _time(value: Any):
    return value


def _uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


async def _reset_target(conn: asyncpg.Connection) -> None:
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
        "users",
    ]
    for table in tables:
        await conn.execute(f'TRUNCATE TABLE "{table}" CASCADE')


async def _bulk_insert(
    conn: asyncpg.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple[Any, ...]],
    chunk_size: int = CHUNK_SIZE,
) -> int:
    if not rows:
        return 0
    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    sql = f'INSERT INTO "{table}" ({", ".join(columns)}) VALUES ({placeholders})'
    inserted = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        await conn.executemany(sql, chunk)
        inserted += len(chunk)
    return inserted


async def _migrate_users(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
    rows = await source.fetch(
        """
        SELECT id, password, username, email, phone_number, is_superuser,
               is_active, is_staff, date_joined, last_login
        FROM authentications_user
        ORDER BY date_joined, id
        """
    )
    values: list[tuple[Any, ...]] = []
    for r in rows:
        user_id = _uuid(r["id"])
        # Source phone numbers are not unique, but fast-kit requires uniqueness.
        # Generate a deterministic, unique phone number from the legacy UUID.
        username = (r["username"] or r["email"])[:50]
        phone = f"+1{user_id.hex[:18]}"
        status = "active" if r["is_active"] else "pending_verification"
        values.append(
            (
                user_id,
                r["email"],
                r["password"],
                phone,
                username,
                status,
                r["is_superuser"],
                r["date_joined"],
                r["last_login"],
            )
        )

    cols = [
        "legacy_id",
        "email",
        "hashed_password",
        "phone_number",
        "username",
        "status",
        "is_superuser",
        "created_at",
        "updated_at",
    ]
    return await _bulk_insert(target, "users", cols, values)


async def _migrate_product_categories(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        "SELECT id, name, created_at, updated_at FROM product_management_productcategory ORDER BY id"
    )
    values = [(r["id"], r["name"], r["created_at"], r["updated_at"]) for r in rows]
    return await _bulk_insert(
        target, "product_categories", ["id", "name", "created_at", "updated_at"], values
    )


async def _migrate_products(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
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
    values = [
        (
            r["id"],
            r["category_id"],
            r["name"],
            r["description"] or "",
            r["product_id"],
            _uuid(r["created_by_id"]),
            r["product_type"],
            r["min_price"],
            r["max_price"],
            r["sqr_ft_price"],
            r["shop_rate_per_hr"],
            r["is_active"],
            r["on_draft"],
            r["base_turnaround"],
            r["combined_shipping"],
            r["ordering"],
            r["show_faq"],
            r["shipping_type"],
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
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
    return await _bulk_insert(target, "products", cols, values)


async def _migrate_orders(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
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
    values = [
        (
            r["id"],
            r["order_id"],
            _uuid(r["user_id"]),
            r["payment_status"],
            r["total_price"],
            r["total_shipping_price"],
            r["final_price"],
            r["discount_amount"],
            r["payment_status"],
            r["extra_payment"],
            r["tax_amount"],
            r["is_additional_payment_paid"],
            r["original_total_price"],
            r["original_shipping_price"],
            r["original_tax_amount"],
            r["points_used"],
            r["total_adjustment_amount"],
            r["total_refunded_amount"],
            _json(r["order_ref"]) or {},
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
    cols = [
        "id",
        "order_number",
        "user_id",
        "status",
        "total_price",
        "total_shipping_price",
        "final_price",
        "discount_amount",
        "payment_status",
        "extra_payment",
        "tax_amount",
        "is_additional_payment_paid",
        "original_total_price",
        "original_shipping_price",
        "original_tax_amount",
        "points_used",
        "total_adjustment_amount",
        "total_refunded_amount",
        "order_ref",
        "created_at",
        "updated_at",
    ]
    return await _bulk_insert(target, "orders", cols, values)


async def _migrate_jobs(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
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
    values = [
        (
            r["id"],
            r["order_id"],
            r["job_id"],
            r["job_name"],
            r["job_status"],
            r["group_id"],
            r["process_status"],
            r["product_id"],
            r["item_code"],
            r["paper"],
            r["size"],
            r["quantity"],
            r["coating"],
            r["color"],
            r["trim_size"],
            r["price"],
            r["original_price"],
            r["notes"],
            r["admin_notes"],
            r["turnaround"],
            r["turnaround_day"],
            r["due_date"],
            r["cut_off_time"] or datetime.strptime("18:00:00", "%H:%M:%S").time(),
            r["file_editable"],
            r["shipping_editable"],
            r["pickup_location"],
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
    cols = [
        "id",
        "order_id",
        "job_id",
        "job_name",
        "job_status",
        "group_id",
        "process_status",
        "product_id",
        "item_code",
        "paper",
        "size",
        "quantity",
        "coating",
        "color",
        "trim_size",
        "price",
        "original_price",
        "notes",
        "admin_notes",
        "turnaround",
        "turnaround_day",
        "due_date",
        "cut_off_time",
        "file_editable",
        "shipping_editable",
        "pickup_location",
        "created_at",
        "updated_at",
    ]
    return await _bulk_insert(target, "jobs", cols, values)


async def _migrate_job_memos(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
    rows = await source.fetch(
        """
        SELECT id, order_item_id AS job_id, note, status, printing_adjustment,
               shipping_adjustment, adjustment_type, total_adjustment,
               created_at, updated_at
        FROM order_management_orderitemmemo
        ORDER BY id
        """
    )
    values = [
        (
            r["id"],
            r["job_id"],
            (r["note"] or "")[:255],
            r["status"],
            r["printing_adjustment"],
            r["shipping_adjustment"],
            r["adjustment_type"],
            r["total_adjustment"],
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
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
    return await _bulk_insert(target, "job_memos", cols, values)


async def _migrate_payments(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
    rows = await source.fetch(
        """
        SELECT id, amount, status, method, type, trans_id, order_id,
               card_number, job_change_id, transactions_history, user_id,
               created_at, updated_at
        FROM payment_management_payment
        ORDER BY id
        """
    )
    values = [
        (
            r["id"],
            Decimal(str(r["amount"])).quantize(Decimal("0.01")),
            r["status"],
            r["method"],
            r["type"],
            r["trans_id"],
            r["order_id"],
            r["card_number"],
            r["job_change_id"],
            _json(r["transactions_history"]),
            _uuid(r["user_id"]),
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
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
    return await _bulk_insert(target, "payments", cols, values)


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
    values = [
        (
            r["id"],
            r["order_id"],
            r["payment_id"],
            r["amount"],
            r["card_number"],
            r["status"],
            r["transaction_id"],
            r["error_message"],
            r["retry_count"],
            r["points"],
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
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
    return await _bulk_insert(target, "pending_refunds", cols, values)


async def _migrate_coupons(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
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
    values = [
        (
            r["id"],
            r["coupon_code"],
            r["coupon_on"],
            r["coupon_type"],
            Decimal(str(r["coupon_value"])).quantize(Decimal("0.01")),
            Decimal(str(r["max_discount"])).quantize(Decimal("0.01")),
            r["coupon_start_date"],
            r["coupon_expiry_date"],
            r["limit_per_user"],
            r["limit_per_coupon"],
            r["coupon_description"],
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
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
    return await _bulk_insert(target, "coupons", cols, values)


async def _migrate_coupon_products(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> int:
    rows = await source.fetch(
        "SELECT id, coupon_id, product_id FROM coupon_management_coupon_products ORDER BY id"
    )
    now = datetime.now(UTC)
    values = [(r["id"], r["coupon_id"], r["product_id"], now, now) for r in rows]
    return await _bulk_insert(
        target, "coupon_products", ["id", "coupon_id", "product_id", "created_at", "updated_at"], values
    )


async def _migrate_coupon_usages(source: asyncpg.Connection, target: asyncpg.Connection) -> int:
    rows = await source.fetch(
        """
        SELECT id, coupon_id, user_id, order_id, status, created_at, updated_at
        FROM coupon_management_couponusage
        ORDER BY id
        """
    )
    values = [
        (
            r["id"],
            r["coupon_id"],
            _uuid(r["user_id"]),
            r["order_id"],
            r["status"],
            r["created_at"],
            r["updated_at"],
        )
        for r in rows
    ]
    return await _bulk_insert(
        target, "coupon_usages", ["id", "coupon_id", "user_id", "order_id", "status", "created_at", "updated_at"], values
    )


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
    import time

    source = await asyncpg.connect(SOURCE_DSN)
    target = await asyncpg.connect(TARGET_DSN)
    started = time.perf_counter()
    try:
        print("Resetting target slice tables...")
        await _reset_target(target)

        # Disable FK triggers for this session to speed up bulk inserts.
        await target.execute("SET session_replication_role = replica")

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

        await target.execute("SET session_replication_role = DEFAULT")

        source_counts = await _source_counts(source)
        target_counts = await _target_counts(target)
        counts.elapsed_seconds = round(time.perf_counter() - started, 2)
        return counts, source_counts, target_counts
    finally:
        await source.close()
        await target.close()


def _print_summary(
    counts: MigrationCounts,
    source_counts: dict[str, int],
    target_counts: dict[str, int],
) -> None:
    print("\n" + "=" * 70)
    print("Migration complete")
    print("=" * 70)
    print(f"{'Table':<22} {'Source':>10} {'Target':>10} {'Migrated':>12}")
    print("-" * 70)
    for name, migrated in vars(counts).items():
        if name == "elapsed_seconds":
            continue
        src = source_counts.get(name, 0)
        tgt = target_counts.get(name, 0)
        print(f"{name:<22} {src:>10} {tgt:>10} {migrated:>12}")
    print("-" * 70)
    print(f"{'TOTAL':<22} {sum(source_counts.values()):>10} {sum(target_counts.values()):>10} {counts.total():>12}")
    print("=" * 70)
    print(f"Elapsed: {counts.elapsed_seconds}s")

    mismatches = [
        name
        for name in vars(counts)
        if name != "elapsed_seconds" and source_counts.get(name, 0) != target_counts.get(name, 0)
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
