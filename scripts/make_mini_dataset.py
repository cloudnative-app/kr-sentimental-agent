#!/usr/bin/env python3
"""
단일 고정 데이터셋 생성: train/valid.jsonl → 80/20 비평가·평가 분할 (폴드 없음).
Seed 반복 실험용: 동일 train/valid를 N회 시드로 반복 실행할 때 사용.

- 입력: experiments/configs/datasets/train/valid.jsonl
- 출력: experiments/configs/datasets/mini/train.csv, valid.csv, valid.gold.jsonl
- 규칙: train_test_split(..., test_size=0.2, random_state=42, stratify=None)
  (stratify 미사용: 리허설은 파이프라인 점검 목적, 라벨 기반 분할은 선택 편향 의심 회피)
- CSV: id, text만 (라벨 컬럼 없음). Gold: valid.gold.jsonl에만 존재.

Usage:
  python scripts/make_mini_dataset.py
  python scripts/make_mini_dataset.py --input experiments/configs/datasets/train/valid.jsonl --outdir experiments/configs/datasets/mini
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "train" / "valid.jsonl"
DEFAULT_OUTDIR = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "mini"


def annotation_to_gold_triplets(item: dict) -> list[dict]:
    text = item.get("sentence_form") or ""
    triplets = []
    for ann in item.get("annotation") or []:
        if len(ann) < 3:
            continue
        aspect_ref, polarity = ann[0], ann[2]
        span_info = ann[1] if len(ann) > 1 else None
        if span_info is None or not isinstance(span_info, (list, tuple)):
            term = ""
        elif span_info[0] is not None and span_info[0] != "":
            term = str(span_info[0]).strip()
        elif len(span_info) >= 3:
            s, e = int(span_info[1]), int(span_info[2])
            term = text[s:e] if 0 <= s <= e <= len(text) else ""
        else:
            term = ""
        triplets.append({"aspect_ref": aspect_ref, "opinion_term": {"term": term}, "polarity": polarity})
    return triplets


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
    ap = argparse.ArgumentParser(description="Single fixed split (no fold) for seed-repeat experiments")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSONL path")
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help="Output directory (mini/)")
    ap.add_argument("--valid_ratio", type=float, default=0.2, help="Valid fraction (default 0.2); ignored if --valid_size set")
    ap.add_argument("--valid_size", type=int, default=None, help="Exact valid set size (e.g. 60). Overrides --valid_ratio.")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for split (default 42)")
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

    if args.valid_size is not None:
        k = min(args.valid_size, n)
        if k < args.valid_size:
            raise ValueError(f"valid_size {args.valid_size} > available {n}")
        import random
        rng = random.Random(args.seed)
        indices = list(range(n))
        rng.shuffle(indices)
        valid_indices = set(indices[:k])
        valid_data = [data[i] for i in indices[:k]]
        train_data = [data[i] for i in indices[k:]]
    else:
        train_data, valid_data = train_test_split(
            data, test_size=args.valid_ratio, random_state=args.seed, stratify=None
        )

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
            f.write(json.dumps({"uid": it.get("id", ""), "gold_triplets": annotation_to_gold_triplets(it)}, ensure_ascii=False) + "\n")

    print(f"Single split (no fold): {n} samples -> {outdir}")
    print(f"  train={len(train_data)}, valid={len(valid_data)}")


if __name__ == "__main__":
    main()
