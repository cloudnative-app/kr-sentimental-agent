"""
Retriever — 1단계: signature + lexical 만 사용.
Top-k 1~3, filters: language 동일, structure overlap. lexical = 단어 겹침(임베딩 없음).
sentence-transformers hybrid는 2단계 옵션(현재 필수 아님).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from schemas.memory_v1_1 import InputSignatureV1_1


def _tokenize(text: str) -> set:
    """간단 토큰화: 공백·구두점 기준, 2글자 이상."""
    if not text or not isinstance(text, str):
        return set()
    t = re.sub(r"[^\w\s가-힣a-zA-Z]", " ", text.lower())
    return {w for w in t.split() if len(w) >= 2}


def _lexical_score(query_tokens: set, entry: Dict[str, Any]) -> float:
    """entry의 case_summary(symptom, rationale_summary)와 query 토큰 겹침 비율."""
    case = entry.get("case_summary") or {}
    symptom = _tokenize(str(case.get("symptom") or ""))
    rationale = _tokenize(str(case.get("rationale_summary") or ""))
    combined = symptom | rationale
    if not query_tokens or not combined:
        return 0.0
    overlap = len(query_tokens & combined) / len(query_tokens)
    return min(1.0, overlap)


class Retriever:
    """
    1단계: signature + lexical 만 사용(필수 수준).
    - signature: input_signature (language, detected_structure, length_bucket 등) 매칭
    - lexical: 단어 겹침으로 순위 부여(임베딩/sentence-transformers 없음)
    sentence-transformers hybrid는 2단계에서 선택적으로 추가 가능.
    """

    def __init__(
        self,
        *,
        mode: str = "signature_lexical",
        topk: int = 3,
        require_same_language: bool = True,
        require_structure_overlap: bool = True,
    ):
        self.mode = mode
        self.topk = max(1, min(3, topk))
        self.require_same_language = require_same_language
        self.require_structure_overlap = require_structure_overlap

    def retrieve(
        self,
        store_entries: List[Dict[str, Any]],
        query_signature: InputSignatureV1_1 | Dict[str, Any],
        query_lexical: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        store_entries 중에서 query_signature와 매칭되는 항목을 topk개 반환.
        language / structure 필터 적용. query_lexical 있으면 단어 겹침으로 정렬 보조.
        """
        if not store_entries:
            return []
        if isinstance(query_signature, InputSignatureV1_1):
            q = query_signature.model_dump()
        else:
            q = query_signature
        q_lang = q.get("language") or "ko"
        q_struct = set(q.get("detected_structure") or [])
        q_tokens = _tokenize(query_lexical or "")

        candidates: List[Dict[str, Any]] = []
        for entry in store_entries:
            sig = entry.get("input_signature") or {}
            if not sig:
                continue
            if self.require_same_language and (sig.get("language") or "ko") != q_lang:
                continue
            if self.require_structure_overlap and q_struct:
                s_struct = set(sig.get("detected_structure") or [])
                if not (q_struct & s_struct) and "none" not in s_struct:
                    continue
            candidates.append(entry)

        def score(e: Dict[str, Any]) -> tuple:
            s = e.get("input_signature") or {}
            ss = set(s.get("detected_structure") or [])
            sig_score = len(q_struct & ss) if q_struct else 0
            lex_score = _lexical_score(q_tokens, e) if q_tokens else 0.0
            return (sig_score, lex_score)

        candidates.sort(key=score, reverse=True)
        return candidates[: self.topk]
