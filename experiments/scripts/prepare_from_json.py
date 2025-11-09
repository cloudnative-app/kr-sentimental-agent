import argparse
import yaml
from pathlib import Path

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from tools.data_tools import load_internal_json_dir


def read_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--split", type=str, default="train", choices=["train", "valid", "test"]) 
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    cfg = read_config(args.config)
    key = f"json_dir_{args.split}"
    json_dir = cfg["data"][key]

    df = load_internal_json_dir(json_dir)
    out = args.out or f"data/{args.split}.csv"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Saved {len(df)} rows to {out}")


if __name__ == "__main__":
    main()


