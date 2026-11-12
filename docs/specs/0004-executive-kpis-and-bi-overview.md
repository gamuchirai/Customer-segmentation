# 0004. Executive KPIs and BI Overview Connection

**Date**: 2026-11-12
**Status**: Proposed

## Summary

This design adds core commercial KPI (Key Performance Indicator) views in SQLite and wires the initial Power BI Desktop semantic model and Executive Overview report page. It keeps store wide revenue and order metrics accurate across all valid sales while isolating identified buyer metrics (active customers, revenue per active customer, and repeat purchase rate) so guest transactions never distort customer ratios. Automated Python tests cross check every SQL KPI output against independent calculations over the exported Parquet files so dashboard numbers reconcile one to one with database queries.

## Context

Spec `0002` established the unified `clean_transactions` table, `dim_date`, `dim_customers`, `dim_products`, and dual SQL views (`vw_store_sales` and `vw_customer_sales`) alongside typed Parquet exports in `exports/`. Roughly 23 percent of raw lines lack a `customer_id`, high volume wholesale accounts sit alongside retail shoppers, and the transaction window ends on `2011-12-09` (leaving December 2011 with only nine days of orders).

Without a shared KPI contract and Power BI semantic model wiring before building later slices, store revenue and customer revenue risk getting mixed in denominators, selecting `Retail` on a slicer could drop guest orders or expose confusing `(Blank)` Power BI keys, and December 2011 would appear as a sudden business collapse on monthly charts. Feature 5 must establish the monthly and headline commercial baseline cleanly while leaving room on Executive Overview for Feature 6 cohort retention and Feature 7 Pareto visuals.

The project runs locally on Windows with Python `3.13.5`, SQLite `3.49.1` (`retail.db`), `sqlfluff`, `ruff`, gradual `ty`, `pytest` synthetic fixtures, typed Parquet files under `exports/`, and a binary Power BI Desktop `.pbix` file in `powerbi/`. Because Power BI Desktop `.pbix` files are binary archives and the Power BI Modeling MCP server is not active in the current workspace session, the build pipeline needs an automated verification bridge between SQLite views and Parquet based DAX formulas plus clear authoring artifacts for Power BI Desktop.

## Requirements

**User stories**:
- As a Business Analyst, I want monthly and overall KPI views in SQLite that separate store wide totals from identified customer metrics so that executive cards stay accurate across every segment filter.
- As a Marketing or E-commerce stakeholder, I want an Executive Overview Power BI page with a Retail vs Wholesale vs All slicer and an explicit partial month indicator for `2011-12` so that I can read trends without misinterpreting B2B spikes or incomplete December data.
- As a reviewer or downstream developer, I want automated tests proving that every SQL KPI view reconciles one to one with the exported Parquet star schema calculations so that dashboard measures remain trustworthy as later slices ship.

