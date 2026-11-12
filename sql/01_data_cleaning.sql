-- Data cleaning and dimension derivation pipeline for customer segmentation.
-- Idempotent SQLite script populating clean_transactions, dim_products,
-- dim_customers, and cleaning_audit from raw_transactions.

-- Reset target clean fact, dimensions, and audit log
DELETE FROM clean_transactions;
DELETE FROM dim_customers;
DELETE FROM dim_products;
DELETE FROM cleaning_audit;

-- Step 1: Materialize normalized rows and sequential cleaning flags in temp storage
DROP TABLE IF EXISTS temp_staged_lines;

CREATE TEMP TABLE temp_staged_lines AS
WITH normalized_base AS (
    SELECT
        raw_id,
        source_sheet,
        source_row_num,
        invoice,
        stock_code,
        description,
        quantity,
        invoice_date,
        price,
        customer_id,
        country,
        TRIM(invoice) AS norm_invoice,
        UPPER(TRIM(stock_code)) AS norm_stock_code,
        NULLIF(TRIM(description), '') AS norm_description,
        COALESCE(NULLIF(TRIM(customer_id), ''), NULL) AS norm_customer_id,
        COALESCE(NULLIF(TRIM(country), ''), 'Unspecified') AS norm_country
    FROM raw_transactions
),

ranked_lines AS (
    SELECT
        raw_id,
        source_sheet,
        source_row_num,
        invoice,
        stock_code,
        description,
        quantity,
        invoice_date,
        price,
        customer_id,
        country,
        norm_invoice,
        norm_stock_code,
        norm_description,
        norm_customer_id,
        norm_country,
        ROW_NUMBER() OVER (
            PARTITION BY
                norm_invoice,
                norm_stock_code,
                COALESCE(norm_description, ''),
                quantity,
                invoice_date,
                price,
                COALESCE(norm_customer_id, ''),
                norm_country
            ORDER BY raw_id ASC
        ) AS dup_rank,
        CASE
            WHEN norm_invoice LIKE 'C%' OR norm_invoice LIKE 'c%' THEN 1
            ELSE 0
        END AS is_cancellation,
        CASE
            WHEN norm_stock_code IN (
                SELECT resc.stock_code FROM ref_excluded_stock_codes AS resc
                WHERE resc.is_active = 1
            ) THEN 1
            ELSE 0
        END AS is_excluded_stock_code,
        CASE
            WHEN quantity <= 0 OR price <= 0 THEN 1
            ELSE 0
        END AS is_non_positive
    FROM normalized_base
)

SELECT
    raw_id,
    source_sheet,
    source_row_num,
    invoice,
    stock_code,
    description,
    quantity,
    invoice_date,
    price,
    customer_id,
    country,
    norm_invoice,
    norm_stock_code,
    norm_description,
    norm_customer_id,
    norm_country,
    dup_rank,
    is_cancellation,
    is_excluded_stock_code,
    is_non_positive,
    CASE
        WHEN
            dup_rank = 1
            AND is_cancellation = 0
            AND is_excluded_stock_code = 0
            AND is_non_positive = 0
            THEN 1
        ELSE 0
    END AS is_valid_merchandise
FROM ranked_lines;

CREATE INDEX idx_temp_staged_valid ON temp_staged_lines (is_valid_merchandise, norm_stock_code);
CREATE INDEX idx_temp_staged_customer ON temp_staged_lines (is_valid_merchandise, norm_customer_id);

-- Step 2: Populate dim_products with canonical descriptions and variants
WITH valid_products AS (
    SELECT
        norm_stock_code,
        invoice_date,
        COALESCE(
            norm_description,
            'UNKNOWN DESCRIPTION (' || norm_stock_code || ')'
        ) AS desc_val
    FROM temp_staged_lines
    WHERE is_valid_merchandise = 1
),

desc_frequencies AS (
    SELECT
        norm_stock_code,
        desc_val,
        COUNT(*) AS freq,
        MAX(invoice_date) AS max_date
    FROM valid_products
    GROUP BY norm_stock_code, desc_val
),

