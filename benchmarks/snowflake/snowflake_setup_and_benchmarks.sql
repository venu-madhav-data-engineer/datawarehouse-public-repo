-- =====================================================================
-- SNOWFLAKE BENCHMARK SETUP & TEST SUITE (FREE TIER / TRIAL OPTIMIZED)
-- =====================================================================

-- Step 1: Set Up Roles and Warehouse with strict Auto-Suspend (Cost Guard)
USE ROLE SYSADMIN;

CREATE OR REPLACE WAREHOUSE BENCHMARK_WH WITH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60          -- Suspend after 60s of inactivity to preserve free credits
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Virtual warehouse for benchmark evaluation';

USE WAREHOUSE BENCHMARK_WH;

-- Step 2: Create Benchmark Database and Schema
CREATE OR REPLACE DATABASE BENCHMARK_DB;
CREATE OR REPLACE SCHEMA BENCHMARK_DB.NYC_TAXI;
USE SCHEMA BENCHMARK_DB.NYC_TAXI;

-- Step 3: Setup External Stage (Public S3 NYC Taxi Parquet Files)
CREATE OR REPLACE STAGE nyc_taxi_s3_stage
    URL = 's3://nyc-tlc/trip data/'
    FILE_FORMAT = (TYPE = 'PARQUET');

-- Step 4: Create Tables and Load Data
-- Taxi Zones Dimension Table
CREATE OR REPLACE TABLE taxi_zones (
    LocationID INT,
    Borough VARCHAR(50),
    Zone VARCHAR(100),
    service_zone VARCHAR(50)
);

-- Load Zones from public CSV
CREATE OR REPLACE STAGE nyc_zones_s3_stage
    URL = 's3://nyc-tlc/misc/taxi _zone_lookup.csv'
    FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1);

COPY INTO taxi_zones FROM @nyc_zones_s3_stage/taxi _zone_lookup.csv
    FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1, FIELD_OPTIONALLY_ENCLOSED_BY = '"');

-- Yellow Taxi Fact Table (Sample for 2022)
CREATE OR REPLACE TABLE yellow_trips AS
SELECT 
    $1:VendorID::INT AS vendor_id,
    $1:tpep_pickup_datetime::TIMESTAMP AS pickup_datetime,
    $1:tpep_dropoff_datetime::TIMESTAMP AS dropoff_datetime,
    $1:passenger_count::INT AS passenger_count,
    $1:trip_distance::FLOAT AS trip_distance,
    $1:PULocationID::INT AS PULocationID,
    $1:DOLocationID::INT AS DOLocationID,
    $1:payment_type::INT AS payment_type,
    $1:fare_amount::FLOAT AS fare_amount,
    $1:tip_amount::FLOAT AS tip_amount,
    $1:total_amount::FLOAT AS total_amount
FROM @nyc_taxi_s3_stage/yellow_tripdata_2022-01.parquet;

-- Verify row count
SELECT COUNT(*) AS total_loaded_rows FROM yellow_trips;

-- =====================================================================
-- BENCHMARK TEST QUERIES
-- NOTE: To test cold cache, disable Snowflake result cache:
-- ALTER SESSION SET USE_CACHED_RESULT = FALSE;
-- To test warm cache, run the query again with USE_CACHED_RESULT = TRUE
-- =====================================================================

ALTER SESSION SET USE_CACHED_RESULT = FALSE;

-- Q1: Scan & Simple Filter
SELECT 
    COUNT(*) AS total_trips,
    AVG(total_amount) AS avg_total,
    MAX(trip_distance) AS max_distance
FROM yellow_trips
WHERE passenger_count > 2 
  AND trip_distance > 5.0 
  AND payment_type = 1;

-- Q2: High-Cardinality Group By Aggregation
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

-- Q3: Time-Series Aggregation & Ordering
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

-- Q4: Star Schema Multi-Table Join
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

-- Q5: Analytical Window Function (Ranking & Rolling Avg)
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
