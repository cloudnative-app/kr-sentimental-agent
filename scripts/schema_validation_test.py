import sys
print("PYTHON EXECUTABLE:", sys.executable)

import argparse
import json
import os
import random
import string
import sys
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from agents import SupervisorAgent, BaselineRunner
from data.datasets.loader import load_datasets, resolve_dataset_paths, BlockedDatasetPathError
from tools.backbone_client import BackboneClient
from tools.data_tools import InternalExample
from tools.llm_runner import default_errors_path
from schemas import FinalOutputSchema


def _has_non_empty_aspects(payload: dict, mode: str) -> bool:
    """
    Check if payload has non-empty aspects for modes that should extract aspects.
    - For proposed/bl3: check process_trace for ATE agent with aspects or ATSA agent with aspect_sentiments
    - For bl2: check process_trace for BL2 agent with aspects
    """
    process_trace = payload.get("process_trace", [])
    for trace in process_trace:
        output = trace.get("output", {})
        # Check for ATE aspects
        aspects = output.get("aspects", [])
        if aspects and len(aspects) > 0:
            return True
        # Check for ATSA aspect_sentiments
        aspect_sentiments = output.get("aspect_sentiments", [])
        if aspect_sentiments and len(aspect_sentiments) > 0:
            return True
    return False


def _generate_run_id(prefix: str | None = None) -> str:
    """
    Build a per-run unique ID using timestamp + random suffix.
    If prefix is provided (e.g., from config), prepend it for continuity.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    base = f"{ts}_{suffix}"
    return f"{prefix}_{base}" if prefix else base


def _run_mode(mode: str, base_run_id: str, cfg: dict, examples: List[InternalExample], max_samples: int, require_non_empty_aspects: bool = False) -> dict:
    backbone_cfg = cfg.get("backbone", {})
    backbone = BackboneClient(provider=backbone_cfg.get("provider"), model=backbone_cfg.get("model"))

    run_id = f"{base_run_id}_{mode}"
    if mode in {"proposed", "abl_no_stage2", "abl_no_moderator", "abl_no_validator"}:
        runner = SupervisorAgent(backbone=backbone, config=cfg.get("pipeline", {}), run_id=run_id)
    else:
        runner = BaselineRunner(mode=mode, backbone=backbone, config=cfg.get("pipeline", {}), run_id=run_id)

    outdir = Path("experiments/results") / mode / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    output_path = outdir / "smoke_outputs.jsonl"

    passed = 0
    total = 0
    parse_failures = 0
    empty_aspects_failures = 0
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        for ex in examples[:max_samples]:
            result = runner.run(ex)
            payload = result.model_dump()
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            total += 1
            try:
                FinalOutputSchema.model_validate(payload)
                # Additional check for non-empty aspects if required
                if require_non_empty_aspects and mode in ("proposed", "bl2", "bl3"):
                    if not _has_non_empty_aspects(payload, mode):
                        empty_aspects_failures += 1
                        continue
                passed += 1
            except Exception:
                parse_failures += 1

    pipeline_errors = cfg.get("pipeline", {}).get("errors_path")
    errors_path = Path(pipeline_errors or default_errors_path(run_id, mode))
    errors_count = 0
    if errors_path.exists():
        errors_count = len([line for line in errors_path.read_text(encoding="utf-8").splitlines() if line.strip()])

    rate = passed / total if total else 0.0
    print(
        f"[{mode}] Validated {passed}/{total} (rate={rate:.2f}), parse_failures={parse_failures}, empty_aspects={empty_aspects_failures}, errors logged={errors_count}, outputs={output_path}"
    )
    return {
        "mode": mode,
        "passed": passed,
        "total": total,
        "rate": rate,
        "parse_failures": parse_failures,
        "empty_aspects_failures": empty_aspects_failures,
        "errors": errors_count,
        "output_path": str(output_path),
    }


def main():
    # Ensure UTF-8 console output on Windows to avoid garbled Korean logs
    os.environ.setdefault("PYTHONUTF8", "1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/proposed.yaml")
    parser.add_argument("--run-id", "--run_id", type=str, default=None, help="Optional run identifier. Defaults to a unique timestamp-based ID.")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["proposed", "abl_no_stage2", "abl_no_moderator", "abl_no_validator", "all"],
        default="all",
    )
    parser.add_argument("--max-samples", "--n", type=int, default=20)
    parser.add_argument(
        "--use_mock",
        type=int,
        default=1,
        help="Set to 1 to force mock backbone (default). When 0, BACKBONE_PROVIDER (env or config.backbone.provider) must be set.",
    )
    parser.add_argument("--require_non_empty_aspects", type=int, default=0, help="If 1, require len(aspects)>0 for proposed/bl2/bl3 to count as validated.")
    args = parser.parse_args()

    if args.use_mock:
        os.environ["BACKBONE_PROVIDER"] = "mock"
        os.environ["BACKBONE_USE_MOCK"] = "1"
    else:
        os.environ["BACKBONE_USE_MOCK"] = "0"
    cfg_path = args.config

    import yaml

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    resolved_data_cfg, _, _ = resolve_dataset_paths(cfg["data"])
    train, valid, test = load_datasets(resolved_data_cfg)
    examples = []
    for split in (train, valid, test):
        if not split:
            continue
        examples.extend(split)
    if not examples:
        examples = [InternalExample(uid="smoke0", text="smoke test text")]

    config_run_id = cfg.get("run_id")
    base_run_id = args.run_id or _generate_run_id(config_run_id)
    print(f"[schema_validation_test] run_id={base_run_id}")
    modes = ["proposed", "abl_no_stage2", "abl_no_moderator", "abl_no_validator"] if args.mode == "all" else [args.mode]
    require_aspects = bool(args.require_non_empty_aspects)

    summary = []
    for mode in modes:
        summary.append(_run_mode(mode.strip(), base_run_id, cfg, examples, args.max_samples, require_non_empty_aspects=require_aspects))

    print("=== Smoke summary ===")
    for item in summary:
        empty_aspects_str = f", empty_aspects={item.get('empty_aspects_failures', 0)}" if require_aspects else ""
        print(
            f"{item['mode']}: rate={item['rate']:.2f}, parse_failures={item['parse_failures']}{empty_aspects_str}, errors={item['errors']}, outputs={item['output_path']}"
        )

    # Save summary
    summary_path = Path("experiments/results/schema_smoke_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved summary to {summary_path}")


if __name__ == "__main__":
    main()
