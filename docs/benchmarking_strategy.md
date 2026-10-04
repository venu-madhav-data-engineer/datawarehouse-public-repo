# Standardized Data Warehouse Benchmarking Playbook

A vendor-neutral, reproducible benchmarking methodology to measure **Query Latency**, **Throughput**, **Cost Efficiency**, and **Resource Utilization** across Snowflake, BigQuery, Redshift, ClickHouse, and DuckDB.

---

## 1. Selected Benchmark Dataset: NYC TLC Yellow Taxi Trips

To ensure an apples-to-apples comparison across free tiers without paying for petabyte-scale storage, we use the standardized **NYC Yellow Taxi Trip Records**:
* **Format**: Apache Parquet (snappy/zstd compressed).
* **Scale**:
  * **Tier 1 (Quick / Free Tier Safe)**: ~10 Million rows (~1.5 GB Parquet).
  * **Tier 2 (Stress Test)**: ~100 Million rows (~15 GB Parquet).
* **Why this dataset?**:
  * Pre-loaded in BigQuery Public Datasets (`bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`).
  * Publicly hosted on AWS S3 (`s3://nyc-tlc/trip data/`) with zero egress fees within `us-east-1`.
  * Publicly queryable directly via ClickHouse `s3()` function.
  * Direct HTTP/S3 querying support in DuckDB via `httpfs`.

---

## 2. The 5 Benchmark Query Archetypes

Every analytical engine exhibits different strengths (scan speed vs. join optimization vs. window functions). The test suite comprises 5 query archetypes:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      BENCHMARK QUERY ARCHETYPES                        │
├──────┬───────────────────────┬─────────────────────────────────────────┤
│ Q1   │ Scan & Simple Filter  │ Columnar pruning & dictionary scan rate │
├──────┼───────────────────────┼─────────────────────────────────────────┤
│ Q2   │ Group By Aggregation  │ Hash aggregation & memory bandwidth     │
├──────┼───────────────────────┼─────────────────────────────────────────┤
│ Q3   │ Date Trunc & Sorting  │ Temporal transforms & sorting pipeline │
├──────┼───────────────────────┼─────────────────────────────────────────┤
│ Q4   │ Two-Table Hash Join   │ Fact-to-Dimension join & broadcast join │
├──────┼───────────────────────┼─────────────────────────────────────────┤
│ Q5   │ Analytical Window     │ Data shuffling & partition windowing    │
└──────┴───────────────────────┴─────────────────────────────────────────┘
```

### SQL Specifications

#### Q1: Raw Scan & Point Filter
*Tests metadata pruning, columnar dictionary lookup, and raw decompression speed.*
```sql
SELECT 
    COUNT(*) AS total_trips,
    AVG(total_amount) AS avg_total,
    MAX(trip_distance) AS max_distance
FROM yellow_trips
WHERE passenger_count > 2 
  AND trip_distance > 5.0 
  AND payment_type = 1;
```

#### Q2: High-Cardinality Group By Aggregation
*Tests hash table construction, group-by memory management, and aggregation efficiency.*
```sql
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
```

#### Q3: Time-Series Aggregation & Ordering
*Tests timestamp extraction, date truncation, and sorting throughput.*
```sql
SELECT 
    DATE_TRUNC('day', pickup_datetime) AS pickup_day,
    EXTRACT(hour FROM pickup_datetime) AS pickup_hour,
    COUNT(*) AS trips_per_hour,
    ROUND(SUM(total_amount), 2) AS hourly_revenue
FROM yellow_trips
WHERE pickup_datetime >= '2022-01-01' 
  AND pickup_datetime < '2022-04-01'
GROUP BY 1, 2
ORDER BY 1, 2;
```

#### Q4: Star Schema Multi-Table Join
*Tests join optimization, dimension broadcast vs hash join, and string matching.*
```sql
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
```

#### Q5: Analytical Window Function (Ranking & Rolling Sum)
*Tests partition shuffling, in-memory sorting, and analytical window calculation.*
```sql
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
```

---

## 3. Execution & Measurement Protocol

For every warehouse:
1. **Cold Run (Run 1)**:
   * Execute query after stopping/suspending the warehouse or clearing query cache.
   * Measures cold disk read, metadata retrieval, and compilation.
2. **Warm Run (Run 2 & Run 3)**:
   * Execute the exact query 2 more times immediately.
   * Average the latency of Run 2 and Run 3.
   * Measures memory caching, SSD caching, and vectorized execution speed.
3. **Record Key Metrics**:
   * **Elapsed Wall-Clock Time (ms)**.
   * **Bytes Scanned / Processed (MB/GB)**.
   * **Effective Cost**:
     * BigQuery: `(Bytes Scanned / 1 TB) * $6.25`.
     * Snowflake: `(Execution Seconds / 3600) * (Warehouse Credits/hr) * ($3.00/credit)`.
     * DuckDB: `$0.00`.

---

## 4. Benchmark Scorecard Template

| Query | Metric | DuckDB (Local) | Snowflake (X-Small) | BigQuery (On-Demand) | Redshift Serverless (8 RPU) | ClickHouse Cloud |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Q1 (Scan & Filter)** | Cold Latency (s)<br>Warm Latency (s)<br>Estimated Cost ($) | | | | | |
| **Q2 (Group By Agg)** | Cold Latency (s)<br>Warm Latency (s)<br>Estimated Cost ($) | | | | | |
| **Q3 (Time-Series)** | Cold Latency (s)<br>Warm Latency (s)<br>Estimated Cost ($) | | | | | |
| **Q4 (Hash Join)** | Cold Latency (s)<br>Warm Latency (s)<br>Estimated Cost ($) | | | | | |
| **Q5 (Window Func)** | Cold Latency (s)<br>Warm Latency (s)<br>Estimated Cost ($) | | | | | |
