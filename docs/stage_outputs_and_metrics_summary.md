# 스테이지별 아웃풋 양식 및 최종 메트릭 요약

스테이지별 수집 데이터, 에이전트별 처리, 최종 메트릭 반영을 한눈에 확인할 수 있도록 정리합니다.

---

## 1. Stage1에서 수집되는 데이터 (에이전트별)

| 에이전트 | 스키마 | 주요 필드 | 수집·기록 내용 | scorecard 반영 위치 |
|----------|--------|-----------|----------------|---------------------|
| **ATE** | `AspectExtractionStage1Schema` | `aspects` | `term`, `span`, `normalized`, `confidence`, `rationale` | `ate`, `inputs.ate_debug`(raw/filtered), `stage1_ate` |
| **ATSA** | `AspectSentimentStage1Schema` | `aspect_sentiments` | `aspect_term`(term+span), `polarity`, `evidence`, `confidence`, `polarity_distribution` | `atsa`, `inputs.aspect_sentiments`, `inputs.sentence_sentiment` |
| **Validator** | `StructuralValidatorStage1Schema` | `structural_risks`, `correction_proposals` | `type`, `scope`, `severity`, `description`, `target_aspect`, `proposal_type`, `rationale` | `validator` 배열 중 `stage=stage1` |

**Stage1 튜플 형태**: `(aspect_ref, aspect_term, polarity)` 집합  
- **추출 경로**: `final_result.stage1_tuples` 또는 `process_trace` stage1 ATSA `output.aspect_sentiments`  
- **Supervisor 후처리**: ATE aspect 정제(topic particle 제거, contrast 규칙, substring 강제), ATSA sentiment backfill, dropped aspect에 대한 sentiment 제거

---

## 2. Supervisor·Moderator·토론 관련 에이전트의 처리

### 2.1 SupervisorAgent 처리

| 입력 산출물 | 처리 내용 |
|-------------|-----------|
| **ATE aspects** | topic particle 제거, contrast 규칙(최소 2 aspect), substring 강제(PJ1), `dropped_substring` 기록 |
| **ATSA aspect_sentiments** | ATE aspects에 맞춰 backfill, dropped aspect에 대한 sentiment 제거 |
| **Validator S1** | Stage2 프롬프트에 structural_risks, correction_proposals 포함 |
| **EpisodicOrchestrator (C2)** | retrieval, slot payload → `meta.memory`(retrieved_k, exposed_to_debate 등) 기록 |
| **Debate summary** | `_build_debate_review_context()`: hint_entries, rebuttal_points → aspect_hints |
| **Stage2 결과** | `_apply_stage2_reviews()`: Validator proposal → ATE review → ATSA review → Debate override(게이트) 순 적용 |
| **Debate override** | `aspect_hints` 기반 가중치·편차 계산, valid_hint_count=0이면 skip_reason=neutral_only → `override_gate_debug.jsonl`, `override_gate_debug_summary.json` 기록 |

### 2.2 Moderator 처리

| 입력 | 규칙 | 출력 |
|------|------|------|
| Stage1/Stage2 집계 레이블 + ValidatorOutput | **Rule Z**: confidence 모두 0 → neutral | `final_label`, `confidence`, `rationale` |
| | **Rule B**: Stage2 선호, confidence drop ≥0.2면 Stage1 유지 | `selected_stage`, `arbiter_flags` |
| | **Rule M**: label 충돌 → mixed | `applied_rules` |
| | **Rule C**: Validator veto (critical/high confidence) | |
| | **Rule A**: span IoU≥0.8, label 일치 시 confidence 보정 | |
| | **Rule D**: confidence tie-break (ATE vs ATSA) | |
| | **Rule E**: 토론 합의(sentence_polarity → final_tuples → consensus) | `rule_e_fired`, `rule_e_block_reason` |
| **final_aspect_sentiments** | `build_final_aspects()` 변환 | `FinalResult.final_aspects` |

### 2.3 토론 관련 에이전트 (EPM, TAN, CJ)

| 역할 | 산출물 | Moderator/Supervisor 접근 |
|------|--------|---------------------------|
| **EPM** (Evidence–Polarity Mapper) | `proposed_edits` (set_polarity, drop_tuple 등) | aspect_hints 구성, Override Gate 점수화 |
| **TAN** (Target–Aspect Normalizer) | `proposed_edits` (set_aspect_ref, merge_tuples 등) | 동일 |
| **CJ** (Consistency Judge) | `summary.final_patch`, `final_tuples`, `sentence_polarity`, `sentence_evidence_spans` | Rule E: sentence_polarity 우선 → final_tuples 극성 집계 |
| **Override Gate** | valid_hint_count, pos_score, neg_score, margin, skip_reason | `override_gate_debug.jsonl`, scorecard `meta.debate_override_stats` |