**Acceptance criteria**:
- **AC-1**: `sql/02_kpi_and_cohorts.sql` executes idempotently (`DROP VIEW IF EXISTS` then `CREATE VIEW`) against `retail.db`, passes `sqlfluff lint sql/ --dialect sqlite`, and creates `vw_kpi_monthly` and `vw_kpi_overall` reading from Spec `0002` relations (`vw_store_sales`, `vw_customer_sales`, `dim_date`, `dim_customers`) via a `UNION ALL` over the four `segment_scope` slices (`vw_customer_sales` supplies `cohort_month` for identified buyer metrics).
- **AC-2**: Both `vw_kpi_monthly` and `vw_kpi_overall` expose the four `segment_scope` grains (`'ALL_STORE'`, `'IDENTIFIED_ALL'`, `'RETAIL_ONLY'`, `'WHOLESALE_ONLY'`) with paired `store_*` metrics (`store_revenue`, `store_orders`, `store_aov`) and `customer_*` metrics (`customer_revenue`, `customer_orders`, `customer_aov`, `active_customers`, `revenue_per_active_customer`), where `'ALL_STORE'` includes all valid rows for `store_*` and identified buyers (`is_identified_customer = 1`) for `customer_*`, `'RETAIL_ONLY'` keeps unidentified guest rows (`COALESCE(is_wholesale, 0) = 0`) in `store_*` totals while restricting `customer_*` metrics to identified non wholesale customers (`is_identified_customer = 1 AND is_wholesale = 0`), `'WHOLESALE_ONLY'` filters both to `is_wholesale = 1`, and `'IDENTIFIED_ALL'` scopes both `store_*` and `customer_*` strictly to `vw_customer_sales` (`store_revenue = customer_revenue`, `store_orders = customer_orders`, `store_aov = customer_aov`, `guest_revenue_share = 0.0`).
- **AC-3**: `vw_kpi_monthly` outputs one row per `(order_month, segment_scope)` containing `month_start_date`, `year`, `month`, global cutoff `is_partial_month` (`1` when the global dataset max `order_date` across `clean_transactions` falls inside that month and is strictly earlier than `MAX(dim_date.calendar_date)` for that month, `0` otherwise), `new_customers` (`order_month = cohort_month`), `returning_customers` (`order_month > cohort_month`, guaranteeing `new_customers + returning_customers = active_customers`), and SQL `LAG()` window metrics `mom_revenue_pct` and `mom_orders_pct` stored as decimal fractions (`0.15` for 15 percent, `NULL` on the first month per scope).
- **AC-4**: `vw_kpi_overall` outputs one row per `segment_scope` containing `min_order_date`, `max_order_date`, overall store and customer totals, `active_customers`, `repeat_customers` (`lifetime_orders >= 2` across the active window), `one_time_customers` (`lifetime_orders = 1`), `repeat_purchase_rate` (`repeat_customers * 1.0 / NULLIF(active_customers, 0)`), `revenue_per_active_customer`, and `guest_revenue_share` (`(store_revenue - customer_revenue) / NULLIF(store_revenue, 0)`), all stored as decimal fractions (`0.0` to `1.0`).
- **AC-5**: Both SQL views guard every division with `NULLIF(..., 0)` and explicit `* 1.0` floating point casts (preventing SQLite integer division truncation) so empty denominators return SQL `NULL`, while preserving full floating point precision with no intermediate SQL `ROUND()` truncation.
- **AC-6**: `scripts/kpis.py` provides pure stateless query and Parquet reconciliation helpers (`apply_kpi_views(conn, kpi_sql_path=DEFAULT_KPI_SQL_PATH)`, `fetch_kpi_tables(conn)`, `reconcile_parquet_kpis(conn, export_dir, tolerance_gbp=0.01, ratio_tolerance=0.0001)` returning `{"status": "ok", "scopes_verified": [...], "max_monetary_delta_gbp": float, "max_ratio_delta": float}`) plus a runnable CLI entry point (`--db-path`, `--export-dir`, `--sql-path`, `--reconcile`) printing a clean text summary and failing explicitly if `clean_transactions` is empty or Spec `0002` relations are missing.
- **AC-7**: Automated `pytest` reconciliation tests (`tests/test_kpis.py`) execute `sql/02_kpi_and_cohorts.sql` on synthetic fixtures from `tests/fixtures/`, export the 5 star schema Parquet tables via `scripts/exports.py`, compute every DAX measure formula independently on the exported Parquet DataFrames, and assert parity across all four `segment_scope` values within `0.01` GBP for monetary totals, `0.0001` (`1e-4`) for floating point ratios and AOV metrics, and exact equality for integer counts (without modifying `EXPORT_SCHEMAS` or adding extra Parquet files to `exports/`).
- **AC-8**: `powerbi/executive_overview_blueprint.md` (paired with structured M and DAX script artifacts in `powerbi/`) specifies the exact Power Query `M` ingestion using the `DataDirectory` parameter over the 5 Parquet exports, star schema relationships (`Many to 1` single direction from `dim_date`, `dim_products`, and `dim_customers` to `clean_transactions`, plus disconnected `cleaning_audit`), `dim_date` Date Table and `Sort by Column` configuration (`order_month` sorted by `month_start_date`), hidden technical and fact FK columns (`clean_id`, `raw_id`, `date_key`, `stock_code`, `customer_id`), `account_segment` (`"Retail"` vs `"Wholesale"`) and `is_acquisition_month` calculated columns eliminating `(Blank)` slicer buckets, all 15 `_Measures` DAX definitions using `DIVIDE(..., 0)` returning `BLANK()`, and Page 1 (`Executive Overview`) visual layout order (Top row: 6 KPI cards; Filter bar: `Account Segment` and `Order Date` slicers; Middle row: Monthly Store Revenue and Orders combo chart using columns for `Store Revenue`, secondary line axis for `Store Orders`, tooltips for `MoM Revenue %` and `MoM Orders %`, and column color conditional formatting from `Partial Month Flag`, beside Monthly Active Customers `New vs Returning` stacked column chart; Bottom row: reserved placeholders for Feature 6 Cohort Matrix and Feature 7 Pareto chart).
- **AC-9**: `powerbi/customer_segmentation.pbix` is wired with the semantic model and Page 1 (`Executive Overview`) visuals matching `powerbi/executive_overview_blueprint.md`, refreshed against `exports/`, and verified one to one against `vw_kpi_overall` and `vw_kpi_monthly` (with a clean `images/executive_overview_preview.png` or Feature 9 full dashboard screenshot check).

## Options considered

### Option 1: Dual Scope SQL KPI Views in SQLite Plus Parquet Star Schema in Power BI Desktop

