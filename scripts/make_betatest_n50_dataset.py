#!/usr/bin/env python3
"""
Betatest N50 데이터셋: real_n50보다 다른 시드로 50개 추출.
기존 pretest/real_n50_seed1(seed=1)과 구분되는 랜덤 50을 위해 seed=99 기본 사용.
입력: train/valid.jsonl (make_real_n100_seed1_dataset.py와 동일 규칙).
출력: experiments/configs/datasets/betatest_n50/train.csv, valid.csv, valid.gold.jsonl

- 동일 seed로 실행 시 항상 같은 ID 집합 추출 (재현성).
- seed=1(real_n50) vs seed=99(betatest) → 서로 다른 50개.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "train" / "valid.jsonl"
DEFAULT_OUTDIR = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "betatest_n50"
DEFAULT_VALID_SIZE = 50
DEFAULT_SEED = 99  # real_n50_seed1(seed=1)과 구분


def annotation_to_gold_tuples(item: dict) -> list[dict]:
    """Gold as list of {aspect_ref, aspect_term, polarity, span?}. NIKLuge annotation 형식."""
    text = item.get("sentence_form") or ""
    out = []
    for ann in item.get("annotation") or []:
        if len(ann) < 3:
            continue
        aspect_ref, polarity = ann[0], ann[2]
        span_info = ann[1] if len(ann) > 1 else None
        span_obj: dict | None = None
        if span_info is None or not isinstance(span_info, (list, tuple)):
            aspect_term = ""
        elif span_info[0] is not None and span_info[0] != "":
            aspect_term = str(span_info[0]).strip()
            if len(span_info) >= 3:
                try:
                    s, e = int(span_info[1]), int(span_info[2])
                    if 0 <= s <= e <= len(text):
                        span_obj = {"start": s, "end": e}
                except (TypeError, ValueError):
                    pass
        elif len(span_info) >= 3:
            s, e = int(span_info[1]), int(span_info[2])
            aspect_term = text[s:e] if 0 <= s <= e <= len(text) else ""
            if 0 <= s <= e <= len(text):
                span_obj = {"start": s, "end": e}
        else:
            aspect_term = ""
        rec: dict = {"aspect_ref": aspect_ref, "aspect_term": aspect_term, "polarity": polarity}
        if span_obj is not None:
            rec["span"] = span_obj
        out.append(rec)
    return out


def load_jsonl(path: Path) -> list[dict]:
    data = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Betatest N50: seed=99로 real_n50_seed1(seed=1)과 구분되는 50개 추출"
    )
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSONL (NIKLuge)")
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help="Output directory (betatest_n50/)")
    ap.add_argument("--valid_size", type=int, default=DEFAULT_VALID_SIZE, help="Valid set size (default 50)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed (default 99, distinct from real_n50)")
    args = ap.parse_args()

    input_path = args.input if args.input.is_absolute() else (PROJECT_ROOT / args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    outdir = args.outdir if args.outdir.is_absolute() else (PROJECT_ROOT / args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    data = load_jsonl(input_path)
    n = len(data)
    if n == 0:
        raise ValueError(f"No records in {input_path}")
    if args.valid_size > n:
        raise ValueError(f"valid_size {args.valid_size} > available {n}")

    k = args.valid_size
    rng = random.Random(args.seed)
    indices = list(range(n))
    rng.shuffle(indices)
    valid_data = [data[i] for i in indices[:k]]
    train_data = [data[i] for i in indices[k:]]

    def row(item: dict) -> dict:
        return {"id": item.get("id", ""), "text": item.get("sentence_form", "")}

    with (outdir / "train.csv").open("w", encoding="utf-8", newline="", errors="replace") as f:
        w = csv.DictWriter(f, fieldnames=["id", "text"])
        w.writeheader()
        w.writerows([row(it) for it in train_data])

    with (outdir / "valid.csv").open("w", encoding="utf-8", newline="", errors="replace") as f:
        w = csv.DictWriter(f, fieldnames=["id", "text"])
        w.writeheader()
        w.writerows([row(it) for it in valid_data])

    with (outdir / "valid.gold.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for it in valid_data:
            f.write(
                json.dumps({"uid": it.get("id", ""), "gold_tuples": annotation_to_gold_tuples(it)}, ensure_ascii=False)
                + "\n"
            )

    print(f"betatest_n50: {n} total -> train={len(train_data)}, valid={len(valid_data)} (seed={args.seed}) -> {outdir}")


if __name__ == "__main__":
    main()
