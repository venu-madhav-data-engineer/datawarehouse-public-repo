# Data Authenticity, Governance & Trustworthiness Comparison

In enterprise analytics, **Authenticity** encompasses five critical pillars:
1. **Transactional Authenticity (ACID Guarantees & Constraint Enforcement)**
2. **Historical Authenticity & Provenance (Time Travel, Snapshots, Lineage)**
3. **Security & Identity Authenticity (Access Control, Masking, Encryption)**
4. **Auditability & Compliance (Tamper-Proof Logs, Regulatory Certifications)**
5. **Format Authenticity & Openness (Vendor Lock-in vs. Open Table Formats)**

---

## 1. Authenticity & Governance Comparison Matrix

| Authenticity Dimension | Snowflake (Horizon) | Google BigQuery (Dataplex) | AWS Redshift Serverless | Databricks SQL (Unity Catalog) | ClickHouse (Cloud / OSS) | DuckDB (In-Process) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ACID Transaction Guarantees** | Full ACID (Multi-statement, serializable/read committed) | Full ACID (Snapshot isolation across multi-statement transactions) | Full ACID (Serializable isolation) | Full ACID (Serializable via Delta Lake multi-version concurrency control) | Eventual Consistency / Partition-level atomicity (No cross-table multi-statement ACID) | Full ACID (Single-writer, multi-reader MVCC) |
| **Unique / Primary Key Enforcement** | ⚠️ **Not Enforced** (Informational only for optimizer) | ⚠️ **Not Enforced** (Informational / Unenforced) | ⚠️ **Not Enforced** (Unless specified; can cause duplicate rows) | ⚠️ **Not Enforced** (Informational in Delta, check constraints supported) | ⚠️ **Asynchronous** (Deduplicated only during background merges or `FINAL`) | ✅ **Strictly Enforced** (Throws error on duplicate PK insert) |
| **Time Travel & Flashback** | Up to **90 Days** (`AT / BEFORE TIMESTAMP`) + 7-day Fail-safe | Up to **7 Days** (`FOR SYSTEM_TIME AS OF`) | Point-in-time restore via automated snapshots | Configurable retention via Delta Log (`VERSION AS OF`) | ❌ No native time travel (requires manual partition versions) | Query past snapshots if using Iceberg/Delta extensions |
| **Data Lineage Tracking** | Built-in Column-level Lineage via `ACCESS_HISTORY` | Built-in Lineage via Google Cloud Dataplex | External via AWS Lake Formation / CloudTrail | Automatic Column-level Lineage in Unity Catalog | Requires external tools (e.g. OpenLineage / dbt) | External only (dbt / git) |
| **Data Masking & RLS** | Native Dynamic Data Masking & Row Access Policies | Policy Tags + Dynamic Data Masking & Row-Level Security | Row-Level Security & Column Masking | Unity Catalog Dynamic Views, Masking & Row Filters | Row Policies & Column Masking via SQL | Local application logic / SQL Views |
| **Audit Trails & Tamper Resistance** | Read-only `QUERY_HISTORY` and `LOGIN_HISTORY` (1 year) | Cloud Audit Logs (tamper-evident, exportable to Cloud Storage) | AWS CloudTrail + STL/SVL system query tables | Unity Catalog Audit Logs to Cloud Storage | System tables (`system.query_log`) | Local history (not enterprise audit grade) |
| **Compliance Certifications** | SOC 1/2/3, ISO 27001, HIPAA, PCI-DSS, FedRAMP High | SOC 1/2/3, ISO 27001, HIPAA, PCI-DSS, FedRAMP High | SOC 1/2/3, ISO 27001, HIPAA, PCI-DSS, FedRAMP High | SOC 1/2/3, ISO 27001, HIPAA, PCI-DSS, FedRAMP Moderate | SOC 2 Type II, ISO 27001, HIPAA, GDPR (Cloud) | N/A (Runs locally on host hardware) |
| **Format Openness / Portability** | Proprietary micro-partitions OR Apache Iceberg (Managed/External) | Proprietary Capacitor format OR BigLake (Iceberg/Delta/Hudi) | Proprietary RMS format OR Redshift Spectrum (Parquet/Iceberg) | Native Open Delta Lake + UniForm (read as Iceberg/Hudi) | Native ClickHouse format; direct Parquet/Iceberg reader | Open Parquet, Arrow, DuckDB local, Iceberg, Delta |

---

## 2. Deep Dive: Key Authenticity Dimensions

### A. The "Constraint Illusion" in Modern Cloud Warehouses

A major trap in enterprise data authenticity is assuming that `PRIMARY KEY` or `UNIQUE` constraints guarantee duplicate-free data:

```sql
-- In Snowflake and BigQuery:
CREATE TABLE customers (
    customer_id INT PRIMARY KEY,  -- <-- THIS IS NOT ENFORCED!
    email VARCHAR(255) UNIQUE     -- <-- THIS IS NOT ENFORCED!
);

-- If an ETL pipeline inserts duplicate IDs:
INSERT INTO customers VALUES (1, 'alice@example.com'), (1, 'alice@example.com');
-- Result: Both rows ARE INSERTED without warning!
```

