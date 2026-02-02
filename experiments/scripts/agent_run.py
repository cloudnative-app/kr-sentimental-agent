import argparse
import json
import os
from pathlib import Path

import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from evaluation.baselines import make_runner, resolve_run_mode
from tools.backbone_client import BackboneClient
from tools.data_tools import InternalExample


def read_config(path: str):
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--text", type=str, required=True)
    parser.add_argument("--run-id", type=str, default="cli_run")
    parser.add_argument("--outdir", type=str, default=None)
    parser.add_argument("--mode", type=str, choices=["proposed", "bl1", "bl2", "bl3", "all"], default=None, help="Pipeline mode (CLI overrides config/env).")
    args = parser.parse_args()

    cfg = read_config(args.config)
    run_id = cfg.get("run_id") or args.run_id or "cli_run"
    mode = resolve_run_mode(args.mode, os.getenv("RUN_MODE"), cfg.get("run_mode") or cfg.get("mode"))

    backbone_cfg = cfg.get("backbone", {})
    backbone = BackboneClient(provider=backbone_cfg.get("provider"), model=backbone_cfg.get("model"))

    modes = ["proposed", "bl1", "bl2", "bl3"] if mode == "all" else [mode]

    for m in modes:
        runner = make_runner(run_mode=m, backbone=backbone, config=cfg.get("pipeline", {}), run_id=f"{run_id}_{m}")
        example = InternalExample(uid="cli_text", text=args.text)
        result = runner.run(example)

        outdir = Path(args.outdir or f"results/{run_id}_{m}")
        outdir.mkdir(parents=True, exist_ok=True)
        output_path = outdir / "outputs.jsonl"
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result.model_dump(), ensure_ascii=False) + "\n")

        print(f"[{m}] {json.dumps(result.model_dump(), ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
