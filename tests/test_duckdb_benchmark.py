"""
CI Test Suite: DuckDB Benchmark & Query Archetype Verification (Q1-Q5)
"""

from pathlib import Path
import sys
import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "duckdb"))

from run_duckdb_benchmark import (  # noqa: E402
    BENCHMARK_QUERIES,
    run_benchmarks,
    setup_synthetic_data,
)


@pytest.fixture(scope="module")
def db_con():
    """Create an in-memory DuckDB instance populated with 20,000 synthetic rows for fast CI testing."""
    con = duckdb.connect(database=":memory:")
    row_count, _ = setup_synthetic_data(con, num_rows=20_000)
    assert row_count == 20_000
    yield con
    con.close()


def test_synthetic_tables_and_bounds(db_con):
    """Verify taxi_zones and yellow_trips schemas and value bounds."""
    zones_count = db_con.execute("SELECT COUNT(*) FROM taxi_zones").fetchone()[0]
    assert zones_count == 265

    null_zones = db_con.execute(
        "SELECT COUNT(*) FROM taxi_zones WHERE LocationID IS NULL OR Borough IS NULL OR Zone IS NULL"
    ).fetchone()[0]
    assert null_zones == 0

    bounds = db_con.execute("""
        SELECT
            MIN(passenger_count), MAX(passenger_count),
            MIN(trip_distance),
            MIN(PULocationID), MAX(PULocationID),
            MIN(payment_type), MAX(payment_type),
            MIN(total_amount)
        FROM yellow_trips
    """).fetchone()

    min_pax, max_pax, min_dist, min_pu, max_pu, min_pay, max_pay, min_total = bounds
    assert 1 <= min_pax <= max_pax <= 5
    assert min_dist >= 0.5
    assert 1 <= min_pu <= max_pu <= 265
    assert 1 <= min_pay <= max_pay <= 4
    assert min_total >= 10.0


def test_q1_scan_and_filter(db_con):
    """Q1: Scan & Filter returns single summary row with valid aggregates."""
    rows = db_con.execute(BENCHMARK_QUERIES["Q1: Scan & Filter"]).fetchall()
    assert len(rows) == 1
    total_trips, avg_total, max_distance = rows[0]
    assert total_trips > 0
    assert avg_total >= 10.0
    assert max_distance > 5.0


def test_q2_group_by_aggregation(db_con):
    """Q2: Group By Aggregation returns grouped metrics ordered by trip_count DESC."""
    rows = db_con.execute(BENCHMARK_QUERIES["Q2: Group By Aggregation"]).fetchall()
    assert len(rows) > 0
    trip_counts = [r[2] for r in rows]
    assert trip_counts == sorted(trip_counts, reverse=True)
    assert sum(trip_counts) == 20_000


def test_q3_time_series_aggregation(db_con):
    """Q3: Time-Series Aggregation returns hourly buckets within January 2022."""
    rows = db_con.execute(BENCHMARK_QUERIES["Q3: Time-Series Aggregation"]).fetchall()
    assert len(rows) > 0
    for pickup_day, pickup_hour, trips_per_hour, hourly_revenue in rows:
        assert pickup_day.year == 2022 and pickup_day.month == 1
        assert 0 <= pickup_hour <= 23
        assert trips_per_hour > 0
        assert hourly_revenue > 0


def test_q4_two_table_star_join(db_con):
    """Q4: Two-Table Star Join matches taxi_zones without orphan keys and limits to 20 rows."""
    rows = db_con.execute(BENCHMARK_QUERIES["Q4: Two-Table Star Join"]).fetchall()
    assert 1 <= len(rows) <= 20
    trip_counts = [r[2] for r in rows]
    assert trip_counts == sorted(trip_counts, reverse=True)
    for borough, zone, total_trips, avg_cost, total_tips in rows:
        assert borough.startswith("Borough_")
        assert zone.startswith("Zone_")
        assert total_trips > 0
        assert avg_cost > 0
        assert total_tips >= 0


def test_q5_analytical_window_function(db_con):
    """Q5: Analytical Window Function computes RANK() and 7-day rolling average."""
    rows = db_con.execute(BENCHMARK_QUERIES["Q5: Analytical Window Function"]).fetchall()
    assert 1 <= len(rows) <= 100
    for trip_date, pu_loc, daily_trips, daily_rev, zone_rank, rolling_avg in rows:
        assert trip_date is not None
        assert 1 <= pu_loc <= 265
        assert daily_trips > 0
        assert daily_rev > 0
        assert zone_rank >= 1
        assert rolling_avg > 0


def test_benchmark_timing_harness(db_con):
    """Verify run_benchmarks executes all 5 queries and records positive cold/warm timings."""
    results = run_benchmarks(db_con, BENCHMARK_QUERIES, warm_runs=2)
    assert len(results) == 5
    for name, cold_ms, warm_ms in results:
        assert name in BENCHMARK_QUERIES
        assert cold_ms > 0.0
        assert warm_ms > 0.0
