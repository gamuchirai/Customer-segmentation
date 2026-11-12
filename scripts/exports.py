"""Typed Parquet and atomic CSV export utilities for Power BI Desktop ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:
    import sqlite3

# Explicit pyarrow schema definitions enforcing timezone-naive timestamps,
# exact date32 units, int64 identifiers, and boolean flags for Power BI.
EXPORT_SCHEMAS: dict[str, pa.Schema] = {
    "clean_transactions": pa.schema(
        [
            ("clean_id", pa.int64()),
            ("raw_id", pa.int64()),
            ("invoice", pa.string()),
            ("stock_code", pa.string()),
            ("raw_description", pa.string()),
            ("quantity", pa.int64()),
            ("unit_price", pa.float64()),
            ("line_revenue", pa.float64()),
            ("invoice_ts", pa.timestamp("ms")),
            ("order_date", pa.date32()),
            ("order_month", pa.string()),
            ("date_key", pa.int64()),
            ("customer_id", pa.string()),
            ("transaction_country", pa.string()),
            ("is_identified_customer", pa.bool_()),
        ]
    ),
    "dim_customers": pa.schema(
        [
            ("customer_id", pa.string()),
            ("primary_country", pa.string()),
            ("country_variant_count", pa.int64()),
            ("first_order_date", pa.date32()),
            ("cohort_month", pa.string()),
            ("last_order_date", pa.date32()),
            ("lifetime_orders", pa.int64()),
            ("lifetime_units", pa.int64()),
            ("lifetime_revenue", pa.float64()),
            ("avg_order_value", pa.float64()),
            ("avg_units_per_order", pa.float64()),
            ("is_wholesale", pa.bool_()),
            ("wholesale_reason", pa.string()),
        ]
    ),
    "dim_products": pa.schema(
        [
            ("stock_code", pa.string()),
            ("canonical_description", pa.string()),
            ("description_variant_count", pa.int64()),
            ("first_sold_date", pa.date32()),
            ("last_sold_date", pa.date32()),
        ]
    ),
    "dim_date": pa.schema(
        [
            ("date_key", pa.int64()),
            ("calendar_date", pa.date32()),
            ("year", pa.int64()),
            ("quarter", pa.int64()),
            ("month", pa.int64()),
            ("order_month", pa.string()),
            ("month_start_date", pa.date32()),
            ("day_of_week", pa.int64()),
            ("day_name", pa.string()),
            ("is_weekend", pa.bool_()),
        ]
    ),
    "cleaning_audit": pa.schema(
        [
            ("audit_id", pa.int64()),
            ("executed_at", pa.timestamp("ms")),
            ("step_order", pa.int64()),
            ("rule_name", pa.string()),
            ("entry_type", pa.string()),
            ("rows_removed_sequential", pa.int64()),
            ("rows_matched_raw", pa.int64()),
            ("revenue_removed_sequential", pa.float64()),
            ("remaining_rows", pa.int64()),
            ("remaining_revenue", pa.float64()),
            ("notes", pa.string()),
        ]
    ),
}

DISALLOWED_EXPORTS: tuple[str, ...] = ("raw_transactions",)


def _convert_dataframe_types(
    df: pd.DataFrame,
    schema: pa.Schema,
) -> pd.DataFrame:
    """Cast DataFrame columns to align cleanly with the target pyarrow Schema.

    Args:
        df: Input pandas DataFrame.
        schema: Target PyArrow schema.

    Returns:
        Type-converted copy of the DataFrame.
    """
    df_converted = df.copy()

    for field in schema:
        col = field.name
        if col not in df_converted.columns:
            continue

        target_type = field.type
        if pa.types.is_date32(target_type):
            df_converted[col] = pd.to_datetime(df_converted[col]).dt.date
        elif pa.types.is_timestamp(target_type):
            df_converted[col] = pd.to_datetime(df_converted[col]).dt.tz_localize(None)
        elif pa.types.is_boolean(target_type):
            df_converted[col] = df_converted[col].astype("boolean")
        elif pa.types.is_integer(target_type):
            df_converted[col] = pd.to_numeric(df_converted[col], errors="coerce").astype("Int64")
        elif pa.types.is_floating(target_type):
            df_converted[col] = pd.to_numeric(df_converted[col], errors="coerce").astype("float64")
        elif pa.types.is_string(target_type):
            df_converted[col] = df_converted[col].astype("string")

    return df_converted


def export_table_pair(
    conn: sqlite3.Connection,
    relation_name: str,
    export_dir: str | Path,
    pa_schema: pa.Schema | None = None,
) -> tuple[Path, Path]:
    """Atomically export a relation to both Parquet and CSV in export_dir.

    Args:
        conn: Active SQLite connection.
        relation_name: Name of the SQLite table or view to export.
        export_dir: Destination directory for exported files.
        pa_schema: Optional explicit pyarrow Schema. If omitted, looked up in EXPORT_SCHEMAS.

    Returns:
        Tuple of (parquet_path, csv_path).

    Raises:
        ValueError: If relation_name is disallowed or not recognized in EXPORT_SCHEMAS.
        PermissionError: If target file cannot be replaced due to a file lock (WinError 32).
    """
    if relation_name in DISALLOWED_EXPORTS:
        msg = f"Export of '{relation_name}' is disallowed; it must remain inside retail.db only."
        raise ValueError(msg)

    resolved_schema = pa_schema if pa_schema is not None else EXPORT_SCHEMAS.get(relation_name)
    if resolved_schema is None:
        msg = f"No export schema defined for relation '{relation_name}'."
        raise ValueError(msg)

    dest_dir = Path(export_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    df_raw = pd.read_sql_query(f"SELECT * FROM {relation_name};", conn)  # noqa: S608
    df_typed = _convert_dataframe_types(df_raw, resolved_schema)

    arrow_table = pa.Table.from_pandas(df_typed, schema=resolved_schema, preserve_index=False)

    parquet_target = dest_dir / f"{relation_name}.parquet"
    csv_target = dest_dir / f"{relation_name}.csv"

    parquet_tmp = dest_dir / f"{relation_name}.parquet.tmp"
    csv_tmp = dest_dir / f"{relation_name}.csv.tmp"

    try:
        pq.write_table(arrow_table, parquet_tmp, compression="snappy")
        df_typed.to_csv(csv_tmp, index=False, encoding="utf-8")

        _atomic_swap(parquet_tmp, parquet_target)
        _atomic_swap(csv_tmp, csv_target)
    except Exception:
        if parquet_tmp.exists():
            parquet_tmp.unlink()
        if csv_tmp.exists():
            csv_tmp.unlink()
        raise

    return parquet_target, csv_target


def _atomic_swap(src: Path, dst: Path) -> None:
    """Replace destination file with source file atomically, diagnosing file locks.

    Args:
        src: Temporary source file path.
        dst: Final destination file path.

    Raises:
        PermissionError: With actionable message if Windows file lock prevents replacement.
    """
    try:
        src.replace(dst)
    except PermissionError as exc:
        msg = (
            f"Failed to replace '{dst}': the file is locked by another process "
            f"(e.g., Power BI Desktop or Excel). Close the file and retry. Details: {exc}"
        )
        raise PermissionError(msg) from exc


def export_all_contract_tables(
    conn: sqlite3.Connection,
    export_dir: str | Path,
) -> dict[str, tuple[Path, Path]]:
    """Export all tables registered in EXPORT_SCHEMAS.

    Args:
        conn: Active SQLite connection.
        export_dir: Destination directory.

    Returns:
        Mapping of table name to (parquet_path, csv_path).
    """
    results: dict[str, Any] = {}
    for table_name, schema in EXPORT_SCHEMAS.items():
        results[table_name] = export_table_pair(
            conn=conn,
            relation_name=table_name,
            export_dir=export_dir,
            pa_schema=schema,
        )
    return results
