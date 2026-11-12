# 0003. Data Ingestion and Cleaning Pipeline

**Date**: 2026-11-12
**Status**: In Progress

## Summary

This decision sets the design for loading and cleaning the two year retail transaction dataset into SQLite. The pipeline reads the raw Excel workbook safely into staging, applies ordered cleaning rules inside SQLite, populates canonical dimensions, records an exact row removal audit log, and refreshes Power BI exports. Using a single Python command with modular SQL scripts keeps execution repeatable and fast without modifying the original spreadsheet.

## Requirements

**User stories**:
- As a Data Analyst, I want raw Excel sheets loaded safely into an immutable staging table so that the source workbook is never modified and every raw row can be queried for verification.
- As an Analytics Engineer, I want explicit cleaning transformations and canonical dimension population running inside SQLite so that deduplication, cancellation filtering, fee exclusion, and tie breaking run repeatably.
- As a Business Stakeholder, I want an exact sequential audit table showing initial row counts, removals per rule, signed revenue impacts, and final view totals so that every removed pound of revenue is accounted for.

**Acceptance criteria**:
- **AC-1**: `scripts/load_to_sql.py` validates the existence of `dataset/online_retail_II.xlsx` and its two expected sheets, parses each sheet into memory using pandas with the openpyxl engine, coerces types safely (trimming text, coercing customer identifiers to clean strings while converting empty or NaN strings to SQL null, casting integer quantities, and assigning 1 based physical Excel row numbers to `source_row_num`), and inserts into `raw_transactions` in 50,000 row batches inside an explicit transaction.
- **AC-2**: The pipeline generates a continuous `dim_date` dimension spanning `2009-12-01` through `2011-12-31` with integer `date_key` (`YYYYMMDD`), calendar attributes, and weekend flags before loading cleaned transactions.
- **AC-3**: Exact duplicate rows matching across all eight normalized attributes (`TRIM(invoice)`, `UPPER(TRIM(stock_code))`, `COALESCE(TRIM(description), '')`, `quantity`, `invoice_date`, `price`, `COALESCE(TRIM(customer_id), '')`, `COALESCE(TRIM(country), '')`) are deduplicated, keeping the row with the lowest `raw_id`.
- **AC-4**: Cancellation invoices (where `invoice` starts with `C` or `c`) and transactions with non positive quantities or prices (`quantity <= 0 OR price <= 0`) are filtered out of merchandise sales, with their counts and signed revenue recorded in the audit log.
- **AC-5**: Non merchandise adjustment and fee lines matching active codes in `ref_excluded_stock_codes` (including `POST`, `D`, `M`, `BANK CHARGES`, `CRUK`, `PADS`, `DOT`, `ADJUST`) are excluded from merchandise sales.
- **AC-6**: Transactions lacking a customer identifier (`customer_id IS NULL`) are isolated in the audit waterfall as a boundary split; these rows are retained in `clean_transactions` for store total sales (`vw_store_sales`) but excluded from identified customer analytics (`vw_customer_sales`).
- **AC-7**: `cleaning_audit` records a complete waterfall snapshot of eight sequential steps (`1: baseline`, `2: exact_duplicate`, `3: cancellation_invoice`, `4: non_merchandise_stock_code`, `5: non_positive_quantity_or_price`, `6: missing_customer_id`, `7: store_valid_sales`, `8: customer_valid_sales`) with exact arithmetic reconciliation where `remaining_rows[i] = remaining_rows[i - 1] - rows_removed_sequential[i]` and `remaining_revenue[i] = remaining_revenue[i - 1] - revenue_removed_sequential[i]` for steps 2 through 5, while capturing raw matches in `rows_matched_raw`.
- **AC-8**: `dim_products` and `dim_customers` are populated deterministically from staged valid transactions using three key tie breaking (frequency desc, latest invoice date desc, alphabetical asc) and wholesale rule evaluation before inserting rows into `clean_transactions`.
- **AC-9**: `scripts/load_to_sql.py` provides a unified command line interface supporting `--stage-only`, `--clean-only`, `--rebuild`, and automatic export invocation via `scripts/exports.py` unless `--no-export` is passed, rejecting conflicting argument combinations.
- **AC-10**: Synthetic fixture tests in `tests/test_data_ingestion.py` verify workbook loading, date dimension generation, duplicate deduplication, cancellation filtering, fee exclusion, audit arithmetic, and export execution without reading the heavy 45MB Excel workbook.

