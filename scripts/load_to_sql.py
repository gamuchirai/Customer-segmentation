"""Data extraction, staging, cleaning, and export orchestration CLI for retail.db."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

# Ensure project root is on sys.path when invoked directly as a script
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.db import connect_db, initialize_schema, seed_dim_date  # noqa: E402
from scripts.exports import export_all_contract_tables  # noqa: E402

if TYPE_CHECKING:
    import sqlite3

EXPECTED_SHEETS: tuple[str, ...] = ("Year 2009-2010", "Year 2010-2011")
EXPECTED_COLUMNS: tuple[str, ...] = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments for the ingestion and cleaning pipeline.

    Args:
        argv: Command line argument list. If None, sys.argv[1:] is used.

    Returns:
        Parsed argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Load raw Excel workbook into SQLite, clean data, and export marts."
    )
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Extract raw Excel sheets into raw_transactions only (skip cleaning).",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Run SQL cleaning and dimension derivation from existing raw_transactions.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop and recreate all tables and views before running.",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Skip automatic Parquet and CSV export generation in exports/.",
    )
    parser.add_argument(
        "--excel-path",
        type=Path,
        default=Path("dataset/online_retail_II.xlsx"),
        help="Path to the raw Excel workbook (default: dataset/online_retail_II.xlsx).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("retail.db"),
        help="Path to the SQLite database file (default: retail.db).",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=Path("exports"),
        help="Directory to write exported Parquet and CSV files (default: exports).",
    )
    return parser.parse_args(argv)


def validate_cli_flags(args: argparse.Namespace) -> None:
    """Validate that CLI flag combinations are mutually compatible.

    Args:
        args: Parsed command line arguments.

    Raises:
        ValueError: If conflicting arguments are provided.
    """
    if args.stage_only and args.clean_only:
        msg = "Cannot combine --stage-only with --clean-only: choose one pipeline phase."
        raise ValueError(msg)

    if args.rebuild and args.clean_only:
        msg = "Cannot combine --rebuild with --clean-only: rebuild wipes raw_transactions."
        raise ValueError(msg)


def validate_excel_source(excel_path: Path) -> list[str]:
    """Validate that the source Excel workbook exists and contains expected sheets.

    Args:
        excel_path: Path to the Excel workbook.

    Returns:
        List of sheet names confirmed in the workbook.

    Raises:
        FileNotFoundError: If the workbook does not exist.
        ValueError: If any expected sheet is missing.
    """
    if not excel_path.is_file():
        msg = f"Raw Excel workbook not found: {excel_path}"
        raise FileNotFoundError(msg)

    excel_file = pd.ExcelFile(excel_path, engine="openpyxl")
    sheet_names = [str(s) for s in excel_file.sheet_names]

    missing_sheets = [s for s in EXPECTED_SHEETS if s not in sheet_names]
    if missing_sheets:
        msg = (
            f"Excel workbook {excel_path} is missing expected sheet(s): {missing_sheets}. "
            f"Found sheets: {sheet_names}"
        )
        raise ValueError(msg)

    return sheet_names


def sanitize_raw_records(
    df: pd.DataFrame,
    sheet_name: str,
    loaded_at: str,
) -> list[tuple[Any, ...]]:
    """Sanitize and normalize DataFrame rows into raw_transactions tuples.

    Args:
        df: Raw DataFrame loaded from one sheet.
        sheet_name: Source Excel sheet name.
        loaded_at: ISO 8601 timestamp string of ingestion.

    Returns:
        List of sanitized tuples ready for raw_transactions insertion.

    Raises:
        ValueError: If required columns are missing from the sheet.
    """
    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing_cols:
        msg = f"Sheet '{sheet_name}' is missing required columns: {missing_cols}"
        raise ValueError(msg)

    rows: list[tuple[Any, ...]] = []
    # Physical Excel rows: 1-based, with header occupying row 1
    for source_row_num, (_, row) in enumerate(df.iterrows(), start=2):
        raw_invoice = row["Invoice"]
        invoice = str(raw_invoice).strip() if pd.notna(raw_invoice) else None

        raw_stock = row["StockCode"]
        stock_code = str(raw_stock).strip() if pd.notna(raw_stock) else None

        raw_desc = row["Description"]
        if pd.isna(raw_desc):
            description = None
        else:
            desc_str = str(raw_desc).strip()
            description = None if desc_str.lower() in ("", "nan", "none", "null") else desc_str

        raw_qty = row["Quantity"]
        quantity = round(float(raw_qty)) if pd.notna(raw_qty) else None

        raw_date = row["InvoiceDate"]
        if pd.isna(raw_date):
            invoice_date = None
        else:
            ts = pd.to_datetime(raw_date)
            invoice_date = ts.strftime("%Y-%m-%d %H:%M:%S")

        raw_price = row["Price"]
        price = float(raw_price) if pd.notna(raw_price) else None

        raw_cust = row["Customer ID"]
        if pd.isna(raw_cust):
            customer_id = None
        else:
            cust_str = str(raw_cust).strip().removesuffix(".0")
            customer_id = None if cust_str.lower() in ("", "nan", "none", "null") else cust_str

        raw_country = row["Country"]
        country = str(raw_country).strip() if pd.notna(raw_country) else None

        rows.append(
            (
                sheet_name,
                source_row_num,
                loaded_at,
                invoice,
                stock_code,
                description,
                quantity,
                invoice_date,
                price,
                customer_id,
                country,
            )
        )

    return rows


def stage_raw_data(
    conn: sqlite3.Connection,
    excel_path: Path,
    batch_size: int = 50000,
) -> int:
    """Read all expected sheets from raw Excel workbook and insert into raw_transactions.

    Args:
        conn: Active SQLite database connection.
        excel_path: Path to raw Excel workbook.
        batch_size: Row batch size for sqlite3 executemany.

    Returns:
        Total number of raw rows inserted.
    """
    validate_excel_source(excel_path)
    loaded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    total_inserted = 0
    for sheet_name in EXPECTED_SHEETS:
        print(f"Reading sheet '{sheet_name}' from {excel_path}...")
        df = pd.read_excel(excel_path, sheet_name=sheet_name, engine="openpyxl")
        print(f"Processing {len(df):,} rows from '{sheet_name}'...")
        rows = sanitize_raw_records(df, sheet_name=sheet_name, loaded_at=loaded_at)

        with conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                conn.executemany(insert_sql, batch)
        total_inserted += len(rows)
        print(f"Staged {len(rows):,} rows from sheet '{sheet_name}'.")

    return total_inserted


def execute_cleaning_pipeline(
    conn: sqlite3.Connection,
    cleaning_sql_path: Path | None = None,
) -> dict[str, Any]:
    """Execute SQL data cleaning, dimension derivations, and audit waterfall logging.

    Args:
        conn: Active SQLite database connection.
        cleaning_sql_path: Optional path to sql/01_data_cleaning.sql.

    Returns:
        Summary dictionary containing table row counts and audit status.
    """
    resolved_path = (
        cleaning_sql_path
        if cleaning_sql_path is not None
        else Path(__file__).resolve().parent.parent / "sql" / "01_data_cleaning.sql"
    )

    if not resolved_path.is_file():
        msg = f"Data cleaning SQL script not found: {resolved_path}"
        raise FileNotFoundError(msg)

    # Pre-seed calendar dimension to ensure foreign key validity
    seed_dim_date(conn)

    sql_script = resolved_path.read_text(encoding="utf-8")
    with conn:
        conn.executescript(sql_script)

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM clean_transactions;")
    clean_count = int(cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM dim_products;")
    product_count = int(cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM dim_customers;")
    customer_count = int(cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM cleaning_audit;")
    audit_count = int(cursor.fetchone()[0])

    cursor.execute(
        "SELECT rule_name, remaining_rows, remaining_revenue "
        "FROM cleaning_audit ORDER BY step_order;"
    )
    audit_steps = [
        {"rule": row[0], "remaining_rows": row[1], "remaining_revenue": round(row[2], 2)}
        for row in cursor.fetchall()
    ]

    return {
        "clean_transactions_count": clean_count,
        "dim_products_count": product_count,
        "dim_customers_count": customer_count,
        "cleaning_audit_steps_count": audit_count,
        "audit_waterfall": audit_steps,
    }


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """Orchestrate the ingestion, cleaning, and export pipeline based on CLI arguments.

    Args:
        args: Parsed command line arguments.

    Returns:
        Dictionary of execution results.
    """
    validate_cli_flags(args)
    conn = connect_db(args.db_path)

    try:
        # Rebuild option reinitializes schema from scratch
        if args.rebuild:
            print(f"Rebuilding database schema at {args.db_path}...")
            initialize_schema(conn)

        # Check raw_transactions status
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM raw_transactions;")
        raw_count = int(cursor.fetchone()[0])

        staged_rows = 0
        if not args.clean_only:
            if raw_count == 0 or args.rebuild:
                print(f"Staging raw data from {args.excel_path}...")
                staged_rows = stage_raw_data(conn, args.excel_path)
            else:
                print(f"raw_transactions already contains {raw_count:,} rows. Skipping extraction.")
        elif raw_count == 0:
            msg = "raw_transactions is empty. Cannot run --clean-only without staged data."
            raise RuntimeError(msg)

        if args.stage_only:
            return {"status": "staged_only", "staged_rows": staged_rows or raw_count}

        print("Executing SQL data cleaning and dimension derivation...")
        clean_results = execute_cleaning_pipeline(conn)
        print(f"Populated {clean_results['clean_transactions_count']:,} clean transactions.")
        print(f"Populated {clean_results['dim_products_count']:,} products in dim_products.")
        print(f"Populated {clean_results['dim_customers_count']:,} customers in dim_customers.")

        export_results = None
        if not args.no_export:
            print(f"Refreshing Power BI export marts in {args.export_dir}...")
            export_results = export_all_contract_tables(conn, args.export_dir)
            print(f"Exported {len(export_results)} tables to Parquet and CSV.")

        return {
            "status": "success",
            "staged_rows": staged_rows or raw_count,
            "cleaning": clean_results,
            "exported_tables": list(export_results.keys()) if export_results else [],
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for python scripts/load_to_sql.py."""
    args = parse_args(argv)
    try:
        results = run_pipeline(args)
        print("\n--- Pipeline Completed Successfully ---")
        if "cleaning" in results and "audit_waterfall" in results["cleaning"]:
            print("Cleaning Waterfall Snapshot:")
            for step in results["cleaning"]["audit_waterfall"]:
                print(
                    f"  {step['rule']:<32} "
                    f"Rows: {step['remaining_rows']:<10,d} "
                    f"Revenue: £{step['remaining_revenue']:<12,.2f}"
                )
    except Exception as exc:  # noqa: BLE001
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
