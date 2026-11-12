# 0002. Data Model and Dual View Contract

**Date**: 2026-11-11
**Status**: Accepted

## Summary

This design sets the SQLite database tables, dual denominator views (separate query layers for store total sales and identified buyer analytics), audit log, and Power BI export contract for the retail segmentation pipeline. Because roughly 23% of raw transactions lack a customer ID, keeping one unified clean table (`clean_transactions`) behind two SQL views (`vw_store_sales` and `vw_customer_sales`) keeps store revenue accurate without breaking customer cohorts or RFM scoring (Recency, Frequency, and Monetary segmentation). Defining these schemas, wholesale account flags, canonical product and country lookups, and typed Parquet export rules up front prevents breaking changes when later slices add KPIs, cohorts, clustering, and deep dives.

## Context

The UCI Online Retail II workbook (`dataset/online_retail_II.xlsx`) holds roughly `1.07 million` rows across two sheets (`Year 2009-2010` and `Year 2010-2011`) with several structural hazards. Roughly `243,000` rows lack a `Customer ID`, cancellation invoices start with `'C'`, non merchandise lines such as postage and bank charges share the same sheet as products, identical rows cross sheet boundaries, single `StockCode` values appear with multiple `Description` strings and mixed casing, single customers appear under multiple countries, and high volume wholesale accounts sit alongside ordinary retail shoppers.

Later project slices compute monthly executive KPIs, monthly acquisition cohorts, RFM quintiles, clustering validation, and product and country over indexing ratios. If Feature 4 loads and cleans data before a shared schema and boundary contract exist, store totals and customer totals risk drifting out of sync, duplicate product descriptions will split rankings in Power BI, and wholesale accounts cannot be sliced cleanly without rewriting SQL scripts and rebuilding dashboard visuals.

The project stack from [0001-stack-and-architecture.md](0001-stack-and-architecture.md) runs locally on Python `3.13.5` and SQLite `3.49.1` (`retail.db`) with `sqlfluff`, `ruff`, gradual `ty`, `pytest` synthetic fixtures, and flat typed Parquet plus CSV exports in `exports/` for Power BI Desktop. Any schema design must obey `snake_case` naming, `STRICT` SQLite type enforcement, atomic idempotent rebuilds, and safe Windows file replacement (`WinError 32` handling).

## Requirements

**User stories**:
- As a Business Analyst, I want separate store wide and identified customer views built on one consistent cleaning pipeline so that store revenue totals stay accurate while cohorts and RFM never include guest noise.
- As a downstream SQL and Python developer, I want strict schemas, canonical product and country dimensions, explicit wholesale flags, and an auditable removal waterfall so that Features 4 through 9 build without schema rewrites.
- As a Power BI report author, I want explicitly typed Parquet exports and matching CSV files so that Power BI Desktop imports exact dates, numbers, and flags without ODBC drivers or type drift.

