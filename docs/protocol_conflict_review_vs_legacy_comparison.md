# protocol_refactor_conflict_review vs Legacy 워크플로우·데이터 플로우 비교

**protocol_refactor_conflict_review** = `conflict_review_v1` (refactor 브랜치)  
**Legacy** = 기본 파이프라인 (`protocol_mode: legacy` 또는 미지정)

---

## 1. 에이전트 워크플로우 비교

### 1.1 Conflict Review v1 (protocol_refactor_conflict_review)

```
text
  │
  ├─► P-NEG (Stage1) ──► triplets (negation/contrast 관점)
  ├─► P-IMP (Stage1) ──► triplets (implicit 관점)
  └─► P-LIT (Stage1) ──► triplets (literal/explicit 관점)
       │
       ▼
  Merge: A(r_neg) + B(r_imp) + C(r_lit) → candidates (tuple_id, origin_agent)
       │
       ▼
  conflict_flags = _compute_conflict_flags(candidates)
       │
       ├─► ReviewA ──► review_actions
       ├─► ReviewB ──► review_actions
       └─► ReviewC ──► review_actions
       │
       ▼
  Arbiter ──► 최종 review_actions (A/B/C 합침)
       │
       ▼
  _apply_review_actions(candidates, arb_actions) → final_candidates
       │
       ▼
  FinalResult (stage1_tuples, final_tuples, final_aspects)
```

**에이전트 목록 (7개 LLM 호출):**
| 순서 | 에이전트 | 역할 | 출력 |
|------|----------|------|------|
| 1 | P-NEG | 부정/대비 관점 ASTE | triplets |
| 2 | P-IMP | 암시적 관점 ASTE | triplets |
| 3 | P-LIT | 문자적 관점 ASTE | triplets |
| 4 | ReviewA | A 관점 리뷰 | review_actions |
| 5 | ReviewB | B 관점 리뷰 | review_actions |
| 6 | ReviewC | C 관점 리뷰 | review_actions |
| 7 | Arbiter | A/B/C 합의 | review_actions |

- **Validator 없음** (validator_risks는 빈 리스트)
- **Debate 없음**
- **Episodic Memory 미사용** (conflict_review 러너 내부)
- **Moderator 없음** (label은 final_tuples 극성 집계로 결정)

---

### 1.2 Legacy (latency 파이프라인)

```
text
  │
  ▼
Stage1:
  ATE ──► aspects
  ATSA ──► aspect_sentiments (ATE aspects 기반)
  Validator ──► structural_risks, correction_proposals
       │
       ▼
  [C2] EpisodicOrchestrator ──► slot_dict, memory_meta
       │
       ▼
  [enable_debate] DebateOrchestrator
       EPM → TAN → CJ ──► DebateOutput (rounds, summary, proposed_edits)
       │
       ▼
  _build_debate_review_context() → debate_context_json
       │
       ▼
Stage2:
  ATE (review) ──► aspect_review (Stage1 + Validator + debate_context)
  ATSA (review) ──► sentiment_review
  Validator S2 ──► 재검증
       │
       ▼
  _apply_stage2_reviews()
       Validator proposals → ATE review → ATSA review → Debate override
       │
       ▼
  _adopt_stage2_decision_with_ev() → adopt_stage2
       │
       ▼
  Moderator (Rule A–E, Z, M, C, D) ──► final_label, final_aspects
```

**에이전트 목록 (6~9+ LLM 호출):**
| 순서 | 에이전트 | 역할 | 출력 |
|------|----------|------|------|
| 1 | ATE | 관점 추출 | aspects |
| 2 | ATSA | 관점–감성 매핑 | aspect_sentiments |
| 3 | Validator S1 | 구조적 위험 검출 | structural_risks, correction_proposals |
| 4 | (C2) EpisodicOrchestrator | episodic retrieval | slot_dict |
| 5 | (debate) EPM, TAN, CJ | 토론·합의 | proposed_edits, final_patch |
| 6 | ATE S2 | 리뷰만 | aspect_review |
| 7 | ATSA S2 | 리뷰만 | sentiment_review |
| 8 | Validator S2 | 재검증 | structural_risks |
| 9 | Moderator | 최종 결정 | final_label, final_aspects |

