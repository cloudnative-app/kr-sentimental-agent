"""
HF classifier as aux signal only: no impact on Validator/Moderator.
Produces hf_signal for scorecard.aux_signals.hf (append-only, toggleable).

Supports: HuggingFace checkpoint or zero-shot (no llm: — use pipeline BackboneClient for LLM).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Normalize polarity to pos/neg/neu for comparison with pipeline final
POLARITY_NORM = {
    "positive": "pos", "pos": "pos", "긍정": "pos",
    "negative": "neg", "neg": "neg", "부정": "neg",
    "neutral": "neu", "neu": "neu", "중립": "neu", "mixed": "neu",
}


def _norm(label: str) -> str:
    if not label:
        return "neu"
    key = (label or "").strip().lower()
    return POLARITY_NORM.get(key) or POLARITY_NORM.get(label.strip()) or "neu"


def run_hf_sentiment(
    text: str,
    checkpoint: str,
    id2label: Optional[Dict[int, str]] = None,
    *,
    model_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Run HF sentiment on text. Returns label (pos/neg/neu), confidence, or None if disabled/failed.
    Does not use llm: checkpoints (prompt_classifier not used here).
    """
    if not checkpoint or not text or checkpoint.strip().startswith("llm:"):
        return None
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
    except ImportError:
        return None
    try:
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        model = AutoModelForSequenceClassification.from_pretrained(checkpoint)
    except Exception:
        return None
    if id2label is None and getattr(model, "config", None) and getattr(model.config, "id2label", None):
        id2label = {int(k): str(v) for k, v in model.config.id2label.items()}
    id2label = id2label or {0: "neg", 1: "pos"}
    inputs = tokenizer(text[:5120], return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits[0]
    probs = torch.softmax(logits, dim=-1).tolist()
    idx = int(torch.argmax(logits).item())
    label_raw = id2label.get(idx, "neu")
    label = _norm(label_raw)
    confidence = float(probs[idx]) if idx < len(probs) else 0.0
    return {
        "task": "sentiment",
        "label": label,
        "confidence": confidence,
        "model_id": model_id or checkpoint,
    }


def build_hf_signal(
    text: str,
    checkpoint: Optional[str],
    id2label: Optional[Dict[int, str]],
    stage1_final_label: str,
    stage2_final_label: str,
    *,
    model_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build aux_signals.hf dict: task, label, confidence, model_id (optional), disagrees_with.
    Returns None if checkpoint is disabled or run_hf_sentiment fails.
    """
    if not checkpoint:
        return None
    out = run_hf_sentiment(text, checkpoint, id2label, model_id=model_id)
    if not out:
        return None
    s1_norm = _norm(stage1_final_label)
    s2_norm = _norm(stage2_final_label)
    out["disagrees_with"] = {
        "stage1_final": out["label"] != s1_norm,
        "stage2_final": out["label"] != s2_norm,
    }
    return out
