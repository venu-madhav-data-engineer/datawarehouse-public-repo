-- =====================================================================
-- CLICKHOUSE BENCHMARK SETUP & TEST SUITE (CLOUD & OPEN-SOURCE)
-- =====================================================================
-- ClickHouse can query S3 Parquet files directly via the s3() table function.
--
-- COST GUARD REMINDER FOR CLICKHOUSE CLOUD:
-- 1. Ensure idle sleep timeout is set to 15 minutes.
-- 2. Querying S3 directly minimizes storage footprint during the trial.
-- =====================================================================

-- Step 1: Create Database
CREATE DATABASE IF NOT EXISTS benchmark_db;
USE benchmark_db;

-- Step 2: Create Ingested MergeTree Table (For Maximum SIMD Speed Comparison)
CREATE TABLE IF NOT EXISTS yellow_trips (
    vendor_id Int32,
    pickup_datetime DateTime,
    dropoff_datetime DateTime,
    passenger_count Int32,
    trip_distance Float32,
    PULocationID Int32,
    DOLocationID Int32,
    payment_type Int32,
    fare_amount Float32,
    tip_amount Float32,
    total_amount Float32
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(pickup_datetime)
PRIMARY KEY (pickup_datetime, PULocationID);

-- Insert 1 month of 2022 data directly from S3 into ClickHouse MergeTree
INSERT INTO yellow_trips
SELECT 
    VendorID AS vendor_id,
    tpep_pickup_datetime AS pickup_datetime,
    tpep_dropoff_datetime AS dropoff_datetime,
    passenger_count,
    trip_distance,
    PULocationID,
    DOLocationID,
    payment_type,
    fare_amount,
    tip_amount,
    total_amount
FROM s3('https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2022-01.parquet', 'Parquet');

-- Load Taxi Zones Dimension Table
CREATE TABLE IF NOT EXISTS taxi_zones (
    LocationID Int32,
    Borough String,
    Zone String,
    service_zone String
) ENGINE = MergeTree()
PRIMARY KEY (LocationID);

INSERT INTO taxi_zones
SELECT * FROM url('https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv', 'CSVWithNames');

-- Verify record count
SELECT count() FROM yellow_trips;

-- =====================================================================
-- BENCHMARK TEST QUERIES
-- Run with: SET max_threads = 8; (or default)
-- =====================================================================

-- Q1: Scan & Simple Filter
SELECT 
    count() AS total_trips,
    avg(total_amount) AS avg_total,
    max(trip_distance) AS max_distance
FROM yellow_trips
WHERE passenger_count > 2 
  AND trip_distance > 5.0 
  AND payment_type = 1;

-- Q2: High-Cardinality Group By Aggregation
SELECT 
    passenger_count,
    payment_type,
    count() AS trip_count,
    round(avg(fare_amount), 2) AS avg_fare,
    round(avg(tip_amount), 2) AS avg_tip,
    round(sum(total_amount), 2) AS total_revenue
FROM yellow_trips
WHERE isNotNull(passenger_count)
GROUP BY passenger_count, payment_type
ORDER BY trip_count DESC;

-- Q3: Time-Series Aggregation & Ordering
SELECT 
    toStartOfDay(pickup_datetime) AS pickup_day,
    toHour(pickup_datetime) AS pickup_hour,
    count() AS trips_per_hour,
    round(sum(total_amount), 2) AS hourly_revenue
FROM yellow_trips
WHERE pickup_datetime >= '2022-01-01' 
  AND pickup_datetime < '2022-02-01'
GROUP BY pickup_day, pickup_hour
ORDER BY pickup_day, pickup_hour;

-- Q4: Star Schema Multi-Table Join
SELECT 
    z.Borough,
    z.Zone,
    count(t.vendor_id) AS total_trips,
    round(avg(t.total_amount), 2) AS avg_trip_cost,
    round(sum(t.tip_amount), 2) AS total_tips
FROM yellow_trips t
JOIN taxi_zones z ON t.PULocationID = z.LocationID
WHERE t.trip_distance > 0
GROUP BY z.Borough, z.Zone
ORDER BY total_trips DESC
LIMIT 20;

-- Q5: Analytical Window Function (Ranking & Rolling Avg)
WITH daily_stats AS (
    SELECT 
        toStartOfDay(pickup_datetime) AS trip_date,
        PULocationID,
        count() AS daily_trips,
        sum(total_amount) AS daily_revenue
    FROM yellow_trips
    WHERE pickup_datetime >= '2022-01-01' 
      AND pickup_datetime < '2022-02-01'
    GROUP BY trip_date, PULocationID
)
SELECT 
    trip_date,
    PULocationID,
    daily_trips,
    daily_revenue,
    rank() OVER (PARTITION BY trip_date ORDER BY daily_trips DESC) AS zone_rank,
    avg(daily_revenue) OVER (
        PARTITION BY PULocationID 
        ORDER BY trip_date 
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_avg_rev
FROM daily_stats
ORDER BY trip_date, zone_rank
LIMIT 100;