## Decision

**Chosen option**: Option 1: Hybrid Python Staging with In Database SQL Transformation and Automatic Exports

We will implement data extraction and staging in `scripts/load_to_sql.py`, date dimension seeding in Python, cleaning and candidate extraction in `sql/01_data_cleaning.sql`, dimension derivation with dynamic wholesale evaluation in Python, and automated export refreshes in `scripts/exports.py`.

**Implementation skills**: `sqlite-best-practices` (`erayack/sqlite-best-practices`, `.agents/skills/sqlite-best-practices/`) · `sqlfluff` (`ivanshamaev/de-agent-skills`, `.agents/skills/sqlfluff/`) · `pandas-pro` (`jeffallan/claude-skills`, `.agents/skills/pandas-pro/`) · `xlsx` (`anthropics/skills`, `.agents/skills/xlsx/`)

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:

The pipeline interacts with the tables and views defined in `sql/00_schema.sql`:

| Table or View | Operation | Content |
|---|---|---|
| `raw_transactions` | Insert / Append | Immutable raw staging rows from both workbook sheets |
| `ref_excluded_stock_codes` | Read / Seed | Active non merchandise fee and adjustment codes |
| `ref_pipeline_config` | Read | Wholesale thresholds and reference parameters |
| `dim_date` | Insert | Complete daily calendar table (2009-12-01 to 2011-12-31) |
| `dim_products` | Insert | Distinct stock codes with canonical descriptions and variants |
| `dim_customers` | Insert | Identified customers with primary country, lifetime metrics, and wholesale flag |
| `clean_transactions` | Insert | Deduplicated valid merchandise sales lines |
| `cleaning_audit` | Insert | Exact sequential row removal and revenue waterfall log |
| `vw_store_sales` | Query / View | Store total sales including guest transactions |
| `vw_customer_sales` | Query / View | Identified customer sales for cohorts and segmentation |

**State transitions**:

```text
Raw Excel Sheets (Year 2009-2010, Year 2010-2011)
  │
  ▼ (scripts/load_to_sql.py: stage_raw_data)
raw_transactions (Staging table, STRICT, indexed)
  │
  ▼ (scripts/db.py: seed_dim_date)
dim_date (Calendar dimension table, 2009-12-01 to 2011-12-31)
  │
  ▼ (sql/01_data_cleaning.sql: deduplication CTE)
Candidate clean records (Lowest raw_id per normalized 8 attribute tuple)
  │
  ▼ (sql/01_data_cleaning.sql + Python wholesale evaluator)
dim_products + dim_customers (Canonical tie breaking + wholesale flags)
  │
  ▼ (sql/01_data_cleaning.sql: clean fact load)
clean_transactions (Valid merchandise sales with foreign keys)
  │
  ▼ (sql/01_data_cleaning.sql: waterfall logging)
cleaning_audit (Sequential removal rows, baseline, boundary split, output totals)
  │
  ▼ (scripts/exports.py: export_all)
exports/*.parquet + exports/*.csv (Power BI star schema files)
```

**API surface**:

CLI interface provided by `scripts/load_to_sql.py`:

| Command / Flag | Purpose | Default | Key Errors |
|---|---|---|---|
| `python scripts/load_to_sql.py` | Full pipeline: stage if raw_transactions empty, seed date dim, clean, export | Normal run | File missing, schema invalid |
| `--stage-only` | Run Excel extraction and stage rows into `raw_transactions` only | False | Sheet missing, column mismatch |
| `--clean-only` | Run SQL cleaning and export without reading Excel workbook | False | `raw_transactions` is empty |
| `--rebuild` | Drop existing data, reinitialize schema, and rerun from scratch | False | Database locked |
| `--no-export` | Skip Parquet and CSV export generation upon completion | False | None |
| `--db-path <path>` | Target SQLite database path | `retail.db` | Directory unwritable |
| `--excel-path <path>` | Source Excel file path | `dataset/online_retail_II.xlsx` | File not found |