- **Validator 있음** (S1/S2)
- **Debate 선택적** (enable_debate)
- **Episodic Memory (C2)** 선택적
- **Override Gate** (debate_override) 선택적

---

## 2. 데이터 플로우 비교

### 2.1 Conflict Review v1

```
입력: text, demos, language_code, domain_id

Stage1 (3개 병렬 개념, 순차 실행):
  P-NEG(text) → PerspectiveASTEStage1Schema { triplets }
  P-IMP(text) → PerspectiveASTEStage1Schema { triplets }
  P-LIT(text) → PerspectiveASTEStage1Schema { triplets }

Merge:
  candidates = [ (t, f"t{i}", "A"/"B"/"C") for t in triplets ]
  conflict_flags = same aspect_term, different polarity

Review (순차):
  ReviewA(text, candidates, conflict_flags, []) → ReviewOutputSchema { review_actions }
  ReviewB(...) → review_actions
  ReviewC(...) → review_actions
  Arbiter(text, candidates, conflict_flags, [], actions_a, actions_b, actions_c) → review_actions

Apply:
  final_candidates = _apply_review_actions(candidates, arb.review_actions)
  → DROP/FLIP/MERGE/KEEP 적용

출력:
  stage1_tuples = [_tup(c) for c in candidates]
  final_tuples   = [_tup(c) for c in final_candidates]
  final_aspects = [{ aspect_term, polarity, evidence } for c in final_candidates ]
  label = aggregate(final_tuples polities)
```

**데이터 구조:**
- **candidates**: `{ tuple_id, aspect_term, aspect_ref, polarity, evidence, span, origin_agent }`
- **review_actions**: `{ action_type, target_tuple_ids, new_value, reason_code, actor }`
- **FinalOutputSchema**: meta, process_trace, analysis_flags, final_result (stage1_tuples, final_tuples, final_aspects)

---

### 2.2 Legacy

```
입력: text, demos, language_code, domain_id

Stage1 (순차):
  ATE(text) → AspectExtractionStage1Schema { aspects }
  ATSA(text, aspects) → AspectSentimentStage1Schema { aspect_sentiments }
  Validator(text) → StructuralValidatorStage1Schema { structural_risks, correction_proposals }

[C2] Memory:
  EpisodicOrchestrator.retrieve(...) → slot_dict
  should_inject_advisory_with_reason() → gate
  debate_context += slot_dict (조건부)

[Debate]:
  DebateOrchestrator.run(topic, context_json) → DebateOutput
  _build_debate_review_context() → debate_context_json (hint_entries, aspect_hints)

Stage2 (순차):
  ATE(text, stage1_ate, stage1_validator, debate_context) → aspect_review
  ATSA(text, stage1_atsa, stage1_validator, debate_context) → sentiment_review
  Validator(text, stage1_validator) → StructuralValidatorStage2Schema

Apply:
  _apply_stage2_reviews():
    1. Validator correction_proposals (FLIP_POLARITY, DROP_ASPECT, REVISE_SPAN)
    2. ATE aspect_review
    3. ATSA sentiment_review
    4. Debate override (enable_debate_override 시)

Adopt:
  _adopt_stage2_decision_with_ev() → adopt_stage2 (Stage1 vs Stage2 선택)

Moderator:
  Rule A–E, Z, M, C, D → final_label, confidence, rationale
  build_final_aspects(patched_stage2_atsa) → FinalResult.final_aspects
```

**데이터 구조:**
- **stage1_ate**: `{ aspects }`
- **stage1_atsa**: `{ aspect_sentiments }`
- **stage1_validator**: `{ structural_risks, correction_proposals }`
- **debate_output**: `{ rounds, summary }` (summary: final_patch, final_tuples, sentence_polarity)
- **stage2_ate/atsa**: review만 (aspects/aspect_sentiments 금지)
- **FinalOutputSchema**: meta, stage1_ate, stage1_atsa, stage1_validator, stage2_ate, stage2_atsa, stage2_validator, moderator, debate, process_trace, analysis_flags, final_result

