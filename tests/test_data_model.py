"""Tests for database schema, dual view contracts, audit reconciliation, and exports."""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import TYPE_CHECKING
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from scripts.db import (
    connect_db,
    initialize_schema,
    verify_schema_contract,
)
from scripts.exports import (
    DISALLOWED_EXPORTS,
    EXPORT_SCHEMAS,
    _atomic_swap,
    _convert_dataframe_types,
    export_all_contract_tables,
    export_table_pair,
)

from tests.fixtures.synthetic_transactions import SAMPLE_RAW_TRANSACTIONS

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite connection with initialized schema."""
    conn = connect_db(":memory:")
    initialize_schema(conn)
    return conn


def test_schema_initialization_and_idempotency(memory_db: sqlite3.Connection) -> None:
    """AC-8: Test that schema initializes and can be rerun idempotently without error."""
    summary = verify_schema_contract(memory_db)
    assert len(summary["tables"]) == 8
    assert len(summary["views"]) == 2
    assert len(summary["indexes"]) == 5
    assert len(summary["config_keys"]) == 5
    assert summary["excluded_stock_codes_count"] >= 10

    # Rerunning initialization on an existing schema must succeed (idempotent drops/recreates)
    initialize_schema(memory_db)
    summary_after = verify_schema_contract(memory_db)
    assert summary_after["tables"] == summary["tables"]


def test_reverse_drop_order_with_foreign_keys(memory_db: sqlite3.Connection) -> None:
    """AC-2, AC-8: Verify tables with active foreign key references drop cleanly on rerun."""
    cursor = memory_db.cursor()

    # Populate parents
    cursor.execute(
        """
        INSERT INTO dim_products (
            stock_code, canonical_description, description_variant_count,
            first_sold_date, last_sold_date
        ) VALUES ('85048', 'CHRISTMAS LIGHTS', 1, '2009-12-01', '2009-12-01');
        """
    )
    cursor.execute(
        """
        INSERT INTO dim_date (
            date_key, calendar_date, year, quarter, month, order_month,
            month_start_date, day_of_week, day_name, is_weekend
        ) VALUES (20091201, '2009-12-01', 2009, 4, 12, '2009-12', '2009-12-01', 2, 'Tuesday', 0);
        """
    )
    cursor.execute(
        """
        INSERT INTO raw_transactions (
            raw_id, source_sheet, source_row_num, loaded_at, invoice,
            stock_code, description, quantity, invoice_date, price, customer_id, country
        ) VALUES (
            1, 'Year 2009-2010', 2, '2026-11-12T00:00:00', '489434',
            '85048', 'LIGHTS', 10, '2009-12-01 08:00:00', 5.0, NULL, 'United Kingdom'
        );
        """
    )
    cursor.execute(
        """
        INSERT INTO clean_transactions (
            clean_id, raw_id, invoice, stock_code, raw_description, quantity,
            unit_price, line_revenue, invoice_ts, order_date, order_month,
            date_key, customer_id, transaction_country, is_identified_customer
        ) VALUES (
            1, 1, '489434', '85048', 'LIGHTS', 10, 5.0, 50.0,
            '2009-12-01 08:00:00', '2009-12-01', '2009-12', 20091201,
            NULL, 'United Kingdom', 0
        );
        """
    )
    memory_db.commit()

    # Re-initialization with active child rows must succeed under reverse dependency DROP
    initialize_schema(memory_db)
    summary = verify_schema_contract(memory_db)
    assert len(summary["tables"]) == 8


def test_strict_and_check_constraints(memory_db: sqlite3.Connection) -> None:
    """AC-1, AC-2: Test STRICT typing and CHECK constraints on positive values and null coupling."""
    cursor = memory_db.cursor()

    # Missing dimension foreign key parent must fail under PRAGMA foreign_keys = ON
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO clean_transactions (
                clean_id, raw_id, invoice, stock_code, raw_description, quantity,
                unit_price, line_revenue, invoice_ts, order_date, order_month,
                date_key, customer_id, transaction_country, is_identified_customer
            ) VALUES (
                1, 999, '489434', 'UNKNOWN_CODE', 'TEST', 1, 1.0, 1.0,
                '2009-12-01 00:00:00', '2009-12-01', '2009-12', 20091201,
                NULL, 'United Kingdom', 0
            );
            """
        )

    # Insert valid dimension rows
    cursor.execute(
        """
        INSERT INTO dim_products (
            stock_code, canonical_description, description_variant_count,
            first_sold_date, last_sold_date
        ) VALUES ('TEST01', 'TEST PRODUCT', 1, '2009-12-01', '2009-12-01');
        """
    )
    cursor.execute(
        """
        INSERT INTO dim_date (
            date_key, calendar_date, year, quarter, month, order_month,
            month_start_date, day_of_week, day_name, is_weekend
        ) VALUES (20091201, '2009-12-01', 2009, 4, 12, '2009-12', '2009-12-01', 2, 'Tuesday', 0);
        """
    )
    cursor.execute(
        """
        INSERT INTO raw_transactions (
            raw_id, source_sheet, source_row_num, loaded_at, invoice,
            stock_code, description, quantity, invoice_date, price, customer_id, country
        ) VALUES (
            1, 'Year 2009-2010', 2, '2026-11-12T00:00:00', '489434',
            'TEST01', 'TEST PRODUCT', 1, '2009-12-01 00:00:00', 10.0, NULL, 'United Kingdom'
        );
        """
    )

    # Negative quantity in clean_transactions must fail CHECK (quantity > 0)
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO clean_transactions (
                clean_id, raw_id, invoice, stock_code, raw_description, quantity,
                unit_price, line_revenue, invoice_ts, order_date, order_month,
                date_key, customer_id, transaction_country, is_identified_customer
            ) VALUES (
                1, 1, '489434', 'TEST01', 'TEST PRODUCT', -5, 10.0, -50.0,
                '2009-12-01 00:00:00', '2009-12-01', '2009-12', 20091201,
                NULL, 'United Kingdom', 0
            );
            """
        )

    # Inconsistent is_identified_customer = 1 with customer_id IS NULL must fail CHECK
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO clean_transactions (
                clean_id, raw_id, invoice, stock_code, raw_description, quantity,
                unit_price, line_revenue, invoice_ts, order_date, order_month,
                date_key, customer_id, transaction_country, is_identified_customer
            ) VALUES (
                1, 1, '489434', 'TEST01', 'TEST PRODUCT', 5, 10.0, 50.0,
                '2009-12-01 00:00:00', '2009-12-01', '2009-12', 20091201,
                NULL, 'United Kingdom', 1
            );
            """
        )