Mutually exclusive flag handling: `--stage-only` and `--clean-only` cannot be used together. `--rebuild` combined with `--clean-only` is rejected because a rebuild wipes staging data.

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Staging | `source_sheet`, `source_row_num` | Sheet name string and physical 1 based Excel row index (`row_idx + 2`) |
| Staging | `loaded_at` | Python `datetime.now(timezone.utc).isoformat()` |
| Date dim | `date_key`, `calendar_date`, `day_of_week` | Generated continuous calendar: `date_key = YYYYMMDD`, ISO day of week 1 to 7 |
| Clean fact | `invoice_ts` | ISO 8601 string parsed from `invoice_date` (`YYYY-MM-DD HH:MM:SS`) |
| Clean fact | `order_date`, `order_month` | `SUBSTR(invoice_ts, 1, 10)` and `SUBSTR(invoice_ts, 1, 7)` |
| Clean fact | `date_key` | `CAST(STRFTIME('%Y%m%d', order_date) AS INTEGER)` |
| Clean fact | `transaction_country` | `COALESCE(NULLIF(TRIM(country), ''), 'Unspecified')` |
| Clean fact | `stock_code` | `UPPER(TRIM(stock_code))` |
| Clean fact | `line_revenue` | Exact `quantity * unit_price` as `REAL` (no early line level rounding) |
| Deduplication | Deduplicated records | Lowest `raw_id` grouped by normalized 8 attributes |
| Product dim | `canonical_description` | Most frequent description, tie broken by latest date and alphabetical sort; fallback `'UNKNOWN DESCRIPTION (' || stock_code || ')'` |
| Product dim | `description_variant_count` | `COUNT(DISTINCT raw_description)` |
| Product dim | `first_sold_date`, `last_sold_date` | `MIN(order_date)` and `MAX(order_date)` |
| Customer dim | `primary_country` | Most frequent country (excluding null/Unspecified), tie broken by latest date and alphabetical sort |
| Customer dim | `country_variant_count` | `COUNT(DISTINCT transaction_country)` |
| Customer dim | `first_order_date`, `last_order_date` | `MIN(order_date)` and `MAX(order_date)` |
| Customer dim | `cohort_month` | Minimum `order_month` (`YYYY-MM`) from valid transactions |
| Customer dim | `lifetime_orders` | `COUNT(DISTINCT invoice)` |
| Customer dim | `lifetime_units`, `lifetime_revenue` | `SUM(quantity)` and `SUM(line_revenue)` |
| Customer dim | `avg_order_value`, `avg_units_per_order` | `lifetime_revenue / lifetime_orders` and `CAST(lifetime_units AS REAL) / lifetime_orders` |
| Customer dim | `is_wholesale`, `wholesale_reason` | Evaluated against `ref_pipeline_config` threshold tokens in Python |
| Audit step 1 | `baseline` | Step 1, type `baseline`: total raw count and signed raw sum (`SUM(quantity * price)`); removals `0` and `0.0` |
| Audit step 2 | `exact_duplicate` | Step 2, type `cleaning_removal`: sequential rows and revenue removed by full 8 attribute duplicate match |
| Audit step 3 | `cancellation_invoice` | Step 3, type `cleaning_removal`: sequential rows and negative revenue removed by `invoice LIKE 'C%'` or `'c%'` |
| Audit step 4 | `non_merchandise_stock_code` | Step 4, type `cleaning_removal`: sequential rows and revenue removed matching `ref_excluded_stock_codes` |
| Audit step 5 | `non_positive_quantity_or_price` | Step 5, type `cleaning_removal`: sequential rows and revenue removed where `quantity <= 0 OR price <= 0` |
| Audit step 6 | `missing_customer_id` | Step 6, type `boundary_split`: count and revenue of valid merchandise rows with null customer id; removals `0` and `0.0` |
| Audit step 7 | `store_valid_sales` | Step 7, type `output_total`: total valid merchandise rows and revenue in `clean_transactions`; removals `0` and `0.0` |
| Audit step 8 | `customer_valid_sales` | Step 8, type `output_total`: valid identified rows and revenue (`is_identified_customer = 1`); removals `0` and `0.0` |
| Audit metrics | `rows_matched_raw` | Count of raw rows matching the rule condition independently before sequential exclusion |
| Audit metrics | `rows_removed_sequential` | Count of rows removed at this exact sequential step |
| Audit metrics | `revenue_removed_sequential` | Signed sum of line revenue removed at this exact sequential step |
| Audit metrics | `remaining_rows`, `remaining_revenue` | Cumulative count and revenue remaining after this sequential step |