Define `vw_kpi_monthly` and `vw_kpi_overall` inside `sql/02_kpi_and_cohorts.sql` partitioned by `segment_scope`, verify them in `scripts/kpis.py` and `tests/test_kpis.py` directly against Parquet star schema calculations, and wire `powerbi/customer_segmentation.pbix` over the 5 existing `exports/*.parquet` tables using `account_segment` and `_Measures` DAX measures.

**Pros**:
- Keeps `exports/` limited to the 5 clean star schema tables from Spec `0002` with a single source of truth inside Power BI.
- Allows automated CI tests on Linux and Windows to prove exact SQL to DAX mathematical parity over real Parquet bytes without opening Power BI Desktop.
- Preserves additive `Retail + Wholesale = All Store` reconciliation by attaching guest rows to `"Retail"` via `account_segment` while keeping `customer_*` metrics restricted to identified buyers.

**Cons**:
- Requires applying the generated Power Query `M`, DAX measures, and visual layout into `powerbi/customer_segmentation.pbix` via `powerbi-modeling-mcp` or Power BI Desktop because `.pbix` is a binary format.
- Adds two derived VertiPaq calculated columns (`account_segment`, `is_acquisition_month`) onto `clean_transactions` in the Power BI model.

### Option 2: Export Precomputed KPI Tables Directly to Parquet for Power BI Visuals

Export `vw_kpi_monthly` and `vw_kpi_overall` as additional `.parquet` files in `exports/` and bind Executive Overview visuals directly to those summarized tables instead of computing DAX over `clean_transactions`.

**Pros**:
- Eliminates complex DAX formulas for `New Customers`, `Returning Customers`, `Repeat Purchase Rate`, and `MoM %`.
- Guarantees identical numbers in Power BI visuals without any DAX filter context subtleties.

**Cons**:
- Breaks interactive cross filtering across `dim_date` day ranges, `dim_products`, and future Segment Explorer slices because summarized views lack transaction grain.
- Expands `EXPORT_SCHEMAS` and forces Power BI to carry duplicate disconnected summary tables alongside the star schema.

### Option 3: Switch Power BI Format to PBIP TMDL Text Files

Replace the single `.pbix` binary deliverable with a Power BI Project (`.pbip`) folder containing TMDL semantic model text files so Python or AI agents can write tables, relationships, and DAX measures directly as version controlled text.

**Pros**:
- Enables direct text diffs in Git pull requests for DAX measures and relationship edits.
- Lets agents modify semantic model metadata without an active Power BI Modeling MCP connection.

**Cons**:
- Changes the `.pbix` deliverable agreed in Spec `0001`, requiring reviewers cloning the repo to enable PBIP preview or open folder structures rather than one `.pbix` file.
- Visual report layout JSON (`report.json`) inside PBIP still requires Power BI Desktop to render and export clean screenshots.

## Decision

**Chosen option**: Option 1: Dual Scope SQL KPI Views in SQLite Plus Parquet Star Schema in Power BI Desktop

We will implement `vw_kpi_monthly` and `vw_kpi_overall` in `sql/02_kpi_and_cohorts.sql`, orchestrate execution and Parquet reconciliation in `scripts/kpis.py` and `tests/test_kpis.py`, and wire `powerbi/customer_segmentation.pbix` over the 5 existing `exports/*.parquet` star schema tables using the explicit M, DAX, and Page 1 blueprint in `powerbi/executive_overview_blueprint.md`.

**Implementation skills**: `sqlite-best-practices` (`erayack/sqlite-best-practices`, `.agents/skills/sqlite-best-practices/`) · `sqlfluff` (`ivanshamaev/de-agent-skills`, `.agents/skills/sqlfluff/`) · `powerbi-modeling` (`github/awesome-copilot`, `.agents/skills/powerbi-modeling/`) · `semantic-model-authoring` (`microsoft/skills-for-fabric`, `.agents/skills/semantic-model-authoring/`)