def test_dual_views_and_wholesale_fallback(memory_db: sqlite3.Connection) -> None:
    """AC-3, AC-5: Verify dual view projections, fallback country, and wholesale flags."""
    cursor = memory_db.cursor()

    # Populate dimensions
    cursor.execute(
        """
        INSERT INTO dim_products (
            stock_code, canonical_description, description_variant_count,
            first_sold_date, last_sold_date
        ) VALUES
        ('PROD_A', 'CANONICAL PRODUCT A', 1, '2009-12-01', '2009-12-01'),
        ('PROD_B', 'CANONICAL PRODUCT B', 1, '2009-12-01', '2009-12-01');
        """
    )
    cursor.execute(
        """
        INSERT INTO dim_date (
            date_key, calendar_date, year, quarter, month, order_month,
            month_start_date, day_of_week, day_name, is_weekend
        ) VALUES
        (20091201, '2009-12-01', 2009, 4, 12, '2009-12', '2009-12-01', 2, 'Tuesday', 0);
        """
    )
    cursor.execute(
        """
        INSERT INTO dim_customers (
            customer_id, primary_country, country_variant_count, first_order_date,
            cohort_month, last_order_date, lifetime_orders, lifetime_units,
            lifetime_revenue, avg_order_value, avg_units_per_order,
            is_wholesale, wholesale_reason
        ) VALUES (
            '13085', 'United Kingdom', 1, '2009-12-01', '2009-12', '2009-12-01',
            10, 50, 500.0, 50.0, 5.0, 0, NULL
        ), (
            '18102', 'United Kingdom', 1, '2009-12-01', '2009-12', '2009-12-01',
            30, 1500, 25000.0, 833.33, 50.0, 1, 'REVENUE_THRESHOLD|ORDER_COUNT_THRESHOLD'
        );
        """
    )

    # Populate raw_transactions
    cursor.execute(
        """
        INSERT INTO raw_transactions (
            raw_id, source_sheet, source_row_num, loaded_at, invoice,
            stock_code, description, quantity, invoice_date, price, customer_id, country
        ) VALUES
        (1, 'Year 2009-2010', 2, '2026-11-12T00:00:00', '489434', 'PROD_A',
         'RAW A', 10, '2009-12-01 08:00:00', 5.0, '13085', 'United Kingdom'),
        (2, 'Year 2009-2010', 3, '2026-11-12T00:00:00', '489435', 'PROD_B',
         'RAW B', 5, '2009-12-01 08:30:00', 10.0, NULL, 'France'),
        (3, 'Year 2009-2010', 4, '2026-11-12T00:00:00', '489436', 'PROD_A',
         'RAW A', 500, '2009-12-01 09:00:00', 25.0, '18102', 'United Kingdom');
        """
    )

    # Populate clean_transactions (2 identified rows, 1 unidentified guest row)
    cursor.execute(
        """
        INSERT INTO clean_transactions (
            clean_id, raw_id, invoice, stock_code, raw_description, quantity,
            unit_price, line_revenue, invoice_ts, order_date, order_month,
            date_key, customer_id, transaction_country, is_identified_customer
        ) VALUES
        (1, 1, '489434', 'PROD_A', 'RAW A', 10, 5.0, 50.0,
         '2009-12-01 08:00:00', '2009-12-01', '2009-12', 20091201, '13085', 'United Kingdom', 1),
        (2, 2, '489435', 'PROD_B', 'RAW B', 5, 10.0, 50.0,
         '2009-12-01 08:30:00', '2009-12-01', '2009-12', 20091201, NULL, 'France', 0),
        (3, 3, '489436', 'PROD_A', 'RAW A', 500, 25.0, 12500.0,
         '2009-12-01 09:00:00', '2009-12-01', '2009-12', 20091201, '18102', 'United Kingdom', 1);
        """
    )
    memory_db.commit()

    # Query vw_store_sales: must include all 3 rows
    df_store = pd.read_sql_query("SELECT * FROM vw_store_sales ORDER BY clean_id;", memory_db)
    assert len(df_store) == 3
    # Unidentified row (clean_id = 2) must have is_wholesale = 0 and country_resolved = France
    unidentified_row = df_store[df_store["clean_id"] == 2].iloc[0]
    assert unidentified_row["is_identified_customer"] == 0
    assert unidentified_row["is_wholesale"] == 0
    assert unidentified_row["country_resolved"] == "France"
    assert pd.isna(unidentified_row["primary_country"])

    # Wholesale row (clean_id = 3)
    wholesale_row = df_store[df_store["clean_id"] == 3].iloc[0]
    assert wholesale_row["is_wholesale"] == 1
    assert "REVENUE_THRESHOLD" in str(wholesale_row["wholesale_reason"])

    # Query vw_customer_sales: must include only the 2 identified rows
    df_cust = pd.read_sql_query("SELECT * FROM vw_customer_sales ORDER BY clean_id;", memory_db)
    assert len(df_cust) == 2
    assert set(df_cust["clean_id"]) == {1, 3}
    assert all(df_cust["cohort_month"] == "2009-12")


