from __future__ import annotations

from typing import Dict

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

from .llm_clients import create_client
from .prompt_classifier import PromptClassifier


class HFClassifier:
    """HuggingFace classifier wrapper with support for LLM-based and zero-shot classification."""
    
    def __init__(self, checkpoint: str, id2label: Dict[int, str], mc_dropout: bool = False):
        self.id2label = id2label
        self.mc_dropout = mc_dropout
        self.zero_shot = False
        self.llm_based = False
        
        if checkpoint.startswith("llm:"):
            # LLM 기반 분류기
            self.llm_based = True
            provider = checkpoint.split(":", 1)[1]  # llm:gemini -> gemini
            client = create_client(provider)
            labels = [id2label[i] for i in range(len(id2label))]
            self.prompt_classifier = PromptClassifier(client, labels)
        elif checkpoint.startswith("zero-shot:"):
            self.zero_shot = True
            model_name = checkpoint.split(":", 1)[1]
            self.zs = pipeline("zero-shot-classification", model=model_name)
        else:
            self.tokenizer = AutoTokenizer.from_pretrained(checkpoint)
            self.model = AutoModelForSequenceClassification.from_pretrained(checkpoint)
            if mc_dropout:
                self._enable_mc_dropout()

    def predict(self, text: str) -> Dict[str, float]:
        """Predict sentiment probabilities for a given text."""
        if self.llm_based:
            return self.prompt_classifier.predict(text)
        elif self.zero_shot:
            labels = [self.id2label[i] for i in range(len(self.id2label))]
            res = self.zs(text, candidate_labels=labels, hypothesis_template="이 문장은 {} 감정을 나타낸다.")
            return {lbl: float(score) for lbl, score in zip(res["labels"], res["scores"])}
        
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = self.model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1).tolist()
        return {self.id2label[i]: float(p) for i, p in enumerate(probs)}

    def predict_mc(self, text: str, n: int = 10) -> Dict[str, float]:
        """Monte Carlo prediction with dropout for uncertainty estimation."""
        if self.llm_based:
            return self.prompt_classifier.predict_mc(text, n)
        elif not self.mc_dropout or self.zero_shot:
            return self.predict(text)
        
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True)
        self.model.train()  # activate dropout
        acc = None
        for _ in range(n):
            logits = self.model(**inputs).logits[0]
            probs = torch.softmax(logits, dim=-1)
            acc = probs if acc is None else acc + probs
        mean_probs = (acc / n).tolist()
        self.model.eval()
        return {self.id2label[i]: float(p) for i, p in enumerate(mean_probs)}

    def _enable_mc_dropout(self):
        """Enable Monte Carlo dropout for uncertainty estimation."""
        for m in self.model.modules():
            if m.__class__.__name__.startswith("Dropout"):
                m.p = max(getattr(m, "p", 0.1), 0.1)