**Acceptance criteria**:
- **AC-1**: `raw_transactions` is a `STRICT` SQLite table storing one row per Excel source row with integer `raw_id` primary key, `source_sheet`, `source_row_num`, ISO 8601 `loaded_at`, `UNIQUE (source_sheet, source_row_num)`, trimmed text `invoice`, `stock_code`, `description`, `.0` stripped nullable `customer_id` (coercing `''`, `'nan'`, `'NaN'`, `'None'`, and `'NULL'` to SQL `NULL`), integer `quantity` (coerced explicitly from pandas floats before insert), ISO 8601 `invoice_date`, and `REAL` `price`.
- **AC-2**: `clean_transactions` is a `STRICT` SQLite table containing only deduplicated positive merchandise lines (`quantity > 0`, `unit_price > 0`, `line_revenue = quantity * unit_price > 0`, non cancellation, non excluded `stock_code`), uppercased and trimmed `stock_code`, preserved `raw_description` and `transaction_country`, unique `raw_id` foreign key to `raw_transactions`, foreign keys to `dim_products` and `dim_date`, nullable foreign key `customer_id` to `dim_customers`, and `CHECK` constraints tying `is_identified_customer` (`0` or `1`) strictly to `customer_id` nullability; dimensions load before `clean_transactions` from staged valid rows so foreign keys stay enabled throughout.
- **AC-3**: Two SQL views (`vw_store_sales` and `vw_customer_sales`) use explicit column projections over `clean_transactions` joined to `dim_products`, `dim_date`, and `dim_customers`: `vw_store_sales` exposes all `clean_transactions` rows with `is_wholesale` defaulted to `0` for unidentified orders plus `transaction_country`, `primary_country`, and `country_resolved = COALESCE(dim_customers.primary_country, clean_transactions.transaction_country)`, while `vw_customer_sales` exposes only `is_identified_customer = 1` rows inner joined to `dim_customers`; Power BI mirrors this boundary over the exported star schema (`clean_transactions` unfiltered for store KPIs vs `is_identified_customer = TRUE()` for customer analytics).
- **AC-4**: `cleaning_audit` records one snapshot per run containing a `baseline` row (total raw count and signed raw net `SUM(quantity * price)`), ordered `cleaning_removal` rows (`exact_duplicate`, `cancellation_invoice`, `non_merchandise_stock_code`, `non_positive_quantity_or_price`), a `boundary_split` row (`missing_customer_id`), and `output_total` rows (`store_valid_sales`, `customer_valid_sales`), storing `rows_removed_sequential`, `rows_matched_raw`, signed `revenue_removed_sequential`, `remaining_rows`, and `remaining_revenue` (`0` and `0.0` removal defaults on `baseline` and `output_total` rows) so `remaining_rows[i] = remaining_rows[i - 1] - rows_removed_sequential[i]` and `remaining_revenue[i] = remaining_revenue[i - 1] - revenue_removed_sequential[i]` reconcile end to end.
- **AC-5**: `dim_customers` stores one row per identified `customer_id` with `primary_country` (most frequent valid value excluding nulls and `'Unspecified'`, tie broken by latest `invoice_ts` then alphabetical `country ASC`), `country_variant_count`, `first_order_date`, `cohort_month` (`YYYY-MM`), `last_order_date`, `lifetime_orders`, `lifetime_units`, `lifetime_revenue`, `avg_order_value`, `avg_units_per_order`, `is_wholesale` (`0` or `1`), and `wholesale_reason` evaluated dynamically in Python from `ref_pipeline_config` (`wholesale_rule_mode` plus active thresholds) using pipe delimited tokens (`REVENUE_THRESHOLD`, `ORDER_COUNT_THRESHOLD`, `UNITS_PER_ORDER_THRESHOLD`, or SQL `NULL` when `is_wholesale = 0`).
- **AC-6**: `dim_products` and `dim_date` eliminate split groupings: `dim_products` picks the most frequent non placeholder `description` per uppercase `stock_code` (tie broken by latest `invoice_ts` then alphabetical `description ASC`, falling back to `'UNKNOWN DESCRIPTION (' || stock_code || ')'`) alongside `description_variant_count`; `dim_date` spans `2009-12-01` through `2011-12-31` continuously with integer `date_key` (`YYYYMMDD`), `calendar_date`, `year`, `quarter`, `month`, `order_month`, `month_start_date`, ISO 8601 `day_of_week` (`1` = Monday through `7` = Sunday), `day_name`, and `is_weekend`.
- **AC-7**: `ref_excluded_stock_codes` and `ref_pipeline_config` hold active rule metadata seeded in SQL (`rfm_reference_date = '2011-12-10'`, initial wholesale thresholds `lifetime_revenue >= 10000 OR lifetime_orders >= 25 OR avg_units_per_order >= 200`, and starter non merchandise stock codes), with an explicit Feature 4 profiling check required before final cleaning runs.
- **AC-8**: `sql/00_schema.sql` executes idempotently inside an atomic SQLite transaction using reverse dependency `DROP` order (`vw_*`, `clean_transactions`, then `dim_*`, audit, config, and `raw_transactions`) with no `WAL` pragma inside the transaction, passes `sqlfluff lint sql/ --dialect sqlite`, creates covering indexes on `clean_transactions`, and pairs with `scripts/db.py:connect_db` setting `PRAGMA journal_mode = WAL`, `PRAGMA foreign_keys = ON`, and `PRAGMA busy_timeout = 5000` prior to opening transactions.
- **AC-9**: Python DB and export modules (`scripts/db.py` and `scripts/exports.py`) apply the explicit `EXPORT_SCHEMAS` `pyarrow.Schema` definitions (timezone naive `timestamp("ms")`, `date32`, `bool_`, `int64`, `float64`, `string`) when exporting `clean_transactions`, `dim_customers`, `dim_products`, `dim_date`, and `cleaning_audit` to `exports/*.parquet` and `exports/*.csv` (keeping `raw_transactions` inside `retail.db` only), writing to temporary files before atomic replacement so Windows file locks (`WinError 32`) fail loudly without leaving partial files.
- **AC-10**: Synthetic fixture tests (`pytest`) prove idempotent schema initialization (including reruns under `foreign_keys = ON`), `STRICT` and `CHECK` constraint rejection of invalid rows, pandas float to int and null string coercions, pre deduplication 8 column normalization across sheets, signed audit reconciliation (including negative cancellations), deterministic 3 key tie breaking, dual view denominators, `wholesale_reason` token grammar, and `EXPORT_SCHEMAS` Parquet typing without reading `dataset/online_retail_II.xlsx`.

## Options considered

### Option 1: Unified Clean Fact Table with Dual Views, Dimensions, and Metadata Rule Tables

Store all cleaned valid merchandise lines once in `clean_transactions` (`STRICT` table with nullable `customer_id`), project `vw_store_sales` and `vw_customer_sales` on top, materialize `dim_customers` (including `is_wholesale`), `dim_products`, and `dim_date`, and externalize excluded codes, thresholds, and removal counts in `ref_excluded_stock_codes`, `ref_pipeline_config`, and `cleaning_audit`.

