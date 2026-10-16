"""
CI Test Suite: Benchmark Execution Harness & Telemetry Results Logging (Phase 1)
Validates runner_base.py, run_all_benchmarks.py, pricing models, cost circuit breakers,
and JSON/CSV output schemas.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.runners.run_all_benchmarks import run_orchestrator
from benchmarks.runners.runner_base import (
    CloudSQLCalibratedRunner,
    DuckDBBenchmarkRunner,
    load_benchmark_config,
)


class TestBenchmarkRunnersAndLogging(unittest.TestCase):
    """Unit and integration tests for multi-warehouse benchmark execution and logging."""

    def setUp(self) -> None:
        self.config = load_benchmark_config()

    def test_config_structure_and_engines(self) -> None:
        """Verify config.yaml defines benchmark_suite and all 5 engines."""
        self.assertIn("benchmark_suite", self.config)
        self.assertIn("engines", self.config)
        engines = self.config["engines"]
        expected = {"duckdb", "bigquery", "snowflake", "redshift", "clickhouse"}
        self.assertEqual(set(engines.keys()), expected)

    def test_pricing_model_calculations(self) -> None:
        """Verify cost-per-query formulas across all pricing models."""
        engines = self.config["engines"]

        # 1. DuckDB: $0.00
        duck_runner = DuckDBBenchmarkRunner(engines["duckdb"], dataset_rows=10_000)
        self.assertEqual(duck_runner.estimate_cost_usd(500.0, 100_000_000), 0.0)

        # 2. BigQuery: $6.25 per TB scanned -> 1 TB = $6.25
        bq_runner = CloudSQLCalibratedRunner("bigquery", engines["bigquery"])
        one_tb = 1024**4
        self.assertAlmostEqual(bq_runner.estimate_cost_usd(1500.0, one_tb), 6.25, places=4)

        # 3. Snowflake: 1 credit/hr * $2/credit = $2.00/hr -> 3600s = $2.00
        sf_runner = CloudSQLCalibratedRunner("snowflake", engines["snowflake"])
        self.assertAlmostEqual(
            sf_runner.estimate_cost_usd(3_600_000.0, 50_000_000), 2.0, places=4
        )

        # 4. Redshift Serverless: 8 RPU * $0.375/RPU-hr = $3.00/hr -> 3600s = $3.00
        rs_runner = CloudSQLCalibratedRunner("redshift", engines["redshift"])
        self.assertAlmostEqual(
            rs_runner.estimate_cost_usd(3_600_000.0, 50_000_000), 3.0, places=4
        )

    def test_bigquery_maximum_bytes_billed_circuit_breaker(self) -> None:
        """Verify BigQuery runner aborts when estimated scanned bytes exceed maximum_bytes_billed."""
        strict_cfg = dict(self.config["engines"]["bigquery"])
        strict_cfg["cost_guardrails"] = {"maximum_bytes_billed": 1024}  # 1 KB cap
        runner = CloudSQLCalibratedRunner("bigquery", strict_cfg, dataset_rows=2_000_000)
        runner.setup()
        with self.assertRaises(RuntimeError):
            runner.run_suite(queries=runner.extracted_queries, warm_runs=1)

    def test_orchestrator_end_to_end_and_result_artifacts(self) -> None:
        """Verify run_orchestrator executes all engines and produces valid JSON and CSV logs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            results, raw_json, raw_csv, summary_json = run_orchestrator(
                selected_engines=["duckdb", "bigquery", "snowflake", "redshift", "clickhouse"],
                dataset_rows=20_000,
                warm_runs=2,
                output_dir=out_path,
            )

            self.assertEqual(len(results), 5)
            self.assertTrue(raw_json.is_file())
            self.assertTrue(raw_csv.is_file())
            self.assertTrue(summary_json.is_file())

            # Validate summary JSON schema
            summary_data = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary_data["engine_count"], 5)
            self.assertIn("engines", summary_data)
            self.assertIn("ranking_by_warm_latency", summary_data)

            ranking = summary_data["ranking_by_warm_latency"]
            self.assertEqual(len(ranking), 5)
            warm_latencies = [item["avg_warm_ms"] for item in ranking]
            self.assertEqual(warm_latencies, sorted(warm_latencies))

            # Validate CSV row count (5 engines * 5 queries = 25 rows)
            with raw_csv.open("r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 25)
            for row in rows:
                self.assertIn(row["query_id"], {"Q1", "Q2", "Q3", "Q4", "Q5"})
                self.assertGreater(float(row["cold_latency_ms"]), 0.0)
                self.assertGreater(float(row["warm_mean_ms"]), 0.0)


if __name__ == "__main__":
    unittest.main()
