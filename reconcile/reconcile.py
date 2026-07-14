#!/usr/bin/env python3
"""Reconcile the Elite4Print slice between legacy source and migrated targets."""

import os
from contextlib import closing
from decimal import Decimal

import psycopg

SOURCE_DSN = os.getenv("LEGACY_DATABASE_URL", "postgresql://e4p:e4p@localhost:5433/e4p_legacy")
DJANGO_DSN = os.getenv("DJANGO_DATABASE_URL", "postgresql://e4p:e4p@localhost:5434/e4p_django")
FASTAPI_DSN = os.getenv("FASTAPI_DATABASE_URL", "postgresql://e4p:e4p@localhost:5435/e4p_fastapi")


QUERIES = {
    "row_counts": {
        "users": ("SELECT COUNT(*) FROM authentications_user", "SELECT COUNT(*) FROM identity_user", "SELECT COUNT(*) FROM users"),
        "product_categories": ("SELECT COUNT(*) FROM product_management_productcategory", "SELECT COUNT(*) FROM catalog_productcategory", "SELECT COUNT(*) FROM product_categories"),
        "products": ("SELECT COUNT(*) FROM product_management_product", "SELECT COUNT(*) FROM catalog_product", "SELECT COUNT(*) FROM products"),
        "orders": ("SELECT COUNT(*) FROM order_management_order", "SELECT COUNT(*) FROM ordering_order", "SELECT COUNT(*) FROM orders"),
        "jobs": ("SELECT COUNT(*) FROM order_management_orderitems", "SELECT COUNT(*) FROM ordering_job", "SELECT COUNT(*) FROM jobs"),
        "job_memos": ("SELECT COUNT(*) FROM order_management_orderitemmemo", "SELECT COUNT(*) FROM ordering_jobmemo", "SELECT COUNT(*) FROM job_memos"),
        "payments": ("SELECT COUNT(*) FROM payment_management_payment", "SELECT COUNT(*) FROM payment_payment", "SELECT COUNT(*) FROM payments"),
        "pending_refunds": ("SELECT COUNT(*) FROM payment_management_pendingrefund", "SELECT COUNT(*) FROM payment_pendingrefund", "SELECT COUNT(*) FROM pending_refunds"),
        "coupons": ("SELECT COUNT(*) FROM coupon_management_coupon", "SELECT COUNT(*) FROM promotion_coupon", "SELECT COUNT(*) FROM coupons"),
        "coupon_usages": ("SELECT COUNT(*) FROM coupon_management_couponusage", "SELECT COUNT(*) FROM promotion_couponusage", "SELECT COUNT(*) FROM coupon_usages"),
    },
    "financials": {
        "orders_total": ("SELECT COALESCE(SUM(total_price), 0) FROM order_management_order", "SELECT COALESCE(SUM(total_price), 0) FROM ordering_order", "SELECT COALESCE(SUM(total_price), 0) FROM orders"),
        "orders_final": ("SELECT COALESCE(SUM(final_price), 0) FROM order_management_order", "SELECT COALESCE(SUM(final_price), 0) FROM ordering_order", "SELECT COALESCE(SUM(final_price), 0) FROM orders"),
        "orders_discount": ("SELECT COALESCE(SUM(discount_amount), 0) FROM order_management_order", "SELECT COALESCE(SUM(discount_amount), 0) FROM ordering_order", "SELECT COALESCE(SUM(discount_amount), 0) FROM orders"),
        "orders_tax": ("SELECT COALESCE(SUM(tax_amount), 0) FROM order_management_order", "SELECT COALESCE(SUM(tax_amount), 0) FROM ordering_order", "SELECT COALESCE(SUM(tax_amount), 0) FROM orders"),
        "orders_shipping": ("SELECT COALESCE(SUM(total_shipping_price), 0) FROM order_management_order", "SELECT COALESCE(SUM(total_shipping_price), 0) FROM ordering_order", "SELECT COALESCE(SUM(total_shipping_price), 0) FROM orders"),
        "payments": ("SELECT COALESCE(SUM(amount), 0) FROM payment_management_payment", "SELECT COALESCE(SUM(amount), 0) FROM payment_payment", "SELECT COALESCE(SUM(amount), 0) FROM payments"),
        "pending_refunds": ("SELECT COALESCE(SUM(amount), 0) FROM payment_management_pendingrefund", "SELECT COALESCE(SUM(amount), 0) FROM payment_pendingrefund", "SELECT COALESCE(SUM(amount), 0) FROM pending_refunds"),
        "jobs_price": ("SELECT COALESCE(SUM(price), 0) FROM order_management_orderitems", "SELECT COALESCE(SUM(price), 0) FROM ordering_job", "SELECT COALESCE(SUM(price), 0) FROM jobs"),
    },
    "referential_integrity": {
        "jobs_without_order": (
            "SELECT COUNT(*) FROM order_management_orderitems oi WHERE NOT EXISTS (SELECT 1 FROM order_management_order o WHERE o.id = oi.order_id)",
            "SELECT COUNT(*) FROM ordering_job j WHERE NOT EXISTS (SELECT 1 FROM ordering_order o WHERE o.id = j.order_id)",
            "SELECT COUNT(*) FROM jobs j WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.id = j.order_id)",
        ),
        "payments_without_order": (
            "SELECT COUNT(*) FROM payment_management_payment p WHERE p.order_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM order_management_order o WHERE o.id = p.order_id)",
            "SELECT COUNT(*) FROM payment_payment p WHERE p.order_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ordering_order o WHERE o.id = p.order_id)",
            "SELECT COUNT(*) FROM payments p WHERE p.order_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.id = p.order_id)",
        ),
        "refunds_without_payment": (
            "SELECT COUNT(*) FROM payment_management_pendingrefund pr WHERE NOT EXISTS (SELECT 1 FROM payment_management_payment p WHERE p.id = pr.payment_id)",
            "SELECT COUNT(*) FROM payment_pendingrefund pr WHERE NOT EXISTS (SELECT 1 FROM payment_payment p WHERE p.id = pr.payment_id)",
            "SELECT COUNT(*) FROM pending_refunds pr WHERE NOT EXISTS (SELECT 1 FROM payments p WHERE p.id = pr.payment_id)",
        ),
    },
}