ranked_descriptions AS (
    SELECT
        norm_stock_code,
        desc_val,
        ROW_NUMBER() OVER (
            PARTITION BY norm_stock_code
            ORDER BY freq DESC, max_date DESC, desc_val ASC
        ) AS desc_rank
    FROM desc_frequencies
),

product_aggregates AS (
    SELECT
        norm_stock_code,
        MAX(1, COUNT(DISTINCT desc_val)) AS description_variant_count,
        MIN(SUBSTR(invoice_date, 1, 10)) AS first_sold_date,
        MAX(SUBSTR(invoice_date, 1, 10)) AS last_sold_date
    FROM valid_products
    GROUP BY norm_stock_code
)

INSERT INTO dim_products (
    stock_code,
    canonical_description,
    description_variant_count,
    first_sold_date,
    last_sold_date
)
SELECT
    pa.norm_stock_code AS stock_code,
    rd.desc_val AS canonical_description,
    pa.description_variant_count,
    pa.first_sold_date,
    pa.last_sold_date
FROM product_aggregates AS pa
INNER JOIN ranked_descriptions AS rd
    ON
        pa.norm_stock_code = rd.norm_stock_code
        AND rd.desc_rank = 1;

-- Step 3: Populate dim_customers with lifetime metrics and wholesale flags
WITH valid_customers AS (
    SELECT
        norm_customer_id,
        norm_country,
        invoice,
        quantity,
        price,
        invoice_date,
        quantity * price AS line_rev
    FROM temp_staged_lines
    WHERE
        is_valid_merchandise = 1
        AND norm_customer_id IS NOT NULL
),

country_frequencies AS (
    SELECT
        norm_customer_id,
        norm_country,
        COUNT(*) AS freq,
        MAX(invoice_date) AS max_date
    FROM valid_customers
    GROUP BY norm_customer_id, norm_country
),

ranked_countries AS (
    SELECT
        norm_customer_id,
        norm_country,
        ROW_NUMBER() OVER (
            PARTITION BY norm_customer_id
            ORDER BY
                CASE WHEN norm_country = 'Unspecified' THEN 1 ELSE 0 END ASC,
                freq DESC,
                max_date DESC,
                norm_country ASC
        ) AS country_rank
    FROM country_frequencies
),

customer_aggregates AS (
    SELECT
        norm_customer_id,
        MAX(1, COUNT(DISTINCT norm_country)) AS country_variant_count,
        MIN(SUBSTR(invoice_date, 1, 10)) AS first_order_date,
        MIN(SUBSTR(invoice_date, 1, 7)) AS cohort_month,
        MAX(SUBSTR(invoice_date, 1, 10)) AS last_order_date,
        COUNT(DISTINCT invoice) AS lifetime_orders,
        SUM(quantity) AS lifetime_units,
        SUM(line_rev) AS lifetime_revenue
    FROM valid_customers
    GROUP BY norm_customer_id
),

wholesale_config AS (
    SELECT
        COALESCE(
            MAX(
                CASE
                    WHEN config_key = 'wholesale_min_lifetime_revenue'
                        THEN CAST(config_value AS REAL)
                END
            ),
            10000.0
        ) AS min_rev,
        COALESCE(
            MAX(
                CASE
                    WHEN config_key = 'wholesale_min_orders'
                        THEN CAST(config_value AS INTEGER)
                END
            ),
            25
        ) AS min_ord,
        COALESCE(
            MAX(
                CASE
                    WHEN config_key = 'wholesale_min_avg_units_per_order'
                        THEN CAST(config_value AS REAL)
                END
            ),
            200.0
        ) AS min_avg
    FROM ref_pipeline_config
)

