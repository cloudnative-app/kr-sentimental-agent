import argparse
import yaml
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from tools.data_tools import build_label2id, build_id2label


def read_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--checkpoint", type=str, default="experiments/results/exp1/final")
    parser.add_argument("--text", type=str, required=True)
    args = parser.parse_args()

    cfg = read_config(args.config)
    label2id = build_label2id(cfg["label_mapping"]) 
    id2label = build_id2label(label2id)

    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.checkpoint, num_labels=len(label2id), id2label=id2label, label2id=label2id
    )

    inputs = tokenizer(args.text, return_tensors="pt", truncation=True, padding=True, max_length=cfg["data"]["max_length"])
    with torch.no_grad():
        logits = model(**inputs).logits
        pred = int(logits.argmax(dim=-1).item())
    print({"text": args.text, "pred_label_id": pred, "pred_label": id2label[pred]})


if __name__ == "__main__":
    main()


