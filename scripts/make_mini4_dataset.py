#!/usr/bin/env python3
"""
단일 고정 데이터셋: train 570개, valid 10개 (총 580).
mini3와 동일 규칙(seed 42, stratify=None, gold_tuples, span 포함). 전체 시트에서 580개 추출 후 valid 10개로 분할.

- 입력: experiments/configs/datasets/train/valid.jsonl
- 출력: experiments/configs/datasets/mini4/train.csv, valid.csv, valid.gold.jsonl
- 규칙: 전체 로드 → seed로 shuffle 후 total_samples개 추출 → valid_size개를 valid로 분할 (나머지 train)

Usage:
  python scripts/make_mini4_dataset.py
  python scripts/make_mini4_dataset.py --total_samples 580 --valid_size 10 --outdir experiments/configs/datasets/mini4
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "train" / "valid.jsonl"
DEFAULT_OUTDIR = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "mini4"
DEFAULT_TOTAL_SAMPLES = 580
DEFAULT_VALID_SIZE = 10


def annotation_to_gold_tuples(item: dict) -> list[dict]:
    """Gold as list of {aspect_ref, aspect_term, polarity, span?}. aspect_term = surface form. span optional (start, end)."""
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
        description="Train 570, valid 10 (total 580). Extract total_samples from full sheet, then split valid_size to valid."
    )
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSONL path")
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help="Output directory (mini4/)")
    ap.add_argument(
        "--total_samples",
        type=int,
        default=DEFAULT_TOTAL_SAMPLES,
        help="Total samples to take from full dataset (default 580)",
    )
    ap.add_argument(
        "--valid_size",
        type=int,
        default=DEFAULT_VALID_SIZE,
        help="Exact number of samples for valid set (default 10)",
    )
    ap.add_argument("--seed", type=int, default=42, help="Random seed for shuffle and split")
    args = ap.parse_args()

    input_path = args.input if args.input.is_absolute() else (PROJECT_ROOT / args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    outdir = args.outdir if args.outdir.is_absolute() else (PROJECT_ROOT / args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    data = load_jsonl(input_path)
    n_total = len(data)
    if n_total == 0:
        raise ValueError(f"No records in {input_path}")

    if args.valid_size > args.total_samples:
        raise ValueError(f"valid_size ({args.valid_size}) must be <= total_samples ({args.total_samples})")

    # 전체에서 total_samples개 추출 (seed로 shuffle 후 앞에서부터)
    k = min(args.total_samples, n_total)
    rng = random.Random(args.seed)
    indices = list(range(n_total))
    rng.shuffle(indices)
    data = [data[i] for i in indices[:k]]
    n = len(data)

    # valid_size개를 valid로, 나머지를 train으로 분할
    train_data, valid_data = train_test_split(
        data, test_size=args.valid_size, random_state=args.seed, stratify=None
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
            f.write(
                json.dumps(
                    {"uid": it.get("id", ""), "gold_tuples": annotation_to_gold_tuples(it)},
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"mini4: {n_total} total -> {n} samples -> {outdir}")
    print(f"  train={len(train_data)}, valid={len(valid_data)}")


if __name__ == "__main__":
    main()
