# DataLens MCP

**A lightweight Model Context Protocol (MCP) server for data exploration and quality checks.**

DataLens gives AI assistants a practical way to inspect local datasets, understand their structure, identify common data-quality issues, and run read-only analytical SQL — without manually opening a notebook.

## Why this project?

Data work often starts with repetitive questions:

- What datasets are available?
- How many rows and columns does this file contain?
- Which columns have missing values?
- Are there duplicate records?
- Can I quickly aggregate or filter the data?

DataLens exposes these workflows as MCP tools so an MCP-compatible client can call them directly.

## Features

| MCP tool | What it does |
|---|---|
| `list_datasets` | Finds supported files and reports their format and size |
| `describe_dataset` | Returns row count, column names, and inferred types |
| `profile_dataset` | Reports null percentages, distinct counts, and sample values |
| `detect_quality_issues` | Flags missing values and duplicate-row groups |
| `run_sql` | Executes capped, read-only SQL against a selected dataset |

Also includes a small `datalens://about` resource.

**Supported inputs:** CSV and Parquet for querying. SQLite files are listed for discovery but are not yet queryable through the current flat-dataset tools.

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/datalens-mcp.git
cd datalens-mcp

python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

### 2. Add a dataset

Create a `data/` directory and copy a CSV or Parquet file into it:

```bash
mkdir data
cp examples/employees.csv data/employees.csv
```

Or point DataLens to another folder:

```bash
# macOS/Linux
export DATALENS_DATA_DIR="/absolute/path/to/your/data"

# Windows PowerShell
$env:DATALENS_DATA_DIR = "C:\path\to\your\data"
```

### 3. Run the MCP server

```bash
datalens-mcp
```

The server uses **stdio transport**, which is the standard local MCP setup for desktop clients.

## Example MCP client configuration

For an MCP client that supports local stdio servers, use a configuration similar to:

```json
{
  "mcpServers": {
    "datalens": {
      "command": "python",
      "args": ["-m", "datalens_mcp.server"],
      "env": {
        "DATALENS_DATA_DIR": "/absolute/path/to/datalens-mcp/data"
      }
    }
  }
}
```

If your client launches the installed console script instead, use `datalens-mcp` as the command.

## Example prompts

Once connected, try asking your assistant:

- "What datasets can you access?"
- "Profile the employees dataset and explain the columns."
- "Find missing values and duplicate records in employees."
- "Show average salary by department."
- "Which department has the highest average salary?"

Example SQL for `run_sql`:

```sql
SELECT department, ROUND(AVG(salary), 2) AS average_salary
FROM employees
GROUP BY department
ORDER BY average_salary DESC
```

## Design and safety notes

- SQL is restricted to a single `SELECT` or `WITH` statement.
- Mutating and administrative SQL keywords are rejected.
- Query results are capped (maximum 500 rows).
- Dataset names and column identifiers are validated before being interpolated into SQL.
- Only files directly inside the configured data directory are discovered.
- Treat datasets as trusted local inputs. This is a developer utility, not a hardened multi-tenant data service.

The SQL guard is a useful safety layer, not a substitute for operating-system sandboxing. Do not expose this local server to untrusted users or place sensitive files in its data directory.

## Run tests

```bash
pytest
```

## Roadmap

- [ ] SQLite table discovery and querying
- [ ] Parquet partition and large-file profiling optimizations
- [ ] Configurable quality rules (uniqueness, ranges, regex, freshness)
- [ ] Exportable Markdown/JSON profiling reports
- [ ] Optional semantic descriptions for columns
- [ ] More granular per-dataset access controls

## Tech stack

- Python
- Model Context Protocol (MCP) Python SDK
- DuckDB

## Author

**Alaina Rahim**  
MSc Advanced Computer Science (Artificial Intelligence), University of Leeds

---

If you build on DataLens, feel free to open an issue or submit a pull request.
