import csv
from pathlib import Path

import pytest

import datalens_mcp.server as server


@pytest.fixture
def sample_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    file_path = data_dir / "people.csv"
    with file_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "team", "score"])
        writer.writerow([1, "A", 10])
        writer.writerow([2, "B", 20])
        writer.writerow([3, "A", ""])
        writer.writerow([3, "A", ""])
    monkeypatch.setattr(server, "DATA_DIR", data_dir)
    return data_dir


def test_list_datasets(sample_dir):
    result = server.list_datasets()
    assert result["count"] == 1
    assert result["datasets"][0]["name"] == "people"


def test_describe_dataset(sample_dir):
    result = server.describe_dataset("people")
    assert result["row_count"] == 4
    assert {column["name"] for column in result["columns"]} == {"id", "team", "score"}


def test_quality_issues_detect_missing_and_duplicates(sample_dir):
    result = server.detect_quality_issues("people")
    issue_types = {issue["type"] for issue in result["issues"]}
    assert "missing_values" in issue_types
    assert "duplicate_rows" in issue_types


def test_run_sql(sample_dir):
    result = server.run_sql(
        "people",
        "SELECT team, COUNT(*) AS n FROM people GROUP BY team ORDER BY team",
    )
    assert result["returned_rows"] == 2


def test_run_sql_rejects_mutations(sample_dir):
    with pytest.raises(ValueError):
        server.run_sql("people", "DELETE FROM people")


def test_run_sql_rejects_multiple_statements(sample_dir):
    with pytest.raises(ValueError):
        server.run_sql("people", "SELECT * FROM people; SELECT 1")