def test_audit_waterfall_conservation(memory_db: sqlite3.Connection) -> None:
    """AC-4: Verify signed audit waterfall math across cancellations and boundary splits."""
    cursor = memory_db.cursor()

    # Insert baseline and cleaning steps
    cursor.execute(
        """
        INSERT INTO cleaning_audit (
            audit_id, executed_at, step_order, rule_name, entry_type,
            rows_removed_sequential, rows_matched_raw, revenue_removed_sequential,
            remaining_rows, remaining_revenue, notes
        ) VALUES
        (1, '2026-11-12T00:00:00', 0, 'raw_baseline', 'baseline',
         0, 1000, 0.0, 1000, 100000.0, 'Total raw rows'),
        (2, '2026-11-12T00:00:00', 1, 'exact_duplicates', 'cleaning_removal',
         50, 50, 5000.0, 950, 95000.0, 'Deduplicated lines'),
        (3, '2026-11-12T00:00:00', 2, 'cancellations', 'cleaning_removal',
         30, 30, -3000.0, 920, 98000.0, 'Cancelled negative invoices'),
        (4, '2026-11-12T00:00:00', 3, 'non_merchandise_fees', 'cleaning_removal',
         10, 10, 500.0, 910, 97500.0, 'Excluded fee codes'),
        (5, '2026-11-12T00:00:00', 4, 'zero_negative_price_qty', 'cleaning_removal',
         10, 10, 0.0, 900, 97500.0, 'Zero price or negative qty'),
        (6, '2026-11-12T00:00:00', 5, 'store_valid_sales', 'output_total',
         0, 0, 0.0, 900, 97500.0, 'Store valid denominator'),
        (7, '2026-11-12T00:00:00', 6, 'missing_customer_id', 'boundary_split',
         200, 200, 20000.0, 700, 77500.0, 'Unidentified orders'),
        (8, '2026-11-12T00:00:00', 7, 'customer_valid_sales', 'output_total',
         0, 0, 0.0, 700, 77500.0, 'Customer valid denominator');
        """
    )
    memory_db.commit()

    df_audit = pd.read_sql_query("SELECT * FROM cleaning_audit ORDER BY step_order;", memory_db)
    assert len(df_audit) == 8

    # Verify arithmetic: remaining = previous - removed
    for i in range(1, 5):
        prev_row = df_audit.iloc[i - 1]
        curr_row = df_audit.iloc[i]
        assert (
            curr_row["remaining_rows"]
            == prev_row["remaining_rows"] - curr_row["rows_removed_sequential"]
        )
        expected_rev = round(
            prev_row["remaining_revenue"] - curr_row["revenue_removed_sequential"], 2
        )
        assert round(curr_row["remaining_revenue"], 2) == expected_rev

    # Verify boundary split arithmetic
    store_total = df_audit[df_audit["rule_name"] == "store_valid_sales"].iloc[0]
    split_step = df_audit[df_audit["rule_name"] == "missing_customer_id"].iloc[0]
    cust_total = df_audit[df_audit["rule_name"] == "customer_valid_sales"].iloc[0]

    assert (
        split_step["remaining_rows"]
        == store_total["remaining_rows"] - split_step["rows_removed_sequential"]
    )
    assert cust_total["remaining_rows"] == split_step["remaining_rows"]
    assert cust_total["remaining_revenue"] == split_step["remaining_revenue"]