**Specific design calls made**:
- **Dynamic repeat rate filter context**: `[Repeat Purchase Rate]` iterates `VALUES(dim_customers[customer_id])` (roughly 5,900 rows instead of scanning ~800,000 fact rows) and counts customers with `[Customer Orders] >= 2` divided by `[Active Customers]`. This matches SQL `vw_kpi_overall` (`lifetime_orders >= 2`) identically when unfiltered and stays internally consistent if a user filters the Date slicer to one year. Runner up: referencing static `dim_customers[lifetime_orders] >= 2`, which would misreport lifetime repeat status inside partial date ranges.
- **Power BI Date Table, hidden keys, and VertiPaq calculated columns**: `dim_date` is marked as the official Date Table on `calendar_date` with `order_month` sorted by `month_start_date`, technical and fact foreign key columns (`clean_id`, `raw_id`, `date_key`, `stock_code`, `customer_id`) are hidden from report view in favor of dimension keys, and `account_segment` plus `is_acquisition_month` live as DAX calculated columns on `clean_transactions` using `RELATED(dim_customers[...])` (`[New Customers]` and `[Returning Customers]` are explicitly scoped to monthly grouped visuals on `dim_date[order_month]`). Runner up: merging `dim_customers` inside Power Query M, which adds slower refresh joins over ~800,000 rows instead of instant VertiPaq lookups.
- **Global cutoff partial month flag**: `vw_kpi_monthly` and `[Partial Month Flag]` compare the global dataset max `order_date` across `clean_transactions` (`2011-12-09`) against each month's calendar bounds (`MIN` and `MAX` of `dim_date.calendar_date` for that month) so only a truncated trailing dataset month evaluates to `1`, avoiding false flags when `WHOLESALE_ONLY` or other slices have zero orders on the 31st. Runner up: comparing per month `MAX(order_date) < MAX(dim_date.calendar_date)`, which falsely flags months whose last order falls before calendar month end, or hardcoding `'2011-12'`.
- **`.pbix` authoring and reconciliation boundary**: Keep `.pbix` in `powerbi/` per Spec `0001`, generate reproducible M, DAX, and Page 1 visual specs (`powerbi/executive_overview_blueprint.md`) verified by `tests/test_kpis.py` over Parquet exports, and wire `powerbi/customer_segmentation.pbix` using `powerbi-modeling-mcp` (when registered) or Power BI Desktop guided setup. Runner up: converting the repo to `.pbip` TMDL text folders.

## Rationale

The central risk in Feature 5 is denominator drift across two realities of `dataset/online_retail_II.xlsx`: roughly 23 percent of valid sales rows have no `customer_id`, and a small set of high volume wholesale accounts skews retail averages. Computing paired `store_*` and `customer_*` columns per `segment_scope` in `vw_kpi_monthly` and `vw_kpi_overall`, while mapping `clean_transactions` in Power BI through `account_segment` (`"Retail"` vs `"Wholesale"`), ensures that `Retail + Wholesale` store revenue sums cleanly to `All Store` revenue with zero `(Blank)` slicer buckets while `Active Customers`, `Revenue per Active Customer`, and `Repeat Purchase Rate` never divide guest revenue by identified buyers.

Keeping `exports/` scoped to the 5 star schema tables from Spec `0002` while placing `vw_kpi_monthly` and `vw_kpi_overall` in `retail.db` avoids duplicating summarized tables inside Power BI and keeps cross filtering intact for Features 6, 7, and 9. At the same time, running `tests/test_kpis.py` to compute the exact DAX formulas in Python over the exported Parquet files verifies every metric within `0.01` GBP in CI even when Power BI Desktop is closed.

Finally, preserving `.pbix` honors Spec `0001` for portfolio reviewers opening the dashboard in one click, while documenting every M query, relationship, measure expression, and visual binding in `powerbi/executive_overview_blueprint.md` ensures `/develop` and any reviewer can build or inspect the live model deterministically.

## Feature design

**Data model sketch**:

New SQL KPI views created in `retail.db` by `sql/02_kpi_and_cohorts.sql`:
- **`vw_kpi_monthly`**: Natural key `(order_month, segment_scope)`. Columns: `order_month TEXT NOT NULL`, `month_start_date TEXT NOT NULL`, `year INTEGER NOT NULL`, `month INTEGER NOT NULL`, `segment_scope TEXT NOT NULL` (`'ALL_STORE'`, `'IDENTIFIED_ALL'`, `'RETAIL_ONLY'`, `'WHOLESALE_ONLY'`), `is_partial_month INTEGER NOT NULL` (`0` or `1`), `store_revenue REAL NOT NULL`, `store_orders INTEGER NOT NULL`, `store_aov REAL`, `mom_revenue_pct REAL` (nullable on first month), `mom_orders_pct REAL` (nullable on first month), `customer_revenue REAL NOT NULL`, `customer_orders INTEGER NOT NULL`, `customer_aov REAL`, `active_customers INTEGER NOT NULL`, `new_customers INTEGER NOT NULL`, `returning_customers INTEGER NOT NULL`, `revenue_per_active_customer REAL`.
- **`vw_kpi_overall`**: Natural key `segment_scope`. Columns: `segment_scope TEXT NOT NULL`, `min_order_date TEXT NOT NULL`, `max_order_date TEXT NOT NULL`, `store_revenue REAL NOT NULL`, `store_orders INTEGER NOT NULL`, `store_aov REAL`, `customer_revenue REAL NOT NULL`, `customer_orders INTEGER NOT NULL`, `customer_aov REAL`, `active_customers INTEGER NOT NULL`, `repeat_customers INTEGER NOT NULL`, `one_time_customers INTEGER NOT NULL`, `repeat_purchase_rate REAL`, `revenue_per_active_customer REAL`, `guest_revenue_share REAL`.

