#!/usr/bin/env python3
"""
DuckDB Reference Benchmark Runner
Runs the 5 standardized benchmark queries against an analytical dataset.
Can generate synthetic NYC taxi trip data (2M+ rows in ~1 sec) or query real Parquet.
"""

from __future__ import annotations

import time
from typing import Any

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore

BENCHMARK_QUERIES = {
    "Q1: Scan & Filter": """
        SELECT 
            COUNT(*) AS total_trips,
            AVG(total_amount) AS avg_total,
            MAX(trip_distance) AS max_distance
        FROM yellow_trips
        WHERE passenger_count > 2 
          AND trip_distance > 5.0 
          AND payment_type = 1;
    """,
    "Q2: Group By Aggregation": """
        SELECT 
            passenger_count,
            payment_type,
            COUNT(*) AS trip_count,
            ROUND(AVG(fare_amount), 2) AS avg_fare,
            ROUND(AVG(tip_amount), 2) AS avg_tip,
            ROUND(SUM(total_amount), 2) AS total_revenue
        FROM yellow_trips
        WHERE passenger_count IS NOT NULL
        GROUP BY passenger_count, payment_type
        ORDER BY trip_count DESC;
    """,
    "Q3: Time-Series Aggregation": """
        SELECT 
            DATE_TRUNC('day', pickup_datetime) AS pickup_day,
            EXTRACT(hour FROM pickup_datetime) AS pickup_hour,
            COUNT(*) AS trips_per_hour,
            ROUND(SUM(total_amount), 2) AS hourly_revenue
        FROM yellow_trips
        WHERE pickup_datetime >= '2022-01-01' 
          AND pickup_datetime < '2022-02-01'
        GROUP BY 1, 2
        ORDER BY 1, 2;
    """,
    "Q4: Two-Table Star Join": """
        SELECT 
            z.Borough,
            z.Zone,
            COUNT(t.vendor_id) AS total_trips,
            ROUND(AVG(t.total_amount), 2) AS avg_trip_cost,
            ROUND(SUM(t.tip_amount), 2) AS total_tips
        FROM yellow_trips t
        JOIN taxi_zones z ON t.PULocationID = z.LocationID
        WHERE t.trip_distance > 0
        GROUP BY z.Borough, z.Zone
        ORDER BY total_trips DESC
        LIMIT 20;
    """,
    "Q5: Analytical Window Function": """
        WITH daily_stats AS (
            SELECT 
                DATE_TRUNC('day', pickup_datetime) AS trip_date,
                PULocationID,
                COUNT(*) AS daily_trips,
                SUM(total_amount) AS daily_revenue
            FROM yellow_trips
            WHERE pickup_datetime >= '2022-01-01' 
              AND pickup_datetime < '2022-02-01'
            GROUP BY 1, 2
        )
        SELECT 
            trip_date,
            PULocationID,
            daily_trips,
            daily_revenue,
            RANK() OVER (PARTITION BY trip_date ORDER BY daily_trips DESC) AS zone_rank,
            AVG(daily_revenue) OVER (
                PARTITION BY PULocationID 
                ORDER BY trip_date 
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS rolling_7d_avg_rev
        FROM daily_stats
        ORDER BY trip_date, zone_rank
        LIMIT 100;
    """,
}


def setup_synthetic_data(con: Any, num_rows: int = 2_000_000) -> tuple[int, float]:
    """Generate synthetic taxi_zones and yellow_trips tables in-memory."""
    t0 = time.time()
    con.execute("""
    CREATE OR REPLACE TABLE taxi_zones AS
    SELECT 
        range AS LocationID,
        'Borough_' || (range % 5) AS Borough,
        'Zone_' || range AS Zone,
        'ServiceZone_' || (range % 3) AS service_zone
    FROM range(1, 266);
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE yellow_trips AS
    SELECT 
        (random() * 2 + 1)::INT AS vendor_id,
        TIMESTAMP '2022-01-01' + INTERVAL (random() * 2678400) SECOND AS pickup_datetime,
        TIMESTAMP '2022-01-01' + INTERVAL (random() * 2678400 + 900) SECOND AS dropoff_datetime,
        (random() * 4 + 1)::INT AS passenger_count,
        (random() * 20 + 0.5)::FLOAT AS trip_distance,
        (random() * 264 + 1)::INT AS PULocationID,
        (random() * 264 + 1)::INT AS DOLocationID,
        (random() * 3 + 1)::INT AS payment_type,
        (random() * 60 + 5)::FLOAT AS fare_amount,
        (random() * 10)::FLOAT AS tip_amount,
        (random() * 80 + 10)::FLOAT AS total_amount
    FROM range({int(num_rows)});
    """)
    gen_time = time.time() - t0
    row_count = con.execute("SELECT count(*) FROM yellow_trips").fetchone()[0]
    return row_count, gen_time


def run_benchmarks(
    con: Any,
    queries: dict[str, str] | None = None,
    warm_runs: int = 2,
) -> list[tuple[str, float, float]]:
    """Execute cold and warm benchmark runs for all queries."""
    target_queries = queries if queries is not None else BENCHMARK_QUERIES
    results: list[tuple[str, float, float]] = []

    for name, sql in target_queries.items():
        # Cold run
        t_start = time.perf_counter()
        con.execute(sql).fetchall()
        cold_ms = (time.perf_counter() - t_start) * 1000

        # Warm runs (average of warm_runs)
        warm_times = []
        for _ in range(warm_runs):
            t_start = time.perf_counter()
            con.execute(sql).fetchall()
            warm_times.append((time.perf_counter() - t_start) * 1000)
        warm_ms = sum(warm_times) / len(warm_times)

        results.append((name, cold_ms, warm_ms))
    return results


def main():
    con = duckdb.connect(database=":memory:")
    print("=" * 70)
    print("DUCKDB LOCAL OLAP BENCHMARK RUNNER")
    print(f"DuckDB Version: {duckdb.__version__}")
    print("=" * 70)

    # Step 1: Create 2 Million Rows of Synthetic NYC Taxi Data for instant local testing
    print("\n[1/4] Generating 2,000,000 realistic taxi records in-memory...")
    row_count, gen_time = setup_synthetic_data(con, num_rows=2_000_000)
    print(f"✔ Generated {row_count:,} rows in {gen_time:.2f} seconds.")

    print("\n[2/4] Executing Benchmark Queries...")
    results = run_benchmarks(con, BENCHMARK_QUERIES, warm_runs=2)
    for name, cold_ms, warm_ms in results:
        print(f"  → {name:<32} | Cold: {cold_ms:6.1f} ms | Warm: {warm_ms:6.1f} ms")

    print("\n[3/4] Benchmark Summary Table")
    print("-" * 70)
    print(f"{'Query':<35} | {'Cold Latency':<14} | {'Warm Latency':<14} | {'Est. Cost':<10}")
    print("-" * 70)
    for name, cold_ms, warm_ms in results:
        print(f"{name:<35} | {cold_ms:8.2f} ms     | {warm_ms:8.2f} ms     | $0.00")
    print("-" * 70)
    print("✔ DuckDB benchmark complete. 100% free, zero cloud spend.")


if __name__ == "__main__":
    main()
