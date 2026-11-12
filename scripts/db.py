"""Database connection, schema initialization, and contract verification for retail.db."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

EXPECTED_TABLES: tuple[str, ...] = (
    "raw_transactions",
    "ref_excluded_stock_codes",
    "ref_pipeline_config",
    "dim_date",
    "dim_products",
    "dim_customers",
    "clean_transactions",
    "cleaning_audit",
)

EXPECTED_VIEWS: tuple[str, ...] = (
    "vw_store_sales",
    "vw_customer_sales",
)

EXPECTED_INDEXES: tuple[str, ...] = (
    "idx_clean_customer_month",
    "idx_clean_order_month",
    "idx_clean_stock_code",
    "idx_clean_date_key",
    "idx_clean_invoice",
)

EXPECTED_CONFIG_KEYS: tuple[str, ...] = (
    "rfm_reference_date",
    "wholesale_min_lifetime_revenue",
    "wholesale_min_orders",
    "wholesale_min_avg_units_per_order",
    "wholesale_rule_mode",
)


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode, foreign keys, and busy timeout enabled.

    Args:
        db_path: Path to the SQLite database file or ':memory:'.

    Returns:
        sqlite3.Connection with active pragmas configured.

    Raises:
        FileNotFoundError: If the parent directory of the database file does not exist.
    """
    path_obj = Path(db_path) if isinstance(db_path, str) else db_path
    if str(path_obj) != ":memory:" and not path_obj.parent.exists():
        msg = f"Database parent directory does not exist: {path_obj.parent}"
        raise FileNotFoundError(msg)

    conn = sqlite3.connect(path_obj, timeout=5.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def initialize_schema(
    conn: sqlite3.Connection,
    schema_sql_path: str | Path | None = None,
) -> None:
    """Execute idempotent schema DDL and reference seeds inside an atomic transaction.

    Args:
        conn: Active SQLite connection.
        schema_sql_path: Optional path to the SQL DDL file. Defaults to sql/00_schema.sql.

    Raises:
        FileNotFoundError: If the schema SQL file cannot be found.
    """
    resolved_path = (
        Path(schema_sql_path)
        if schema_sql_path is not None
        else Path(__file__).resolve().parent.parent / "sql" / "00_schema.sql"
    )

    if not resolved_path.is_file():
        msg = f"Schema SQL file not found: {resolved_path}"
        raise FileNotFoundError(msg)

    sql_script = resolved_path.read_text(encoding="utf-8")
    with conn:
        conn.executescript(sql_script)


def verify_schema_contract(conn: sqlite3.Connection) -> dict[str, Any]:
    """Verify that all required tables, views, indexes, and config keys exist.

    Args:
        conn: Active SQLite connection.

    Returns:
        Dictionary summarizing verified tables, views, indexes, and seeds.

    Raises:
        RuntimeError: If any expected table, view, index, or config key is missing.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table';")
    existing_tables = {row[0] for row in cursor.fetchall()}
    missing_tables = [t for t in EXPECTED_TABLES if t not in existing_tables]
    if missing_tables:
        msg = f"Missing required database tables: {missing_tables}"
        raise RuntimeError(msg)

    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'view';")
    existing_views = {row[0] for row in cursor.fetchall()}
    missing_views = [v for v in EXPECTED_VIEWS if v not in existing_views]
    if missing_views:
        msg = f"Missing required database views: {missing_views}"
        raise RuntimeError(msg)

    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'index' AND name NOT LIKE 'sqlite_autoindex_%';"
    )
    existing_indexes = {row[0] for row in cursor.fetchall()}
    missing_indexes = [idx for idx in EXPECTED_INDEXES if idx not in existing_indexes]
    if missing_indexes:
        msg = f"Missing required database indexes: {missing_indexes}"
        raise RuntimeError(msg)

    cursor.execute("SELECT config_key FROM ref_pipeline_config;")
    existing_keys = {row[0] for row in cursor.fetchall()}
    missing_keys = [k for k in EXPECTED_CONFIG_KEYS if k not in existing_keys]
    if missing_keys:
        msg = f"Missing required pipeline configuration keys: {missing_keys}"
        raise RuntimeError(msg)

    cursor.execute("SELECT COUNT(*) FROM ref_excluded_stock_codes;")
    excluded_count = int(cursor.fetchone()[0])
    if excluded_count == 0:
        msg = "ref_excluded_stock_codes table is empty; starter seeds missing"
        raise RuntimeError(msg)

    return {
        "tables": sorted(existing_tables),
        "views": sorted(existing_views),
        "indexes": sorted(existing_indexes),
        "config_keys": sorted(existing_keys),
        "excluded_stock_codes_count": excluded_count,
    }


def seed_dim_date(
    conn: sqlite3.Connection,
    start_date: str = "2009-12-01",
    end_date: str = "2011-12-31",
) -> int:
    """Generate continuous calendar dimension rows and bulk insert into dim_date.

    Args:
        conn: Active SQLite database connection.
        start_date: Start date string in ISO format (YYYY-MM-DD).
        end_date: End date string in ISO format (YYYY-MM-DD).

    Returns:
        Total number of date records populated.
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        msg = f"start_date ({start_date}) cannot be after end_date ({end_date})"
        raise ValueError(msg)

    rows: list[tuple[int, str, int, int, int, str, str, int, str, int]] = []
    curr = start
    while curr <= end:
        date_key = int(curr.strftime("%Y%m%d"))
        calendar_date = curr.isoformat()
        year = curr.year
        quarter = (curr.month - 1) // 3 + 1
        month = curr.month
        order_month = curr.strftime("%Y-%m")
        month_start_date = f"{curr.year:04d}-{curr.month:02d}-01"
        day_of_week = curr.isoweekday()
        day_name = curr.strftime("%A")
        is_weekend = 1 if day_of_week in (6, 7) else 0

        rows.append(
            (
                date_key,
                calendar_date,
                year,
                quarter,
                month,
                order_month,
                month_start_date,
                day_of_week,
                day_name,
                is_weekend,
            )
        )
        curr += timedelta(days=1)

    insert_sql = """
        INSERT OR REPLACE INTO dim_date (
            date_key,
            calendar_date,
            year,
            quarter,
            month,
            order_month,
            month_start_date,
            day_of_week,
            day_name,
            is_weekend
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    with conn:
        conn.executemany(insert_sql, rows)

    return len(rows)


def reset_clean_tables(conn: sqlite3.Connection) -> None:
    """Clear clean fact, dimensions, and audit tables in reverse foreign key order.

    Args:
        conn: Active SQLite connection.
    """
    with conn:
        conn.execute("DELETE FROM clean_transactions;")
        conn.execute("DELETE FROM dim_customers;")
        conn.execute("DELETE FROM dim_products;")
        conn.execute("DELETE FROM cleaning_audit;")