Power BI Desktop star schema (`powerbi/customer_segmentation.pbix`, reading `exports/*.parquet` via `DataDirectory` parameter):
- **`clean_transactions`** (Fact, PK `clean_id`): Connects `N:1` single direction (`OneDirection`) to `dim_date[date_key]`, `dim_products[stock_code]`, and `dim_customers[customer_id]` (nullable FK). Adds DAX calculated columns:
  - `account_segment = IF(COALESCE(RELATED(dim_customers[is_wholesale]), FALSE()) = TRUE(), "Wholesale", "Retail")`
  - `is_acquisition_month = IF(clean_transactions[is_identified_customer] = TRUE() && clean_transactions[order_month] = RELATED(dim_customers[cohort_month]), TRUE(), FALSE())`
- **`dim_date`** (Dimension, PK `date_key`): Marked as Date Table on `calendar_date`; `order_month` configured with `Sort by Column = month_start_date`.
- **`dim_products`** (Dimension, PK `stock_code`): Filters `clean_transactions` (`1:N`).
- **`dim_customers`** (Dimension, PK `customer_id`): Filters `clean_transactions` (`1:N`).
- **`cleaning_audit`** (Standalone table, PK `audit_id`): Disconnected audit reference.
- **`_Measures`** (Measure container): Dedicated empty table holding all 15 formatted DAX measures (`Store Revenue`, `Store Orders`, `Store AOV`, `Customer Revenue`, `Customer Orders`, `Customer AOV`, `Active Customers`, `New Customers`, `Returning Customers`, `Revenue per Active Customer`, `Repeat Purchase Rate`, `MoM Revenue %`, `MoM Orders %`, `Partial Month Flag`, `Guest Revenue Share`).

**API surface** (SQL, Python runner, and Power BI report surface):

| Surface | Type | Key Inputs | Key Outputs | Auth | Key Errors |
|---|---|---|---|---|---|
| `sql/02_kpi_and_cohorts.sql` | Idempotent SQLite script | Populated Spec `0002` tables and dual views | Drops and creates `vw_kpi_monthly` and `vw_kpi_overall` via `UNION ALL` across 4 scopes with `* 1.0` float casts and `LAG()` windowing | Local file | SQLite syntax or missing table error |
| `scripts.kpis.apply_kpi_views` | Python helper | `conn: sqlite3.Connection`, `kpi_sql_path: Path = DEFAULT_KPI_SQL_PATH` (`sql/02_kpi_and_cohorts.sql`) | Verifies Spec `0002` contract plus non empty `clean_transactions` and executes `02_kpi_and_cohorts.sql` atomically | Local file | `FileNotFoundError` on missing SQL; `RuntimeError` if `clean_transactions` is empty or contract missing |
| `scripts.kpis.fetch_kpi_tables` | Python helper | `conn: sqlite3.Connection` | Tuple `(df_monthly, df_overall)` queried from `vw_kpi_monthly` and `vw_kpi_overall` ordered by `(segment_scope, order_month)` | Local file | `sqlite3.OperationalError` if views not yet applied |
| `scripts.kpis.reconcile_parquet_kpis` | Python helper | `conn: sqlite3.Connection`, `export_dir: Path`, `tolerance_gbp: float = 0.01`, `ratio_tolerance: float = 0.0001` | Dict `{"status": "ok", "scopes_verified": list[str], "max_monetary_delta_gbp": float, "max_ratio_delta": float}` | Local file | `ValueError` naming mismatched `(segment_scope, order_month, metric)` when delta exceeds tolerance |
| `scripts.kpis` CLI (`python -m scripts.kpis`) | CLI command | `--db-path` (default `retail.db`), `--export-dir` (default `exports`), `--sql-path` (default `sql/02_kpi_and_cohorts.sql`), `--reconcile` flag | Applies KPI views, prints clean plain text KPI summary to stdout, optionally reconciles against Parquet | Local file | Non zero exit with diagnostic message on missing DB, missing Parquet, or reconciliation failure |
| `powerbi/executive_overview_blueprint.md` | Build blueprint | `exports/*.parquet`, `DataDirectory` parameter | Exact M queries, relationship definitions, hidden column list, all 15 DAX measures, and Page 1 visual coordinates | Local file | N/A |

**Value sourcing** (every KPI displayed on Executive Overview traces to its SQL, Parquet, and DAX source):