* **Snowflake & BigQuery**: Treat `PRIMARY KEY` and `FOREIGN KEY` declarations as **informational metadata**. They use these constraints to help the query optimizer prune joins, but they **do not validate or block duplicates** during `INSERT` or `COPY` operations for performance reasons. Authenticity must be enforced at the transformation layer (e.g., dbt `unique` test or `MERGE` statements).
* **ClickHouse**: Handles deduplication asynchronously via `ReplacingMergeTree`. Duplicates remain physically present until background compaction runs, unless queries explicitly include `SELECT ... FROM table FINAL` (which incurs a performance penalty).
* **DuckDB**: **Strictly enforces** constraints. Attempting to insert a duplicate primary key immediately aborts the transaction with `Constraint Error: Duplicate key`.

---

### B. Historical Authenticity: Time Travel & Immutability

When validating financial figures, audits, or model retraining, you must prove the state of your data at a specific microsecond in the past:

#### 1. Snowflake Time Travel & Fail-safe
* Query data as it existed up to 90 days ago:
  ```sql
  SELECT * FROM revenue_transactions 
  AT(TIMESTAMP => '2026-09-15 09:00:00'::TIMESTAMP);
  ```
* Provides **Undrop**: Accidental `DROP TABLE` can be undone instantly with `UNDROP TABLE revenue_transactions;`.
* **Fail-Safe**: If an disaster strikes beyond the 90-day time travel window, Snowflake retains a 7-day non-configurable disaster recovery snapshot accessible exclusively through Snowflake Support.

#### 2. Google BigQuery Time Travel
* Available for **7 days** backwards by default:
  ```sql
  SELECT * FROM `my_project.finance.revenue`
  FOR SYSTEM_TIME AS OF TIMESTAMP('2026-09-15 09:00:00 UTC');
  ```
* Seamlessly integrates with Snapshot Tables to freeze historical data permanently without paying double compute.

#### 3. Databricks Delta Lake Time Travel
* Powered by the immutable `_delta_log` JSON/Parquet transaction log.
* Every single write operation is an atomic, immutable version:
  ```sql
  SELECT * FROM delta_table VERSION AS OF 42;
  SELECT * FROM delta_table TIMESTAMP AS OF '2026-09-15';
  ```
* Retained as long as `VACUUM` has not purged older transaction files.

---

### C. Lineage Authenticity: "Where Did This Number Come From?"

In regulated environments (e.g., BCBS 239 in banking, FDA in pharmaceuticals), raw data authenticity is meaningless without verifiable **data provenance**.

```
Source System (Kafka / CDC) ──► Raw Staging ──► dbt Silver Layer ──► Gold Metric
     │                                                                      ▲
     └────────────── Automated Column-Level Lineage Graph ─────────────────┘
```

1. **Databricks Unity Catalog**:
   - Automatically tracks **column-level lineage** across SQL queries, Python notebooks, dbt models, and BI dashboard views.
   - If an upstream column changes formula, Unity Catalog highlights every downstream report affected.
2. **Snowflake Horizon**:
   - Exposes `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY`.
   - Records which specific columns were read (`base_objects_accessed`) and which columns were produced (`direct_objects_modified`), allowing lineage extraction without third-party instrumentation.
3. **Google Cloud Dataplex**:
   - Integrates with BigQuery to discover schemas, track data quality anomalies (e.g., null rate spikes), and construct end-to-end lineage graphs in the Google Cloud Console.

---

### D. Format Authenticity & Vendor Lock-In (The Iceberg Shift)

If a cloud vendor triples its prices or faces an extended outage, is your data truly yours?

* **Proprietary Formats (High Lock-In)**:
  * Snowflake standard micro-partitions and BigQuery Capacitor files cannot be directly read by external tools. To migrate data out, you must pay compute and egress fees to export to Parquet/CSV.
* **Open Table Formats (True Format Authenticity & Sovereign Data)**:
  * **Apache Iceberg & Delta Lake**: Data is stored as standard Parquet files on your own cloud object storage (S3/GCS/Azure).
  * **Databricks UniForm**: Writes once in Delta format and automatically generates Iceberg and Hudi metadata so Snowflake, BigQuery, and DuckDB can read the exact same physical files simultaneously without data duplication.
  * **Snowflake Managed Iceberg Tables**: Snowflake acts as an analytical query engine over an Apache Iceberg catalog, storing metadata and Parquet in your customer-owned bucket.

---

## 3. Summary: Which Warehouse Has the Strongest Authenticity?

1. **For Strict Audit Trails, Enterprise Governance & Lineage**:
   - **Snowflake Horizon** and **Databricks Unity Catalog** lead the industry in turnkey, enterprise-grade access control, dynamic masking, and column-level provenance.
2. **For Zero-Trust Cloud Compliance (HIPAA, FedRAMP, SOC2)**:
   - **BigQuery**, **Snowflake**, and **AWS Redshift** are battle-tested with FedRAMP High authorizations, customer-managed encryption keys (CMEK), and tamper-evident audit logging.
3. **For Format Sovereign Authenticity (Zero Lock-In)**:
   - **Databricks (Delta/UniForm)**, **Apache Iceberg on Snowflake/BigQuery**, or **DuckDB on local Parquet** ensure you retain 100% control over your raw data bytes.
4. **For Code-Level Determinism & Local Integrity**:
   - **DuckDB** is the only engine among these that strictly enforces Primary Key / Unique constraints out-of-the-box on write.
