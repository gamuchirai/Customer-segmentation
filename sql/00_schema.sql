-- Schema definition and dual view contract for customer segmentation pipeline.
-- Idempotent SQLite script defining raw staging, cleaned transactions,
-- dimension tables, metadata rule seeds, audit log, and dual views.

DROP VIEW IF EXISTS vw_customer_sales;
DROP VIEW IF EXISTS vw_store_sales;
DROP TABLE IF EXISTS clean_transactions;
DROP TABLE IF EXISTS dim_customers;
DROP TABLE IF EXISTS dim_products;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS cleaning_audit;
DROP TABLE IF EXISTS ref_pipeline_config;
DROP TABLE IF EXISTS ref_excluded_stock_codes;
DROP TABLE IF EXISTS raw_transactions;

-- Staging table for raw Excel transactions across both sheets
CREATE TABLE raw_transactions (
    raw_id INTEGER PRIMARY KEY,
    source_sheet TEXT NOT NULL,
    source_row_num INTEGER NOT NULL,
    loaded_at TEXT NOT NULL,
    invoice TEXT,
    stock_code TEXT,
    description TEXT,
    quantity INTEGER,
    invoice_date TEXT,
    price REAL,
    customer_id TEXT,
    country TEXT,
    UNIQUE (source_sheet, source_row_num)
) STRICT;

-- Lookup table of non merchandise and adjustment stock codes
CREATE TABLE ref_excluded_stock_codes (
    stock_code TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    reason TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
) STRICT;

-- Configurable pipeline thresholds and reference parameters
CREATE TABLE ref_pipeline_config (
    config_key TEXT PRIMARY KEY,
    config_value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    description TEXT NOT NULL
) STRICT;

-- Calendar dimension table supporting date slicing and Power BI star schema
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    calendar_date TEXT NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    order_month TEXT NOT NULL,
    month_start_date TEXT NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    day_name TEXT NOT NULL,
    is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
) STRICT;

-- Product dimension table with canonical descriptions
CREATE TABLE dim_products (
    stock_code TEXT PRIMARY KEY,
    canonical_description TEXT NOT NULL,
    description_variant_count INTEGER NOT NULL CHECK (description_variant_count >= 1),
    first_sold_date TEXT NOT NULL,
    last_sold_date TEXT NOT NULL
) STRICT;

-- Customer dimension table with lifetime metrics and wholesale flag
CREATE TABLE dim_customers (
    customer_id TEXT PRIMARY KEY,
    primary_country TEXT NOT NULL,
    country_variant_count INTEGER NOT NULL CHECK (country_variant_count >= 1),
    first_order_date TEXT NOT NULL,
    cohort_month TEXT NOT NULL,
    last_order_date TEXT NOT NULL,
    lifetime_orders INTEGER NOT NULL CHECK (lifetime_orders >= 1),
    lifetime_units INTEGER NOT NULL CHECK (lifetime_units >= 1),
    lifetime_revenue REAL NOT NULL CHECK (lifetime_revenue > 0),
    avg_order_value REAL NOT NULL CHECK (avg_order_value > 0),
    avg_units_per_order REAL NOT NULL CHECK (avg_units_per_order > 0),
    is_wholesale INTEGER NOT NULL CHECK (is_wholesale IN (0, 1)),
    wholesale_reason TEXT
) STRICT;

-- Cleaned valid merchandise transactions table
CREATE TABLE clean_transactions (
    clean_id INTEGER PRIMARY KEY,
    raw_id INTEGER NOT NULL UNIQUE REFERENCES raw_transactions (raw_id),
    invoice TEXT NOT NULL,
    stock_code TEXT NOT NULL REFERENCES dim_products (stock_code),
    raw_description TEXT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL CHECK (unit_price > 0),
    line_revenue REAL NOT NULL CHECK (line_revenue > 0),
    invoice_ts TEXT NOT NULL,
    order_date TEXT NOT NULL,
    order_month TEXT NOT NULL,
    date_key INTEGER NOT NULL REFERENCES dim_date (date_key),
    customer_id TEXT REFERENCES dim_customers (customer_id),
    transaction_country TEXT NOT NULL,
    is_identified_customer INTEGER NOT NULL CHECK (is_identified_customer IN (0, 1)),
    CHECK (
        (is_identified_customer = 1 AND customer_id IS NOT NULL)
        OR (is_identified_customer = 0 AND customer_id IS NULL)
    )
) STRICT;

CREATE INDEX idx_clean_customer_month ON clean_transactions (customer_id, order_month);
CREATE INDEX idx_clean_order_month ON clean_transactions (order_month);
CREATE INDEX idx_clean_stock_code ON clean_transactions (stock_code);
CREATE INDEX idx_clean_date_key ON clean_transactions (date_key);
CREATE INDEX idx_clean_invoice ON clean_transactions (invoice);

