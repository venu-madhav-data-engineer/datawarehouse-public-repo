"""
CI Test Suite: Multi-Dialect SQL Validation, Q1-Q5 Completeness & Cost Guardrails
"""

from pathlib import Path
import re
import pytest
import sqlglot
from sqlglot import exp

REPO_ROOT = Path(__file__).resolve().parents[1]

SQL_SUITES = {
    "bigquery": REPO_ROOT / "benchmarks" / "bigquery" / "bigquery_setup_and_benchmarks.sql",
    "snowflake": REPO_ROOT / "benchmarks" / "snowflake" / "snowflake_setup_and_benchmarks.sql",
    "redshift": REPO_ROOT / "benchmarks" / "redshift" / "redshift_setup_and_benchmarks.sql",
    "clickhouse": REPO_ROOT / "benchmarks" / "clickhouse" / "clickhouse_setup_and_benchmarks.sql",
}


def extract_benchmark_queries(sql_text: str) -> dict[str, str]:
    """Extract Q1 through Q5 SQL statements from a benchmark SQL file."""
    pattern = re.compile(
        r"--\s*(Q[1-5]):[^\n]*\n(.*?;)",
        re.DOTALL,
    )
    return {match.group(1): match.group(2).strip() for match in pattern.finditer(sql_text)}


@pytest.mark.parametrize("engine,sql_path", SQL_SUITES.items())
def test_sql_file_exists_and_has_all_5_queries(engine: str, sql_path: Path):
    """Every warehouse SQL benchmark file must exist and define Q1 through Q5."""
    assert sql_path.is_file(), f"Missing SQL suite for {engine}: {sql_path}"
    content = sql_path.read_text(encoding="utf-8")
    queries = extract_benchmark_queries(content)
    assert set(queries.keys()) == {"Q1", "Q2", "Q3", "Q4", "Q5"}, (
        f"{engine} SQL suite is missing benchmark queries. Found: {list(queries.keys())}"
    )


@pytest.mark.parametrize("engine,sql_path", SQL_SUITES.items())
def test_sql_ast_parsing_for_q1_to_q5(engine: str, sql_path: Path):
    """Parse Q1-Q5 in each engine's native SQL dialect using sqlglot and verify AST structure."""
    content = sql_path.read_text(encoding="utf-8")
    queries = extract_benchmark_queries(content)

    for q_id, query_sql in queries.items():
        parsed = sqlglot.parse_one(query_sql, read=engine)
        assert parsed is not None, f"Failed to parse {q_id} for {engine}"
        assert isinstance(parsed, exp.Select), f"{engine} {q_id} root AST node should be SELECT"

        # Verify expected relational clauses per query archetype
        if q_id == "Q1":
            assert parsed.find(exp.Where) is not None, f"{engine} Q1 must contain a WHERE filter"
        elif q_id in ("Q2", "Q3"):
            assert parsed.find(exp.Group) is not None, f"{engine} {q_id} must contain GROUP BY"
            assert parsed.find(exp.Order) is not None, f"{engine} {q_id} must contain ORDER BY"
        elif q_id == "Q4":
            assert parsed.find(exp.Join) is not None, f"{engine} Q4 must contain a JOIN"
            assert parsed.find(exp.Limit) is not None, f"{engine} Q4 must contain LIMIT"
        elif q_id == "Q5":
            assert parsed.find(exp.With) is not None, f"{engine} Q5 must contain a CTE (WITH)"
            assert parsed.find(exp.Window) is not None, f"{engine} Q5 must contain a WINDOW function"


def test_snowflake_cost_guardrails():
    """Verify Snowflake script enforces X-SMALL warehouse, 60s auto-suspend, and cache bypass."""
    content = SQL_SUITES["snowflake"].read_text(encoding="utf-8")
    assert "WAREHOUSE_SIZE = 'X-SMALL'" in content
    assert "AUTO_SUSPEND = 60" in content
    assert "INITIALLY_SUSPENDED = TRUE" in content
    assert "USE_CACHED_RESULT = FALSE" in content


def test_redshift_distribution_and_sort_keys():
    """Verify Redshift script enforces DISTSTYLE, DISTKEY, and SORTKEY."""
    content = SQL_SUITES["redshift"].read_text(encoding="utf-8")
    assert "DISTSTYLE ALL" in content
    assert "DISTSTYLE KEY" in content
    assert "DISTKEY (PULocationID)" in content
    assert "SORTKEY (pickup_datetime)" in content


def test_clickhouse_mergetree_and_partitioning():
    """Verify ClickHouse script uses MergeTree engine with partitioning and primary key."""
    content = SQL_SUITES["clickhouse"].read_text(encoding="utf-8")
    assert "ENGINE = MergeTree()" in content
    assert "PARTITION BY toYYYYMM(pickup_datetime)" in content
    assert "PRIMARY KEY (pickup_datetime, PULocationID)" in content


def test_bigquery_public_dataset_references():
    """Verify BigQuery script references the zero-storage-cost public NYC taxi dataset."""
    content = SQL_SUITES["bigquery"].read_text(encoding="utf-8")
    assert "bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022" in content
    assert "bigquery-public-data.new_york_taxi_trips.taxi_zone_geom" in content
