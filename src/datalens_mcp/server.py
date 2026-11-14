"""DataLens MCP: dataset discovery, profiling, quality checks, and read-only SQL."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import duckdb
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "DataLens",
    instructions=(
        "Use DataLens to inspect local CSV, Parquet, and SQLite datasets. "
        "Start with list_datasets, then profile a dataset or inspect its columns. "
        "SQL execution is read-only and limited to SELECT/WITH queries."
    ),
)

DATA_DIR = Path(os.getenv("DATALENS_DATA_DIR", "./data")).expanduser().resolve()
SUPPORTED_SUFFIXES = {".csv", ".parquet", ".pq", ".db", ".sqlite", ".sqlite3"}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|COPY|ATTACH|DETACH|INSTALL|LOAD|"
    r"EXPORT|IMPORT|CALL|PRAGMA|SET|RESET|TRUNCATE|VACUUM|秘密)\b",
    re.IGNORECASE,
)


def _discover() -> dict[str, Path]:
    """Discover supported files directly inside the configured data directory."""
    if not DATA_DIR.exists():
        return {}
    return {
        path.stem: path.resolve()
        for path in sorted(DATA_DIR.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    }


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid dataset or column identifier: {value!r}")
    return f'"{value}"'


def _relation_sql(path: Path) -> str:
    escaped = str(path).replace("'", "''")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return f"read_csv_auto('{escaped}', header=true)"
    if suffix in {".parquet", ".pq"}:
        return f"read_parquet('{escaped}')"
    raise ValueError("SQLite files are discoverable but are not yet queryable as flat datasets.")


def _load_relation(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> None:
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW {_quote_identifier(name)} AS "
        f"SELECT * FROM {_relation_sql(path)}"
    )


def _get_dataset(name: str) -> Path:
    datasets = _discover()
    if name not in datasets:
        available = ", ".join(sorted(datasets)) or "(none)"
        raise ValueError(f"Dataset {name!r} not found. Available datasets: {available}")
    return datasets[name]


def _connect_with_dataset(name: str) -> duckdb.DuckDBPyConnection:
    path = _get_dataset(name)
    con = duckdb.connect(":memory:")
    _load_relation(con, name, path)
    return con


@mcp.tool()
def list_datasets() -> dict[str, Any]:
    """List supported data files in DATALENS_DATA_DIR, including file type and size."""
    results = []
    for name, path in _discover().items():
        results.append({
            "name": name,
            "file": path.name,
            "format": path.suffix.lower().lstrip("."),
            "size_bytes": path.stat().st_size,
        })
    return {"data_directory": str(DATA_DIR), "count": len(results), "datasets": results}


@mcp.tool()
def describe_dataset(dataset: str) -> dict[str, Any]:
    """Return row count, column names, and inferred data types for a CSV or Parquet dataset."""
    con = _connect_with_dataset(dataset)
    try:
        columns = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [dataset],
        ).fetchall()
        row_count = con.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(dataset)}"
        ).fetchone()[0]
        return {
            "dataset": dataset,
            "row_count": row_count,
            "columns": [{"name": name, "type": dtype} for name, dtype in columns],
        }
    finally:
        con.close()


@mcp.tool()
def profile_dataset(dataset: str, sample_size: int = 5) -> dict[str, Any]:
    """Create a compact data profile with null counts, distinct counts, and sample values."""
    if not 1 <= sample_size <= 20:
        raise ValueError("sample_size must be between 1 and 20")
    con = _connect_with_dataset(dataset)
    try:
        description = con.execute(
            f"DESCRIBE SELECT * FROM {_quote_identifier(dataset)}"
        ).fetchall()
        columns = []
        for row in description:
            column_name, column_type = row[0], row[1]
            col = _quote_identifier(column_name)
            stats = con.execute(
                f"SELECT COUNT(*) AS total, "
                f"COUNT(*) FILTER (WHERE {col} IS NULL) AS nulls, "
                f"COUNT(DISTINCT {col}) AS distinct_values "
                f"FROM {_quote_identifier(dataset)}"
            ).fetchone()
            sample = con.execute(
                f"SELECT DISTINCT CAST({col} AS VARCHAR) "
                f"FROM {_quote_identifier(dataset)} WHERE {col} IS NOT NULL "
                f"LIMIT {sample_size}"
            ).fetchall()
            total, nulls, distinct_values = stats
            columns.append({
                "name": column_name,
                "type": column_type,
                "null_count": nulls,
                "null_percent": round((nulls / total) * 100, 2) if total else 0.0,
                "distinct_count": distinct_values,
                "sample_values": [item[0] for item in sample],
            })
        row_count = con.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(dataset)}"
        ).fetchone()[0]
        return {"dataset": dataset, "row_count": row_count, "columns": columns}
    finally:
        con.close()


@mcp.tool()
def detect_quality_issues(dataset: str) -> dict[str, Any]:
    """Flag columns with missing values and datasets containing duplicate rows."""
    con = _connect_with_dataset(dataset)
    try:
        schema = con.execute(
            f"DESCRIBE SELECT * FROM {_quote_identifier(dataset)}"
        ).fetchall()
        row_count = con.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(dataset)}"
        ).fetchone()[0]
        issues = []
        for row in schema:
            name = row[0]
            col = _quote_identifier(name)
            nulls = con.execute(
                f"SELECT COUNT(*) FROM {_quote_identifier(dataset)} WHERE {col} IS NULL"
            ).fetchone()[0]
            if nulls:
                issues.append({
                    "type": "missing_values",
                    "column": name,
                    "count": nulls,
                    "percent": round(nulls / row_count * 100, 2) if row_count else 0.0,
                    "severity": "high" if row_count and nulls / row_count >= 0.2 else "medium",
                })

        duplicate_count = con.execute(
            f"SELECT COUNT(*) FROM (SELECT * FROM {_quote_identifier(dataset)} "
            f"GROUP BY ALL HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        if duplicate_count:
            issues.append({
                "type": "duplicate_rows",
                "duplicate_groups": duplicate_count,
                "severity": "medium",
            })
        return {
            "dataset": dataset,
            "row_count": row_count,
            "issue_count": len(issues),
            "issues": issues,
        }
    finally:
        con.close()


@mcp.tool()
def run_sql(dataset: str, query: str, limit: int = 100) -> dict[str, Any]:
    """Run a read-only SELECT/WITH query against one registered dataset.

    The dataset is available as a table named after its file (without extension).
    Results are capped by `limit` (1-500). Example:
    SELECT department, COUNT(*) AS n FROM employees GROUP BY department
    """
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    normalized = query.strip()
    if not normalized:
        raise ValueError("Query cannot be empty")
    # Permit one optional trailing semicolon, but reject multi-statement input.
    normalized = normalized[:-1].rstrip() if normalized.endswith(";") else normalized
    if ";" in normalized:
        raise ValueError("Only one SQL statement is allowed")
    if not re.match(r"^(SELECT|WITH)\b", normalized, flags=re.IGNORECASE):
        raise ValueError("Only SELECT or WITH queries are allowed")
    if _FORBIDDEN_SQL.search(normalized):
        raise ValueError("Query contains a prohibited SQL operation")
    con = _connect_with_dataset(dataset)
    try:
        result = con.execute(normalized).fetchmany(limit + 1)
        truncated = len(result) > limit
        result = result[:limit]
        columns = [item[0] for item in con.description] if con.description else []
        return {
            "dataset": dataset,
            "columns": columns,
            "rows": [dict(zip(columns, row)) for row in result],
            "returned_rows": len(result),
            "truncated": truncated,
        }
    finally:
        con.close()


@mcp.resource("datalens://about")
def about() -> str:
    """Describe DataLens capabilities and configuration."""
    return (
        "DataLens MCP provides dataset discovery, schema inspection, data profiling, "
        "basic quality checks, and read-only SQL for CSV and Parquet files. "
        f"Dataset directory: {DATA_DIR}. Set DATALENS_DATA_DIR to change it."
    )


def main() -> None:
    """Run the MCP server over stdio."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    mcp.run()


if __name__ == "__main__":
    main()
