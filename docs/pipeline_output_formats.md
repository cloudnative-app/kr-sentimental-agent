# 파이프라인 단계별 에이전트 산출물 및 최종 산출물 형식

## 1. 단계별 에이전트 산출물 (스키마)

### Stage1

| 에이전트 | 스키마 | 주요 필드 |
|----------|--------|-----------|
| **ATE** | `AspectExtractionStage1Schema` | `aspects: List[AspectExtractionItem]` — 각 항목: `term`, `span`, `normalized`, `confidence`, `rationale` |
| **ATSA** | `AspectSentimentStage1Schema` | `aspect_sentiments: List[AspectSentimentItem]` — 각 항목: `aspect_term`, `polarity`, `evidence`, `confidence`, `polarity_distribution` |
| **Validator** | `StructuralValidatorStage1Schema` | `structural_risks`, `consistency_score`, `correction_proposals` |

- **ATE**: 관점(속성) 추출 — `AspectExtractionItem`: term, span(Span), confidence, rationale
- **ATSA**: 관점별 감성 — `AspectSentimentItem`: **aspect_term**(AspectTerm: term, span, 문장 내 관점 표면형), polarity, evidence, confidence
- **Validator**: 구조적 위험·수정 제안 — `StructuralRiskItem`(type, scope, severity, description), `CorrectionProposal`(target_aspect, proposal_type, rationale)

### Debate (선택)

| 산출물 | 스키마 | 주요 필드 |
|--------|--------|-----------|
| **Debate** | `DebateOutput` | `topic`, `personas`, `rounds: List[DebateRound]`, `summary: DebateSummary` |
| **Round** | `DebateRound` | `round_index`, `turns: List[DebateTurn]` |
| **Turn** | `DebateTurn` | `speaker`, `stance`, `message`, `key_points` |
| **Summary** | `DebateSummary` | `winner`, `consensus`, `key_agreements`, `key_disagreements`, `rationale` |

### Stage2 (Review)

| 에이전트 | 스키마 | 주요 필드 |
|----------|--------|-----------|
| **ATE Review** | `AspectExtractionStage2Schema` | `aspect_review: List[AspectExtractionReviewItem]` — 각 항목: `term`, `action`(keep/revise_span/remove), `revised_span`, `reason`, `provenance` |
| **ATSA Review** | `AspectSentimentStage2Schema` | `sentiment_review: List[SentimentReviewItem]` — 각 항목: `aspect_term`(대상 식별용 term 문자열), `action`(maintain/flip_polarity/revise_span 등), `revised_polarity`, `reason`, `provenance` |
| **Validator** | `StructuralValidatorStage2Schema` | `final_validation: Dict` |

### Moderator (규칙 기반)

| 산출물 | 스키마 | 주요 필드 |
|--------|--------|-----------|
| **Moderator** | `ModeratorOutput` | `final_label`, `confidence`, `rationale`, `selected_stage`, `applied_rules`, `decision_reason`, `arbiter_flags` |

- 집계용 보조 타입: `ATEOutput` / `ATSAOutput` (label, confidence, rationale) — 문장 수준 집계 시 사용  
- `ValidatorOutput`: agrees_with_ate/atsa, suggested_label, issues, confidence

---

## 2. 최종 산출물 형식

### 2.1 `FinalOutputSchema` (outputs.jsonl 한 줄 = 1샘플)

```text
meta: Dict[str, Any]                    # 요청/트레이스 메타 (text_id, run_id, profile, latency_ms 등)
stage1_ate: Optional[ATEOutput]         # Stage1 ATE 집계 (label, confidence, rationale)
stage1_atsa: Optional[ATSAOutput]       # Stage1 ATSA 집계
stage1_validator: Optional[ValidatorOutput]
stage2_ate: Optional[ATEOutput]         # Stage2 ATE 집계 (리뷰 반영 후)
stage2_atsa: Optional[ATSAOutput]
stage2_validator: Optional[ValidatorOutput]
moderator: Optional[ModeratorOutput]    # 최종 문장 수준 라벨/신뢰도/규칙
debate: Optional[DebateOutput]          # 토론 전체 (rounds, summary)
process_trace: List[ProcessTrace]       # 단계별 트레이스 (stage, agent, input_text, output)
analysis_flags: AnalysisFlags           # correction_occurred, stage2_executed 등
final_result: FinalResult               # ★ 최종 ABSA 결과
```

### 2.2 `FinalResult` (최종 ABSA 출력)

| 필드 | 타입 | 설명 |
|------|------|------|
| `label` | str | 문장 수준 최종 극성 (neutral/positive/negative/mixed) |
| `confidence` | float | 대표 신뢰도 |
| `rationale` | str | 최종 결정 요약 |
| `final_aspects` | List[Dict] | **최종 관점별 감성 리스트** — 각 항목: aspect_term(term, span), polarity, evidence, confidence, polarity_distribution |

- `final_aspects` 한 항목 ≈ (aspect_term, polarity) + evidence/confidence 등. 채점은 (aspect_term.term, polarity) 기준.

---

## 3. 파이프라인 산출 파일과 내용

| 파일 | 내용 |
|------|------|
| **outputs.jsonl** | 샘플당 1줄. `FinalOutputSchema.model_dump()` — meta, stage1/2 에이전트, moderator, debate, process_trace, analysis_flags, **final_result** |
| **traces.jsonl** | 샘플당 1줄. 케이스별 트레이스(process_trace 요약 + 메타, latency 등). |
| **scorecards.jsonl** | 샘플당 1줄. `make_scorecard(payload)` — meta, debate(mapping_stats, override_stats), ate/atsa/validator 블록, moderator, stage_delta, latency, flags, **inputs**(ate_debug, aspect_sentiments, sentence_sentiment, gold_triplets 주입 시), **parsed_output**=전체 payload. 즉 **final_result.final_aspects**는 `parsed_output.final_result.final_aspects` 또는 inputs.aspect_sentiments 파생으로 접근 가능. |

---

## 4. ProcessTrace (단계별 트레이스 한 항목)

| 필드 | 설명 |
|------|------|
| stage | "stage1" / "stage2" 등 |
| agent | "ATE", "ATSA", "Validator", "Moderator" 등 |
| uid, split, language_code, domain_id | 전파된 메타 |
| input_text | 해당 에이전트 입력 텍스트 |
| output | 해당 에이전트 원시 출력 Dict (스키마별 model_dump) |
| call_metadata | LLM 호출 메타 (선택) |
| stage_status, notes | 상태/비고 |

---

## 5. 요약

- **단계별 산출물**: Stage1(ATE/ATSA/Validator) → Debate(선택) → Stage2(ATE/ATSA 리뷰, Validator) → Moderator. 각각 `schemas/agent_outputs.py`에 정의된 스키마로 나옴.
- **최종 산출물**: `FinalOutputSchema.final_result` — `label`, `confidence`, `rationale`, **`final_aspects`**(트리플렛 형태 리스트).
- **파일**: `outputs.jsonl` = 샘플당 전체 FinalOutputSchema; `scorecards.jsonl` = 메트릭/디버그용 요약 + `parsed_output`(전체 payload 포함).
