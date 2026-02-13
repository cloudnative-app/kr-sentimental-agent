# 파이프라인 구조: 에이전트 호출 순서 및 규칙

이 문서는 현재 ABSA 파이프라인의 에이전트 호출 순서, HF 분류기 참조 시점, Validator 의견 반영 방식, ATE/ATSA의 Validator 반영 여부, Moderator 최종 규칙을 정리합니다.

---

## 1. 에이전트 호출 및 작업 순서

**전제:** Stage2는 항상 실행됨 (`enable_stage2=True`).  
**추가:** `enable_debate_override`로 토론 기반 override on/off 가능 (기본 true).

### 1.1 Stage1 (독립 추론)

| 순서 | 에이전트 | 입력 | 출력 | 비고 |
|------|----------|------|------|------|
| 1 | **ATE** | text, demos, language_code, domain_id | AspectExtractionStage1Schema (aspects) | 후처리: topic particle 제거, contrast 규칙(최소 2 aspect) |
| 2 | **ATSA** | text, demos, … | AspectSentimentStage1Schema (aspect_sentiments) | ATE aspects에 맞춰 sentiment backfill |
| 3 | **Validator** | text, demos, … | StructuralValidatorStage1Schema (structural_risks, correction_proposals) | contrast 시 2차 aspect 주입 시 MISSING_SECOND_ASPECT risk 추가 |

- Validator가 비활성(`enable_validator=False`)이면 빈 StructuralValidatorStage1Schema가 trace에만 기록됨.
- Stage1 결과는 `stage1_outputs`(ate, atsa, validator)로 보관되며, Stage2 입력으로 사용됨.

### 1.2 토론 (Debate: EPM → TAN → CJ 패치)

- **위치:** Stage1 이후, Stage2 이전  
- **구성:** EPM(Evidence–Polarity Mapper), TAN(Target–Aspect Normalizer), CJ(Consistency Judge) 3명. **패치(proposed_edits)만 출력**, pro/con 대결 없음.  
- **산출물:** `DebateOutput` (rounds, summary). summary: `final_patch`, `final_tuples`, `sentence_polarity`, `sentence_evidence_spans` 등.  
- **목적:** EPM/TAN이 proposed_edits로 수정 제안, CJ가 final_patch/final_tuples로 일관된 aspect–polarity 집합을 만들어 **Stage2 리뷰의 추가 컨텍스트**로 사용

### 1.3 Stage2 (재분석: Validator 피드백 반영)

| 순서 | 에이전트 | 입력 | 출력 | 비고 |
|------|----------|------|------|------|
| 1 | **ATE** | text, **stage1_ate**, **stage1_validator**, demos, … | AspectExtractionStage2Schema (aspect_review) | Stage1 결과 + Validator JSON을 프롬프트에 포함. **aspects 금지**(review만) |
| 2 | **ATSA** | text, **stage1_atsa**, **stage1_validator**, demos, … | AspectSentimentStage2Schema (sentiment_review) | 동일하게 Validator 참조. **aspect_sentiments 금지**(review만) |
| 3 | **Validator** | text, stage1_validator, … | StructuralValidatorStage2Schema | Stage2 재검증 |

- Stage2 ATE/ATSA는 **Validator의 structural_risks와 correction_proposals를 프롬프트로 전달받아** 재분석만 수행하며, 전체 목록을 새로 생성하지 않음(`_enforce_stage2_review_only`로 aspects / aspect_sentiments 출력 금지).
- **Debate review context(JSON)** 가 Stage2 프롬프트에 추가로 주입되어, **토론 proposed_edits/final_patch를 review 항목에 매핑**하도록 유도합니다.  
  - Stage1 ATE/ATSA의 aspect_terms를 기준으로 **정규화 매핑**(공백/구두점 제거)을 수행해 aspect_refs를 제공합니다.  
  - **동의어 힌트(synonym_hints)** 를 사용해 매칭 후보를 확장합니다 (`resources/patterns/ko.json`).  
  - **proposed_edits**가 있으면 op·target·value에서 aspect_ref/aspect_term, polarity를 추출해 aspect_hints를 구성합니다.  
  - proposed_edits가 없으면 legacy: message/key_points + speaker stance 기반 fallback.  
  - Stage2 적용 시 **review reason/evidence에 provenance_hint가 자동 삽입**됩니다 (LLM 의존 없음).  
  - review 항목에 `provenance` 필드가 존재하며, 토론 출처가 구조적으로 분리됩니다.
  - scorecard에는 `debate.mapping_stats` / `debate.mapping_coverage`가 기록됩니다.
  - quality_report / structural_error_aggregator 에서 debate 매핑 지표가 집계됩니다.
  - 매핑 실패 원인(`mapping_fail_reasons`: no_aspects/no_match/neutral_stance/fallback_used)이 scorecard 및 리포트에 기록됩니다.
  - 경고 임계값은 `experiments/configs/debate_thresholds.json`에서 조정합니다.
  - Debate override 임계값은 `experiments/configs/debate_override_thresholds.json`에서 조정하며, 적용/스킵 카운트가 리포트에 기록됩니다.