---

## 3. 요약 비교표

| 항목 | Conflict Review v1 | Legacy |
|------|-------------------|--------|
| **Stage1 에이전트** | P-NEG, P-IMP, P-LIT (3개 관점) | ATE, ATSA, Validator |
| **Stage2** | 없음 (Review 계열로 대체) | ATE review, ATSA review, Validator S2 |
| **Validator** | 없음 | S1 + S2 |
| **Debate** | 없음 | EPM, TAN, CJ (선택) |
| **Episodic Memory** | 없음 | C2 시 retrieval + debate/Stage2 주입 |
| **Override Gate** | 없음 | debate_override 선택 |
| **Moderator** | 없음 (자동 집계) | Rule A–E, Z, M, C, D |
| **최종 결정** | Arbiter review_actions → _apply → final_tuples | Moderator(Stage1 vs Stage2) |
| **교정 방식** | DROP/FLIP/MERGE/KEEP (review_actions) | Validator proposals + ATE/ATSA review + Debate override |
| **LLM 호출 수** | 7 (고정) | 6~9+ (debate, memory 설정에 따라) |

---

## 4. Latency 영향

| 구분 | Conflict Review v1 | Legacy |
|------|-------------------|--------|
| **샘플당 LLM 호출** | 7회 | 6~9+ 회 |
| **Debate** | 0 | 1 (EPM+TAN+CJ) |
| **Memory retrieval** | 0 | C2 시 1 |
| **Validator** | 0 | 2 (S1+S2) |
| **평균 지연** | P-NEG/P-IMP/P-LIT + ReviewA/B/C + Arbiter 직렬 | ATE→ATSA→Val + (Debate) + Stage2 3개 + Moderator |

Conflict Review는 Debate·Memory·Validator가 없어 구조적으로 호출 회수가 적지만, Review 4개(ReviewA/B/C + Arbiter)가 추가되어 Legacy와 비슷한 수준의 latency가 발생할 수 있음.

---

## 5. Conflict Review v1: 데이터 플로우 → 메트릭 정합성

### 5.1 전체 데이터 플로우 (Conflict Review v1)

```
[데이터셋 CSV] → run_experiments
       ↓
runner.run() → protocol_mode == "conflict_review_v1" → run_conflict_review_v1()
       ↓
FinalOutputSchema {
  meta, process_trace, analysis_flags, final_result
  final_result: { stage1_tuples, stage2_tuples, final_tuples, final_aspects, label }
  stage1_ate: null, stage1_atsa: null, stage1_validator: null
  stage2_ate: null, stage2_atsa: null, stage2_validator: null
  moderator: null, debate: null
}
       ↓
payload = result.model_dump() → outputs.jsonl 1줄
       ↓
make_scorecard(payload) → scorecards.jsonl 1줄
       ↓
structural_error_aggregator (scorecards.jsonl)
       ↓
structural_metrics.csv / structural_metrics_table.md
       ↓
build_metric_report → metric_report.html
```

### 5.2 산출물 → scorecard 정합성

| 산출물 경로 | Conflict Review v1 | make_scorecard 사용 | aggregator 추출 |
|-------------|-------------------|---------------------|-----------------|
| **final_result.stage1_tuples** | ✅ 존재 (candidates → _tup) | stage_delta pairs_changed | `_extract_stage1_tuples` ✓ |
| **final_result.final_tuples** | ✅ 존재 (final_candidates → _tup) | stage_delta pairs_changed | `_extract_final_tuples` ✓ |
| **final_result.final_aspects** | ✅ 존재 | inputs.aspect_sentiments fallback | `_extract_final_tuples` fallback |
| **final_result.label** | ✅ 존재 (극성 집계) | - | final_label |
| **stage1_ate** | ❌ null | aspects 빈 배열 → ate_score | - |
| **stage1_atsa** | ❌ null | aspect_sentiments 빈 배열 | - |
| **stage1_validator** | ❌ null | validator 빈 배열 | - |
| **moderator** | ❌ null | stage_delta: selected_stage 불가 | - |
| **debate** | ❌ null | override_stats 없음 | - |