def test_export_table_pair_and_schemas(memory_db: sqlite3.Connection, tmp_path: Path) -> None:
    """AC-9: Verify Parquet export schemas, native types, CSV generation, and lock handling."""
    cursor = memory_db.cursor()

    # Populate minimal valid rows in dim_products, dim_date, dim_customers, clean_transactions
    cursor.execute(
        """
        INSERT INTO dim_products VALUES ('P1', 'PROD 1', 1, '2009-12-01', '2009-12-01');
        """
    )
    cursor.execute(
        """
        INSERT INTO dim_date VALUES
        (20091201, '2009-12-01', 2009, 4, 12, '2009-12', '2009-12-01', 2, 'Tuesday', 0);
        """
    )
    cursor.execute(
        """
        INSERT INTO dim_customers VALUES
        ('C1', 'United Kingdom', 1, '2009-12-01', '2009-12', '2009-12-01',
         1, 5, 25.0, 25.0, 5.0, 0, NULL);
        """
    )
    cursor.execute(
        """
        INSERT INTO raw_transactions VALUES
        (1, 'Year 2009-2010', 2, '2026-11-12T00:00:00', '100', 'P1',
         'PROD 1', 5, '2009-12-01 10:00:00', 5.0, 'C1', 'United Kingdom');
        """
    )
    cursor.execute(
        """
        INSERT INTO clean_transactions VALUES
        (1, 1, '100', 'P1', 'PROD 1', 5, 5.0, 25.0,
         '2009-12-01 10:00:00', '2009-12-01', '2009-12', 20091201, 'C1', 'United Kingdom', 1);
        """
    )
    cursor.execute(
        """
        INSERT INTO cleaning_audit VALUES
        (1, '2026-11-12T00:00:00', 0, 'baseline', 'baseline', 0, 1, 0.0, 1, 25.0, 'init');
        """
    )
    memory_db.commit()

    export_dir = tmp_path / "exports"
    results = export_all_contract_tables(memory_db, export_dir)

    assert set(results.keys()) == set(EXPORT_SCHEMAS.keys())

    # Verify clean_transactions parquet schema
    pq_path, csv_path = results["clean_transactions"]
    assert pq_path.is_file()
    assert csv_path.is_file()

    schema_read = pq.read_schema(pq_path)
    assert schema_read.field("clean_id").type.equals(
        EXPORT_SCHEMAS["clean_transactions"].field("clean_id").type
    )
    assert schema_read.field("order_date").type.equals(
        EXPORT_SCHEMAS["clean_transactions"].field("order_date").type
    )
    assert schema_read.field("invoice_ts").type.equals(
        EXPORT_SCHEMAS["clean_transactions"].field("invoice_ts").type
    )
    assert schema_read.field("is_identified_customer").type.equals(
        EXPORT_SCHEMAS["clean_transactions"].field("is_identified_customer").type
    )

    # raw_transactions must NOT be exportable
    with pytest.raises(ValueError, match="disallowed"):
        export_table_pair(memory_db, "raw_transactions", export_dir)


