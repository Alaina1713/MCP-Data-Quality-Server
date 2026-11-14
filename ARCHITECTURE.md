# Architecture

```text
MCP-compatible client
        |
        | stdio / MCP
        v
  DataLens MCP server
        |
        +-- list_datasets
        +-- describe_dataset
        +-- profile_dataset
        +-- detect_quality_issues
        +-- run_sql
        |
        v
   DuckDB in-memory connection
        |
        v
 Local CSV / Parquet files
```

Each tool call creates a short-lived in-memory DuckDB connection, registers the selected
file as a temporary view, performs the requested operation, and closes the connection.
This keeps calls isolated and avoids maintaining a long-lived mutable database state.
