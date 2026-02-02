#!/usr/bin/env python3
"""
NIKLuge SA 2022 train JSONL을 stratified split하여 저장.

- 입력: experiments/configs/datasets/train/nikluge-sa-2022-train.jsonl
- 출력: --outdir 에 train.jsonl / valid.jsonl (80/20) 및 train.csv / valid.csv. 기본 outdir = experiments/configs/datasets/train.
- random_state=42, stratify=대표 polarity → 완전 재현·클래스 비율 유지.
- ABSA annotation 손상 없음 (원본 항목 그대로 유지). CSV 컬럼: uid, text, split, label, annotation(JSON 문자열).

Usage:
  python scripts/split_nikluge_train.py
  python scripts/split_nikluge_train.py --input experiments/configs/datasets/train/nikluge-sa-2022-train.jsonl --outdir experiments/configs/datasets/train --valid_ratio 0.2 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "train" / "nikluge-sa-2022-train.jsonl"
DEFAULT_OUTDIR = PROJECT_ROOT / "experiments" / "configs" / "datasets" / "train"


def extract_representative_label(item: dict) -> str:
    """
    ABSA 샘플에서 stratify용 대표 polarity 1개 추출.
    규칙: negative > positive > neutral 우선.
    annotation이 비어있으면 'neutral'.
    """
    polarities = []
    for ann in item.get("annotation", []):
        if len(ann) >= 3:
            polarities.append(ann[2])
    if not polarities:
        return "neutral"
    if "negative" in polarities:
        return "negative"
    if "positive" in polarities:
        return "positive"
    return "neutral"


def load_jsonl(path: Path) -> list[dict]:
    data = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def save_jsonl(data: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def item_to_csv_row(item: dict, split_name: str) -> dict:
    """NIKLuge 항목을 CSV 행으로 변환. annotation은 JSON 문자열로 저장."""
    uid = str(item.get("id", ""))
    text = str(item.get("sentence_form", ""))
    label = extract_representative_label(item)
    ann = item.get("annotation", [])
    ann_str = json.dumps(ann, ensure_ascii=False) if ann else ""
    return {"uid": uid, "text": text, "split": split_name, "label": label, "annotation": ann_str}


def save_csv(data: list[dict], path: Path, split_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not data:
        return
    fieldnames = ["uid", "text", "split", "label", "annotation"]
    with path.open("w", encoding="utf-8", newline="", errors="replace") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in data:
            writer.writerow(item_to_csv_row(item, split_name))


def main() -> None:
    ap = argparse.ArgumentParser(description="Stratified split of NIKLuge SA 2022 train JSONL")
    ap.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input JSONL (default: {DEFAULT_INPUT})",
    )
    ap.add_argument(
        "--outdir",
        type=Path,
        default=DEFAULT_OUTDIR,
        help=f"Output directory for train.jsonl and valid.jsonl (default: {DEFAULT_OUTDIR})",
    )
    ap.add_argument(
        "--valid_ratio",
        type=float,
        default=0.2,
        help="Fraction for valid split (default: 0.2 → 80/20)",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = ap.parse_args()

    input_path = args.input if args.input.is_absolute() else (PROJECT_ROOT / args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    outdir = args.outdir if args.outdir.is_absolute() else (PROJECT_ROOT / args.outdir)
    train_path = outdir / "train.jsonl"
    valid_path = outdir / "valid.jsonl"
    train_csv_path = outdir / "train.csv"
    valid_csv_path = outdir / "valid.csv"

    # 1. Load
    train_data = load_jsonl(input_path)
    n_total = len(train_data)
    if n_total == 0:
        raise ValueError(f"No records in {input_path}")

    # 2. Stratify label
    labels = [extract_representative_label(item) for item in train_data]
    print(f"Total samples: {n_total}")
    print("Label distribution (original):", dict(Counter(labels)))

    # 3. Stratified split
    train_split, valid_split = train_test_split(
        train_data,
        test_size=args.valid_ratio,
        random_state=args.seed,
        stratify=labels,
    )
    print(f"Train split: {len(train_split)}")
    print(f"Valid split: {len(valid_split)}")

    # 4. Verify distribution
    train_labels = [extract_representative_label(item) for item in train_split]
    valid_labels = [extract_representative_label(item) for item in valid_split]
    print("Train label distribution:", dict(Counter(train_labels)))
    print("Valid label distribution:", dict(Counter(valid_labels)))

    # 5. Save JSONL (ABSA annotation unchanged)
    save_jsonl(train_split, train_path)
    save_jsonl(valid_split, valid_path)
    print(f"Wrote {train_path}")
    print(f"Wrote {valid_path}")

    # 6. Save CSV (uid, text, split, label, annotation)
    save_csv(train_split, train_csv_path, "train")
    save_csv(valid_split, valid_csv_path, "valid")
    print(f"Wrote {train_csv_path}")
    print(f"Wrote {valid_csv_path}")


if __name__ == "__main__":
    main()