| Consumer / Visual | Value Produced / Displayed | Source |
|---|---|---|
| KPI Card 1: `Store Revenue` | Total valid merchandise revenue (`£#,##0.00`) | SQL: `SUM(line_revenue)` in `vw_store_sales` (`vw_kpi_monthly.store_revenue`, `vw_kpi_overall.store_revenue`); DAX: `SUM(clean_transactions[line_revenue])` |
| KPI Card 2: `Store Orders` | Distinct valid store invoices (`#,##0`) | SQL: `COUNT(DISTINCT invoice)` in `vw_store_sales`; DAX: `DISTINCTCOUNT(clean_transactions[invoice])` |
| KPI Card 3: `Store AOV` | Average store revenue per order (`£#,##0.00`) | SQL: `store_revenue * 1.0 / NULLIF(store_orders, 0)`; DAX: `DIVIDE([Store Revenue], [Store Orders])` |
| Helper / Scope Card: `Customer Revenue` | Valid merchandise revenue from identified customers (`£#,##0.00`) | SQL: `SUM(line_revenue)` in `vw_customer_sales`; DAX: `CALCULATE([Store Revenue], clean_transactions[is_identified_customer] = TRUE())` |
| Helper / Scope Card: `Customer Orders` | Distinct valid invoices from identified customers (`#,##0`) | SQL: `COUNT(DISTINCT invoice)` in `vw_customer_sales`; DAX: `CALCULATE([Store Orders], clean_transactions[is_identified_customer] = TRUE())` |
| Helper / Scope Card: `Customer AOV` | Average identified customer revenue per order (`£#,##0.00`) | SQL: `customer_revenue * 1.0 / NULLIF(customer_orders, 0)`; DAX: `DIVIDE([Customer Revenue], [Customer Orders])` |
| KPI Card 4: `Active Customers` | Distinct identified buyers (`#,##0`) | SQL: `COUNT(DISTINCT customer_id)` in `vw_customer_sales`; DAX: `CALCULATE(DISTINCTCOUNT(clean_transactions[customer_id]), clean_transactions[is_identified_customer] = TRUE())` |
| KPI Card 5: `Revenue per Active Customer` | Identified revenue per identified buyer (`£#,##0.00`) | SQL: `customer_revenue * 1.0 / NULLIF(active_customers, 0)` (uses `vw_customer_sales` numerator, excluding guest revenue); DAX: `DIVIDE([Customer Revenue], [Active Customers])` |
| KPI Card 6: `Repeat Purchase Rate` | Share of identified buyers with `>= 2` clean orders (`0.0%`) | SQL (`vw_kpi_overall`): `COUNT(CASE WHEN lifetime_orders >= 2 THEN 1 END) * 1.0 / NULLIF(COUNT(*), 0)` from `dim_customers`; DAX: `DIVIDE(COUNTROWS(FILTER(VALUES(dim_customers[customer_id]), [Customer Orders] >= 2)), [Active Customers])` |
| Combo Chart: `Monthly Revenue & Orders` | Columns: `Store Revenue`; Secondary Line: `Store Orders`; Tooltips: `MoM Revenue %`, `MoM Orders %`; Column Color: `Partial Month Flag` | X axis: `dim_date[order_month]` sorted by `month_start_date`; SQL: `LAG(store_revenue)` and `LAG(store_orders)` (`* 1.0 / NULLIF(prev, 0)`), `is_partial_month` using global `MAX(order_date)` vs `MAX(dim_date.calendar_date)`; DAX `MoM Revenue %`: `VAR PrevRev = CALCULATE([Store Revenue], DATEADD(dim_date[calendar_date], -1, MONTH)) RETURN DIVIDE([Store Revenue] - PrevRev, PrevRev)`; DAX `MoM Orders %`: `VAR PrevOrd = CALCULATE([Store Orders], DATEADD(dim_date[calendar_date], -1, MONTH)) RETURN DIVIDE([Store Orders] - PrevOrd, PrevOrd)`; DAX `Partial Month Flag`: `VAR GlobalMax = CALCULATE(MAX(clean_transactions[order_date]), ALL(clean_transactions)) RETURN IF(GlobalMax >= MIN(dim_date[calendar_date]) && GlobalMax < MAX(dim_date[calendar_date]), 1, 0)` |
| Stacked Column Chart: `Monthly Active Customers` | Monthly `New Customers` vs `Returning Customers` (strictly scoped to monthly `dim_date[order_month]` grain) | SQL: `COUNT(DISTINCT CASE WHEN order_month = cohort_month THEN customer_id END)` and `order_month > cohort_month` from `vw_customer_sales`; DAX `New Customers`: `CALCULATE(DISTINCTCOUNT(clean_transactions[customer_id]), clean_transactions[is_identified_customer] = TRUE(), clean_transactions[is_acquisition_month] = TRUE())`; DAX `Returning Customers`: `CALCULATE(DISTINCTCOUNT(clean_transactions[customer_id]), clean_transactions[is_identified_customer] = TRUE(), clean_transactions[is_acquisition_month] = FALSE())` |
| Slicer 1: `Account Segment` | `All` (unfiltered), `Retail`, `Wholesale` | DAX calculated column `clean_transactions[account_segment]` (`"Retail"` when `COALESCE(RELATED(dim_customers[is_wholesale]), FALSE()) = FALSE()`, else `"Wholesale"`) matching SQL `segment_scope` (`ALL_STORE`, `RETAIL_ONLY`, `WHOLESALE_ONLY`) |
| Slicer 2: `Order Date / Month` | Interactive date range filter | `dim_date[calendar_date]` / `dim_date[order_month]` marked as Date Table |
| Tooltip / Audit Detail: `Guest Revenue Share` | Share of store revenue without `customer_id` (`0.0%`) | SQL: `(store_revenue - customer_revenue) * 1.0 / NULLIF(store_revenue, 0)` in `vw_kpi_overall`; DAX: `DIVIDE([Store Revenue] - [Customer Revenue], [Store Revenue])` |