**Key invariants**:
- The raw source Excel workbook in `dataset/` is strictly read only; no script ever opens it for writing.
- Deduplication is deterministic: repeating the run always selects identical `raw_id` records.
- Foreign key integrity is strictly enforced with `PRAGMA foreign_keys = ON` throughout cleaning.
- Cleaning idempotency: table resets execute in reverse foreign key order (`DELETE FROM clean_transactions; DELETE FROM dim_customers; DELETE FROM dim_products; DELETE FROM cleaning_audit;`).
- `cleaning_audit` reconciliation must balance to zero discrepancy: `remaining_rows[i] = remaining_rows[i - 1] - rows_removed_sequential[i]` for cleaning steps 2 through 5.
- `clean_transactions` contains only positive quantities and positive unit prices (`quantity > 0 AND unit_price > 0`).
- Line revenue preserves exact `REAL` arithmetic without early line level rounding.

**Security model**:
- All operations run locally on the developer workstation.
- No network requests, external APIs, cloud credentials, or secrets are used or stored.
- Database access uses standard local file permissions.

**Configuration required**:
- No external environment variables required. Pipeline parameters and thresholds are read directly from `ref_pipeline_config` and `ref_excluded_stock_codes` inside `retail.db`.

**Critical test scenarios**:
- Happy path: run full ingestion and cleaning against synthetic fixtures, verifying all clean transactions, dimensions, and audit entries populate correctly, verifying **AC-1**, **AC-2**, **AC-3**, **AC-7**, **AC-8**, **AC-9**.
- Missing workbook failure: verify pipeline raises an explicit informative error when the Excel workbook or required sheet is missing, verifying **AC-1**.
- Fee exclusion and cancellation isolation: verify cancellations and fee codes are excluded from `clean_transactions` and logged in `cleaning_audit`, verifying **AC-4**, **AC-5**.
- Audit waterfall reconciliation: verify that baseline minus sequential removals matches remaining rows and revenue, verifying **AC-7**.
- Deterministic tie breaking: verify that products and customers with multiple variants resolve to predictable canonical values, verifying **AC-8**.

## Build plan

Order of execution follows our vertical Tracer Bullet approach: build the core loading and cleaning thread end to end first, then add robust CLI controls, validation tests, and export integration.

1. [x] Create `sql/01_data_cleaning.sql` with idempotent CTE queries implementing deduplication, non merchandise code exclusion, cancellation isolation, clean transaction insertion, and sequential audit logging, satisfies **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**.
2. [x] Implement date dimension generation in `scripts/db.py` populating continuous `dim_date` records from 2009-12-01 to 2011-12-31, satisfies **AC-2**.
3. [x] Implement `scripts/load_to_sql.py` Excel reading, type coercion, batch staging into `raw_transactions`, dimension derivation with dynamic wholesale evaluation, and CLI flag orchestration, satisfies **AC-1**, **AC-8**, **AC-9**.
4. [x] Wire automatic export triggers in `scripts/load_to_sql.py` calling `scripts/exports.py:export_all` unless `--no-export` is set, satisfies **AC-9**.
5. [x] Add comprehensive synthetic fixture tests in `tests/test_data_ingestion.py` covering pre flight checks, deduplication, cancellation removal, fee exclusion, audit reconciliation, and CLI flags, satisfies **AC-10**.

## Consequences

**Positive**:
- Repeatable, automated loading from raw Excel to queryable star schema in under two minutes.
- Clear separation between raw extraction in Python and business transformation in SQL.
- Complete auditability with verified row and revenue tracking at every stage.
- Zero manual steps required between loading data and refreshing Power BI reports.

**Negative / tradeoffs**:
- Loading one million rows from Excel into SQLite takes memory and roughly 30 to 60 seconds on initial ingestion.
- Storing both `raw_transactions` and `clean_transactions` in SQLite increases local database file size to roughly 150MB to 200MB.

**Neutral**:
- Developers must run `uv run sqlfluff lint sql/ --dialect sqlite` when editing `sql/01_data_cleaning.sql`.

## Follow-up

- [x] Execute `python scripts/load_to_sql.py` against the real `dataset/online_retail_II.xlsx` workbook during implementation to verify memory usage and real world load time (completed: 1,067,371 rows staged, 1,003,420 valid lines cleaned, 5 tables exported in ~5 minutes).
- [x] Inspect the resulting `cleaning_audit` table on the real dataset to confirm exact removal counts across both years (completed: exact penny and row count reconciliation confirmed).
