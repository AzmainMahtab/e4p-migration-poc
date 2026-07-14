-- Simplified Elite4Print legacy schema for the migration POC slice.
-- Covers: users, product category, product, order, order items, order item memo,
-- payment, pending refund, coupon, coupon usage.

CREATE SCHEMA IF NOT EXISTS public;

CREATE TABLE IF NOT EXISTS authentications_user (
    id SERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE NULL,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    email VARCHAR(254) NOT NULL UNIQUE,
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_management_productcategory (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_management_product (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES product_management_productcategory(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    product_id VARCHAR(255) NOT NULL UNIQUE,
    created_by_id INTEGER REFERENCES authentications_user(id) ON DELETE RESTRICT,
    product_type VARCHAR(255) NOT NULL DEFAULT 'OFFSET',
    min_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    max_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    sqr_ft_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    shop_rate_per_hr NUMERIC(8, 4) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    on_draft BOOLEAN NOT NULL DEFAULT TRUE,
    base_turnaround INTEGER NOT NULL DEFAULT 2,
    combined_shipping BOOLEAN NOT NULL DEFAULT FALSE,
    ordering INTEGER NOT NULL DEFAULT 1,
    show_faq BOOLEAN NOT NULL DEFAULT TRUE,
    shipping_type VARCHAR(10) NOT NULL DEFAULT 'DEFAULT',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_management_order (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES authentications_user(id) ON DELETE RESTRICT,
    total_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total_shipping_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    final_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    payment_status VARCHAR(255) NOT NULL DEFAULT 'PENDING',
    extra_payment NUMERIC(10, 2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    is_additional_payment_paid BOOLEAN NOT NULL DEFAULT FALSE,
    original_total_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    original_shipping_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    original_tax_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    points_used INTEGER NOT NULL DEFAULT 0,
    total_adjustment_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total_refunded_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    order_id VARCHAR(255) NOT NULL UNIQUE,
    order_ref JSONB NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_user_payment ON order_management_order(user_id, payment_status);
CREATE INDEX IF NOT EXISTS idx_order_payment_created ON order_management_order(payment_status, created_at DESC);

CREATE TABLE IF NOT EXISTS order_management_orderitems (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES order_management_order(id) ON DELETE CASCADE,
    job_id VARCHAR(255) NOT NULL UNIQUE,
    job_name VARCHAR(255),
    job_status VARCHAR(255) NOT NULL DEFAULT 'PENDING',
    group_id VARCHAR(40) NOT NULL,
    process_status VARCHAR(5),
    product_id INTEGER REFERENCES product_management_product(id) ON DELETE SET NULL,
    item_code VARCHAR(255),
    paper VARCHAR(150) NOT NULL DEFAULT 'No Paper',
    size VARCHAR(50),
    quantity INTEGER NOT NULL DEFAULT 0,
    coating VARCHAR(150) NOT NULL DEFAULT 'No Coating',
    color VARCHAR(150) NOT NULL DEFAULT 'No Color',
    trim_size VARCHAR(50),
    price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    original_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    notes TEXT,
    admin_notes TEXT,
    turnaround VARCHAR(50) NOT NULL DEFAULT '2 Business days',
    turnaround_day INTEGER NOT NULL DEFAULT 0,
    due_date DATE,
    cut_off_time TIME NOT NULL DEFAULT '18:00:00',
    file_editable BOOLEAN NOT NULL DEFAULT FALSE,
    shipping_editable BOOLEAN NOT NULL DEFAULT TRUE,
    pickup_location VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orderitems_order ON order_management_orderitems(order_id);
CREATE INDEX IF NOT EXISTS idx_orderitems_job_status ON order_management_orderitems(job_status);

CREATE TABLE IF NOT EXISTS order_management_orderitemmemo (
    id SERIAL PRIMARY KEY,
    order_item_id INTEGER NOT NULL REFERENCES order_management_orderitems(id) ON DELETE CASCADE,
    note VARCHAR(255) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'PENDING',
    printing_adjustment NUMERIC(10, 2) NOT NULL DEFAULT 0,
    shipping_adjustment NUMERIC(10, 2) NOT NULL DEFAULT 0,
    adjustment_type VARCHAR(15) NOT NULL DEFAULT 'NONE',
    total_adjustment NUMERIC(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payment_management_payment (
    id SERIAL PRIMARY KEY,
    amount DOUBLE PRECISION NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'SUCCESS',
    method VARCHAR(10) NOT NULL DEFAULT 'CARD',
    type VARCHAR(10) NOT NULL DEFAULT 'PAYMENT',
    trans_id VARCHAR(255),
    order_id INTEGER REFERENCES order_management_order(id) ON DELETE CASCADE,
    card_number VARCHAR(50),
    job_change_id INTEGER REFERENCES order_management_orderitemmemo(id) ON DELETE SET NULL,
    transactions_history JSONB,
    user_id INTEGER REFERENCES authentications_user(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_order ON payment_management_payment(order_id);

CREATE TABLE IF NOT EXISTS payment_management_pendingrefund (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES order_management_order(id) ON DELETE CASCADE,
    payment_id INTEGER NOT NULL REFERENCES payment_management_payment(id) ON DELETE CASCADE,
    amount NUMERIC(10, 3) NOT NULL,
    card_number VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    transaction_id VARCHAR(255) NOT NULL,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    points INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupon_management_coupon (
    id SERIAL PRIMARY KEY,
    coupon_code VARCHAR(50) NOT NULL UNIQUE,
    coupon_on VARCHAR(50) NOT NULL,
    coupon_type VARCHAR(50) NOT NULL,
    coupon_value DOUBLE PRECISION NOT NULL,
    max_discount DOUBLE PRECISION NOT NULL DEFAULT 0,
    coupon_start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    coupon_expiry_date TIMESTAMP WITH TIME ZONE NOT NULL,
    limit_per_user INTEGER NOT NULL DEFAULT -1,
    limit_per_coupon INTEGER NOT NULL DEFAULT -1,
    coupon_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupon_management_coupon_products (
    id SERIAL PRIMARY KEY,
    coupon_id INTEGER NOT NULL REFERENCES coupon_management_coupon(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES product_management_product(id) ON DELETE CASCADE,
    UNIQUE(coupon_id, product_id)
);

CREATE TABLE IF NOT EXISTS coupon_management_couponusage (
    id SERIAL PRIMARY KEY,
    coupon_id INTEGER NOT NULL REFERENCES coupon_management_coupon(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES authentications_user(id) ON DELETE CASCADE,
    order_id INTEGER NOT NULL UNIQUE REFERENCES order_management_order(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'RESERVED',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_couponusage_order ON coupon_management_couponusage(order_id);
