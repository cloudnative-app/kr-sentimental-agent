import argparse
import json
from pathlib import Path
import yaml

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from tools.data_tools import build_label2id, build_id2label
from agents.supervisor_agent import SupervisorAgent


def read_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def predict_label(text: str, probs: dict) -> str:
    return max(probs.items(), key=lambda x: x[1])[0]


def run_condition(texts, mode: str, clf_ckpt: str, id2label, aggregate: str = "mean", mc: bool = False, 
                 llm_provider: str = "openai", model_name: str = None):
    logs = []
    
    if mode == "two_stage":
        # Use two-stage supervisor (matches the image structure)
        coord = SupervisorAgent(llm_provider=llm_provider, model_name=model_name)
        for t in texts:
            outputs = coord.run(t)
            logs.append({"text": t, **{k: v.__dict__ for k, v in outputs.items()}})
        return logs



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--checkpoint", type=str, default="experiments/results/exp1/final")
    parser.add_argument("--input", type=str, required=True, help="CSV with a column 'text'")
    parser.add_argument("--outdir", type=str, default="experiments/results")
    parser.add_argument("--llm-provider", type=str, default="openai", choices=["openai", "anthropic", "google"])
    parser.add_argument("--model-name", type=str, default=None)
    args = parser.parse_args()

    import pandas as pd
    df = pd.read_csv(args.input)
    texts = df["text"].astype(str).tolist()

    cfg = read_config(args.config)
    id2label = build_id2label(build_label2id(cfg["label_mapping"]))

    conditions = [
        ("two_stage", {"aggregate": "mean", "llm_provider": args.llm_provider, "model_name": args.model_name}),
    ]

    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    for mode, opts in conditions:
        logs = run_condition(texts, mode, args.checkpoint, id2label, **opts)
        out_path = Path(args.outdir) / f"{mode}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()