-- Audit log capturing row removals and boundary split reconciliation
CREATE TABLE cleaning_audit (
    audit_id INTEGER PRIMARY KEY,
    executed_at TEXT NOT NULL,
    step_order INTEGER NOT NULL UNIQUE,
    rule_name TEXT NOT NULL UNIQUE,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN ('baseline', 'cleaning_removal', 'boundary_split', 'output_total')
    ),
    rows_removed_sequential INTEGER NOT NULL CHECK (rows_removed_sequential >= 0),
    rows_matched_raw INTEGER NOT NULL CHECK (rows_matched_raw >= 0),
    revenue_removed_sequential REAL NOT NULL,
    remaining_rows INTEGER NOT NULL CHECK (remaining_rows >= 0),
    remaining_revenue REAL NOT NULL,
    notes TEXT
) STRICT;

-- Dual view: store wide valid merchandise sales
CREATE VIEW vw_store_sales AS
SELECT
    ct.clean_id,
    ct.raw_id,
    ct.invoice,
    ct.stock_code,
    dp.canonical_description,
    ct.raw_description,
    ct.quantity,
    ct.unit_price,
    ct.line_revenue,
    ct.invoice_ts,
    ct.order_date,
    ct.order_month,
    ct.date_key,
    dd.year,
    dd.quarter,
    dd.month,
    dd.month_start_date,
    dd.day_of_week,
    dd.day_name,
    dd.is_weekend,
    ct.customer_id,
    ct.transaction_country,
    ct.is_identified_customer,
    dc.primary_country,
    dc.wholesale_reason,
    COALESCE(dc.primary_country, ct.transaction_country) AS country_resolved,
    COALESCE(dc.is_wholesale, 0) AS is_wholesale
FROM clean_transactions AS ct
INNER JOIN dim_products AS dp
    ON ct.stock_code = dp.stock_code
INNER JOIN dim_date AS dd
    ON ct.date_key = dd.date_key
LEFT JOIN dim_customers AS dc
    ON ct.customer_id = dc.customer_id;

-- Dual view: identified customer sales for cohorts and RFM
CREATE VIEW vw_customer_sales AS
SELECT
    ct.clean_id,
    ct.raw_id,
    ct.invoice,
    ct.stock_code,
    dp.canonical_description,
    ct.raw_description,
    ct.quantity,
    ct.unit_price,
    ct.line_revenue,
    ct.invoice_ts,
    ct.order_date,
    ct.order_month,
    ct.date_key,
    dd.year,
    dd.quarter,
    dd.month,
    dd.month_start_date,
    dd.day_of_week,
    dd.day_name,
    dd.is_weekend,
    ct.customer_id,
    ct.transaction_country,
    dc.primary_country,
    dc.cohort_month,
    dc.first_order_date,
    dc.last_order_date,
    dc.lifetime_orders,
    dc.lifetime_units,
    dc.lifetime_revenue,
    dc.avg_order_value,
    dc.avg_units_per_order,
    dc.is_wholesale,
    dc.wholesale_reason
FROM clean_transactions AS ct
INNER JOIN dim_customers AS dc
    ON ct.customer_id = dc.customer_id
INNER JOIN dim_products AS dp
    ON ct.stock_code = dp.stock_code
INNER JOIN dim_date AS dd
    ON ct.date_key = dd.date_key
WHERE ct.is_identified_customer = 1;

-- Starter seeds for known non merchandise codes
INSERT INTO ref_excluded_stock_codes (stock_code, category, reason, is_active) VALUES
('POST', 'postage', 'Postal service charge lines', 1),
('D', 'discount', 'Manual discount adjustment lines', 1),
('M', 'manual_fee', 'Manual accounting and service lines', 1),
('DOT', 'postage', 'DOTCOM postage fee lines', 1),
('BANK CHARGES', 'bank_charge', 'Bank processing fee lines', 1),
('CRUK', 'charity', 'Cancer Research UK fee lines', 1),
('B', 'adjustment', 'Bad debt adjustment lines', 1),
('C2', 'carriage', 'Carriage shipping fee lines', 1),
('AMAZONFEE', 'platform_fee', 'Amazon marketplace fee lines', 1),
('S', 'sample', 'Free product sample lines', 1),
('PADS', 'pads', 'Pads adjustment lines', 1),
('ADJUST', 'adjustment', 'Adjustment lines', 1),
('TEST001', 'test', 'Internal system testing lines', 1),
('TEST002', 'test', 'Internal system testing lines', 1);

-- Baseline pipeline configuration seeds
INSERT INTO ref_pipeline_config (config_key, config_value, value_type, description) VALUES
(
    'rfm_reference_date',
    '2011-12-10',
    'date',
    'Fixed RFM analysis cutoff date one day after max invoice date'
),
(
    'wholesale_min_lifetime_revenue',
    '10000',
    'real',
    'Minimum lifetime revenue cutoff in GBP for wholesale account flag'
),
(
    'wholesale_min_orders',
    '25',
    'integer',
    'Minimum distinct orders cutoff for wholesale account flag'
),
(
    'wholesale_min_avg_units_per_order',
    '200',
    'real',
    'Minimum average units per order cutoff for wholesale account flag'
),
(
    'wholesale_rule_mode',
    'OR',
    'text',
    'Combination operator across active wholesale rule thresholds'
);
