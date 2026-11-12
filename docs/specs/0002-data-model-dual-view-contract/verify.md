# Verify: Data model and dual view contract · spec 0002

## Commands

- [x] `uv run python scratch/verify_data_model.py` → database pragmas, live schema objects, constraint rejections, dual views, and Parquet exports verified on disk → AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-9
- [x] `uv run sqlfluff lint sql/ --dialect sqlite` → passes with zero lint violations → AC-8
- [x] `uv run ruff check .` → passes with zero lint violations → AC-8, AC-9
- [x] `uv run ruff format --check .` → passes with all files formatted → AC-8, AC-9
- [x] `uv run ty check` → passes with zero type violations → AC-8, AC-9
- [x] `uv run pytest` → 21 passed unit and contract tests → AC-10

## Live surfaces

- [x] SQLite database tables (`raw_transactions`, `ref_excluded_stock_codes`, `ref_pipeline_config`, `dim_date`, `dim_products`, `dim_customers`, `clean_transactions`, `cleaning_audit`) → verified live in sqlite_master → AC-1, AC-2, AC-4, AC-5, AC-6, AC-7
- [x] SQLite database views (`vw_store_sales`, `vw_customer_sales`) → verified live in sqlite_master and executed against staged data → AC-3
- [x] SQLite covering indexes (`idx_clean_customer_month`, `idx_clean_date_key`, `idx_clean_invoice`, `idx_clean_order_month`, `idx_clean_stock_code`) → verified live in sqlite_master → AC-8
- [x] Export bridge files in `exports/` (`clean_transactions`, `dim_customers`, `dim_products`, `dim_date`, `cleaning_audit` in `.parquet` and `.csv`) → verified live with typed PyArrow schemas → AC-9

## Acceptance criteria coverage

- AC-1: `raw_transactions` table enforces `STRICT` typing, source sheet and row coordinates, and nullable customer IDs → met
- AC-2: `clean_transactions` table enforces `STRICT` typing, positive units and revenue, and customer ID identification constraints → met
- AC-3: Dual SQL views `vw_store_sales` and `vw_customer_sales` expose store wide valid sales and identified customer sales respectively → met
- AC-4: `cleaning_audit` table logs sequential row and revenue removal with signed waterfall conservation → met
- AC-5: `dim_customers` dimension stores customer summaries, resolved primary country, and wholesale account flags → met
- AC-6: `dim_products` and `dim_date` dimensions eliminate split descriptions and provide continuous calendar dimensions → met
- AC-7: Seed metadata tables `ref_excluded_stock_codes` (12 codes) and `ref_pipeline_config` (5 keys) seeded in SQL → met
- AC-8: `sql/00_schema.sql` runs idempotently under active foreign keys and WAL mode with covering indexes → met
- AC-9: `scripts/exports.py` enforces explicit PyArrow schemas and handles Windows file lock diagnostics during atomic replacement → met
- AC-10: Test suite passes completely on synthetic fixtures without reading the raw Excel workbook → met