def test_raw_transactions_sample_loading(memory_db: sqlite3.Connection) -> None:
    """AC-1: Test loading synthetic raw transactions fixture into raw_transactions."""
    cursor = memory_db.cursor()

    for row in SAMPLE_RAW_TRANSACTIONS:
        cursor.execute(
            """
            INSERT INTO raw_transactions (
                source_sheet, source_row_num, loaded_at, invoice,
                stock_code, description, quantity, invoice_date, price, customer_id, country
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                row["source_sheet"],
                row["source_row_num"],
                row["loaded_at"],
                row["invoice"],
                row["stock_code"],
                row["description"],
                row["quantity"],
                row["invoice_date"],
                row["price"],
                row["customer_id"],
                row["country"],
            ),
        )
    memory_db.commit()

    cursor.execute("SELECT COUNT(*) FROM raw_transactions;")
    assert cursor.fetchone()[0] == len(SAMPLE_RAW_TRANSACTIONS)


def test_connect_db_directory_validation(tmp_path: Path) -> None:
    """Verify connect_db enforces existing parent directory and configures pragmas."""
    missing_dir_path = tmp_path / "nonexistent_subfolder" / "retail.db"
    with pytest.raises(FileNotFoundError, match="Database parent directory does not exist"):
        connect_db(missing_dir_path)

    # Valid disk connection
    valid_db_path = tmp_path / "valid_retail.db"
    conn = connect_db(valid_db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode;")
    assert cur.fetchone()[0].lower() == "wal"
    cur.execute("PRAGMA foreign_keys;")
    assert cur.fetchone()[0] == 1
    cur.execute("PRAGMA busy_timeout;")
    assert cur.fetchone()[0] == 5000
    conn.close()


def test_initialize_schema_missing_sql_file(memory_db: sqlite3.Connection, tmp_path: Path) -> None:
    """Verify initialize_schema raises FileNotFoundError when SQL file is missing."""
    missing_file = tmp_path / "missing_schema.sql"
    with pytest.raises(FileNotFoundError, match="Schema SQL file not found"):
        initialize_schema(memory_db, missing_file)


def test_verify_schema_contract_missing_objects(memory_db: sqlite3.Connection) -> None:
    """Verify verify_schema_contract raises RuntimeError on missing tables, views, or seeds."""
    # 1. Missing table
    memory_db.execute("DROP TABLE cleaning_audit;")
    with pytest.raises(RuntimeError, match="Missing required database tables"):
        verify_schema_contract(memory_db)
    initialize_schema(memory_db)

    # 2. Missing view
    memory_db.execute("DROP VIEW vw_store_sales;")
    with pytest.raises(RuntimeError, match="Missing required database views"):
        verify_schema_contract(memory_db)
    initialize_schema(memory_db)

    # 3. Missing index
    memory_db.execute("DROP INDEX idx_clean_invoice;")
    with pytest.raises(RuntimeError, match="Missing required database indexes"):
        verify_schema_contract(memory_db)
    initialize_schema(memory_db)

    # 4. Missing config key
    memory_db.execute("DELETE FROM ref_pipeline_config WHERE config_key = 'rfm_reference_date';")
    with pytest.raises(RuntimeError, match="Missing required pipeline configuration keys"):
        verify_schema_contract(memory_db)
    initialize_schema(memory_db)

    # 5. Empty ref_excluded_stock_codes table
    memory_db.execute("DELETE FROM ref_excluded_stock_codes;")
    with pytest.raises(RuntimeError, match="ref_excluded_stock_codes table is empty"):
        verify_schema_contract(memory_db)


def test_export_disallowed_and_unknown_relations(
    memory_db: sqlite3.Connection, tmp_path: Path
) -> None:
    """Verify export_table_pair rejects disallowed raw tables and unknown table names."""
    export_dir = tmp_path / "exports"
    for disallowed in DISALLOWED_EXPORTS:
        with pytest.raises(ValueError, match="disallowed"):
            export_table_pair(memory_db, disallowed, export_dir)

    with pytest.raises(ValueError, match="No export schema defined"):
        export_table_pair(memory_db, "unknown_table_xyz", export_dir)


def test_atomic_swap_diagnoses_windows_file_lock(tmp_path: Path) -> None:
    """Verify _atomic_swap wraps PermissionError into actionable lock diagnostics."""
    src = tmp_path / "source.tmp"
    dst = tmp_path / "target.parquet"
    src.write_text("sample content", encoding="utf-8")
    dst.write_text("initial content", encoding="utf-8")

    # Mock Path.replace raising PermissionError as seen on locked Windows files
    with patch.object(
        type(src), "replace", side_effect=PermissionError("WinError 32: The process cannot access")
    ):
        with pytest.raises(PermissionError, match="locked by another process") as exc_info:
            _atomic_swap(src, dst)
        assert "Power BI Desktop or Excel" in str(exc_info.value)


def test_convert_dataframe_types_edge_cases() -> None:
    """Verify _convert_dataframe_types accurately casts and preserves nulls across types."""
    schema = pa.schema(
        [
            ("date_col", pa.date32()),
            ("ts_col", pa.timestamp("ms")),
            ("bool_col", pa.bool_()),
            ("int_col", pa.int64()),
            ("float_col", pa.float64()),
            ("str_col", pa.string()),
        ]
    )

    df_in = pd.DataFrame(
        {
            "date_col": ["2010-01-15", None],
            "ts_col": ["2010-01-15 14:30:00", None],
            "bool_col": [1, 0],
            "int_col": [42.0, None],
            "float_col": ["99.95", None],
            "str_col": ["12345", None],
        }
    )

    df_out = _convert_dataframe_types(df_in, schema)

    assert isinstance(df_out["date_col"].iloc[0], dt.date)
    assert pd.api.types.is_datetime64_any_dtype(df_out["ts_col"])
    assert df_out["bool_col"].dtype.name == "boolean"
    assert df_out["bool_col"].iloc[0] is True or df_out["bool_col"].iloc[0] == 1
    assert df_out["int_col"].dtype.name == "Int64"
    assert df_out["int_col"].iloc[0] == 42
    assert pd.isna(df_out["int_col"].iloc[1])
    assert df_out["float_col"].dtype.name == "float64"
    assert df_out["float_col"].iloc[0] == 99.95
    assert df_out["str_col"].dtype.name == "string"
    assert df_out["str_col"].iloc[0] == "12345"
    assert pd.isna(df_out["str_col"].iloc[1])