**Pros**:
- Cleaning logic runs once in one place, preventing store wide and customer totals from drifting apart.
- Metadata rule tables (`ref_excluded_stock_codes`, `ref_pipeline_config`) make business thresholds inspectable as SQL data and easy to calibrate in Features 4 and 9 without schema edits.
- Star schema dimension tables plus explicit `pyarrow.Schema` exports support both aggregated BI visuals and invoice level drill through in Power BI.

**Cons**:
- Requires populating `dim_products`, `dim_customers`, and `dim_date` before inserting into `clean_transactions` because foreign keys are enforced at write time.
- Exporting the full `clean_transactions` table alongside dimensions creates larger local files in `exports/` than exporting pre aggregated marts alone.

### Option 2: Two Separate Physical Clean Tables with Inline SQL Constants

Create two physical tables (`store_valid_transactions` and `customer_valid_transactions`) without a shared base table, and embed excluded stock codes and wholesale cutoffs directly inside SQL query files.

**Pros**:
- Simple single table queries for downstream scripts with zero view joins needed at query time.
- Eliminates nullable `customer_id` foreign key handling on the customer table.

**Cons**:
- Duplicates roughly `800,000` cleaned rows on disk and duplicates filter maintenance across two physical tables.
- Scattering hardcoded stock code lists and wholesale cutoffs across SQL scripts invites drift between KPIs, RFM, and deep dive queries.

### Option 3: Customer Only Clean Table Plus Raw Store Queries

Store only rows with a non null `customer_id` inside `clean_transactions` (matching naive Step 3 tutorials) and query `raw_transactions` with ad hoc `WHERE` filters whenever store wide metrics are needed.

**Pros**:
- Minimal initial table count and fastest single table setup for cohorts and RFM.
- Every row in `clean_transactions` automatically has a non null customer foreign key.

**Cons**:
- Store wide KPI scripts must reimplement cancellation, fee, zero price, and duplicate filtering on `raw_transactions`, risking mismatched revenue totals across pages.
- Does not solve split product descriptions or mixed country labels cleanly across unidentified orders.

## Decision

**Chosen option**: Option 1: Unified Clean Fact Table with Dual Views, Dimensions, and Metadata Rule Tables

Define all `STRICT` staging, clean fact, dimension, audit, and rule metadata tables plus the `vw_store_sales` and `vw_customer_sales` dual views in `sql/00_schema.sql`, paired with typed SQLite and atomic Parquet/CSV export helpers in `scripts/db.py` and `scripts/exports.py`.

**Implementation skills**: `sqlite-best-practices` (`erayack/sqlite-best-practices`, `.agents/skills/sqlite-best-practices/`) · `sqlfluff` (`ivanshamaev/de-agent-skills`, `.agents/skills/sqlfluff/`) · `pandas-pro` (`Jeffallan/claude-skills`, `.agents/skills/pandas-pro/`) · `powerbi-modeling` (`github/awesome-copilot`, `.agents/skills/powerbi-modeling/`) · `semantic-model-authoring` (`microsoft/skills-for-fabric`, `.agents/skills/semantic-model-authoring/`)

## Rationale

The core technical force in `dataset/online_retail_II.xlsx` is that valid store revenue and identified buyer behavior diverge by roughly 23% due to missing `Customer ID` values, while both denominators depend on identical deduplication, cancellation, fee, and price cleaning rules. Placing a single normalized `clean_transactions` table beneath `vw_store_sales` and `vw_customer_sales` guarantees that store wide KPIs and customer analytics share one source of truth for what counts as valid merchandise revenue while never leaking guest transactions into cohorts or RFM.

Externalizing excluded stock codes (`ref_excluded_stock_codes`), wholesale rules and the fixed RFM reference date (`ref_pipeline_config`), and sequential plus raw overlap counts (`cleaning_audit`) addresses the operational reality of a portfolio case study built for auditability. Reviewers and downstream scripts can inspect exact rules and removal reconciliations directly in SQL tables rather than reading scattered `CASE` expressions, and Features 4 and 9 can tune cutoffs or add newly discovered fee codes without altering table definitions.

Enforcing SQLite `STRICT` tables, `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`, and explicit `pyarrow.Schema` conversions bridges SQLite's flexible typing to Power BI Desktop cleanly. Because Power BI Desktop locks files inside `exports/` when open on Windows, writing exports through temporary files before atomic replacement ensures failed refreshes never leave corrupt Parquet or CSV files behind.

## Feature design

**Data model sketch**:

