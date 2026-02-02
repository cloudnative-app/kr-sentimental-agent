#!/usr/bin/env python3
"""
Unified pipeline runner for ABSA experiments.

Orchestrates existing scripts in sequence:
- smoke profile: run_experiments -> build_run_snapshot -> build_html_report(ops)
- paper profile: run_experiments -> build_run_snapshot -> build_paper_tables -> build_html_report(paper)

Usage:
    python scripts/run_pipeline.py --config experiments/configs/smoke_xlang.yaml --run-id my_run --mode proposed --profile smoke
    python scripts/run_pipeline.py --config experiments/configs/paper.yaml --run-id paper_run --mode proposed --profile paper
"""

import argparse
import copy
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    parser = argparse.ArgumentParser(
        description="Unified pipeline runner for ABSA experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Smoke profile (quick ops check)
  python scripts/run_pipeline.py --config experiments/configs/smoke_xlang.yaml --run-id smoke_test --mode proposed --profile smoke

  # Paper profile (full paper artifacts)
  python scripts/run_pipeline.py --config experiments/configs/paper.yaml --run-id paper_run --mode proposed --profile paper

  # With optional steps
  python scripts/run_pipeline.py --config cfg.yaml --run-id test --mode proposed --profile smoke --with_dry_run --with_filter
        """,
    )
    # Required arguments
    parser.add_argument("--config", required=True, help="Path to config YAML file")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--mode", required=True, help="Run mode (e.g., proposed, bl1, bl2, bl3)")
    parser.add_argument(
        "--profile",
        required=True,
        choices=["smoke", "paper"],
        help="Pipeline profile: smoke (ops only) or paper (full paper artifacts)",
    )

    # Optional step flags
    parser.add_argument(
        "--with_dry_run",
        action="store_true",
        help="Run provider_dry_run.py before experiments (checks API connectivity)",
    )
    parser.add_argument(
        "--with_postprocess",
        action="store_true",
        help="Run postprocess_runs.py after experiments (stability metrics, root-cause tagging)",
    )
    parser.add_argument(
        "--with_filter",
        action="store_true",
        help="Run filter_scorecards.py after experiments (creates summary in derived/)",
    )
    parser.add_argument(
        "--with_payload",
        action="store_true",
        help="Run make_pretest_payload.py after snapshot (bundle smoke+scorecards+inputs)",
    )
    parser.add_argument(
        "--force_paper_tables",
        action="store_true",
        help="Forward --force to build_paper_tables.py (allows smoke/sanity runs)",
    )
    parser.add_argument(
        "--with_metrics",
        action="store_true",
        help="Run structural_error_aggregator.py after report (structural + HF metrics to derived/metrics)",
    )
    parser.add_argument(
        "--metrics_profile",
        default="paper_main",
        choices=["smoke", "regression", "paper_main"],
        help="Profile for structural_error_aggregator (default: paper_main)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Run only this seed (for seed-repeat configs). Avoids long single run; run N times with --seed 42, --seed 123, ... instead of one 5-seed run.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Max seconds per pipeline step (default: none). Use to avoid env kill; prefer --seed for seed-repeat.",
    )
    parser.add_argument(
        "--seed_concurrency",
        type=int,
        default=None,
        metavar="N",
        help="Max concurrent seed runs when experiment.repeat.seeds has 2+ seeds (default: 1 = sequential). Overrides experiment.repeat.concurrency.",
    )
    parser.add_argument(
        "--with_integrity_check",
        action="store_true",
        help="Run check_experiment_config.py --strict before pipeline (실험 무결성·누수 검사). 무겁다면 개별 실행 권장.",
    )
    parser.add_argument(
        "--run_summary_fail_fast",
        action="store_true",
        help="After pipeline, run run_summary with --fail_fast (processing_splits, unique_uid 등 불일치 시 exit 1).",
    )
    parser.add_argument(
        "--with_aggregate",
        action="store_true",
        help="After all seeds complete, run aggregate_seed_metrics.py (머징·평균±표준편차·통합 보고서). Seed 반복 시에만 유효.",
    )

    return parser.parse_args()


def run_command(cmd: list, step_name: str, log_dir: Path, env=None, timeout_s: int | None = None) -> bool:
    """
    Run a command, log output, and return success status.

    Args:
        cmd: Command as list of strings
        step_name: Name for logging (e.g., "run_experiments")
        log_dir: Directory to write logs
        env: Optional environment variables
        timeout_s: Optional max seconds (None = no limit; use to avoid env kill on long runs)

    Returns:
        True if command succeeded, False otherwise
    """
    returncode = run_command_rc(cmd, step_name, log_dir, env=env, timeout_s=timeout_s)
    return returncode == 0


def run_command_rc(cmd: list, step_name: str, log_dir: Path, env=None, timeout_s: int | None = None) -> int:
    """
    Run a command, log output, and return the process return code.

    This is useful when the caller needs to branch on specific exit codes.
    """
    log_file = log_dir / f"{step_name}.log"
    cmd_str = " ".join(str(c) for c in cmd)

    print(f"\n{'='*60}")
    print(f"[STEP] {step_name}")
    print(f"[CMD]  {cmd_str}")
    print(f"[LOG]  {log_file}")
    print("=" * 60)

    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"# Step: {step_name}\n")
            f.write(f"# Command: {cmd_str}\n")
            f.write(f"# Started: {datetime.now().isoformat()}\n")
            f.write("-" * 60 + "\n\n")

            kwargs = dict(
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=PROJECT_ROOT,
                env=env,
                check=False,
            )
            if timeout_s is not None and timeout_s > 0:
                kwargs["timeout"] = timeout_s
            result = subprocess.run(cmd, **kwargs)

            f.write("\n" + "-" * 60 + "\n")
            f.write(f"# Finished: {datetime.now().isoformat()}\n")
            f.write(f"# Exit code: {result.returncode}\n")

        if result.returncode != 0:
            print(f"[FAIL] {step_name} exited with code {result.returncode}")
            print(f"       See log: {log_file}")
        else:
            print(f"[OK]   {step_name} completed successfully")
        return int(result.returncode)

    except Exception as e:
        print(f"[ERROR] {step_name} failed with exception: {e}")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n# Exception: {e}\n")
        return 1


def check_use_mock(config_path: Path) -> bool:
    """
    Try to detect if config uses mock provider.
    Returns True if mock, False if real, None if unknown.
    """
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        backbone = cfg.get("backbone", {})
        provider = backbone.get("provider", "").lower()

        if provider == "mock":
            return True
        elif provider in ("openai", "anthropic", "azure", "google"):
            return False

        # Check for use_mock flag
        if cfg.get("use_mock") is True:
            return True
        elif cfg.get("use_mock") is False:
            return False

    except Exception:
        pass

    return None  # Unknown


def get_sample_text_from_config(config_path: Path) -> str:
    """Extract a sample text from the dataset for dry run."""
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        data_cfg = cfg.get("data", {})
        dataset_root = data_cfg.get("dataset_root", "")
        train_file = data_cfg.get("train_file", "")

        if dataset_root and train_file:
            train_path = PROJECT_ROOT / dataset_root / train_file
            if train_path.exists():
                import csv
                with open(train_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if "text" in row and row["text"]:
                            return row["text"]
    except Exception:
        pass

    return "테스트 문장입니다."  # Default fallback


def run_single_pipeline(config_path: Path, run_id: str, mode: str, profile: str, args, timeout_s: int | None = None) -> int:
    """Run the full pipeline once (one config + one run_id). Used for single run or per-seed in seed repeat. timeout_s: optional per-step limit (None = no limit). Returns 0 on success, non-zero on failure."""
    # Standard run_dir convention (seed suffix already in run_id when seed repeat)
    run_dir = PROJECT_ROOT / "results" / f"{run_id}_{mode}"
    derived_dir = run_dir / "derived"
    reports_dir = PROJECT_ROOT / "reports" / f"{run_id}_{mode}"

    print("\n" + "=" * 60)
    print("ABSA Pipeline Runner")
    print("=" * 60)
    print(f"Config:    {config_path}")
    print(f"Run ID:    {run_id}")
    print(f"Mode:      {mode}")
    print(f"Profile:   {profile}")
    print(f"Run dir:   {run_dir}")
    print(f"Derived:   {derived_dir}")
    print(f"Reports:   {reports_dir}")
    print("=" * 60)

    # Validate config exists
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        return 1

    # Create derived directory for logs (before optional steps that write there)
    derived_dir.mkdir(parents=True, exist_ok=True)

    # Optional: integrity check before pipeline (실험 무결성·누수 검사)
    if getattr(args, "with_integrity_check", False):
        cmd_check = [
            sys.executable,
            "scripts/check_experiment_config.py",
            "--config", str(config_path),
            "--strict",
        ]
        rc_check = run_command_rc(cmd_check, "check_experiment_config", derived_dir, timeout_s=timeout_s)
        if rc_check != 0:
            print("\n[ABORT] check_experiment_config failed. Fix config or run without --with_integrity_check.")
            return 1

    # Track success/failure/policy-blocked steps (local to this run)
    steps_run = []
    steps_failed = []
    steps_blocked = []

    # =========================================================================
    # STEP 0 (optional): Provider dry run
    # =========================================================================
    if args.with_dry_run:
        use_mock = check_use_mock(config_path)

        # Run dry run if:
        # - Provider is not mock (use_mock=False)
        # - Or we can't determine (use_mock=None)
        if use_mock is not True:
            sample_text = get_sample_text_from_config(config_path)
            cmd = [
                sys.executable,
                "scripts/provider_dry_run.py",
                "--text", sample_text,
                "--mode", mode,
            ]

            if not run_command(cmd, "provider_dry_run", derived_dir, timeout_s=timeout_s):
                steps_failed.append("provider_dry_run")
                print("\n[ABORT] Provider dry run failed. Check API connectivity.")
                return 1
            steps_run.append("provider_dry_run")
        else:
            print("\n[SKIP] provider_dry_run: config uses mock provider")

    # =========================================================================
    # STEP 1: Run experiments
    # =========================================================================
    cmd = [
        sys.executable,
        "experiments/scripts/run_experiments.py",
        "--config", str(config_path),
        "--run-id", run_id,
        "--mode", mode,
    ]

    if not run_command(cmd, "run_experiments", derived_dir, timeout_s=timeout_s):
        steps_failed.append("run_experiments")
        print("\n[ABORT] run_experiments failed. Cannot continue.")
        return 1
    steps_run.append("run_experiments")

    # =========================================================================
    # STEP 2 (optional): Postprocess runs
    # =========================================================================
    if args.with_postprocess:
        scorecards_path = run_dir / "scorecards.jsonl"
        postprocess_outdir = derived_dir / "postprocess"
        postprocess_outdir.mkdir(parents=True, exist_ok=True)

        if scorecards_path.exists():
            cmd = [
                sys.executable,
                "scripts/postprocess_runs.py",
                "--merged", str(scorecards_path),
                "--outdir", str(postprocess_outdir),
            ]

            if not run_command(cmd, "postprocess_runs", derived_dir, timeout_s=timeout_s):
                steps_failed.append("postprocess_runs")
                print("[WARN] postprocess_runs failed, continuing...")
            else:
                steps_run.append("postprocess_runs")
                # List generated files
                postprocess_files = list(postprocess_outdir.glob("*"))
                if postprocess_files:
                    print(f"       Generated: {', '.join(f.name for f in postprocess_files)}")
        else:
            print(f"[SKIP] postprocess_runs: scorecards.jsonl not found at {scorecards_path}")

    # =========================================================================
    # STEP 3 (optional): Filter scorecards
    # =========================================================================
    if args.with_filter:
        scorecards_path = run_dir / "scorecards.jsonl"
        filter_outdir = derived_dir / "filtered"
        filter_outdir.mkdir(parents=True, exist_ok=True)

        if scorecards_path.exists():
            # Create summary for all splits (full summary)
            cmd = [
                sys.executable,
                "scripts/filter_scorecards.py",
                "--scorecards", str(scorecards_path),
                "--splits", "train,valid,test",
                "--runner", mode,
                "--outdir", str(filter_outdir),
            ]

            if not run_command(cmd, "filter_scorecards", derived_dir, timeout_s=timeout_s):
                steps_failed.append("filter_scorecards")
                print("[WARN] filter_scorecards failed, continuing...")
            else:
                steps_run.append("filter_scorecards")
                # List generated files
                filter_files = list(filter_outdir.glob("*"))
                if filter_files:
                    print(f"       Generated: {', '.join(f.name for f in filter_files)}")
        else:
            print(f"[SKIP] filter_scorecards: scorecards.jsonl not found at {scorecards_path}")

    # =========================================================================
    # STEP 4: Build run snapshot
    # =========================================================================
    cmd = [
        sys.executable,
        "scripts/build_run_snapshot.py",
        "--run_dir", str(run_dir),
    ]

    if not run_command(cmd, "build_run_snapshot", derived_dir, timeout_s=timeout_s):
        steps_failed.append("build_run_snapshot")
        print("[WARN] build_run_snapshot failed, continuing...")
    else:
        steps_run.append("build_run_snapshot")

    # =========================================================================
    # STEP 5 (optional): Make pretest payload
    # =========================================================================
    if args.with_payload:
        smoke_outputs = run_dir / "smoke_outputs.jsonl"
        scorecards_path = run_dir / "scorecards.jsonl"

        # Try to find input file from manifest
        input_file = None
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                # Try to get an input file path
                split_files = manifest.get("dataset", {}).get("split_files", {})
                for split_name in ["test", "valid", "train"]:
                    if split_name in split_files and split_files[split_name]:
                        input_file = split_files[split_name]
                        break
            except Exception:
                pass

        if smoke_outputs.exists() and scorecards_path.exists():
            cmd = [
                sys.executable,
                "scripts/make_pretest_payload.py",
                "--smoke", str(smoke_outputs),
                "--scorecards", str(scorecards_path),
                "--outdir", str(derived_dir / "payload"),
            ]
            if input_file:
                cmd.extend(["--input", str(input_file)])

            if not run_command(cmd, "make_pretest_payload", derived_dir, timeout_s=timeout_s):
                steps_failed.append("make_pretest_payload")
                print("[WARN] make_pretest_payload failed, continuing...")
            else:
                steps_run.append("make_pretest_payload")
        else:
            print("[SKIP] make_pretest_payload: required files not found")

    # =========================================================================
    # STEP 6 (paper profile only): Build paper tables
    # =========================================================================
    if profile == "paper":
        cmd = [
            sys.executable,
            "scripts/build_paper_tables.py",
            "--run_dir", str(run_dir),
        ]

        if args.force_paper_tables:
            cmd.append("--force")

        rc = run_command_rc(cmd, "build_paper_tables", derived_dir, timeout_s=timeout_s)
        if rc == 0:
            steps_run.append("build_paper_tables")
        elif rc == 2:
            # Intentional block (smoke/sanity policy). Continue pipeline.
            steps_blocked.append("build_paper_tables (policy: purpose=smoke/sanity)")
            print("[SKIP] build_paper_tables: blocked for smoke/sanity purpose (exit code 2)")
            print("       Use --force_paper_tables to override")
        else:
            steps_failed.append("build_paper_tables")
            print("[WARN] build_paper_tables failed (exit code != 0/2)")

    # =========================================================================
    # STEP 7: Build HTML report
    # =========================================================================
    html_profile = "paper" if profile == "paper" else "ops"

    cmd = [
        sys.executable,
        "scripts/build_html_report.py",
        "--run_dir", str(run_dir),
        "--out_dir", str(reports_dir),
        "--profile", html_profile,
    ]

    if not run_command(cmd, "build_html_report", derived_dir, timeout_s=timeout_s):
        steps_failed.append("build_html_report")
        print("[WARN] build_html_report failed")
    else:
        steps_run.append("build_html_report")

    # =========================================================================
    # STEP 8 (optional): Structural + HF metrics
    # =========================================================================
    if args.with_metrics:
        scorecards_path = run_dir / "scorecards.jsonl"
        metrics_outdir = derived_dir / "metrics"
        metrics_outdir.mkdir(parents=True, exist_ok=True)

        if scorecards_path.exists():
            cmd = [
                sys.executable,
                "scripts/structural_error_aggregator.py",
                "--input", str(scorecards_path),
                "--outdir", str(metrics_outdir),
                "--profile", args.metrics_profile,
            ]
            if not run_command(cmd, "structural_error_aggregator", derived_dir, timeout_s=timeout_s):
                steps_failed.append("structural_error_aggregator")
                print("[WARN] structural_error_aggregator failed, continuing...")
            else:
                steps_run.append("structural_error_aggregator")
                for f in ["structural_metrics.csv", "structural_metrics_table.md"]:
                    if (metrics_outdir / f).exists():
                        print(f"       Generated: derived/metrics/{f}")
        else:
            print(f"[SKIP] structural_error_aggregator: scorecards.jsonl not found at {scorecards_path}")

        # STEP 9 (with_metrics): Metric report HTML
        if run_dir.exists() and (run_dir / "scorecards.jsonl").exists():
            cmd = [
                sys.executable,
                "scripts/build_metric_report.py",
                "--run_dir", str(run_dir),
                "--out_dir", str(reports_dir),
                "--metrics_profile", args.metrics_profile,
            ]
            if not run_command(cmd, "build_metric_report", derived_dir, timeout_s=timeout_s):
                steps_failed.append("build_metric_report")
                print("[WARN] build_metric_report failed, continuing...")
            else:
                steps_run.append("build_metric_report")
                if (reports_dir / "metric_report.html").exists():
                    print("       Generated: reports/.../metric_report.html")

    # =========================================================================
    # DONE: Summary
    # =========================================================================
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Profile:        {profile}")
    print(f"Run directory:  {run_dir}")
    print(f"Reports:        {reports_dir}")
    print(f"Logs:           {derived_dir}")
    print()

    # Check key artifacts
    print("Key artifacts:")
    artifacts = [
        ("manifest.json", run_dir / "manifest.json"),
        ("traces.jsonl", run_dir / "traces.jsonl"),
        ("scorecards.jsonl", run_dir / "scorecards.jsonl"),
        ("outputs.jsonl", run_dir / "outputs.jsonl"),
        ("ops_outputs/run_snapshot.json", run_dir / "ops_outputs" / "run_snapshot.json"),
        ("ops_outputs/run_snapshot.md", run_dir / "ops_outputs" / "run_snapshot.md"),
    ]

    if profile == "paper":
        artifacts.extend([
            ("paper_outputs/paper_report.md", run_dir / "paper_outputs" / "paper_report.md"),
        ])

    artifacts.append(("reports/index.html", reports_dir / "index.html"))

    if args.with_metrics:
        artifacts.append(("derived/metrics/structural_metrics.csv", derived_dir / "metrics" / "structural_metrics.csv"))
        artifacts.append(("reports/metric_report.html", reports_dir / "metric_report.html"))

    for name, path in artifacts:
        status = "OK" if path.exists() else "MISSING"
        print(f"  [{status:7s}] {name}")

    # Show derived folder contents
    print()
    print("Derived outputs:")
    derived_subdirs = ["filtered", "postprocess", "payload", "metrics"]
    for subdir in derived_subdirs:
        subdir_path = derived_dir / subdir
        if subdir_path.exists() and subdir_path.is_dir():
            files = list(subdir_path.glob("*"))
            if files:
                print(f"  derived/{subdir}/")
                for f in files:
                    print(f"    - {f.name}")

    # Show log files
    log_files = list(derived_dir.glob("*.log"))
    if log_files:
        print(f"  derived/ logs: {', '.join(f.name for f in log_files)}")

    print()
    print(f"Steps run:    {', '.join(steps_run) if steps_run else '(none)'}")
    if steps_blocked:
        print(f"Steps blocked (policy): {', '.join(steps_blocked)}")
        print("  [POLICY BLOCK] Paper tables are disabled for smoke/sanity runs. This is expected behavior (exit code=2).")
    if steps_failed:
        print(f"Steps failed: {', '.join(steps_failed)}")

    print()
    if steps_failed:
        print("DONE (with warnings)")
    else:
        print("DONE")

    # RUN SUMMARY (런 서머리: outputs 줄 수, unique_uid, errors, processing_splits 등) — 콘솔에 출력
    cmd_summary = [sys.executable, "scripts/run_summary.py", "--run_dir", str(run_dir)]
    if getattr(args, "run_summary_fail_fast", False):
        cmd_summary.append("--fail_fast")
    print("\n[STEP] run_summary (RUN SUMMARY)")
    result_summary = subprocess.run(cmd_summary, cwd=PROJECT_ROOT, check=False)
    if result_summary.returncode != 0 and getattr(args, "run_summary_fail_fast", False):
        return 1

    return 1 if steps_failed else 0


def _run_aggregate(base_run_id: str, seeds: list, mode: str, args) -> int:
    """Run aggregate_seed_metrics.py after all seeds completed. Returns 0 on success, 1 on failure."""
    outdir = PROJECT_ROOT / "results" / f"{base_run_id}_aggregated"
    seeds_str = ",".join(str(s) for s in seeds)
    cmd = [
        sys.executable,
        "scripts/aggregate_seed_metrics.py",
        "--base_run_id", base_run_id,
        "--seeds", seeds_str,
        "--mode", mode,
        "--outdir", str(outdir),
    ]
    if getattr(args, "metrics_profile", None):
        cmd.extend(["--metrics_profile", args.metrics_profile])
    if getattr(args, "with_metrics", False):
        cmd.append("--with_metric_report")
    print("\n[STEP] aggregate_seed_metrics (머징·평균±표준편차·통합 보고서)")
    rc = run_command_rc(cmd, "aggregate_seed_metrics", PROJECT_ROOT / "results", timeout_s=getattr(args, "timeout", None))
    return 0 if rc == 0 else 1


def main():
    args = parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    timeout_s = getattr(args, "timeout", None) or None
    repeat = config.get("experiment", {}).get("repeat", {})
    seeds = repeat.get("seeds") if repeat.get("mode") == "seed" else None

    # --seed N: run only that seed (avoids long single run / runtime timeout)
    if getattr(args, "seed", None) is not None:
        seed = int(args.seed)
        base_run_id = args.run_id or config.get("run_id")
        run_id_cur = f"{base_run_id}__seed{seed}"
        cfg = copy.deepcopy(config)
        cfg.setdefault("demo", {})["seed"] = seed
        cfg["run_id"] = run_id_cur
        temp_dir = PROJECT_ROOT / "results" / ".run_pipeline_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{base_run_id}_seed{seed}.yaml"
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True)
        rc = run_single_pipeline(temp_path, run_id_cur, args.mode, args.profile, args, timeout_s=timeout_s)
        sys.exit(rc)
    if repeat.get("mode") == "seed" and seeds:
        # Seed repeat: run pipeline once per seed with run_id__seedN (outdir per seed, no overwrite)
        base_run_id = args.run_id or config.get("run_id")
        concurrency = getattr(args, "seed_concurrency", None)
        if concurrency is None:
            concurrency = repeat.get("concurrency", 1)
        concurrency = max(1, int(concurrency))

        # Fail-fast: base_run_id must not contain __seed so that run_id_cur = base_run_id__seed{N} is unambiguous and outdirs never collide
        if "__seed" in base_run_id:
            print(f"[FAIL-FAST] experiment run_id (or --run-id) must not contain '__seed'; we append __seed{{N}} per seed. Got: {base_run_id}")
            sys.exit(1)

        temp_dir = PROJECT_ROOT / "results" / ".run_pipeline_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        def _run_one(seed: int) -> tuple[int, int]:
            run_id_cur = f"{base_run_id}__seed{seed}"
            cfg = copy.deepcopy(config)
            cfg.setdefault("demo", {})["seed"] = seed
            cfg["run_id"] = run_id_cur
            temp_path = temp_dir / f"{base_run_id}_seed{seed}.yaml"
            with open(temp_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True)
            return seed, run_single_pipeline(temp_path, run_id_cur, args.mode, args.profile, args, timeout_s=timeout_s)

        if concurrency <= 1 or len(seeds) <= 1:
            # Sequential
            exit_code = 0
            for seed in seeds:
                _, rc = _run_one(seed)
                if rc != 0:
                    exit_code = rc
            print("\n[SEED REPEAT] Completed all seeds. Run IDs: " + ", ".join(f"{base_run_id}__seed{s}" for s in seeds))
            if exit_code == 0 and getattr(args, "with_aggregate", False):
                exit_code = _run_aggregate(base_run_id, seeds, args.mode, args)
            sys.exit(exit_code)
        # Parallel: cap workers by number of seeds
        max_workers = min(concurrency, len(seeds))
        print(f"\n[SEED REPEAT] Running {len(seeds)} seeds with concurrency={max_workers}. Run IDs: " + ", ".join(f"{base_run_id}__seed{s}" for s in seeds))
        exit_codes = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, seed): seed for seed in seeds}
            for fut in as_completed(futures):
                seed = futures[fut]
                try:
                    s, rc = fut.result()
                    exit_codes.append(rc)
                    status = "OK" if rc == 0 else "FAIL"
                    print(f"[SEED {s}] {status} (exit {rc})")
                except Exception as e:
                    print(f"[SEED {seed}] EXCEPTION: {e}")
                    exit_codes.append(1)
        failed = [c for c in exit_codes if c != 0]
        if failed:
            print("\n[SEED REPEAT] At least one seed failed. Exit codes: " + ", ".join(str(c) for c in exit_codes))
            sys.exit(failed[0])
        print("\n[SEED REPEAT] Completed all seeds. Run IDs: " + ", ".join(f"{base_run_id}__seed{s}" for s in seeds))
        if getattr(args, "with_aggregate", False):
            sys.exit(_run_aggregate(base_run_id, seeds, args.mode, args))
        sys.exit(0)
    else:
        rc = run_single_pipeline(config_path, args.run_id, args.mode, args.profile, args, timeout_s=timeout_s)
        sys.exit(rc)


if __name__ == "__main__":
    main()
