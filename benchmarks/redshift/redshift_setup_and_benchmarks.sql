-- =====================================================================
-- AWS REDSHIFT SERVERLESS BENCHMARK SETUP & TEST SUITE
-- =====================================================================
-- IMPORTANT COST GUARDS IN AWS CONSOLE:
-- 1. Ensure Workgroup Base RPU is set to 8 (minimum).
-- 2. Under Limits, set daily cap to 5 RPU-hours.
-- =====================================================================

-- Step 1: Create Dimension and Fact Tables with optimal distribution and sort keys
CREATE TABLE IF NOT EXISTS taxi_zones (
    LocationID INT NOT NULL,
    Borough VARCHAR(50),
    Zone VARCHAR(100),
    service_zone VARCHAR(50)
)
DISTSTYLE ALL -- Small dimension table: replicate to all nodes for fastest joins
SORTKEY (LocationID);

CREATE TABLE IF NOT EXISTS yellow_trips (
    vendor_id INT,
    pickup_datetime TIMESTAMP,
    dropoff_datetime TIMESTAMP,
    passenger_count INT,
    trip_distance FLOAT,
    PULocationID INT,
    DOLocationID INT,
    payment_type INT,
    fare_amount FLOAT,
    tip_amount FLOAT,
    total_amount FLOAT
)
DISTSTYLE KEY
DISTKEY (PULocationID) -- Align distribution with taxi_zones join
SORTKEY (pickup_datetime);

-- Step 2: Load Data using COPY (Replace <YOUR-IAM-ROLE-ARN> with your Redshift IAM Role)
-- COPY taxi_zones FROM 's3://nyc-tlc/misc/taxi _zone_lookup.csv'
-- IAM_ROLE '<YOUR-IAM-ROLE-ARN>'
-- CSV IGNOREHEADER 1;

-- COPY yellow_trips FROM 's3://nyc-tlc/trip data/yellow_tripdata_2022-01.parquet'
-- IAM_ROLE '<YOUR-IAM-ROLE-ARN>'
-- FORMAT AS PARQUET;

-- =====================================================================
-- BENCHMARK TEST QUERIES
-- =====================================================================

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
    DATE_PART(hour, pickup_datetime) AS pickup_hour,
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