### 1.4 Stage2 결과 적용 (Supervisor 내부)

- **`_apply_stage2_reviews`** 가 다음 순서로 Stage1 결과에 패치를 적용합니다.
  1. **Validator correction_proposals (Stage1)**  
     FLIP_POLARITY / DROP_ASPECT / REVISE_SPAN을 순서대로 적용.  
     적용 여부·사유는 `correction_applied_log`에 기록 (`applied`, `reason`).
  2. **ATE aspect_review**  
     revise_span, drop, add 등으로 aspects/sentiments 수정.
  3. **ATSA sentiment_review**  
     maintain, flip_polarity, drop, add 등으로 sentiment만 수정.
  4. **Debate override (강한 논점 기반 보정)**  
     토론 힌트가 충분히 강하고 일치하는 경우(가중치 합 & 편차 기준) polarity를 강제로 보정.  
     `DEBATE_OVERRIDE`로 `correction_applied_log`에 기록.
     - `enable_debate_override=false`이면 이 단계는 스킵됨.

- 결과물: `patched_stage2_ate`, `patched_stage2_atsa`, `correction_applied_log`.

### 1.5 Moderator (최종 결정)

- **입력:**  
  - Stage1/Stage2 **집계 레이블** (agg_stage1_ate, agg_stage2_ate: sentiments에서 추출한 ATEOutput)  
  - Stage1/Stage2 validator **ValidatorOutput** (issues, confidence 등 집계용)  
  - `final_aspect_sentiments` = patched_stage2_atsa의 aspect_sentiments 중 patched_stage2_ate에 있는 aspect만

- **역할:** Rule A–D, Rule M, Rule Z + **Rule E(토론 합의 힌트)** 에 따라 최종 레이블·신뢰도·rationale 결정.  
- **출력:** ModeratorOutput (final_label, confidence, rationale, applied_rules, arbiter_flags).  
- `build_final_aspects(final_aspect_sentiments)`로 `FinalResult.final_aspects` 생성.

---

## 2. HF(Human Feedback) 분류기 참조 시점

- **사용처:** 에이전트 결정에는 **전혀 사용되지 않음**.  
- **참조 시점:**  
  - `experiments/scripts/run_experiments.py`에서 각 예시에 대해 `runner.run(normalized)` **이후**,  
  - `aux_hf_enabled` 및 `aux_hf_checkpoint`가 설정되어 있으면 `build_hf_signal(text, checkpoint, id2label, stage1_final, stage2_final)` 호출.  
- **결과:** `payload["aux_signals"]["hf"]`에만 기록되며, scorecard의 `aux_signals.hf`로 전달.  
- **용도:** 메트릭 전용 (hf_polarity_disagreement_rate, hf_disagreement_coverage_of_structural_risks 등).  
- 구현: `tools/aux_hf_runner.py` (HuggingFace 체크포인트 또는 zero-shot; `llm:` 접두사는 사용하지 않음).

---

## 3. Validator 의견이 어떻게 작동하는지

- **Stage1 Validator:**  
  - 텍스트만 보고 structural_risks와 correction_proposals를 출력.  
  - ATE/ATSA Stage1에는 **반영되지 않음** (Stage1은 독립 추론).

- **Stage2 ATE/ATSA:**  
  - **프롬프트에** Stage1 결과와 함께 **Validator의 JSON(structural_risks, correction_proposals)** 이 포함됨.  
  - 따라서 모델은 “Validator가 지적한 위험/제안”을 **참고하여** aspect_review / sentiment_review만 출력.

- **실제 반영(코드):**  
  - **Validator 제안**은 Supervisor의 `_apply_stage2_reviews`에서 **코드로** 적용됨.  
  - FLIP_POLARITY → 해당 aspect_ref sentiment 반전  
  - DROP_ASPECT → 해당 aspect·sentiment 제거  
  - REVISE_SPAN → 해당 aspect의 span 교체  
  - 적용 성공 시 `correction_applied_log[i].applied = True`, 실패 시 `False`와 `reason` 기록 (예: target_aspect 불일치).

- **Stage2 Validator:**  
  - Stage2 재분석 후 다시 structural_risks를 출력.  
  - 이 출력은 **메트릭(risk_resolution_rate, residual risk 등)** 에만 사용되고, Moderator 결정에는 **집계된 ValidatorOutput(issues, confidence)** 형태로만 전달됨.

---

## 4. ATE·ATSA가 Validator 의견을 참조한 것이 반영되는지