---

## 3. 최종 메트릭에 포함되는 산출물

### 3.1 메트릭 소스 매핑 (scorecard → structural_metrics)

| 최종 메트릭 | scorecard 소스 | 산출물 경로 |
|-------------|----------------|-------------|
| **tuple_f1_s1** | Stage1 튜플 | `final_result.stage1_tuples` \| process_trace stage1 ATSA |
| **tuple_f1_s2**, **delta_f1** | 최종 튜플 | `final_result.final_tuples` → `final_aspects` → `inputs.aspect_sentiments` |
| **fix_rate**, **break_rate**, **net_gain** | gold vs stage1 vs final | `inputs.gold_tuples` |
| **polarity_conflict_rate** | final_aspects 대표 선택 후 | `final_result.final_aspects` |
| **stage_mismatch_rate** | moderator.selected_stage | `moderator.selected_stage` vs stage1/2 |
| **guided_change_rate**, **unguided_drift_rate** | stage_delta | `stage_delta.change_type` |
| **risk_resolution_rate**, **residual_risk_rate** | validator S1/S2 | `validator[*].structural_risks` |
| **negation_contrast_failure_rate** | validator risk_id | `validators[*].structural_risks` |
| **debate_override_*** | meta.debate_override_stats | `meta.debate_override_stats`, `override_gate_debug_summary.json` |
| **aspect_hallucination_rate** | ate_debug filtered | `inputs.ate_debug.filtered` (drop_reason) |
| **implicit_grounding_rate** 등 | rq1_grounding_bucket | `ate`, `atsa`, `inputs` |

### 3.2 최종 메트릭 포함 산출물 요약표

| 산출물 | 포함 메트릭 | 비고 |
|--------|-------------|------|
| **final_result.stage1_tuples** | tuple_f1_s1, fix_rate/break_rate 분모 | stage1 튜플 F1 |
| **final_result.final_tuples** / **final_aspects** | tuple_f1_s2, delta_f1, fix_rate, break_rate, net_gain, polarity_conflict_rate | 최종 튜플 F1 |
| **inputs.gold_tuples** | tuple_f1_s1/2, fix/break/net_gain | gold 있는 샘플만 |
| **moderator.selected_stage**, **applied_rules** | stage_mismatch_rate | |
| **stage_delta** (changed, change_type) | guided_change_rate, unguided_drift_rate | 라벨 또는 pairs 변경 기준 |
| **validator** (stage1, stage2) | risk_resolution_rate, residual_risk_rate, negation_contrast_failure_rate | |
| **meta.debate_override_stats** | debate_override_*, override_* | applied, skipped_* 등 |
| **override_gate_debug_summary.json** | override_hint_invalid_rate, polarity_repair_rate | aggregator가 별도 파일에서 읽음 |
| **inputs.ate_debug** | aspect_hallucination_rate, alignment_failure_rate | filtered drop_reason |

### 3.3 산출 파일 → 메트릭 흐름

```
outputs.jsonl (FinalOutputSchema)
    ↓ make_scorecard
scorecards.jsonl
    ↓ structural_error_aggregator
structural_metrics.csv / structural_metrics_table.md
    ↓ build_metric_report
metric_report.html
```

**override_gate_debug_summary.json** → aggregator가 `override_hint_invalid_total`, `override_hint_repair_total` 등 추가 읽음.

---

## 4. 체크리스트 (확인용)

| 확인 항목 | 위치 |
|-----------|------|
| Stage1 ATE aspects | `process_trace` stage=stage1, agent=ATE |
| Stage1 ATSA aspect_sentiments | `process_trace` stage=stage1, agent=ATSA |
| Stage1 Validator risks | `process_trace` stage=stage1, agent=Validator |
| Stage1 튜플 집합 | `final_result.stage1_tuples` 또는 process_trace stage1 ATSA |
| 최종 튜플 집합 | `final_result.final_tuples` → `final_aspects` → `inputs.aspect_sentiments` |
| Moderator 최종 결정 | `moderator.final_label`, `final_aspects` |
| Debate override 적용 여부 | `meta.debate_override_stats`, `override_gate_debug.jsonl` |
| F1·fix/break 소스 | scorecard `runtime.parsed_output` 내 final_result |