| Table or View | Kind | Primary Key | Foreign Keys | Key Constraints & Grain |
|---|---|---|---|---|
| `raw_transactions` | `STRICT` table | `raw_id` (`INTEGER`) | None | `UNIQUE (source_sheet, source_row_num)`; one row per raw Excel line |
| `ref_excluded_stock_codes` | `STRICT` table | `stock_code` (`TEXT`) | None | Uppercase trimmed fee/adjustment code; `is_active IN (0, 1)` |
| `ref_pipeline_config` | `STRICT` table | `config_key` (`TEXT`) | None | Seeded key value pairs (`rfm_reference_date`, wholesale cutoffs) |
| `dim_date` | `STRICT` table | `date_key` (`INTEGER`) | None | `YYYYMMDD` PK; `calendar_date TEXT NOT NULL UNIQUE`; `2009-12-01` to `2011-12-31`; ISO `day_of_week` (`1` to `7`); `is_weekend IN (0, 1)` |
| `dim_products` | `STRICT` table | `stock_code` (`TEXT`) | None | Uppercase trimmed PK; `canonical_description TEXT NOT NULL` |
| `dim_customers` | `STRICT` table | `customer_id` (`TEXT`) | None | `.0` stripped string PK; `is_wholesale IN (0, 1)`, nullable pipe delimited `wholesale_reason` |
| `clean_transactions` | `STRICT` table | `clean_id` (`INTEGER`) | `raw_id` (unique), `stock_code`, `date_key`, nullable `customer_id` | `quantity > 0`, `unit_price > 0`, `line_revenue > 0`, strict `is_identified_customer` vs `customer_id` check |
| `cleaning_audit` | `STRICT` table | `audit_id` (`INTEGER`) | None | `UNIQUE (step_order)`, `UNIQUE (rule_name)`; `entry_type IN ('baseline', 'cleaning_removal', 'boundary_split', 'output_total')`; includes signed `remaining_revenue` |
| `vw_store_sales` | SQL `VIEW` | `clean_id` | Reads `clean_transactions` + dims (`LEFT JOIN dim_customers`) | All valid merchandise rows; unidentified rows get `is_wholesale = 0` |
| `vw_customer_sales` | SQL `VIEW` | `clean_id` | Reads `clean_transactions` + dims (`INNER JOIN dim_customers`) | Identified rows (`is_identified_customer = 1`) only |

Column definitions by entity:
- **`raw_transactions`**: `raw_id INTEGER PRIMARY KEY`, `source_sheet TEXT NOT NULL`, `source_row_num INTEGER NOT NULL`, `loaded_at TEXT NOT NULL`, `invoice TEXT`, `stock_code TEXT`, `description TEXT`, `quantity INTEGER`, `invoice_date TEXT`, `price REAL`, `customer_id TEXT`, `country TEXT`.
- **`ref_excluded_stock_codes`**: `stock_code TEXT PRIMARY KEY`, `category TEXT NOT NULL`, `reason TEXT NOT NULL`, `is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))`.
- **`ref_pipeline_config`**: `config_key TEXT PRIMARY KEY`, `config_value TEXT NOT NULL`, `value_type TEXT NOT NULL`, `description TEXT NOT NULL`.
- **`dim_date`**: `date_key INTEGER PRIMARY KEY`, `calendar_date TEXT NOT NULL UNIQUE`, `year INTEGER NOT NULL`, `quarter INTEGER NOT NULL`, `month INTEGER NOT NULL`, `order_month TEXT NOT NULL`, `month_start_date TEXT NOT NULL`, `day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7)`, `day_name TEXT NOT NULL`, `is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))`.
- **`dim_products`**: `stock_code TEXT PRIMARY KEY`, `canonical_description TEXT NOT NULL`, `description_variant_count INTEGER NOT NULL CHECK (description_variant_count >= 1)`, `first_sold_date TEXT NOT NULL`, `last_sold_date TEXT NOT NULL`.
- **`dim_customers`**: `customer_id TEXT PRIMARY KEY`, `primary_country TEXT NOT NULL`, `country_variant_count INTEGER NOT NULL CHECK (country_variant_count >= 1)`, `first_order_date TEXT NOT NULL`, `cohort_month TEXT NOT NULL`, `last_order_date TEXT NOT NULL`, `lifetime_orders INTEGER NOT NULL CHECK (lifetime_orders >= 1)`, `lifetime_units INTEGER NOT NULL CHECK (lifetime_units >= 1)`, `lifetime_revenue REAL NOT NULL CHECK (lifetime_revenue > 0)`, `avg_order_value REAL NOT NULL CHECK (avg_order_value > 0)`, `avg_units_per_order REAL NOT NULL CHECK (avg_units_per_order > 0)`, `is_wholesale INTEGER NOT NULL CHECK (is_wholesale IN (0, 1))`, `wholesale_reason TEXT`.
- **`clean_transactions`**: `clean_id INTEGER PRIMARY KEY`, `raw_id INTEGER NOT NULL UNIQUE REFERENCES raw_transactions(raw_id)`, `invoice TEXT NOT NULL`, `stock_code TEXT NOT NULL REFERENCES dim_products(stock_code)`, `raw_description TEXT`, `quantity INTEGER NOT NULL CHECK (quantity > 0)`, `unit_price REAL NOT NULL CHECK (unit_price > 0)`, `line_revenue REAL NOT NULL CHECK (line_revenue > 0)`, `invoice_ts TEXT NOT NULL`, `order_date TEXT NOT NULL`, `order_month TEXT NOT NULL`, `date_key INTEGER NOT NULL REFERENCES dim_date(date_key)`, `customer_id TEXT REFERENCES dim_customers(customer_id)`, `transaction_country TEXT NOT NULL`, `is_identified_customer INTEGER NOT NULL CHECK (is_identified_customer IN (0, 1))`, `CHECK ((is_identified_customer = 1 AND customer_id IS NOT NULL) OR (is_identified_customer = 0 AND customer_id IS NULL))`.
- **`cleaning_audit`**: `audit_id INTEGER PRIMARY KEY`, `executed_at TEXT NOT NULL`, `step_order INTEGER NOT NULL UNIQUE`, `rule_name TEXT NOT NULL UNIQUE`, `entry_type TEXT NOT NULL CHECK (entry_type IN ('baseline', 'cleaning_removal', 'boundary_split', 'output_total'))`, `rows_removed_sequential INTEGER NOT NULL CHECK (rows_removed_sequential >= 0)`, `rows_matched_raw INTEGER NOT NULL CHECK (rows_matched_raw >= 0)`, `revenue_removed_sequential REAL NOT NULL`, `remaining_rows INTEGER NOT NULL CHECK (remaining_rows >= 0)`, `remaining_revenue REAL NOT NULL`, `notes TEXT`.