**Key invariants**:
- **Scope additivity**: For any `order_month` and overall summary, `RETAIL_ONLY.store_revenue + WHOLESALE_ONLY.store_revenue` equals `ALL_STORE.store_revenue` (within floating point tolerance), and `RETAIL_ONLY.active_customers + WHOLESALE_ONLY.active_customers` equals `ALL_STORE.active_customers` (`IDENTIFIED_ALL.active_customers`).
- **New plus Returning partition**: In `vw_kpi_monthly` and per month in DAX, `new_customers + returning_customers = active_customers` holds strictly for every `(order_month, segment_scope)` row.
- **Repeat plus One Time partition**: In `vw_kpi_overall`, `repeat_customers + one_time_customers = active_customers` holds strictly for every `segment_scope`.
- **Guest exclusion in customer metrics**: Unidentified rows (`is_identified_customer = 0`) never enter `active_customers`, `new_customers`, `returning_customers`, `customer_revenue`, `revenue_per_active_customer`, or `repeat_purchase_rate`, even when `segment_scope = 'ALL_STORE'` or `'RETAIL_ONLY'`.
- **Null safe denominators**: Zero orders or zero active customers always yield SQL `NULL` and DAX `BLANK()`, never `0` or divide by zero errors.
- **Idempotency**: Rerunning `sql/02_kpi_and_cohorts.sql` or `scripts/kpis.py` produces identical view definitions and identical KPI metrics.

**Security model**:
- Local single analyst workflow with no user authentication, network APIs, or personal customer PII (uses opaque numeric `customer_id` and country labels inherited from Specs `0001` and `0002`).
- `exports/*.parquet` and `retail.db` remain excluded from Git via `.gitignore`.

**Configuration required**:
- Power BI Desktop parameter `DataDirectory` (Text parameter pointing to the local `exports/` folder path so clones run portably across machines per Spec `0001`).
- No environment variables or external API secrets required.

**Critical test scenarios**:
- Happy path: Populate a synthetic fixture database covering multiple months (including one complete month, one partial final month, guest rows, retail repeat buyers, and wholesale buyers), export the 5 Parquet files, run `apply_kpi_views`, and verify `reconcile_parquet_kpis` passes within `0.01` GBP for monetary metrics, `0.0001` (`1e-4`) for ratios, and exact equality for integer counts across all 4 `segment_scope` values (`ALL_STORE`, `IDENTIFIED_ALL`, `RETAIL_ONLY`, `WHOLESALE_ONLY`), verifies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-6**, **AC-7**.
- Partial month and MoM boundary check: Verify `vw_kpi_monthly` assigns `is_partial_month = 1` only to the global dataset cutoff month when its max `order_date` precedes `dim_date` month end (and `0` to earlier months even when `WHOLESALE_ONLY` has no order on the 31st), and sets `mom_revenue_pct` and `mom_orders_pct` to `NULL` on the earliest month per scope, verifies **AC-3**, **AC-5**.
- Retail + Guest vs Identified denominator check: Verify `RETAIL_ONLY` includes guest revenue in `store_revenue` while keeping `customer_revenue` and `revenue_per_active_customer` scoped strictly to identified non wholesale buyers, verifies **AC-2**, **AC-4**.
- Empty denominator and missing prerequisite failures: Verify `NULLIF` returns SQL `NULL` when a month or scope has zero rows/orders, and verify `apply_kpi_views` raises `RuntimeError` when `clean_transactions` is empty or Spec `0002` views are absent, verifies **AC-5**, **AC-6**.
- Parity mismatch detection: Perturb a synthetic Parquet revenue value by `0.05` GBP and assert `reconcile_parquet_kpis` raises `ValueError` identifying the exact scope, month, and metric, verifies **AC-7**.
- Power BI Desktop live verification: Wire `powerbi/customer_segmentation.pbix` from `powerbi/executive_overview_blueprint.md`, refresh from `exports/`, check every card and monthly bar under `All`, `Retail`, and `Wholesale` slicer states against `vw_kpi_overall` and `vw_kpi_monthly`, and confirm `2011-12` partial month callout renders cleanly without `(Blank)` slicer options, verifies **AC-8**, **AC-9**.