INSERT INTO dim_customers (
    customer_id,
    primary_country,
    country_variant_count,
    first_order_date,
    cohort_month,
    last_order_date,
    lifetime_orders,
    lifetime_units,
    lifetime_revenue,
    avg_order_value,
    avg_units_per_order,
    is_wholesale,
    wholesale_reason
)
SELECT
    ca.norm_customer_id AS customer_id,
    rc.norm_country AS primary_country,
    ca.country_variant_count,
    ca.first_order_date,
    ca.cohort_month,
    ca.last_order_date,
    ca.lifetime_orders,
    ca.lifetime_units,
    ca.lifetime_revenue,
    ca.lifetime_revenue / ca.lifetime_orders AS avg_order_value,
    CAST(ca.lifetime_units AS REAL) / ca.lifetime_orders AS avg_units_per_order,
    CASE
        WHEN
            ca.lifetime_revenue >= wc.min_rev
            OR ca.lifetime_orders >= wc.min_ord
            OR (CAST(ca.lifetime_units AS REAL) / ca.lifetime_orders) >= wc.min_avg
            THEN 1
        ELSE 0
    END AS is_wholesale,
    CASE
        WHEN
            ca.lifetime_revenue >= wc.min_rev
            OR ca.lifetime_orders >= wc.min_ord
            OR (CAST(ca.lifetime_units AS REAL) / ca.lifetime_orders) >= wc.min_avg
            THEN TRIM(
                (
                    CASE
                        WHEN ca.lifetime_revenue >= wc.min_rev
                            THEN 'REVENUE_THRESHOLD|'
                        ELSE ''
                    END
                )
                || (
                    CASE
                        WHEN ca.lifetime_orders >= wc.min_ord
                            THEN 'ORDER_COUNT_THRESHOLD|'
                        ELSE ''
                    END
                )
                || (
                    CASE
                        WHEN
                            (CAST(ca.lifetime_units AS REAL) / ca.lifetime_orders) >= wc.min_avg
                            THEN 'UNITS_PER_ORDER_THRESHOLD|'
                        ELSE ''
                    END
                ),
                '|'
            )
    END AS wholesale_reason
FROM customer_aggregates AS ca
INNER JOIN ranked_countries AS rc
    ON
        ca.norm_customer_id = rc.norm_customer_id
        AND rc.country_rank = 1
CROSS JOIN wholesale_config AS wc;

-- Step 4: Populate clean_transactions fact table
INSERT INTO clean_transactions (
    raw_id,
    invoice,
    stock_code,
    raw_description,
    quantity,
    unit_price,
    line_revenue,
    invoice_ts,
    order_date,
    order_month,
    date_key,
    customer_id,
    transaction_country,
    is_identified_customer
)
SELECT
    ts.raw_id,
    ts.invoice,
    ts.norm_stock_code AS stock_code,
    ts.description AS raw_description,
    ts.quantity,
    ts.price AS unit_price,
    ts.quantity * ts.price AS line_revenue,
    ts.invoice_date AS invoice_ts,
    SUBSTR(ts.invoice_date, 1, 10) AS order_date,
    SUBSTR(ts.invoice_date, 1, 7) AS order_month,
    CAST(STRFTIME('%Y%m%d', SUBSTR(ts.invoice_date, 1, 10)) AS INTEGER) AS date_key,
    ts.norm_customer_id AS customer_id,
    ts.norm_country AS transaction_country,
    CASE
        WHEN ts.norm_customer_id IS NOT NULL THEN 1
        ELSE 0
    END AS is_identified_customer
FROM temp_staged_lines AS ts
WHERE ts.is_valid_merchandise = 1;