Indexes on `clean_transactions`:
- `idx_clean_customer_month ON clean_transactions (customer_id, order_month)`
- `idx_clean_order_month ON clean_transactions (order_month)`
- `idx_clean_stock_code ON clean_transactions (stock_code)`
- `idx_clean_date_key ON clean_transactions (date_key)`
- `idx_clean_invoice ON clean_transactions (invoice)`

Idempotent drop order and load sequence:
- `sql/00_schema.sql` drops views then tables in reverse foreign key dependency order (`vw_customer_sales`, `vw_store_sales`, `clean_transactions`, `dim_customers`, `dim_products`, `dim_date`, `cleaning_audit`, `ref_pipeline_config`, `ref_excluded_stock_codes`, `raw_transactions`) so reruns succeed with `PRAGMA foreign_keys = ON`.
- To avoid a circular foreign key deadlock during Feature 4 rebuilds, valid merchandise rows are staged first (in Python or a temporary SQLite staging table) to compute and insert `dim_date`, `dim_products`, and `dim_customers` before inserting `clean_transactions`.

Exact SQL dual view projections:

```sql
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
    dc.primary_country,
    COALESCE(dc.primary_country, ct.transaction_country) AS country_resolved,
    ct.is_identified_customer,
    COALESCE(dc.is_wholesale, 0) AS is_wholesale,
    dc.wholesale_reason
FROM clean_transactions AS ct
INNER JOIN dim_products AS dp
    ON ct.stock_code = dp.stock_code
INNER JOIN dim_date AS dd
    ON ct.date_key = dd.date_key
LEFT JOIN dim_customers AS dc
    ON ct.customer_id = dc.customer_id;

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
```

Explicit `EXPORT_SCHEMAS` mapping (`scripts/exports.py`, timezone naive `timestamp("ms")` for Power BI compatibility):
- **`clean_transactions`**: `clean_id` (`int64`), `raw_id` (`int64`), `invoice` (`string`), `stock_code` (`string`), `raw_description` (`string`), `quantity` (`int64`), `unit_price` (`float64`), `line_revenue` (`float64`), `invoice_ts` (`timestamp("ms")`), `order_date` (`date32`), `order_month` (`string`), `date_key` (`int64`), `customer_id` (`string`), `transaction_country` (`string`), `is_identified_customer` (`bool_`).
- **`dim_customers`**: `customer_id` (`string`), `primary_country` (`string`), `country_variant_count` (`int64`), `first_order_date` (`date32`), `cohort_month` (`string`), `last_order_date` (`date32`), `lifetime_orders` (`int64`), `lifetime_units` (`int64`), `lifetime_revenue` (`float64`), `avg_order_value` (`float64`), `avg_units_per_order` (`float64`), `is_wholesale` (`bool_`), `wholesale_reason` (`string`).
- **`dim_products`**: `stock_code` (`string`), `canonical_description` (`string`), `description_variant_count` (`int64`), `first_sold_date` (`date32`), `last_sold_date` (`date32`).
- **`dim_date`**: `date_key` (`int64`), `calendar_date` (`date32`), `year` (`int64`), `quarter` (`int64`), `month` (`int64`), `order_month` (`string`), `month_start_date` (`date32`), `day_of_week` (`int64`), `day_name` (`string`), `is_weekend` (`bool_`).
- **`cleaning_audit`**: `audit_id` (`int64`), `executed_at` (`timestamp("ms")`), `step_order` (`int64`), `rule_name` (`string`), `entry_type` (`string`), `rows_removed_sequential` (`int64`), `rows_matched_raw` (`int64`), `revenue_removed_sequential` (`float64`), `remaining_rows` (`int64`), `remaining_revenue` (`float64`), `notes` (`string`).

**State transitions**: Not applicable. Pipeline runs perform a full idempotent atomic rebuild rather than mutating row lifecycle states.