def scalar(dsn, sql):
    with closing(psycopg.connect(dsn)) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]


def fmt(value):
    if isinstance(value, (Decimal, float)):
        return f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}"
    return str(value)


def main():
    print("=" * 80)
    print("Elite4Print Migration Reconciliation")
    print("=" * 80)

    all_pass = True

    for section_name, checks in QUERIES.items():
        print(f"\n{section_name.replace('_', ' ').title()}")
        print("-" * 80)
        for check_name, (source_sql, django_sql, fastapi_sql) in checks.items():
            source = scalar(SOURCE_DSN, source_sql)
            django = scalar(DJANGO_DSN, django_sql)
            fastapi = scalar(FASTAPI_DSN, fastapi_sql)

            # Normalize floats to 2 decimal places for comparison.
            source_norm = Decimal(str(source)).quantize(Decimal("0.01")) if isinstance(source, float) else source
            django_norm = Decimal(str(django)).quantize(Decimal("0.01")) if isinstance(django, float) else django
            fastapi_norm = Decimal(str(fastapi)).quantize(Decimal("0.01")) if isinstance(fastapi, float) else fastapi

            source_match = source_norm == django_norm == fastapi_norm
            if not source_match:
                all_pass = False

            status = "PASS" if source_match else "FAIL"
            print(
                f"  {check_name:30s}  source={fmt(source):>14s}  django={fmt(django):>14s}  fastapi={fmt(fastapi):>14s}  [{status}]"
            )

    print("\n" + "=" * 80)
    if all_pass:
        print("RESULT: ALL CHECKS PASS")
    else:
        print("RESULT: SOME CHECKS FAILED")
    print("=" * 80)

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
