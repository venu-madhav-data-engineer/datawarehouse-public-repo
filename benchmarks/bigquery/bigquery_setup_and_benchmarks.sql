-- =====================================================================
-- GOOGLE BIGQUERY BENCHMARK SETUP & TEST SUITE (FREE TIER OPTIMIZED)
-- =====================================================================
-- Note: BigQuery already hosts the official NYC Taxi dataset in public data.
-- You DO NOT need to pay to load or store this data!
-- Source dataset: `bigquery-public-data.new_york_taxi_trips`
--
-- COST GUARD REMINDER:
-- In the BigQuery Console:
-- 1. Click "More" -> "Query settings".
-- 2. Check the "Bytes billed" validator at the top right before clicking Run!
-- =====================================================================

-- Verify table schema and preview records (Free, cached metadata)
SELECT 
    table_name,
    row_count,
    size_bytes / (1024*1024*1024) AS size_gb
FROM `bigquery-public-data.new_york_taxi_trips.__TABLES__`
WHERE table_id = 'tlc_yellow_trips_2022';

-- =====================================================================
-- BENCHMARK TEST QUERIES
-- Run each query 3 times:
-- Run 1: Check "Execution details" -> Slot ms, Elapsed time (Cold/Uncached)
-- Run 2 & 3: Disable "Use cached results" in Query Settings if testing engine,
--            or keep enabled to test BigQuery Result Cache.
-- =====================================================================

-- Q1: Scan & Simple Filter
SELECT 
    COUNT(*) AS total_trips,
    AVG(total_amount) AS avg_total,
    MAX(trip_distance) AS max_distance
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
WHERE passenger_count > 2 
  AND trip_distance > 5.0 
  AND payment_type = '1';

-- Q2: High-Cardinality Group By Aggregation
SELECT 
    passenger_count,
    payment_type,
    COUNT(*) AS trip_count,
    ROUND(AVG(fare_amount), 2) AS avg_fare,
    ROUND(AVG(tip_amount), 2) AS avg_tip,
    ROUND(SUM(total_amount), 2) AS total_revenue
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
WHERE passenger_count IS NOT NULL
GROUP BY passenger_count, payment_type
ORDER BY trip_count DESC;

-- Q3: Time-Series Aggregation & Ordering
SELECT 
    TIMESTAMP_TRUNC(pickup_datetime, DAY) AS pickup_day,
    EXTRACT(HOUR FROM pickup_datetime) AS pickup_hour,
    COUNT(*) AS trips_per_hour,
    ROUND(SUM(total_amount), 2) AS hourly_revenue
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
WHERE pickup_datetime >= '2022-01-01' 
  AND pickup_datetime < '2022-02-01'
GROUP BY 1, 2
ORDER BY 1, 2;

-- Q4: Star Schema Multi-Table Join
SELECT 
    z.zone_name,
    z.borough,
    COUNT(t.vendor_id) AS total_trips,
    ROUND(AVG(t.total_amount), 2) AS avg_trip_cost,
    ROUND(SUM(t.tip_amount), 2) AS total_tips
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022` t
JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` z 
  ON CAST(t.pickup_location_id AS STRING) = z.zone_id
WHERE t.trip_distance > 0
GROUP BY z.zone_name, z.borough
ORDER BY total_trips DESC
LIMIT 20;

-- Q5: Analytical Window Function (Ranking & Rolling Avg)
WITH daily_stats AS (
    SELECT 
        DATE(pickup_datetime) AS trip_date,
        pickup_location_id,
        COUNT(*) AS daily_trips,
        SUM(total_amount) AS daily_revenue
    FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
    WHERE pickup_datetime >= '2022-01-01' 
      AND pickup_datetime < '2022-02-01'
    GROUP BY 1, 2
)
SELECT 
    trip_date,
    pickup_location_id,
    daily_trips,
    daily_revenue,
    RANK() OVER (PARTITION BY trip_date ORDER BY daily_trips DESC) AS zone_rank,
    AVG(daily_revenue) OVER (
        PARTITION BY pickup_location_id 
        ORDER BY trip_date 
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_avg_rev
FROM daily_stats
ORDER BY trip_date, zone_rank
LIMIT 100;