-- Step 5: Build sequential audit waterfall logging
WITH audit_metrics AS (
    SELECT
        -- Step 1: Baseline
        COUNT(*) AS base_rows,
        COALESCE(SUM(quantity * price), 0.0) AS base_rev,

        -- Step 2: Exact duplicates
        COALESCE(SUM(CASE WHEN dup_rank > 1 THEN 1 ELSE 0 END), 0) AS dup_rows,
        COALESCE(SUM(CASE WHEN dup_rank > 1 THEN quantity * price ELSE 0.0 END), 0.0) AS dup_rev,

        -- Step 3: Cancellations (sequential from dup_rank = 1)
        COALESCE(
            SUM(CASE WHEN dup_rank = 1 AND is_cancellation = 1 THEN 1 ELSE 0 END),
            0
        ) AS cancel_rows,
        COALESCE(
            SUM(
                CASE
                    WHEN dup_rank = 1 AND is_cancellation = 1
                        THEN quantity * price
                    ELSE 0.0
                END
            ),
            0.0
        ) AS cancel_rev,

        -- Step 4: Non merchandise (sequential from dup_rank = 1 and is_cancellation = 0)
        COALESCE(
            SUM(
                CASE
                    WHEN
                        dup_rank = 1
                        AND is_cancellation = 0
                        AND is_excluded_stock_code = 1
                        THEN 1
                    ELSE 0
                END
            ),
            0
        ) AS fee_rows,
        COALESCE(
            SUM(
                CASE
                    WHEN
                        dup_rank = 1
                        AND is_cancellation = 0
                        AND is_excluded_stock_code = 1
                        THEN quantity * price
                    ELSE 0.0
                END
            ),
            0.0
        ) AS fee_rev,

        -- Step 5: Non positive (sequential from prior filters)
        COALESCE(
            SUM(
                CASE
                    WHEN
                        dup_rank = 1
                        AND is_cancellation = 0
                        AND is_excluded_stock_code = 0
                        AND is_non_positive = 1
                        THEN 1
                    ELSE 0
                END
            ),
            0
        ) AS nonpos_rows,
        COALESCE(
            SUM(
                CASE
                    WHEN
                        dup_rank = 1
                        AND is_cancellation = 0
                        AND is_excluded_stock_code = 0
                        AND is_non_positive = 1
                        THEN quantity * price
                    ELSE 0.0
                END
            ),
            0.0
        ) AS nonpos_rev,

        -- Step 6: Missing customer boundary split (from valid merchandise)
        COALESCE(
            SUM(
                CASE
                    WHEN is_valid_merchandise = 1 AND norm_customer_id IS NULL
                        THEN 1
                    ELSE 0
                END
            ),
            0
        ) AS guest_rows,
        COALESCE(
            SUM(
                CASE
                    WHEN is_valid_merchandise = 1 AND norm_customer_id IS NULL
                        THEN quantity * price
                    ELSE 0.0
                END
            ),
            0.0
        ) AS guest_rev,

        -- Raw matches (independent matching counts)
        COALESCE(SUM(CASE WHEN is_cancellation = 1 THEN 1 ELSE 0 END), 0) AS raw_cancel_rows,
        COALESCE(
            SUM(CASE WHEN is_excluded_stock_code = 1 THEN 1 ELSE 0 END),
            0
        ) AS raw_fee_rows,
        COALESCE(
            SUM(CASE WHEN is_non_positive = 1 THEN 1 ELSE 0 END),
            0
        ) AS raw_nonpos_rows,
        COALESCE(
            SUM(CASE WHEN norm_customer_id IS NULL THEN 1 ELSE 0 END),
            0
        ) AS raw_guest_rows
    FROM temp_staged_lines
),