- **참조:**  
  - Stage2 ATE/ATSA는 **입력(프롬프트)** 으로 Validator 결과를 받으므로, **의견을 “참조”한 출력**(aspect_review, sentiment_review)을 낸다.

- **반영:**  
  - **Validator 제안** → `_apply_stage2_reviews`에서 **먼저** 적용 (correction_applied_log 기록).  
  - **ATE/ATSA의 review** → 같은 함수에서 그 다음에 적용 (revise_span, drop, add, flip_polarity 등).  
  - 따라서 Validator 제안이 적용되면 `correction_applied_log[].applied`가 True가 되고,  
    Stage2 ATE/ATSA의 review도 순서대로 반영되어 최종 `patched_stage2_ate` / `patched_stage2_atsa`와 `final_aspect_sentiments`가 만들어진다.  
  - 이 **patched 결과**가 Moderator의 `final_aspect_sentiments`와 집계 레이블(stage2_ate/atsa)에 사용되므로, **반영된다**.

- **정리:**  
  - Validator 의견은 (1) Stage2 프롬프트로 ATE/ATSA가 참조하고, (2) Validator proposal은 코드로 먼저 적용되며, (3) ATE/ATSA review가 그 위에 적용되어 최종 출력에 반영된다.

---

## 5. Moderator가 가지는 최종 규칙

Moderator는 **Rule 기반(LLM 없음)**. `agents/specialized_agents/moderator.py` 기준.

| 규칙 | 내용 |
|------|------|
| **Rule Z** | stage1_ate.confidence == 0 && stage2_ate.confidence == 0 → final_label="neutral", confidence=0. |
| **Rule B** | Stage2 선호. 단, stage1_ate.confidence - stage2_ate.confidence ≥ 0.2 이면 Stage2 거부(drop_guard), Stage1 유지. |
| **Rule M** | stage1_ate.label ≠ stage2_ate.label 이면 **conflict** → final_label="mixed", confidence=max(두 신뢰도). |
| **Rule C** | Validator veto: validator.suggested_label이 있고, (critical risk 또는 validator.confidence ≥ current_conf) 이면 validator 제안으로 덮음. |
| **Rule A** | Span alignment: candidate_atsa와 stage1_atsa의 span IoU ≥ 0.8이고 레이블 일치 시 confidence 보정. (drop_guard일 때는 스킵) |
| **Rule D** | Confidence tie-break: ate vs atsa 레이블이 다를 때 diff&lt;0.1이면 sentence ATE 우선, 아니면 confidence 큰 쪽 우선. |
| **Rule E** | 토론 합의 힌트: debate_summary에서 레이블 추론. **우선순위:** (1) sentence_polarity (2) final_tuples 극성 집계 (3) consensus/rationale/key_* 텍스트. 추론값이 있고 현재 final_label과 다르며 (confidence &lt; 0.55 또는 final_label=="mixed") 이면 토론 쪽으로 덮음. block 시: label_unchanged, confidence_too_high, inferred_empty. |

- **최종 출력:** final_label, confidence, rationale, applied_rules, arbiter_flags.  
- **ArbiterFlags:** stage2_rejected_due_to_confidence(drop_guard), validator_override_applied, confidence_margin_used, **rule_e_fired**, **rule_e_block_reason**, **rule_b_applied**, **rule_e_attempted_after_b**.  
- **final_aspects:** Moderator는 `build_final_aspects(final_aspect_sentiments)`로 patched_stage2_atsa의 aspect_sentiments를 그대로 리스트로 변환해 FinalResult에 넣음.

---

## 6. 메트릭과의 관계 (요약)

- **risk_resolution_rate:** `(stage1_risks - stage2_risks) / stage1_risks`.  
  - “위험 개수 감소” 기준. **실제로 수정이 적용되었는지(change applied)와는 별개**일 수 있음.
- **guided_change_rate:** `stage_delta.change_type == "guided"` 인 케이스 비율.  
  - `change_type`은 `scripts/scorecard_from_smoke.py`의 `_build_stage_delta`에서,  
  - `changed` = analysis_flags.correction_occurred 또는 stage1_label ≠ stage2_label,  
  - **guided** = `correction_applied_log` 중 **최소 하나 applied==True**.  
  - 따라서 Validator proposal이 한 번도 적용되지 않으면 guided는 항상 False → guided_change_rate=0 가능.
- **ignored_proposal_rate:** Stage1에서 risk_flagged인데 stage_delta.changed가 False인 비율.  
  - “제안이 있었지만 변경이 일어나지 않은” 비율.  
  - 무시 사유(불가능/모호/충돌/수정했으나 효과 없음)는 현재 구분하지 않음.

이 구조를 전제로 한 “guided_change 0 원인” 및 “개선 작업명세서”는 `docs/work_spec_guided_change_ignored_s2_hallucination.md`를 참고하면 됩니다.
