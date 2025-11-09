import argparse
import os
import yaml
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from tools.data_tools import load_csv_dataset, apply_label_mapping, load_internal_json_dir
from tools.data_tools import build_label2id, build_id2label


def read_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--checkpoint", type=str, required=True)
    args = parser.parse_args()

    cfg = read_config(args.config)
    torch.manual_seed(cfg["seed"]) 

    label2id = build_label2id(cfg["label_mapping"])
    id2label = build_id2label(label2id)

    if cfg["data"].get("input_format", "csv") == "csv":
        _, _, test_df = load_csv_dataset(
            cfg["data"]["train_file"],
            cfg["data"]["valid_file"],
            cfg["data"]["test_file"],
            cfg["data"]["text_column"],
            cfg["data"]["label_column"],
        )
    else:
        test_df = load_internal_json_dir(cfg["data"]["json_dir_test"]) 
    test_df = apply_label_mapping(test_df, cfg["data"]["label_column"], label2id)

    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.checkpoint, num_labels=len(label2id), id2label=id2label, label2id=label2id
    )

    def tokenize_fn(examples):
        return tokenizer(
            examples[cfg["data"]["text_column"]],
            max_length=cfg["data"]["max_length"],
            padding="max_length",
            truncation=True,
        )

    test_df = test_df[[cfg["data"]["text_column"], cfg["data"]["label_column"]]].rename(columns={cfg["data"]["text_column"]: "text", cfg["data"]["label_column"]: "label"})
    test_ds = Dataset.from_pandas(test_df, preserve_index=False).map(tokenize_fn, batched=True)

    from evaluate import load as load_metric
    f1_metric = load_metric("f1")
    acc_metric = load_metric("accuracy")

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = logits.argmax(axis=-1)
        return {
            "accuracy": acc_metric.compute(predictions=preds, references=labels)["accuracy"],
            "f1": f1_metric.compute(predictions=preds, references=labels, average="macro")["f1"],
        }

    trainer = Trainer(model=model, tokenizer=tokenizer, compute_metrics=compute_metrics)
    metrics = trainer.evaluate(test_ds)
    print(metrics)


if __name__ == "__main__":
    main()