## Build plan

Ordered following the project's **Tracer Bullet** approach (stand up the minimal end to end SQLite KPI views and Python runner first, then add all four `segment_scope` grains, MoM window metrics, automated Parquet DAX parity tests, and the Power BI blueprint plus `.pbix` wiring):

1. Write `sql/02_kpi_and_cohorts.sql` with idempotent `DROP VIEW IF EXISTS` and `CREATE VIEW` definitions for `vw_kpi_monthly` and `vw_kpi_overall` (`UNION ALL` across `ALL_STORE`, `IDENTIFIED_ALL`, `RETAIL_ONLY`, `WHOLESALE_ONLY`), global cutoff `is_partial_month`, `new_customers` / `returning_customers`, `LAG()` MoM decimal fractions, `repeat_purchase_rate`, `guest_revenue_share`, `* 1.0` float casts, and `NULLIF(..., 0)` guards, then validate with `sqlfluff lint sql/ --dialect sqlite`, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**.
2. Implement `scripts/kpis.py` (`apply_kpi_views`, `fetch_kpi_tables`, `reconcile_parquet_kpis` with `0.01` GBP and `0.0001` tolerances, and CLI entry point) with strict type hints (`ty check`) and `ruff` compliance, verifying Spec `0002` contract preconditions and cross checking SQL KPI views against independent Parquet DataFrame formulas, satisfies **AC-6**, **AC-7**.
3. Add `tests/test_kpis.py` using synthetic SQLite and Parquet fixtures (covering full and partial months, wholesale gap months without false partial flags, guest transactions, retail vs wholesale splits, repeat vs one time buyers, `NULL` first month MoM, zero denominator safety, and mismatch detection within `0.01` GBP and `0.0001` ratio tolerances), satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-6**, **AC-7**.
4. Author `powerbi/executive_overview_blueprint.md` (and any companion `.m` / `.dax` scripts in `powerbi/`) documenting the `DataDirectory` Power Query setup over the 5 `exports/*.parquet` files, star schema relationships, `dim_date` Date Table and `Sort by Column` rules, hidden fact keys (`clean_id`, `raw_id`, `date_key`, `stock_code`, `customer_id`), `account_segment` and `is_acquisition_month` columns, all 15 `_Measures` DAX expressions, and Page 1 (`Executive Overview`) visual layout with tooltips/color rules and reserved slots for Features 6 and 7, satisfies **AC-8**.
5. Wire `powerbi/customer_segmentation.pbix` in Power BI Desktop (or via `powerbi-modeling-mcp`), refresh from `exports/`, reconcile all Page 1 KPI cards and trend visuals one to one against `scripts/kpis.py` outputs across `All`, `Retail`, and `Wholesale` slicer states, and save clean Page 1 preview screenshot evidence, satisfies **AC-8**, **AC-9**.

## Consequences

**Positive**:
- Store wide totals and identified customer KPIs reconcile deterministically across SQLite, Python tests, and Power BI DAX without splitting `exports/` or duplicating cleaning rules.
- The `account_segment` calculated column removes Power BI's `(Blank)` slicer item for guest transactions while keeping `Retail + Wholesale = All Store` additive.
- Global cutoff `is_partial_month` detection protects stakeholders from misreading the nine day `2011-12` window as a sharp December drop without falsely flagging wholesale gap months.

**Negative / tradeoffs**:
- Because `.pbix` is a binary archive and `@microsoft/powerbi-modeling-mcp` is not registered by default, Step 5 of the build plan requires either connecting `@microsoft/powerbi-modeling-mcp` to an open Power BI Desktop instance or clicking through the blueprint inside Power BI Desktop on Windows.
- Adding `account_segment` and `is_acquisition_month` as DAX calculated columns increases Power BI `.pbix` memory footprint slightly compared to keeping only raw imported columns, though remaining negligible at ~800,000 rows.
- `sql/02_kpi_and_cohorts.sql` holds KPI views now and will be extended in Feature 6 when monthly cohort retention views are added.

## Follow-up

- [ ] Before starting `/develop` on Feature 5's `.pbix` wiring (Build plan step 5), ensure Feature 4 (`Data ingestion and cleaning pipeline`) has populated `retail.db` and `exports/*.parquet`, and optionally register `@microsoft/powerbi-modeling-mcp` in your MCP config if you want the agent to inspect and edit the open `.pbix` model directly.
- [ ] In Feature 6 (`Monthly cohort retention analysis`), extend `sql/02_kpi_and_cohorts.sql` with cohort retention views and place the Cohort Retention Matrix into the reserved Page 1 slot in `powerbi/customer_segmentation.pbix`.
- [ ] In Feature 7 (`RFM scoring and customer segments`), add the 80/20 Pareto segment summary visual into the reserved Page 1 slot alongside Page 2 (`Segment Explorer`).
