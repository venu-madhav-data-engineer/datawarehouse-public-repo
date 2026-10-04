# Free Tier Guide: Setup, Quotas & Zero-Bill Guardrails

This guide provides practical instructions to activate, utilize, and protect yourself against unexpected charges across all major data warehouse free tiers and free trials.

---

## 1. Quick Free Tier Summary

| Data Warehouse | Free Tier Offer | Expiration | Credit Card Needed? | Danger Level (Risk of Runaway Cost) |
| :--- | :--- | :--- | :--- | :--- |
| **DuckDB** | 100% Free & Open Source | Never | **No** | 🟢 **Zero Risk** ($0 forever) |
| **BigQuery Sandbox** | 10 GB Storage, 1 TB queries/month | Never | **No** | 🟢 **Zero Risk** (Credit card not attached) |
| **BigQuery (GCP Full)** | 10 GB Storage, 1 TB queries/mo + $300 credit | 90 days for credits; 1 TB/mo is permanent | Yes | 🟡 **Low-Medium** (If query bytes limit not set) |
| **Snowflake** | $400 credits | 30 days | Yes (in most regions) | 🟡 **Low-Medium** (If auto-suspend is omitted) |
| **AWS Redshift Serverless** | $300 trial credits | 90 days | Yes | 🟠 **Medium** (If high RPU limit is configured) |
| **ClickHouse Cloud** | $300 trial credits | 30 days | Yes | 🟡 **Low** (Auto-idles by default) |
| **Databricks Trial** | 14-day software trial | 14 days | Yes (AWS/GCP/Azure) | 🔴 **High Risk** (Databricks trial does NOT cover cloud VM costs!) |

---

## 2. Platform-Specific Setup & Guardrails

### A. DuckDB (The 100% Free Baseline)
* **What you get**: Unlimited queries, local storage, multi-threaded columnar execution.
* **How to run**:
  ```bash
  # Python
  pip install duckdb
  # Or binary
  curl -L https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip -o duckdb.zip
  unzip duckdb.zip && ./duckdb
  ```
* **Guardrail**: No guardrails needed. You can analyze 100GB of Parquet files directly from local disk or public S3 URLs without paying a cent.

---

### B. Google BigQuery: Sandbox vs. Always Free Tier

Google BigQuery offers two modes:
1. **BigQuery Sandbox** (Recommended for zero-risk learning):
   - **No credit card required**.
   - 10 GB active storage, 1 TB query data processed per month.
   - Tables expire automatically after 60 days.
   - DML (Data Manipulation Language) statements and streaming inserts are limited.
2. **Standard GCP Account with BigQuery Free Tier**:
   - Requires credit card; grants $300 GCP credit for 90 days.
   - **Permanent free allowance**: 10 GB active storage + 1 TB analytical queries processed every month.

#### 🛡️ Critical BigQuery Guardrails:
1. **Set `maximum_bytes_billed` in query options**:
   Never execute queries via script or SDK without setting a byte cap. Example in Python:
   ```python
   from google.cloud import bigquery
   client = bigquery.Client()
   job_config = bigquery.QueryJobConfig(
       maximum_bytes_billed=10 * 1024 * 1024 * 1024  # Fail if query reads > 10 GB (~$0.06)
   )
   query_job = client.query("SELECT ...", job_config=job_config)
   ```
2. **Enable Custom Cost Controls in GCP Console**:
   * Navigate to: **BigQuery** > **Settings** > **Query management**.
   * Set a daily project-level query limit (e.g., 500 GB / day).
3. **Partition & Cluster your Tables**:
   * Always partition by timestamp/date and enforce partition filtering:
   ```sql
   CREATE TABLE my_dataset.trips
   PARTITION BY DATE(pickup_datetime)
   OPTIONS (require_partition_filter = true) AS ...
   ```

---

### C. Snowflake: 30-Day $400 Trial

