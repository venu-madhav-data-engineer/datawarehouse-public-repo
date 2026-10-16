#!/usr/bin/env python3
"""
Master CLI Orchestrator: Multi-Warehouse Benchmark Execution & Results Logging
Runs Q1-Q5 across DuckDB and configured cloud warehouse suites, prints comparative
latency/cost tables, and persists timestamped JSON/CSV telemetry to benchmarks/results/.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.runners.runner_base import (  # noqa: E402
    BenchmarkResultLogger,
    CloudSQLCalibratedRunner,
    DuckDBBenchmarkRunner,
    EngineBenchmarkResult,
    load_benchmark_config,
)


def create_runner(engine: str, engine_cfg: dict, dataset_rows: int):
    """Instantiate the appropriate benchmark runner for the given engine."""
    if engine == "duckdb":
        return DuckDBBenchmarkRunner(engine_cfg, dataset_rows=dataset_rows)
    return CloudSQLCalibratedRunner(engine, engine_cfg, dataset_rows=dataset_rows)


def print_comparative_report(results: list[EngineBenchmarkResult]) -> None:
    """Print detailed per-engine Q1-Q5 breakdowns and an executive cross-engine leaderboard."""
    print("\n" + "=" * 96)
    print("MULTI-WAREHOUSE OLAP BENCHMARK TELEMETRY REPORT (Q1 - Q5)")
    print("=" * 96)

    for res in results:
        print(
            f"\n▶ {res.display_name}  [mode: {res.execution_mode} | rows: {res.dataset_rows:,}]"
        )
        print("-" * 96)
        print(
            f"{'Query Archetype':<34} | {'Cold (ms)':>10} | {'Warm (ms)':>10} | "
            f"{'Speedup':>8} | {'Scanned MB':>10} | {'Cost / 1k ($)':>13}"
        )
        print("-" * 96)
        for q in res.queries:
            scanned_mb = q.bytes_scanned / (1024 * 1024)
            print(
                f"{q.query_name:<34} | {q.cold_latency_ms:10.2f} | {q.warm_mean_ms:10.2f} | "
                f"{q.speedup_ratio:7.2f}x | {scanned_mb:10.2f} | ${q.cost_per_1k_queries_usd:12.4f}"
            )
        print("-" * 96)
        print(
            f"{'TOTAL / AVERAGE':<34} | {res.total_cold_ms:10.2f} | {res.total_warm_ms:10.2f} | "
            f"{'':>8} | {'':>10} | ${res.total_estimated_cost_usd * 1000:12.4f}"
        )

    print("\n" + "=" * 96)
    print("EXECUTIVE LEADERBOARD (RANKED BY AVERAGE WARM LATENCY)")
    print("=" * 96)
    print(
        f"{'Rank':<5} | {'Engine':<12} | {'Mode':<19} | {'Avg Cold (ms)':>13} | "
        f"{'Avg Warm (ms)':>13} | {'Suite Cost / 1k Runs':>20}"
    )
    print("-" * 96)
    ranked = sorted(results, key=lambda r: r.avg_warm_ms)
    for rank, res in enumerate(ranked, start=1):
        suite_1k = res.total_estimated_cost_usd * 1000.0
        print(
            f"#{rank:<4} | {res.engine:<12} | {res.execution_mode:<19} | "
            f"{res.avg_cold_ms:13.2f} | {res.avg_warm_ms:13.2f} | ${suite_1k:19.4f}"
        )
    print("=" * 96)


def run_orchestrator(
    selected_engines: list[str] | None = None,
    dataset_rows: int | None = None,
    warm_runs: int | None = None,
    output_dir: Path | None = None,
    config_path: Path | None = None,
) -> tuple[list[EngineBenchmarkResult], Path, Path, Path]:
    """Execute benchmarks across selected engines and persist JSON/CSV results."""
    config = load_benchmark_config(config_path)
    suite_cfg = config.get("benchmark_suite", {})
    engines_cfg = config.get("engines", {})

    rows = dataset_rows if dataset_rows is not None else int(suite_cfg.get("default_rows", 2_000_000))
    w_runs = warm_runs if warm_runs is not None else int(suite_cfg.get("warm_runs", 2))
    suite_name = suite_cfg.get("name", "NYC TLC Yellow Taxi Benchmark")
    dataset_tier = suite_cfg.get("dataset_tier", "tier1_2m")

    if selected_engines:
        target_engines = [e.strip().lower() for e in selected_engines if e.strip()]
    else:
        target_engines = [
            eng for eng, cfg in engines_cfg.items() if cfg.get("enabled", True)
        ]

    results: list[EngineBenchmarkResult] = []
    for eng in target_engines:
        if eng not in engines_cfg:
            raise ValueError(
                f"Unknown engine '{eng}'. Available engines: {list(engines_cfg.keys())}"
            )
        runner = create_runner(eng, engines_cfg[eng], dataset_rows=rows)
        if isinstance(runner, CloudSQLCalibratedRunner):
            runner.setup()
            res = runner.run_suite(queries=runner.extracted_queries, warm_runs=w_runs)
        else:
            res = runner.run_suite(warm_runs=w_runs)
        results.append(res)

    results_dir = output_dir or (REPO_ROOT / suite_cfg.get("results_dir", "benchmarks/results"))
    logger = BenchmarkResultLogger(results_dir=results_dir)
    raw_json, raw_csv, summary_json = logger.save_run(
        suite_name=suite_name,
        dataset_tier=dataset_tier,
        engine_results=results,
    )
    return results, raw_json, raw_csv, summary_json


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run standardized Q1-Q5 OLAP benchmarks and log structured results."
    )
    parser.add_argument(
        "--engines",
        type=str,
        default="all",
        help="Comma-separated list of engines to run (e.g. duckdb,bigquery,snowflake) or 'all'.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=None,
        help="Number of synthetic rows for local benchmark (default from config.yaml: 2,000,000).",
    )
    parser.add_argument(
        "--warm-runs",
        type=int,
        default=None,
        help="Number of warm cache iterations per query (default from config.yaml: 2).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom output directory for JSON/CSV benchmark results.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    engines_list = (
        None
        if args.engines.strip().lower() == "all"
        else [e.strip() for e in args.engines.split(",")]
    )
    out_dir = Path(args.output_dir) if args.output_dir else None

    results, raw_json, raw_csv, summary_json = run_orchestrator(
        selected_engines=engines_list,
        dataset_rows=args.rows,
        warm_runs=args.warm_runs,
        output_dir=out_dir,
    )
    print_comparative_report(results)
    print(f"\n✔ Saved raw JSON telemetry : {raw_json.relative_to(REPO_ROOT) if raw_json.is_relative_to(REPO_ROOT) else raw_json}")
    print(f"✔ Saved raw CSV telemetry  : {raw_csv.relative_to(REPO_ROOT) if raw_csv.is_relative_to(REPO_ROOT) else raw_csv}")
    print(f"✔ Updated summary artifact : {summary_json.relative_to(REPO_ROOT) if summary_json.is_relative_to(REPO_ROOT) else summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
