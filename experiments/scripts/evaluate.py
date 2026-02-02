import argparse

from datasets import Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer
import yaml

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from data.datasets.loader import examples_to_dataframe, load_datasets
from tools.data_tools import build_id2label, build_label2id


def read_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--checkpoint", type=str, required=True)
    args = parser.parse_args()

    cfg = read_config(args.config)

    label2id = build_label2id(cfg["label_mapping"])
    id2label = build_id2label(label2id)

    _, _, test_examples = load_datasets(cfg["data"])
    if not test_examples:
        raise ValueError("Test split is empty after loading; check data configuration.")

    test_df = examples_to_dataframe(test_examples, label2id=label2id)[["text", "label"]]

    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.checkpoint, num_labels=len(label2id), id2label=id2label, label2id=label2id
    )

    def tokenize_fn(examples):
        return tokenizer(
            examples["text"],
            max_length=cfg["data"]["max_length"],
            padding="max_length",
            truncation=True,
        )

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