* **Sign up**: [signup.snowflake.com](https://signup.snowflake.com/)
* **What you get**: $400 in Snowflake credits across 30 days.
* **Edition to choose**: Select **Enterprise Edition** (to test features like Multi-Cluster Warehouses, Masking, and Time Travel up to 90 days).
* **Cloud Provider**: AWS or GCP (choose the region closest to you or closest to your public test datasets).

#### 🛡️ Critical Snowflake Guardrails (Run these SQL commands immediately upon sign-in):

1. **Configure Aggressive Auto-Suspend on your Virtual Warehouse**:
   ```sql
   -- Alter the default warehouse to suspend after 60 seconds of inactivity
   ALTER WAREHOUSE COMPUTE_WH SET 
       WAREHOUSE_SIZE = 'X-SMALL'
       AUTO_SUSPEND = 60
       AUTO_RESUME = TRUE;
   ```
   * *Why?* An `X-SMALL` warehouse consumes 1 credit per hour (~$2.00–$3.00). If suspended after 60s of inactivity, a 5-second test query costs fractions of a cent.

2. **Create an Account-Level Resource Monitor**:
   ```sql
   USE ROLE ACCOUNTADMIN;

   CREATE OR REPLACE RESOURCE MONITOR trial_budget_guard
   WITH 
       CREDIT_QUOTA = 100 -- Set limit to 100 credits (out of your 400 credit trial)
       FREQUENCY = MONTHLY
       START_TIMESTAMP = IMMEDIATELY
   TRIGGERS
       ON 75 PERCENT DO NOTIFY
       ON 90 PERCENT DO NOTIFY
       ON 100 PERCENT DO SUSPEND_IMMEDIATELY;

   -- Assign to your warehouse:
   ALTER WAREHOUSE COMPUTE_WH SET RESOURCE_MONITOR = trial_budget_guard;
   ```

3. **Check Credit Consumption Daily**:
   ```sql
   SELECT 
       START_TIME::DATE AS usage_date,
       WAREHOUSE_NAME,
       SUM(CREDITS_USED) AS total_credits
   FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
   WHERE START_TIME >= DATEADD(day, -7, CURRENT_TIMESTAMP())
   GROUP BY 1, 2
   ORDER BY 1 DESC;
   ```

---

### D. AWS Redshift Serverless: $300 / 90-Day Credit

* **What you get**: AWS offers $300 in credits specifically for testing Redshift Serverless for first-time users.
* **Architecture**: Redshift Serverless charges based on Redshift Processing Unit (RPU) hours ($0.375 per RPU-hour in us-east-1).

#### 🛡️ Critical Redshift Serverless Guardrails:
1. **Set Base RPU Capacity to the Minimum**:
   * By default, Redshift Serverless may assign 128 RPUs (which costs ~$48/hour).
   * **Change Base Capacity to 8 RPUs** (the minimum allowed, which costs only $3.00/hour while actively running queries).
2. **Set Spend and Usage Limits**:
   * Navigate to **Amazon Redshift** > **Serverless dashboard** > **Workgroup settings** > **Limits**.
   * Set **RPU-hours limit**: e.g., 5 RPU-hours per day or 20 RPU-hours per month.
   * Action when limit is reached: Choose **Turn off user queries** or **Log to system table & send SNS alert**.
3. **Set an AWS Budget Alert**:
   * Open the **AWS Budgets** console.
   * Create a cost budget for Redshift with a threshold of **$10.00**.
   * Configure notifications to your email.

---

### E. ClickHouse Cloud: 30-Day $300 Trial

* **Sign up**: [clickhouse.cloud](https://clickhouse.cloud/)
* **What you get**: $300 in credits across 30 days.
* **Architecture**: Fully managed ClickHouse instances that automatically scale compute and storage.

#### 🛡️ Critical ClickHouse Cloud Guardrails:
1. **Enable Auto-Idle / Sleep Mode**:
   * In the ClickHouse Cloud console, ensure your service is configured with **Idle Timeout = 15 minutes**.
   * When no queries are received for 15 minutes, compute scales down to zero, stopping compute credit consumption.
2. **Avoid Massive Uncompressed CSV Ingestion**:
   * Always ingest from compressed Parquet or use native `s3()` table functions to avoid excessive temporary storage consumption.
3. **Delete Service Before Day 30**:
   * If you don't intend to convert to a paid subscription, delete the trial service 2 days before the 30-day window expires.

---

### F. Databricks Free Trial (⚠️ Read Carefully)

* **The Trap**: Databricks offers a 14-day free trial of the **Databricks software layer (DBUs)**.
* **The Reality**: Databricks does **NOT** provide free cloud infrastructure. When Databricks spins up a SQL Warehouse or cluster, it launches virtual machines (e.g., AWS EC2 `m5d.2xlarge` or Azure VMs) inside **your** cloud account.
* **Your cloud provider will bill you for EC2, EBS, and NAT Gateways**, even though Databricks DBUs are free during the trial!

#### 🛡️ Safe Testing Plan for Databricks:
1. If testing on AWS, set up an AWS Budget for $20.00.
2. Use **Serverless SQL Warehouses** with **Auto-Stop set to 10 minutes**.
3. When finished benchmarking, terminate the SQL Warehouse immediately. Do not leave running overnight.
4. If you only want to test Spark or Delta Lake without cloud bills, use **DuckDB with Delta extension** or **Databricks Community Edition** (limited single-node micro-cluster with no SQL Warehouse).

---

## 3. Pre-Flight Safety Checklist Before Running Any Benchmark

- [ ] **Billing Alert Activated**: A budget alert for $1.00 / $5.00 is configured in the cloud account.
- [ ] **Auto-Suspend Verified**: Snowflake warehouse is set to `AUTO_SUSPEND = 60`; Redshift Serverless Base RPU is set to `8`.
- [ ] **Byte-Scan Guard Enabled**: BigQuery queries include `maximum_bytes_billed`.
- [ ] **Zero-Cost Dry Run**: The query has been tested and validated locally in DuckDB first.
- [ ] **Calendar Reminder Set**: An alert is scheduled 5 days before any 30-day trial expires to review usage or delete test clusters.
