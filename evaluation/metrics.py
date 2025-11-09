from typing import Dict, Any
import torch
from evaluate import load as load_metric


def compute_metrics(eval_pred) -> Dict[str, float]:
    """Compute evaluation metrics for sentiment analysis."""
    logits, labels = eval_pred
    preds = logits.argmax(axis=-1)
    
    f1_metric = load_metric("f1")
    acc_metric = load_metric("accuracy")
    
    return {
        "accuracy": acc_metric.compute(predictions=preds, references=labels)["accuracy"],
        "f1": f1_metric.compute(predictions=preds, references=labels, average="macro")["f1"],
    }


def evaluate_model(model, tokenizer, test_dataset) -> Dict[str, float]:
    """Evaluate a model on test dataset."""
    from transformers import Trainer
    
    trainer = Trainer(model=model, tokenizer=tokenizer, compute_metrics=compute_metrics)
    metrics = trainer.evaluate(test_dataset)
    return metrics