### 5.3 메트릭별 정합성 검토

| 메트릭 | 소스 | Conflict Review v1 | 정합성 |
|--------|------|-------------------|--------|
| **tuple_f1_s1** | final_result.stage1_tuples | ✅ stage1_tuples 존재 | ✓ 동작 |
| **tuple_f1_s2**, **delta_f1** | final_result.final_tuples | ✅ final_tuples 존재 | ✓ 동작 |
| **fix_rate**, **break_rate**, **net_gain** | gold vs stage1 vs final | stage1/final 모두 추출 가능 | ✓ 동작 |
| **changed_samples_rate** | stage_delta.changed | pairs_changed (s1_pairs ≠ final_pairs) | ✓ 동작 |
| **guided_change_rate** | stage_delta.change_type | correction_log/override 없음 → **항상 0** | ⚠️ 의미 다름 |
| **unguided_drift_rate** | stage_delta.change_type | pairs_changed 시 "unguided" | ⚠️ Review/Arbiter 교정도 unguided로 집계 |
| **stage_mismatch_rate** | moderator.selected_stage | moderator null → **0** | ✓ (Stage2 선택 개념 없음) |
| **validator_clear_rate** | validator structural_risks | validator 없음 → **1.0** | ✓ (리스크 0개) |
| **risk_resolution_rate** | validator S1/S2 | validator 없음 → **0** | ✓ |
| **negation_contrast_failure_rate** | validator risk_id | validator 없음 → **0** | ✓ |
| **debate_override_*** | meta.debate_override_stats | debate 없음 → **0** | ✓ |
| **aspect_hallucination_rate** | ate_debug filtered | stage1_ate null → aspects 빈 배열 | ⚠️ 0 또는 N/A (ATE 경로 미사용) |
| **implicit_grounding_rate** | ate/atsa 기반 | stage1_ate/atsa null | ⚠️ NO_ASPECT 트리거 가능 |
| **parse_generate_failure_rate** | runtime.flags | 정상 | ✓ 동작 |
| **N_pred_final_tuples** | final_tuples 사용 행 수 | final_tuples 사용 | ✓ 10/10 |

### 5.4 정합성 요약

| 구분 | 상태 | 비고 |
|------|------|------|
| **튜플 F1 계열** | ✓ | stage1_tuples, final_tuples 정상 추출 |
| **교정률 (fix/break/net_gain)** | ✓ | gold 있는 샘플에서 정상 |
| **changed_samples_rate** | ✓ | pairs 기반 변경 탐지 |
| **guided/unguided** | ⚠️ | Conflict Review 교정은 모두 "unguided"로 집계 (Legacy의 correction_log/override 미사용) |
| **Validator 계열** | ✓ | validator 없음 → 0/1.0 등 기대값 |
| **Debate/Override 계열** | ✓ | debate 없음 → 0 |
| **ATE/ATSA 품질** | ⚠️ | stage1_ate/atsa null → ate_debug/atsa_score 빈 동작 |

### 5.5 권장 사항

1. **guided_change 해석**: Conflict Review에서는 Review/Arbiter가 교정을 수행하므로, `guided_change_rate`가 0인 것은 "Legacy Validator/Override 기반 guided"가 없음을 의미할 뿐. `changed_samples_rate`로 교정 발생 여부를 보는 것이 적절함.
2. **ATE/ATSA 메트릭**: Conflict Review는 P-NEG/P-IMP/P-LIT → triplets 구조를 사용. `stage1_ate`/`stage1_atsa` fallback이 process_trace의 agent=ATE/ATSA를 찾지 못하므로, ate_debug/aspect_hallucination_rate 등은 Legacy 대비 의미가 다름. 필요 시 `process_trace`의 P-NEG/P-IMP/P-LIT output으로 별도 추출 로직 추가 검토.
