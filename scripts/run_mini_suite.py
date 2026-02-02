"""
Run a fixed input suite multiple times with the real backbone, then emit per-run scorecards and a merged file.

Usage (example):
    python scripts/run_mini_suite.py ^
        --input experiments/configs/datasets/mini_suite_60.jsonl ^
        --n_runs 3 ^
        --run_prefix mini60_real ^
        --mode proposed ^
        --use_mock 0 ^
        --allowlist experiments/configs/aspect_allowlists/conflict_allowlist.json

Outputs per run (i = 1..n):
  - smoke:   experiments/results/proposed/{run_prefix}_r{i}_proposed/smoke_outputs.jsonl
  - cards:   experiments/results/proposed/{run_prefix}_r{i}_proposed/scorecards.jsonl (run field added)
Merged:
  - experiments/results/proposed/{run_prefix}_proposed/scorecards_3runs.jsonl  (or _{n_runs}runs)
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Dict, List


def load_jsonl(path: Path) -> List[Dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def jsonl_to_csv(src: Path, dst: Path):
    rows = load_jsonl(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="\n") as f:
        f.write("text,case_id,case_type\n")
        for r in rows:
            text = (r.get("text") or "").replace('"', '""')
            cid = r.get("case_id", "")
            ctype = r.get("case_type", "")
            f.write(f"\"{text}\",{cid},{ctype}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to input JSONL (must include case_id, case_type, text).")
    ap.add_argument("--n_runs", type=int, default=3, help="Number of repeated runs.")
    ap.add_argument("--run_prefix", default="mini60_real", help="Run-id prefix; _r{idx} will be appended.")
    ap.add_argument("--mode", default="proposed")
    ap.add_argument("--use_mock", type=int, default=0)
    ap.add_argument("--allowlist", default=None, help="Aspect allowlist file passed to scorecard_from_smoke.py")
    ap.add_argument("--config_base", default="experiments/configs/proposed.yaml", help="Base YAML config to clone.")
    args = ap.parse_args()

    input_path = Path(args.input)
    samples = load_jsonl(input_path)
    id_map = {s.get("case_id"): s for s in samples}

    merged: List[Dict] = []

    # Prepare temp csv + config
    tmp_dir = Path("experiments/configs/datasets/tmp_runs")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_dir / f"{args.run_prefix}_mini_suite.csv"
    jsonl_to_csv(input_path, csv_path)

    import yaml

    base_cfg = yaml.safe_load(Path(args.config_base).read_text(encoding="utf-8"))
    cfg = base_cfg or {}
    cfg["data"] = {
        "input_format": "csv",
        "train_file": str(csv_path),
        "text_column": "text",
        "label_column": None,
        "target_column": None,
    }
    cfg_path = tmp_dir / f"{args.run_prefix}_config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    for i in range(1, args.n_runs + 1):
        run_id = f"{args.run_prefix}_r{i}"
        # 1) run pipeline to produce smoke_outputs
        cmd_smoke = [
            "python",
            "scripts/schema_validation_test.py",
            "--config",
            str(cfg_path),
            "--mode",
            args.mode,
            "--use_mock",
            str(args.use_mock),
            "--n",
            str(len(samples)),
            "--run-id",
            run_id,
        ]
        subprocess.run(cmd_smoke, check=True)

        smoke_path = Path(f"experiments/results/proposed/{run_id}_proposed/smoke_outputs.jsonl")
        if not smoke_path.exists():
            raise FileNotFoundError(smoke_path)

        # 2) scorecards
        cmd_cards = [
            "python",
            "scripts/scorecard_from_smoke.py",
            "--smoke",
            str(smoke_path),
        ]
        if args.allowlist:
            cmd_cards += ["--aspect_allowlist", args.allowlist]
        subprocess.run(cmd_cards, check=True)

        cards_path = smoke_path.parent / "scorecards.jsonl"
        cards = load_jsonl(cards_path)

        # 3) annotate run + case info
        annotated = []
        for row in cards:
            meta = row.get("meta", {})
            # case_id in input; fall back to text match if needed
            case_id = meta.get("case_id") or meta.get("text_id") or ""
            if not case_id:
                # try to recover by input text
                txt = meta.get("input_text")
                for cid, rec in id_map.items():
                    if rec.get("text") == txt:
                        case_id = cid
                        break
            case_rec = id_map.get(case_id, {})
            meta["case_id"] = case_id
            meta["case_type"] = case_rec.get("case_type")
            meta["run"] = i
            row["meta"] = meta
            annotated.append(row)

        write_jsonl(cards_path, annotated)
        merged.extend(annotated)
        print(f"[run {i}] wrote {cards_path} ({len(annotated)} records)")

    merged_path = Path(f"experiments/results/proposed/{args.run_prefix}_proposed/scorecards_{args.n_runs}runs.jsonl")
    write_jsonl(merged_path, merged)
    print(f"[merged] wrote {merged_path} ({len(merged)} records)")


if __name__ == "__main__":
    main()
