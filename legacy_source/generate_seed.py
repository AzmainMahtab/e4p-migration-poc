#!/usr/bin/env python3
"""Generate seed SQL for the Elite4Print migration POC."""

import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

random.seed(42)

NUM_USERS = 10
NUM_CATEGORIES = 5
NUM_PRODUCTS = 20
NUM_ORDERS = 100
NUM_COUPONS = 10

# Fixed recent month window for the POC.
END_DATE = datetime(2026, 6, 30, 23, 59, 59)
START_DATE = END_DATE - timedelta(days=30)

ORDER_STATUSES = [
    "PENDING", "RECEIVED-ARTWORK", "PDF-REQUEST", "PREPRESS", "BATCHED",
    "PLATED", "PRESS", "BATCHED_CUTTING", "COATING", "LAMINATING", "CUTTING",
    "BINDERY", "SADDLE_STITCH", "FINISHING", "DIE_CUTTING", "EMBOSSING",
    "FOIL_STAMPING", "GLUING", "BUYOUT", "READY_FOR_PICKUP",
    "READY_FOR_DELIVERY", "SHIPPED", "READY", "APPROVED", "SHIPPING",
    "COMPLETE", "CANCELED", "HOLD",
]

PAYMENT_STATUSES = ["PENDING", "PAID", "PARTIALLY_PAID"]
PAYMENT_STATUSES_DETAIL = ["PENDING", "SUCCESS", "FAILED"]
PAYMENT_METHODS = ["CASH", "CARD", "CHEQUE", "ONLINE", "POINTS"]
PAYMENT_TYPES = ["PAYMENT", "REFUND"]
COUPON_ONS = ["product", "shipping", "combined"]
COUPON_TYPES = ["percentage", "fixed"]
COUPON_USAGE_STATUSES = ["RESERVED", "CONFIRMED", "REVERSED"]


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S%z")


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_users():
    rows = []
    for i in range(1, NUM_USERS + 1):
        rows.append(
            f"({i}, 'pbkdf2_sha256$fake$password{i}', NULL, FALSE, "
            f"'user{i}@example.com', FALSE, TRUE, NOW(), NOW())"
        )
    return (
        "INSERT INTO authentications_user (id, password, last_login, is_superuser, email, is_staff, is_active, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_categories():
    names = ["Business Cards", "Flyers", "Brochures", "Posters", "Banners"]
    rows = [f"({i + 1}, '{name}', NOW(), NOW())" for i, name in enumerate(names)]
    return (
        "INSERT INTO product_management_productcategory (id, name, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_products():
    rows = []
    for i in range(1, NUM_PRODUCTS + 1):
        cat = ((i - 1) % NUM_CATEGORIES) + 1
        name = f"Product {i:03d}"
        base = random.uniform(10, 500)
        rows.append(
            f"({i}, {cat}, '{name}', 'Description for {name}', "
            f"'PRD-{i:05d}', 1, 'OFFSET', {money(base)}, {money(base * 1.5)}, "
            f"{money(base / 10)}, 25.0000, TRUE, FALSE, 2, FALSE, 1, TRUE, 'DEFAULT', NOW(), NOW())"
        )
    return (
        "INSERT INTO product_management_product (id, category_id, name, description, product_id, created_by_id, product_type, min_price, max_price, sqr_ft_price, shop_rate_per_hr, is_active, on_draft, base_turnaround, combined_shipping, ordering, show_faq, shipping_type, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_orders():
    rows = []
    for i in range(1, NUM_ORDERS + 1):
        user = random.randint(1, NUM_USERS)
        created = START_DATE + timedelta(seconds=random.randint(0, int((END_DATE - START_DATE).total_seconds())))
        total = money(random.uniform(50, 2500))
        shipping = money(random.uniform(0, 150))
        discount = money(random.uniform(0, min(float(total) * 0.3, 200)))
        tax = money((float(total) + float(shipping) - float(discount)) * 0.08)
        final = money(float(total) + float(shipping) + float(tax) - float(discount))
        pay_status = random.choice(PAYMENT_STATUSES)
        extra = money(random.uniform(0, 50)) if random.random() < 0.1 else money(0)
        is_add_paid = random.choice([True, False]) if extra > 0 else False
        points = random.randint(0, 500) if random.random() < 0.3 else 0
        adj = money(random.uniform(-100, 100)) if random.random() < 0.1 else money(0)
        refunded = money(random.uniform(0, min(float(final), 300))) if random.random() < 0.1 else money(0)
        order_ref = "'{}'" if random.random() < 0.5 else "'{}'"
        rows.append(
            f"({i}, {user}, {total}, {shipping}, {final}, {discount}, '{pay_status}', "
            f"{extra}, {tax}, {is_add_paid}, {total}, {shipping}, {tax}, {points}, "
            f"{adj}, {refunded}, 'ORD-{i:05d}', {order_ref}, '{ts(created)}', '{ts(created)}')"
        )
    return (
        "INSERT INTO order_management_order (id, user_id, total_price, total_shipping_price, final_price, discount_amount, payment_status, extra_payment, tax_amount, is_additional_payment_paid, original_total_price, original_shipping_price, original_tax_amount, points_used, total_adjustment_amount, total_refunded_amount, order_id, order_ref, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_order_items():
    rows = []
    order_items = []
    item_id = 1
    for order_id in range(1, NUM_ORDERS + 1):
        num_items = random.randint(1, 3)
        group_id = str(uuid.uuid4())
        for _ in range(num_items):
            product = random.randint(1, NUM_PRODUCTS)
            qty = random.randint(100, 5000)
            price = money(random.uniform(20, 800))
            original_price = price
            status = random.choice(ORDER_STATUSES)
            job_id = f"JOB-{item_id:06d}"
            job_name = f"Job {item_id}"
            process_status = random.choice(["1", "2", "3", None])
            process_status_sql = f"'{process_status}'" if process_status else "NULL"
            rows.append(
                f"({item_id}, {order_id}, '{job_id}', '{job_name}', '{status}', '{group_id}', "
                f"{process_status_sql}, {product}, 'ITM-{item_id:05d}', 'Premium Paper', '8.5x11', {qty}, "
                f"'UV Coating', '4/4 Color', '8.5x11', {price}, {original_price}, NULL, NULL, "
                f"'2 Business days', 2, NULL, '18:00:00', FALSE, TRUE, NULL, NOW(), NOW())"
            )
            order_items.append({"id": item_id, "order_id": order_id})
            item_id += 1
    sql = (
        "INSERT INTO order_management_orderitems (id, order_id, job_id, job_name, job_status, group_id, process_status, product_id, item_code, paper, size, quantity, coating, color, trim_size, price, original_price, notes, admin_notes, turnaround, turnaround_day, due_date, cut_off_time, file_editable, shipping_editable, pickup_location, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )
    return sql, order_items


def generate_order_item_memos(order_items):
    rows = []
    memo_id = 1
    for item in order_items:
        if random.random() < 0.15:
            printing_adj = money(random.uniform(10, 100))
            shipping_adj = money(random.uniform(0, 30))
            adj_type = random.choice(["ADDITIONAL", "REFUND", "NONE"])
            total_adj = printing_adj + shipping_adj if adj_type != "NONE" else money(0)
            rows.append(
                f"({memo_id}, {item['id']}, 'Adjustment memo {memo_id}', 'PENDING', "
                f"{printing_adj}, {shipping_adj}, '{adj_type}', {total_adj}, NOW(), NOW())"
            )
            memo_id += 1
    if not rows:
        return ""
    return (
        "INSERT INTO order_management_orderitemmemo (id, order_item_id, note, status, printing_adjustment, shipping_adjustment, adjustment_type, total_adjustment, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_payments():
    rows = []
    payment_ids = []
    for i in range(1, NUM_ORDERS + 1):
        # 80% of orders have at least one payment.
        if random.random() < 0.8:
            order_id = i
            user = random.randint(1, NUM_USERS)
            amount = float(generate_order_amounts.get(order_id, 100))
            status = random.choice(PAYMENT_STATUSES_DETAIL)
            method = random.choice(PAYMENT_METHODS)
            ptype = "PAYMENT"
            trans_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
            rows.append(
                f"({i}, {amount:.2f}, '{status}', '{method}', '{ptype}', '{trans_id}', "
                f"{order_id}, NULL, NULL, NULL, {user}, NOW(), NOW())"
            )
            payment_ids.append(i)
    return (
        "INSERT INTO payment_management_payment (id, amount, status, method, type, trans_id, order_id, card_number, job_change_id, transactions_history, user_id, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    ), payment_ids


# Store order final prices so payments can be realistic.
generate_order_amounts = {}


def generate_coupons():
    rows = []
    for i in range(1, NUM_COUPONS + 1):
        code = f"COUPON{i:03d}"
        on = random.choice(COUPON_ONS)
        ctype = random.choice(COUPON_TYPES)
        value = random.uniform(5, 30) if ctype == "fixed" else random.uniform(5, 25)
        max_disc = random.uniform(10, 100)
        start = END_DATE - timedelta(days=60)
        expiry = END_DATE + timedelta(days=30)
        rows.append(
            f"({i}, '{code}', '{on}', '{ctype}', {value:.2f}, {max_disc:.2f}, "
            f"'{ts(start)}', '{ts(expiry)}', -1, -1, 'Sample coupon {i}', NOW(), NOW())"
        )
    return (
        "INSERT INTO coupon_management_coupon (id, coupon_code, coupon_on, coupon_type, coupon_value, max_discount, coupon_start_date, coupon_expiry_date, limit_per_user, limit_per_coupon, coupon_description, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_coupon_products():
    rows = []
    cp_id = 1
    for coupon_id in range(1, NUM_COUPONS + 1):
        products = random.sample(range(1, NUM_PRODUCTS + 1), k=random.randint(1, 5))
        for product_id in products:
            rows.append(f"({cp_id}, {coupon_id}, {product_id})")
            cp_id += 1
    return (
        "INSERT INTO coupon_management_coupon_products (id, coupon_id, product_id) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_coupon_usages():
    rows = []
    num_usages = min(NUM_ORDERS // 3, NUM_COUPONS * 3)
    order_ids = random.sample(range(1, NUM_ORDERS + 1), k=num_usages)
    for i, order_id in enumerate(order_ids, start=1):
        coupon_id = random.randint(1, NUM_COUPONS)
        user = random.randint(1, NUM_USERS)
        status = random.choice(COUPON_USAGE_STATUSES)
        rows.append(
            f"({i}, {coupon_id}, {user}, {order_id}, '{status}', NOW(), NOW())"
        )
    return (
        "INSERT INTO coupon_management_couponusage (id, coupon_id, user_id, order_id, status, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def generate_pending_refunds(payment_ids):
    rows = []
    for i in range(1, 11):
        order_id = random.randint(1, NUM_ORDERS)
        payment_id = random.choice(payment_ids) if payment_ids else random.randint(1, NUM_ORDERS)
        amount = random.uniform(10, 200)
        card = f"****{random.randint(1000, 9999)}"
        status = random.choice(["PENDING", "PROCESSING", "COMPLETED", "FAILED"])
        trans_id = f"REF-{uuid.uuid4().hex[:12].upper()}"
        rows.append(
            f"({i}, {order_id}, {payment_id}, {amount:.3f}, '{card}', '{status}', '{trans_id}', NULL, 0, NULL, NOW(), NOW())"
        )
    return (
        "INSERT INTO payment_management_pendingrefund (id, order_id, payment_id, amount, card_number, status, transaction_id, error_message, retry_count, points, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";"
    )


def main():
    # We need order amounts for payment generation. Replicate the order generation
    # logic to populate the lookup dict without executing SQL.
    for i in range(1, NUM_ORDERS + 1):
        total = money(random.uniform(50, 2500))
        shipping = money(random.uniform(0, 150))
        discount = money(random.uniform(0, min(float(total) * 0.3, 200)))
        tax = money((float(total) + float(shipping) - float(discount)) * 0.08)
        final = money(float(total) + float(shipping) + float(tax) - float(discount))
        generate_order_amounts[i] = final

    lines = [
        "-- Auto-generated seed data for Elite4Print migration POC",
        "TRUNCATE TABLE coupon_management_couponusage RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE coupon_management_coupon_products RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE coupon_management_coupon RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE payment_management_pendingrefund RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE payment_management_payment RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE order_management_orderitemmemo RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE order_management_orderitems RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE order_management_order RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE product_management_product RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE product_management_productcategory RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE authentications_user RESTART IDENTITY CASCADE;",
        "",
        generate_users(),
        "",
        generate_categories(),
        "",
        generate_products(),
        "",
        generate_orders(),
        "",
    ]

    order_items_sql, order_items = generate_order_items()
    lines.append(order_items_sql)
    lines.append("")
    lines.append(generate_order_item_memos(order_items))
    lines.append("")
    payments_sql, payment_ids = generate_payments()
    lines.append(payments_sql)
    lines.append("")
    lines.append(generate_pending_refunds(payment_ids))
    lines.append("")
    lines.append(generate_coupons())
    lines.append("")
    lines.append(generate_coupon_products())
    lines.append("")
    lines.append(generate_coupon_usages())

    with open("legacy_source/seed.sql", "w") as f:
        f.write("\n".join(lines))

    print("Generated legacy_source/seed.sql")


if __name__ == "__main__":
    main()
