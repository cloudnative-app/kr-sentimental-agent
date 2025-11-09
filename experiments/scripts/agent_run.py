import argparse
import json
import yaml
import os

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from tools.data_tools import build_label2id, build_id2label
from agents.supervisor_agent import SupervisorAgent


def read_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--checkpoint", type=str, default="experiments/results/exp1/final")
    parser.add_argument("--mode", type=str, default="two_stage", 
                       choices=["two_stage"]) 
    parser.add_argument("--aggregate", type=str, default="mean", choices=["mean", "vote", "max"]) 
    parser.add_argument("--mc", action="store_true", help="enable MC Dropout self-consistency")
    parser.add_argument("--text", type=str, required=True)
    parser.add_argument("--llm-provider", type=str, default="openai", choices=["openai", "anthropic", "google"])
    parser.add_argument("--model-name", type=str, default=None)
    args = parser.parse_args()

    cfg = read_config(args.config)
    label2id = build_label2id(cfg["label_mapping"]) 
    id2label = build_id2label(label2id)

    # Two-stage mode execution
    if args.mode == "two_stage":
        # Use two-stage supervisor (matches the image structure)
        coord = SupervisorAgent(llm_provider=args.llm_provider, model_name=args.model_name)
        outputs = coord.run(args.text)
    print(json.dumps({k: v.__dict__ for k, v in outputs.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