**API surface** (SQL schema & Python contract modules):

| Surface | Type | Key Inputs | Key Outputs | Auth | Key Errors |
|---|---|---|---|---|---|
| `sql/00_schema.sql` | Idempotent SQLite script | `retail.db` connection | Drops and creates all 8 `STRICT` tables, 5 indexes, 2 dual views, and reference seeds | Local file | SQLite constraint or syntax error rolls back transaction |
| `scripts.db.connect_db` | Python helper | `db_path: Path` | `sqlite3.Connection` with `PRAGMA journal_mode = WAL`, `PRAGMA foreign_keys = ON`, and `PRAGMA busy_timeout = 5000` set before transactions | Local file | `FileNotFoundError` on invalid parent dir, `sqlite3.OperationalError` on lock |
| `scripts.db.initialize_schema` | Python helper | `conn: sqlite3.Connection`, `schema_sql_path: Path` | Executes `00_schema.sql` atomically inside one transaction | Local file | `FileNotFoundError` if SQL path missing; rolls back on SQL failure |
| `scripts.db.verify_schema_contract` | Python helper | `conn: sqlite3.Connection` | Dict summary verifying all 8 tables, 2 views, indexes, and required config keys exist | Local file | `RuntimeError` naming missing table, view, index, or seed key |
| `scripts.exports.export_table_pair` | Python helper | `conn`, `relation_name`, `export_dir`, `pa_schema` | Atomically writes `<name>.parquet` (strict `EXPORT_SCHEMAS` `pyarrow.Schema`) and `<name>.csv` | Local file | `ValueError` on unknown relation or schema mismatch; `PermissionError` naming locked file on `WinError 32` |

**Value sourcing** (every value downstream slices must produce, compute, or display traces to a named source):

| Downstream Consumer / Action | Value Produced / Displayed | Source |
|---|---|---|
| Feature 4: Staging normalization | Clean raw strings and strict integer `quantity` | Excel cells trimmed; `customer_id` `.0` stripped and `''`/`'nan'`/`'NaN'`/`'None'`/`'NULL'` coerced to SQL `NULL`; `quantity` cast to nullable `int` before `STRICT` insert |
| Feature 4: Deduplication | Unique 8 column business tuple keeping `MIN(raw_id)` | Normalized `raw_transactions` excluding `source_sheet`: `(TRIM(invoice), UPPER(TRIM(stock_code)), TRIM(COALESCE(description, '')), quantity, invoice_date, price, COALESCE(TRIM(customer_id), ''), TRIM(COALESCE(country, '')))` |
| Feature 4: Cleaning audit waterfall | `rows_removed_sequential`, `rows_matched_raw`, `revenue_removed_sequential`, `remaining_rows`, `remaining_revenue` | Baseline (`raw_transactions` count and net `SUM(quantity * price)`) minus sequential steps (`exact_duplicate` -> `cancellation_invoice` -> `non_merchandise_stock_code` -> `non_positive_quantity_or_price`) and `missing_customer_id` boundary split |
| Feature 5: Store wide KPIs | Monthly revenue, distinct orders, store AOV | `vw_store_sales.line_revenue`, `COUNT(DISTINCT vw_store_sales.invoice)`, `SUM(line_revenue) / COUNT(DISTINCT invoice)` grouped by `vw_store_sales.order_month` |
| Feature 5: Customer KPIs | Active customers, revenue per customer, repeat rate | `vw_customer_sales.customer_id`, `vw_customer_sales.line_revenue`, `vw_customer_sales.invoice` |
| Feature 6: Monthly cohorts | `cohort_month`, `cohort_index`, retained customer % | `vw_customer_sales.cohort_month`, `vw_customer_sales.order_month`, integer month diff `(year_diff * 12 + month_diff)` |
| Feature 7: RFM scoring | Fixed reference date, R/F/M metrics | `ref_pipeline_config` (`rfm_reference_date = '2011-12-10'`), `vw_customer_sales` (`order_date`, `invoice`, `line_revenue`) |
| Feature 8: Clustering & wholesale audit | Wholesale vs retail customer flag and trigger reason | `dim_customers.is_wholesale`, `dim_customers.wholesale_reason` (`REVENUE_THRESHOLD`, `ORDER_COUNT_THRESHOLD`, `UNITS_PER_ORDER_THRESHOLD` joined by `|`, or `NULL`) computed in Python from `ref_pipeline_config` |
| Feature 9: Product & country deep dives | Canonical product label, country label, wholesale slice | `vw_store_sales.canonical_description`, `vw_store_sales.transaction_country`, `vw_store_sales.country_resolved`, `vw_store_sales.is_wholesale` (default `0` for guests) |
| Power BI star schema consumption | Store wide vs customer metrics, resolved country, native column types | `exports/*.parquet` matching `EXPORT_SCHEMAS`; store measures scan `clean_transactions` unfiltered (`COALESCE(RELATED(dim_customers[primary_country]), clean_transactions[transaction_country])`), while customer measures filter `clean_transactions[is_identified_customer] = TRUE()` |