audit_steps AS (
    SELECT
        1 AS step_order,
        'baseline' AS rule_name,
        'baseline' AS entry_type,
        0 AS rows_removed_sequential,
        base_rows AS rows_matched_raw,
        0.0 AS revenue_removed_sequential,
        base_rows AS remaining_rows,
        base_rev AS remaining_revenue,
        'Total raw transactions baseline across all sheets' AS notes
    FROM audit_metrics
    UNION ALL
    SELECT
        2 AS step_order,
        'exact_duplicate' AS rule_name,
        'cleaning_removal' AS entry_type,
        dup_rows AS rows_removed_sequential,
        dup_rows AS rows_matched_raw,
        dup_rev AS revenue_removed_sequential,
        base_rows - dup_rows AS remaining_rows,
        base_rev - dup_rev AS remaining_revenue,
        'Exact duplicates matching across 8 normalized attributes' AS notes
    FROM audit_metrics
    UNION ALL
    SELECT
        3 AS step_order,
        'cancellation_invoice' AS rule_name,
        'cleaning_removal' AS entry_type,
        cancel_rows AS rows_removed_sequential,
        raw_cancel_rows AS rows_matched_raw,
        cancel_rev AS revenue_removed_sequential,
        base_rows - dup_rows - cancel_rows AS remaining_rows,
        base_rev - dup_rev - cancel_rev AS remaining_revenue,
        'Cancellation invoices starting with C' AS notes
    FROM audit_metrics
    UNION ALL
    SELECT
        4 AS step_order,
        'non_merchandise_stock_code' AS rule_name,
        'cleaning_removal' AS entry_type,
        fee_rows AS rows_removed_sequential,
        raw_fee_rows AS rows_matched_raw,
        fee_rev AS revenue_removed_sequential,
        base_rows - dup_rows - cancel_rows - fee_rows AS remaining_rows,
        base_rev - dup_rev - cancel_rev - fee_rev AS remaining_revenue,
        'Non merchandise fees and adjustments' AS notes
    FROM audit_metrics
    UNION ALL
    SELECT
        5 AS step_order,
        'non_positive_quantity_or_price' AS rule_name,
        'cleaning_removal' AS entry_type,
        nonpos_rows AS rows_removed_sequential,
        raw_nonpos_rows AS rows_matched_raw,
        nonpos_rev AS revenue_removed_sequential,
        base_rows - dup_rows - cancel_rows - fee_rows - nonpos_rows AS remaining_rows,
        base_rev - dup_rev - cancel_rev - fee_rev - nonpos_rev AS remaining_revenue,
        'Transactions with non positive quantity or unit price' AS notes
    FROM audit_metrics
    UNION ALL
    SELECT
        6 AS step_order,
        'missing_customer_id' AS rule_name,
        'boundary_split' AS entry_type,
        0 AS rows_removed_sequential,
        raw_guest_rows AS rows_matched_raw,
        0.0 AS revenue_removed_sequential,
        guest_rows AS remaining_rows,
        guest_rev AS remaining_revenue,
        'Boundary split: guest transactions retained in store sales but excluded from cohorts'
            AS notes
    FROM audit_metrics
    UNION ALL
    SELECT
        7 AS step_order,
        'store_valid_sales' AS rule_name,
        'output_total' AS entry_type,
        0 AS rows_removed_sequential,
        base_rows - dup_rows - cancel_rows - fee_rows - nonpos_rows AS rows_matched_raw,
        0.0 AS revenue_removed_sequential,
        base_rows - dup_rows - cancel_rows - fee_rows - nonpos_rows AS remaining_rows,
        base_rev - dup_rev - cancel_rev - fee_rev - nonpos_rev AS remaining_revenue,
        'Total store valid merchandise sales (vw_store_sales)' AS notes
    FROM audit_metrics
    UNION ALL
    SELECT
        8 AS step_order,
        'customer_valid_sales' AS rule_name,
        'output_total' AS entry_type,
        0 AS rows_removed_sequential,
        base_rows
        - dup_rows
        - cancel_rows
        - fee_rows
        - nonpos_rows
        - guest_rows AS rows_matched_raw,
        0.0 AS revenue_removed_sequential,
        base_rows - dup_rows - cancel_rows - fee_rows - nonpos_rows - guest_rows AS remaining_rows,
        base_rev - dup_rev - cancel_rev - fee_rev - nonpos_rev - guest_rev AS remaining_revenue,
        'Identified customer valid sales (vw_customer_sales)' AS notes
    FROM audit_metrics
)

INSERT INTO cleaning_audit (
    executed_at,
    step_order,
    rule_name,
    entry_type,
    rows_removed_sequential,
    rows_matched_raw,
    revenue_removed_sequential,
    remaining_rows,
    remaining_revenue,
    notes
)
SELECT
    DATETIME('now') AS executed_at,
    step_order,
    rule_name,
    entry_type,
    rows_removed_sequential,
    rows_matched_raw,
    revenue_removed_sequential,
    remaining_rows,
    remaining_revenue,
    notes
FROM audit_steps;

-- Clean up temporary storage table
DROP TABLE IF EXISTS temp_staged_lines;
