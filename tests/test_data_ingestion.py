"""Tests for data ingestion, staging, SQL cleaning, and export orchestration."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pandas as pd
import pytest
from scripts.db import (
    connect_db,
    initialize_schema,
    reset_clean_tables,
    seed_dim_date,
)
from scripts.load_to_sql import (
    execute_cleaning_pipeline,
    main,
    run_pipeline,
    sanitize_raw_records,
    validate_cli_flags,
    validate_excel_source,
)

from tests.fixtures.synthetic_transactions import SAMPLE_RAW_TRANSACTIONS

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def memory_db():
    """Yield an initialized in-memory SQLite database connection."""
    conn = connect_db(":memory:")
    initialize_schema(conn)
    yield conn
    conn.close()


def test_seed_dim_date_range_and_attributes(memory_db):
    """AC-2: dim_date spans continuous dates with complete calendar attributes."""
    count = seed_dim_date(memory_db, start_date="2009-12-01", end_date="2011-12-31")
    # 2009-12-01 to 2011-12-31 is 31 + 365 + 365 = 761 days
    assert count == 761

    cursor = memory_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM dim_date;")
    assert cursor.fetchone()[0] == 761

    # Inspect first day: 2009-12-01 was a Tuesday
    cursor.execute(
        "SELECT date_key, calendar_date, year, quarter, month, order_month, "
        "month_start_date, day_of_week, day_name, is_weekend "
        "FROM dim_date WHERE calendar_date = '2009-12-01';"
    )
    row = cursor.fetchone()
    assert row == (
        20091201,
        "2009-12-01",
        2009,
        4,
        12,
        "2009-12",
        "2009-12-01",
        2,
        "Tuesday",
        0,
    )

    # Inspect a weekend day: 2009-12-05 was a Saturday
    cursor.execute(
        "SELECT day_of_week, day_name, is_weekend FROM dim_date WHERE calendar_date = '2009-12-05';"
    )
    assert cursor.fetchone() == (6, "Saturday", 1)

    # Verify idempotency
    count_rerun = seed_dim_date(memory_db, start_date="2009-12-01", end_date="2011-12-31")
    assert count_rerun == 761


def test_seed_dim_date_invalid_range(memory_db):
    """seed_dim_date raises ValueError if start_date is after end_date."""
    with pytest.raises(ValueError, match="cannot be after end_date"):
        seed_dim_date(memory_db, start_date="2011-12-31", end_date="2009-12-01")


def test_validate_cli_flags_conflicts():
    """AC-9: CLI validator rejects incompatible flag combinations."""
    with pytest.raises(ValueError, match="Cannot combine --stage-only with --clean-only"):
        validate_cli_flags(argparse.Namespace(stage_only=True, clean_only=True, rebuild=False))

    with pytest.raises(ValueError, match="Cannot combine --rebuild with --clean-only"):
        validate_cli_flags(argparse.Namespace(stage_only=False, clean_only=True, rebuild=True))

    # Valid configurations do not raise
    validate_cli_flags(argparse.Namespace(stage_only=True, clean_only=False, rebuild=False))
    validate_cli_flags(argparse.Namespace(stage_only=False, clean_only=True, rebuild=False))
    validate_cli_flags(argparse.Namespace(stage_only=False, clean_only=False, rebuild=True))


def test_validate_excel_source_errors(tmp_path: Path):
    """AC-1: validate_excel_source raises explicit errors for missing files or sheets."""
    missing_file = tmp_path / "non_existent.xlsx"
    with pytest.raises(FileNotFoundError, match="not found"):
        validate_excel_source(missing_file)

    # Create dummy excel with wrong sheet names
    invalid_excel = tmp_path / "invalid_sheets.xlsx"
    with pd.ExcelWriter(invalid_excel, engine="openpyxl") as writer:
        pd.DataFrame({"A": [1]}).to_excel(writer, sheet_name="Sheet1", index=False)

    with pytest.raises(ValueError, match="missing expected sheet"):
        validate_excel_source(invalid_excel)


def test_sanitize_raw_records():
    """AC-1: sanitize_raw_records coerces types, strips customer floats, and cleans nulls."""
    df = pd.DataFrame(
        {
            "Invoice": ["489434", "C489435"],
            "StockCode": ["85048", "POST"],
            "Description": ["TEST ITEM", "   "],
            "Quantity": [12.0, -1.0],
            "InvoiceDate": ["2009-12-01 07:45:00", "2009-12-01 08:00:00"],
            "Price": [6.95, 18.0],
            "Customer ID": [13085.0, "nan"],
            "Country": ["United Kingdom", "France"],
        }
    )

    rows = sanitize_raw_records(df, sheet_name="Year 2009-2010", loaded_at="2026-11-12T00:00:00Z")
    assert len(rows) == 2

    row1 = rows[0]
    assert row1[0] == "Year 2009-2010"
    assert row1[1] == 2  # source_row_num is 1-based physical row
    assert row1[3] == "489434"
    assert row1[4] == "85048"
    assert row1[5] == "TEST ITEM"
    assert row1[6] == 12  # coerced integer
    assert row1[8] == 6.95
    assert row1[9] == "13085"  # stripped .0
    assert row1[10] == "United Kingdom"

    row2 = rows[1]
    assert row2[5] is None  # blank string becomes None
    assert row2[9] is None  # 'nan' string becomes None


def test_execute_cleaning_pipeline_synthetic(memory_db):
    """AC-3 to AC-8: Full cleaning waterfall, tie-breaking, dimensions, and audit log."""
    insert_sql = """
        INSERT INTO raw_transactions (
            source_sheet,
            source_row_num,
            loaded_at,
            invoice,
            stock_code,
            description,
            quantity,
            invoice_date,
            price,
            customer_id,
            country
        ) VALUES (
            :source_sheet,
            :source_row_num,
            :loaded_at,
            :invoice,
            :stock_code,
            :description,
            :quantity,
            :invoice_date,
            :price,
            :customer_id,
            :country
        );
    """
    with memory_db:
        memory_db.executemany(insert_sql, SAMPLE_RAW_TRANSACTIONS)

    results = execute_cleaning_pipeline(memory_db)

    # 9 raw transactions:
    # Row 1: Valid 489434 / 85048 / Cust 13085 (kept)
    # Row 2: Valid 489434 / 79323p / Cust 13085 (kept)
    # Row 3: Valid 489435 / 22350 / Guest (kept in store sales, boundary split)
    # Row 4: Valid 489436 / 85048 / Cust 18102 (kept, wholesale)
    # Row 5: Cancellation C489437 (removed)
    # Row 6: Non-merchandise POST (removed)
    # Row 7: Non-merchandise M (removed)
    # Row 8: Zero price adjustment (removed)
    # Row 9: Cross-sheet duplicate of Row 1 (removed)
    # Total clean lines = 4
    assert results["clean_transactions_count"] == 4
    assert results["dim_products_count"] == 3  # 85048, 79323P, 22350
    assert results["dim_customers_count"] == 2  # 13085, 18102
    assert results["cleaning_audit_steps_count"] == 8

    cursor = memory_db.cursor()

    # AC-3: stock codes uppercased in dim_products and clean_transactions
    cursor.execute("SELECT stock_code FROM dim_products ORDER BY stock_code;")
    products = [row[0] for row in cursor.fetchall()]
    assert products == ["22350", "79323P", "85048"]

    # AC-5: wholesale flag and token grammar
    cursor.execute(
        "SELECT customer_id, is_wholesale, wholesale_reason, lifetime_revenue, avg_units_per_order "
        "FROM dim_customers WHERE customer_id = '18102';"
    )
    ws_row = cursor.fetchone()
    assert ws_row[1] == 1
    assert ws_row[2] == "REVENUE_THRESHOLD|UNITS_PER_ORDER_THRESHOLD"
    assert ws_row[3] == 12500.0
    assert ws_row[4] == 500.0

    cursor.execute(
        "SELECT is_wholesale, wholesale_reason FROM dim_customers WHERE customer_id = '13085';"
    )
    std_row = cursor.fetchone()
    assert std_row == (0, None)

    # AC-6: Dual views contract
    cursor.execute("SELECT COUNT(*) FROM vw_store_sales;")
    assert cursor.fetchone()[0] == 4

    cursor.execute("SELECT COUNT(*) FROM vw_customer_sales;")
    assert cursor.fetchone()[0] == 3

    # AC-7: Audit waterfall sequential math
    cursor.execute(
        "SELECT step_order, rule_name, entry_type, rows_removed_sequential, "
        "revenue_removed_sequential, remaining_rows, remaining_revenue "
        "FROM cleaning_audit ORDER BY step_order;"
    )
    audit_rows = cursor.fetchall()
    assert len(audit_rows) == 8

    # Step 1: baseline (9 rows)
    assert audit_rows[0][1] == "baseline"
    assert audit_rows[0][5] == 9

    # Step 2: exact_duplicate (1 duplicate removed, 8 remaining)
    assert audit_rows[1][1] == "exact_duplicate"
    assert audit_rows[1][3] == 1
    assert audit_rows[1][5] == 8

    # Step 3: cancellation_invoice (1 cancellation removed, 7 remaining)
    assert audit_rows[2][1] == "cancellation_invoice"
    assert audit_rows[2][3] == 1
    assert audit_rows[2][5] == 7

    # Step 4: non_merchandise_stock_code (2 fee lines removed, 5 remaining)
    assert audit_rows[3][1] == "non_merchandise_stock_code"
    assert audit_rows[3][3] == 2
    assert audit_rows[3][5] == 5

    # Step 5: non_positive_quantity_or_price (1 non-positive removed, 4 remaining)
    assert audit_rows[4][1] == "non_positive_quantity_or_price"
    assert audit_rows[4][3] == 1
    assert audit_rows[4][5] == 4

    # Step 7: store_valid_sales matches step 5 remaining
    assert audit_rows[6][1] == "store_valid_sales"
    assert audit_rows[6][5] == 4
    assert audit_rows[6][6] == audit_rows[4][6]

    # Step 8: customer_valid_sales matches identified rows
    assert audit_rows[7][1] == "customer_valid_sales"
    assert audit_rows[7][5] == 3


def test_reset_clean_tables(memory_db):
    """reset_clean_tables clears fact, dimensions, and audit tables safely."""
    with memory_db:
        memory_db.execute(
            "INSERT INTO dim_products (stock_code, canonical_description, "
            "description_variant_count, first_sold_date, last_sold_date) "
            "VALUES ('TEST', 'Test item', 1, '2009-12-01', '2009-12-01');"
        )
    reset_clean_tables(memory_db)
    cursor = memory_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM dim_products;")
    assert cursor.fetchone()[0] == 0


def test_run_pipeline_end_to_end_with_synthetic_excel(tmp_path: Path):
    """AC-9 & AC-10: run_pipeline loads Excel, cleans, and exports Parquet/CSV marts."""
    excel_file = tmp_path / "synthetic_retail.xlsx"
    db_file = tmp_path / "test_retail.db"
    export_dir = tmp_path / "exports"

    df_2009 = pd.DataFrame(SAMPLE_RAW_TRANSACTIONS[:8])
    df_2009_renamed = df_2009.rename(
        columns={
            "invoice": "Invoice",
            "stock_code": "StockCode",
            "description": "Description",
            "quantity": "Quantity",
            "invoice_date": "InvoiceDate",
            "price": "Price",
            "customer_id": "Customer ID",
            "country": "Country",
        }
    )

    df_2010 = pd.DataFrame([SAMPLE_RAW_TRANSACTIONS[8]])
    df_2010_renamed = df_2010.rename(
        columns={
            "invoice": "Invoice",
            "stock_code": "StockCode",
            "description": "Description",
            "quantity": "Quantity",
            "invoice_date": "InvoiceDate",
            "price": "Price",
            "customer_id": "Customer ID",
            "country": "Country",
        }
    )

    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        df_2009_renamed.to_excel(writer, sheet_name="Year 2009-2010", index=False)
        df_2010_renamed.to_excel(writer, sheet_name="Year 2010-2011", index=False)

    args = argparse.Namespace(
        stage_only=False,
        clean_only=False,
        rebuild=True,
        no_export=False,
        excel_path=excel_file,
        db_path=db_file,
        export_dir=export_dir,
    )

    results = run_pipeline(args)
    assert results["status"] == "success"
    assert results["staged_rows"] == 9
    assert results["cleaning"]["clean_transactions_count"] == 4
    assert len(results["exported_tables"]) == 5

    # Check that export files exist
    assert (export_dir / "clean_transactions.parquet").is_file()
    assert (export_dir / "clean_transactions.csv").is_file()
    assert (export_dir / "dim_customers.parquet").is_file()
    assert (export_dir / "dim_customers.csv").is_file()
    assert (export_dir / "cleaning_audit.parquet").is_file()
    assert (export_dir / "cleaning_audit.csv").is_file()


def test_sanitize_raw_records_missing_columns():
    """sanitize_raw_records raises ValueError when required column is missing."""
    df = pd.DataFrame({"Invoice": ["123"], "StockCode": ["85048"]})
    with pytest.raises(ValueError, match="missing required columns"):
        sanitize_raw_records(df, sheet_name="Year 2009-2010", loaded_at="2026-11-12T00:00:00Z")


def test_run_pipeline_stage_only(tmp_path: Path):
    """AC-9: run_pipeline with --stage-only stages data without cleaning or exporting."""
    excel_file = tmp_path / "synthetic_retail.xlsx"
    db_file = tmp_path / "test_stage_only.db"

    df_2009 = pd.DataFrame(SAMPLE_RAW_TRANSACTIONS[:2]).rename(
        columns={
            "invoice": "Invoice",
            "stock_code": "StockCode",
            "description": "Description",
            "quantity": "Quantity",
            "invoice_date": "InvoiceDate",
            "price": "Price",
            "customer_id": "Customer ID",
            "country": "Country",
        }
    )
    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        df_2009.to_excel(writer, sheet_name="Year 2009-2010", index=False)
        df_2009.to_excel(writer, sheet_name="Year 2010-2011", index=False)

    conn = connect_db(db_file)
    initialize_schema(conn)
    conn.close()

    args = argparse.Namespace(
        stage_only=True,
        clean_only=False,
        rebuild=False,
        no_export=True,
        excel_path=excel_file,
        db_path=db_file,
        export_dir=tmp_path / "exports",
    )
    results = run_pipeline(args)
    assert results["status"] == "staged_only"
    assert results["staged_rows"] == 4

    conn = connect_db(db_file)
    cur = conn.cursor()
    assert cur.execute("SELECT COUNT(*) FROM raw_transactions;").fetchone()[0] == 4
    assert cur.execute("SELECT COUNT(*) FROM clean_transactions;").fetchone()[0] == 0
    conn.close()


def test_run_pipeline_clean_only_empty_raw(tmp_path: Path):
    """run_pipeline raises RuntimeError when --clean-only is run on empty raw_transactions."""
    db_file = tmp_path / "test_empty.db"
    conn = connect_db(db_file)
    initialize_schema(conn)
    conn.close()

    args = argparse.Namespace(
        stage_only=False,
        clean_only=True,
        rebuild=False,
        no_export=True,
        excel_path=tmp_path / "dummy.xlsx",
        db_path=db_file,
        export_dir=tmp_path / "exports",
    )
    with pytest.raises(RuntimeError, match="raw_transactions is empty"):
        run_pipeline(args)


def test_canonical_product_description_tie_breaking(memory_db):
    """AC-8: dim_products chooses most frequent description, tie-broken by date and alphabetical."""
    insert_sql = """
        INSERT INTO raw_transactions (
            source_sheet, source_row_num, loaded_at, invoice, stock_code, description,
            quantity, invoice_date, price, customer_id, country
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    rows = [
        (
            "Year 2009-2010",
            2,
            "2026-11-12T00:00:00Z",
            "1001",
            "TEST_CODE",
            "OLDER DESC",
            1,
            "2010-01-01 10:00:00",
            5.0,
            "1001",
            "United Kingdom",
        ),
        (
            "Year 2009-2010",
            3,
            "2026-11-12T00:00:00Z",
            "1002",
            "TEST_CODE",
            "NEWER DESC",
            1,
            "2010-05-01 10:00:00",
            5.0,
            "1001",
            "United Kingdom",
        ),
    ]
    with memory_db:
        memory_db.executemany(insert_sql, rows)

    execute_cleaning_pipeline(memory_db)
    cur = memory_db.cursor()
    cur.execute(
        "SELECT canonical_description, description_variant_count "
        "FROM dim_products WHERE stock_code = 'TEST_CODE';"
    )
    # Equal frequency (1 each): NEWER DESC has later date 2010-05-01 vs 2010-01-01
    assert cur.fetchone() == ("NEWER DESC", 2)


def test_customer_primary_country_tie_breaking(memory_db):
    """AC-8: dim_customers prefers real country over Unspecified and breaks ties.

    Tie-breaking hierarchy: valid country > Unspecified, frequency, latest date.
    """
    insert_sql = """
        INSERT INTO raw_transactions (
            source_sheet, source_row_num, loaded_at, invoice, stock_code, description,
            quantity, invoice_date, price, customer_id, country
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    rows = [
        (
            "Year 2009-2010",
            2,
            "2026-11-12T00:00:00Z",
            "1001",
            "ITEM1",
            "DESC1",
            1,
            "2010-01-01 10:00:00",
            5.0,
            "CUST_TIE",
            "Unspecified",
        ),
        (
            "Year 2009-2010",
            3,
            "2026-11-12T00:00:00Z",
            "1002",
            "ITEM1",
            "DESC1",
            1,
            "2010-02-01 10:00:00",
            5.0,
            "CUST_TIE",
            "France",
        ),
    ]
    with memory_db:
        memory_db.executemany(insert_sql, rows)

    execute_cleaning_pipeline(memory_db)
    cur = memory_db.cursor()
    cur.execute("SELECT primary_country FROM dim_customers WHERE customer_id = 'CUST_TIE';")
    # Real country France beats Unspecified despite equal frequency
    assert cur.fetchone()[0] == "France"


def test_main_cli_execution_and_error():
    """AC-9: main() exits 0 on valid run and exits 1 on invalid arguments."""
    # Invalid args returns 1
    assert main(["--stage-only", "--clean-only"]) == 1