**Key invariants**:
- **Denominator parity**: `COUNT(*) FROM vw_store_sales` equals `COUNT(*) FROM clean_transactions`; `COUNT(*) FROM vw_customer_sales` equals `COUNT(*) FROM clean_transactions WHERE is_identified_customer = 1`.
- **Audit waterfall conservation**: For every step `i >= 1`, `remaining_rows[i] = remaining_rows[i - 1] - rows_removed_sequential[i]` and `remaining_revenue[i] = remaining_revenue[i - 1] - revenue_removed_sequential[i]`, where cancellations carry negative signed `revenue_removed_sequential` so subtracting them cleanly reconciles net raw revenue to positive gross valid merchandise sales.
- **Load order under foreign keys**: Dimension tables (`dim_date`, `dim_products`, `dim_customers`) load from staged valid rows prior to inserting `clean_transactions` while `PRAGMA foreign_keys = ON` stays enabled.
- **Nullability coupling**: `is_identified_customer = 1` if and only if `customer_id IS NOT NULL`, enforced by SQLite `CHECK` constraint.
- **Line revenue exactness**: `line_revenue` stores exact `REAL` `quantity * unit_price` (no early line level rounding), preserving sub penny unit prices.
- **Deterministic canonical tie breaking**: `dim_products.canonical_description` and `dim_customers.primary_country` exclude `NULL` and placeholders (`'?'`, `''`, `'Unspecified'`), ranking by `frequency DESC, latest_invoice_ts DESC, label ASC` (falling back to `'UNKNOWN DESCRIPTION (' || stock_code || ')'` or `'Unspecified'` only if no valid label exists).
- **Wholesale token grammar**: `wholesale_reason` contains sorted pipe delimited codes (`REVENUE_THRESHOLD`, `ORDER_COUNT_THRESHOLD`, `UNITS_PER_ORDER_THRESHOLD`) evaluated dynamically in Python using `ref_pipeline_config.wholesale_rule_mode`, or SQL `NULL` when `is_wholesale = 0`.
- **Starter reference seeds and verification**: `ref_excluded_stock_codes` seeds known Online Retail II non product codes (`POST`, `D`, `M`, `DOT`, `BANK CHARGES`, `CRUK`, `B`, `C2`, `AMAZONFEE`, `S`, `TEST001`, `TEST002`), and Feature 4 profiles all distinct non numeric `stock_code` values in `raw_transactions` to confirm or extend this table before finalizing cleaned exports.

**Security model**:
- Local single analyst workflow with no user authentication or multi tenant isolation needed.
- `dataset/online_retail_II.xlsx` is accessed strictly read only and never modified or committed.
- `retail.db` (plus `-wal` and `-shm` sidecar files) and `exports/` remain excluded from Git via `.gitignore` (from spec 0001).
- Contains only opaque numeric `customer_id` and `country` with zero personal names, emails, or payment credentials.

**Configuration required**:
- No environment variables or external secrets required.
- Seeded configuration keys in `ref_pipeline_config`:
  - `rfm_reference_date` = `'2011-12-10'` (`date`, fixed RFM cutoff one day after max dataset timestamp)
  - `wholesale_min_lifetime_revenue` = `'10000'` (`real`, initial cutoff in GBP, subject to Feature 4 and Feature 9 calibration)
  - `wholesale_min_orders` = `'25'` (`integer`, initial cutoff on distinct valid invoices)
  - `wholesale_min_avg_units_per_order` = `'200'` (`real`, initial cutoff on mean quantity per distinct invoice)
  - `wholesale_rule_mode` = `'OR'` (`text`, combination operator read by Python dimension builder)

**Critical test scenarios**:
- Happy path: connect via `connect_db` (verifying `WAL` and `foreign_keys = ON` outside transaction), execute `sql/00_schema.sql` twice idempotently, stage and load synthetic `raw_transactions`, dimensions, `clean_transactions`, and `cleaning_audit`, verify exact `vw_store_sales` and `vw_customer_sales` projections and signed audit math, and export all 5 relations cleanly to Parquet and CSV (`AC-1`, `AC-2`, `AC-3`, `AC-4`, `AC-5`, `AC-6`, `AC-7`, `AC-8`, `AC-9`, `AC-10`).
- Constraint and coercion failure cases: reject non positive `quantity` or `unit_price`, reject mismatched `is_identified_customer = 1` with `customer_id IS NULL`, reject missing FK parent in `dim_products` or `dim_date`, verify pandas float `12.0` quantity coercion and `'nan'` `customer_id` null coercion, and verify `STRICT` type enforcement (`AC-1`, `AC-2`, `AC-8`, `AC-10`).
- Edge case normalization, tie breaking, and token grammar: normalize `'85123a'` and `'85123A'` plus `'13085.0'` across sheets before 8 column duplicate removal, verify signed `remaining_revenue` reconciliation across a negative cancellation row, confirm 3 way deterministic tie break (`frequency DESC, latest_invoice_ts DESC, label ASC`), verify `'UNKNOWN DESCRIPTION (<code>)'` fallback, and check multi trigger `wholesale_reason` pipe formatting (`AC-4`, `AC-5`, `AC-6`, `AC-10`).
- File lock failure case: simulate a `PermissionError` (`WinError 32`) during export atomic swap and confirm the helper raises a clear error naming the locked path while leaving existing `.parquet` and `.csv` files intact (`AC-9`, `AC-10`).

