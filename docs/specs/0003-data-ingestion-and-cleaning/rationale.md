# 0003. Data Ingestion and Cleaning Pipeline: Rationale

## Context

The raw workbook `dataset/online_retail_II.xlsx` contains over one million transaction rows across two annual sheets (`Year 2009-2010` and `Year 2010-2011`). The data holds several messy real world problems. More than two hundred thousand rows lack customer identifiers, cancellation orders start with the letter C, non merchandise fees such as postage and bank charges share the item columns, quantities and unit prices can be negative or zero, and exact duplicate rows appear across transactions.

If these dirty lines are cleaned inconsistently across ad hoc scripts, store revenue and customer analytics will disagree. Furthermore, downstream analytical features like cohort retention and RFM segmentation depend on deterministic tie breaking when picking customer countries and product descriptions. Without an auditable sequential waterfall log, stakeholders and recruiters cannot verify which records were removed and why.

This project uses Python 3.13.5 and SQLite 3.49.1 with pandas, openpyxl, pyarrow, and sqlfluff. The pipeline must leave the raw workbook completely untouched, support fast idempotent reruns, enforce strict foreign keys, and integrate cleanly with our existing export helpers.

## Options considered

### Option 1: Hybrid Python Staging with In Database SQL Transformation and Automatic Exports

Use Python and pandas with openpyxl to parse raw sheets and bulk insert rows into `raw_transactions`. Execute cleaning, deduplication, candidate extraction, and sequential audit logging inside SQLite via an idempotent SQL script (`sql/01_data_cleaning.sql`). Populate dimensions using SQL aggregations with dynamic wholesale rule evaluation in Python, and automatically trigger Parquet and CSV exports upon clean completion.

**Pros**:
- Combines Python strengths (robust Excel parsing, flexible CLI argument parsing, fast calendar generation, dynamic wholesale rule configuration) with SQL strengths (declarative set operations, window functions, fast in database joins).
- SQL transformations in `sql/01_data_cleaning.sql` can be linted with sqlfluff and inspected directly by database analysts.
- Full pipeline runs with one standard command while preserving fine grained control for rerunning only cleaning or staging.

**Cons**:
- Requires coordinating logic between Python and SQL scripts rather than keeping everything in a single Python file.

### Option 2: Pure Python and Pandas In Memory Pipeline

Perform both staging and cleaning in Python memory using pandas dataframes. Filter duplicates, cancellations, fees, and invalid prices in memory, compute audit counts, populate dimension tables using pandas aggregations, and write final tables directly to SQLite using `to_sql`.

**Pros**:
- All transformation logic lives in a single language and test suite.
- Fast execution for in memory dataframe operations.

**Cons**:
- Bypasses SQL window functions and declarative database logic, which reduces recruiter visibility into production SQL engineering skills.
- Holds multiple large dataframes in memory at once, increasing RAM usage on developer machines.

### Option 3: Two Separate Decoupled Scripts with Manual Export Execution

Create two separate standalone CLI scripts (`scripts/load_raw.py` and `scripts/clean_data.py`) that must be run sequentially, leaving export generation to a separate third manual step.

**Pros**:
- Strict separation between raw extraction and downstream business cleaning.

**Cons**:
- Creates operational friction during routine development and testing because developers must remember to run three commands in sequence.
- Increases the risk of out of date exports when tables are cleaned but exports are not refreshed.

## Rationale

The hybrid approach aligns directly with the architectural foundations established in specs 0001 and 0002. Staging raw data first into `raw_transactions` protects the raw Excel spreadsheet from accidental edits and creates an immutable baseline that can be verified at any time.

Running the core cleaning transformations in `sql/01_data_cleaning.sql` allows the project to demonstrate rigorous SQL competence through window functions, common table expressions, strict foreign key constraints, and declarative tie breaking. Keeping the calendar dimension generation in Python avoids cumbersome recursive SQL queries while guaranteeing valid ISO date attributes.

Automating the export step ensures that `exports/*.parquet` and `exports/*.csv` stay immediately synchronized with `retail.db`, preventing confusion when inspecting reports in Power BI Desktop. The CLI flags (`--stage-only`, `--clean-only`, `--rebuild`, `--no-export`) give developers the flexibility to iterate rapidly on SQL queries without reloading the large Excel workbook every time.
