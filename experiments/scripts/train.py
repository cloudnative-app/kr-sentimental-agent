import argparse
import os
from dataclasses import dataclass
from typing import Dict

import torch
import yaml
from datasets import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from data.datasets.loader import examples_to_dataframe, load_datasets
from tools.data_tools import build_id2label, build_label2id


@dataclass
class Config:
    seed: int
    model_name: str
    output_dir: str
    data: Dict
    label_mapping: Dict[str, int]
    train: Dict


def read_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return Config(**cfg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    args = parser.parse_args()

    cfg = read_config(args.config)
    torch.manual_seed(cfg.seed)

    label2id = build_label2id(cfg.label_mapping)
    id2label = build_id2label(label2id)

    train_examples, valid_examples, _ = load_datasets(cfg.data)
    if not train_examples:
        raise ValueError("Training split is empty after loading; check data configuration.")
    if not valid_examples:
        raise ValueError("Validation split is empty after loading; check data configuration.")

    train_df = examples_to_dataframe(train_examples, label2id=label2id)
    valid_df = examples_to_dataframe(valid_examples, label2id=label2id)

    tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)

    def tokenize_fn(examples):
        return tokenizer(
            examples["text"],
            max_length=cfg.data["max_length"],
            padding="max_length",
            truncation=True,
        )

    train_df = train_df[["text", "label"]]
    valid_df = valid_df[["text", "label"]]

    train_ds = Dataset.from_pandas(train_df, preserve_index=False)
    valid_ds = Dataset.from_pandas(valid_df, preserve_index=False)
    train_ds = train_ds.map(tokenize_fn, batched=True)
    valid_ds = valid_ds.map(tokenize_fn, batched=True)

    num_labels = len(label2id)
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg.model_name, num_labels=num_labels, id2label=id2label, label2id=label2id
    )

    training_args = TrainingArguments(
        output_dir=cfg.output_dir,
        per_device_train_batch_size=cfg.train["per_device_train_batch_size"],
        per_device_eval_batch_size=cfg.train["per_device_eval_batch_size"],
        learning_rate=cfg.train["learning_rate"],
        weight_decay=cfg.train["weight_decay"],
        num_train_epochs=cfg.train["num_train_epochs"],
        warmup_ratio=cfg.train["warmup_ratio"],
        gradient_accumulation_steps=cfg.train["gradient_accumulation_steps"],
        fp16=cfg.train.get("fp16", False),
        logging_steps=cfg.train["logging_steps"],
        evaluation_strategy=cfg.train["eval_strategy"],
        eval_steps=cfg.train["eval_steps"],
        save_steps=cfg.train["save_steps"],
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        report_to=["none"],
    )

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

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )

    trainer.train()
    trainer.save_model(os.path.join(cfg.output_dir, "final"))


if __name__ == "__main__":
    main()