## Build plan

Ordered following the project's **Tracer Bullet** approach (stand up an executable end to end schema and DB connection slice first, then thicken dual views, rule seeds, typed exports, and full contract verification):

1. [x] Write `sql/00_schema.sql` with reverse dependency `DROP VIEW IF EXISTS` and `DROP TABLE IF EXISTS` DDL for `raw_transactions`, `ref_excluded_stock_codes`, `ref_pipeline_config`, `dim_date`, `dim_products`, `dim_customers`, `clean_transactions` (including `STRICT`, `CHECK`, FK, and covering indexes), and `cleaning_audit` (including `remaining_revenue`), without `PRAGMA journal_mode = WAL` inside the SQL script, and validate with `sqlfluff`, satisfies **AC-1**, **AC-2**, **AC-4**, **AC-7**, **AC-8**.
2. [x] Add the explicit `CREATE VIEW` definitions for `vw_store_sales` and `vw_customer_sales` plus initial `INSERT` seeds for `ref_excluded_stock_codes` and `ref_pipeline_config` to `sql/00_schema.sql`, confirming fallback expressions and config defaults, satisfies **AC-3**, **AC-5**, **AC-6**, **AC-7**.
3. [x] Implement `scripts/db.py` (`connect_db`, `initialize_schema`, `verify_schema_contract`) setting `PRAGMA journal_mode = WAL`, `PRAGMA foreign_keys = ON`, and `PRAGMA busy_timeout = 5000` on the connection prior to transactions, executing `sql/00_schema.sql` atomically, and failing loudly on missing contract objects, satisfies **AC-8**, **AC-10**.
4. [x] Implement `scripts/exports.py` (`EXPORT_SCHEMAS` explicit `pyarrow.Schema` registry with timezone naive `timestamp("ms")` and `export_table_pair` temp file atomic swap with `WinError 32` lock diagnostics) covering `clean_transactions`, `dim_customers`, `dim_products`, `dim_date`, and `cleaning_audit` while excluding `raw_transactions`, satisfies **AC-9**.
5. [x] Build `tests/fixtures/` synthetic SQLite transaction fixture and `tests/test_data_model.py` covering idempotent reruns under `foreign_keys = ON`, `STRICT` and `CHECK` rejections, pandas float/null coercions, 8 column normalization/tie breaking, signed audit reconciliation across negative cancellations, dual view projections, `wholesale_reason` tokens, atomic export locking, and `EXPORT_SCHEMAS` Parquet typing, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**, **AC-8**, **AC-9**, **AC-10**.

## Consequences

**Positive**:
- Store wide KPIs and customer analytics share one deduplicated, cleaned base (`clean_transactions`) with zero duplicated cleaning logic.
- Downstream Features 4 through 9 inherit stable column names, canonical descriptions, resolved primary countries, wholesale flags, and typed Parquet exports with no breaking schema changes.
- Every removed row and boundary split is quantitatively reconciled from raw Excel counts down to `vw_store_sales` and `vw_customer_sales`.

**Negative / tradeoffs**:
- Dimension tables (`dim_products`, `dim_customers`, `dim_date`) must be computed from staged valid rows and loaded before `clean_transactions` on every rebuild due to enforced foreign keys.
- Rebuilding the full database atomically replaces prior `cleaning_audit` snapshots, so historical tuning comparisons require reading git commits or docs rather than querying old audit rows in SQLite.
- Exporting the full `clean_transactions` table to both Parquet and CSV adds local disk usage in `exports/` and increases refresh time when Power BI Desktop holds file locks.

**Neutral**:
- Initial wholesale cutoffs in `ref_pipeline_config` (`10,000` GBP revenue, `25` orders, `200` units per order) and starter excluded stock codes serve as explicit baseline contracts that Feature 4 and Feature 9 will verify and calibrate against real data distributions.

## Follow-up

- [ ] In Feature 4 (`Data ingestion and cleaning pipeline`), query all distinct non numeric `stock_code` values in `raw_transactions` to verify and extend `ref_excluded_stock_codes` before finalizing `clean_transactions`.
- [ ] In Feature 4 or Feature 9 (`Product and country deep dive plus wholesale audit`), inspect the actual `dim_customers` spend, frequency, and units per order percentiles and update `ref_pipeline_config` wholesale thresholds if initial baseline cutoffs over or under flag B2B accounts.
- [ ] Note: Sequential cleaning waterfall order is set to `exact_duplicate` -> `cancellation_invoice` -> `non_merchandise_stock_code` -> `non_positive_quantity_or_price` (runner up: placing `exact_duplicate` last), while `rows_matched_raw` preserves raw overlap counts regardless of order.
