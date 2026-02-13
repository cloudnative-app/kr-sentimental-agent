# Debate Override 규칙 정리

Debate override는 **Stage2 리뷰 후** 토론(CJ/EPM/TAN) 힌트를 이용해 aspect–polarity를 보정하는 게이트·적용 규칙입니다.  
구현: `agents/supervisor_agent.py`, 설정: `pipeline.debate_override` 또는 `experiments/configs/debate_override_thresholds.json`.

---

## 1. 개요

- **위치**: Stage2 ATE/ATSA/Validator 리뷰 적용 직후, **Moderator 취합 전**.
- **활성화**: `enable_debate_override: true`(기본)일 때만 실행.
- **입력**: `debate_review_context`(aspect_hints, summary), Stage1 Validator structural_risks, 입력 문장.
- **산출**: polarity·confidence 보정, `_override_stats`, `override_gate_debug.jsonl` / `override_gate_debug_summary.json`.

---

## 2. 설정(파라미터)

| 파라미터 | 의미 | 기본값 | 출처 |
|----------|------|--------|------|
| **min_total** | pos_score + neg_score 최소 (총 신호) | 1.6 | debate_override_cfg |
| **min_margin** | \|pos_score − neg_score\| 최소 (극성 차이) | 0.8 | debate_override_cfg |
| **min_target_conf** | override 적용 시 부여/상한 confidence | 0.7 | debate_override_cfg |
| **ev_threshold** | EV 점수 하한 — 이하면 adopt 불가 | 0.5 | debate_override_cfg |
| **l3_conservative** | L3 리스크 있으면 override 적용 안 함 | true (JSON) / 실험 YAML에서 오버라이드 가능 | debate_override_cfg |

- **설정 경로**: 실험 YAML의 `pipeline.debate_override`가 있으면 사용, 없으면 `experiments/configs/debate_override_thresholds.json` 로드.

---

## 3. Gate 판정 순서 (aspect별)

각 **aspect**에 대해 아래 순서로 판정. 한 번이라도 해당되면 **SKIP**하고 다음 aspect로.

| 순서 | 조건 | skip_reason | 비고 |
|------|------|-------------|------|
| 1 | 이 샘플에서 이미 override 1건 적용됨 | **max_one_override_per_sample** | 샘플당 최대 1개 aspect만 override |
| 2 | valid_hint_count == 0 (극성 힌트가 모두 neutral/없음) | **neutral_only** | skipped_neutral_only + skipped_low_signal |
| 3 | evidence_span 없음 | **no_evidence_span** | |
| 4 | evidence_span이 입력 문장에 없음 | **evidence_span_not_in_text** | |
| 5 | evidence_span 길이 < 2 | **evidence_span_missing_trigger** | |
| 6 | total < min_total | **low_signal** | |
| 7 | margin < min_margin | **action_ambiguity** | skipped_conflict + action_ambiguity |
| 8 | L3 리스크 있음 (l3_conservative=true) | **l3_conservative** | skipped_conflict + L3_conservative |
| 9 | 해당 aspect가 모두 implicit | **implicit_soft_only** | skipped_conflict + implicit_soft_only |
| 10 | (통과 시) matching sentiment 없음 → **새 tuple 추가** | — | APPLY, debate_override_add |
| 11 | (통과 시) 이미 confidence ≥ min_target_conf 이고 polarity 일치 | **already_confident** | skipped_already_confident |
| 12 | (통과 시) 그 외 → **polarity/confidence 보정** | — | APPLY, debate_override_flip |

- **L3 리스크**: Stage1 Validator의 structural_risks 중 type이  
  `NEGATION_SCOPE`, `CONTRAST_SCOPE`, `POLARITY_MISMATCH`, `NEGATION`, `CONTRAST`, `IRONY` 중 하나.
- **evidence**: `debate_review_context.summary.aspect_evidence[aspect]` 또는 `sentence_evidence_spans[0]`.  
  `has_actionable_evidence(text, evidence_span)`으로 비어있음/문장 내 포함/길이≥2 검사.

---

## 4. Polarity canonicalization (힌트)

- **정책**: strict canonical만 허용. `positive`/`negative`/`neutral`, `pos`/`neg`/`neu` 외는 **invalid** → 힌트 제외, `invalid_hint_count` 증가.  
  상세: `docs/polarity_canonicalization_policy.md`.
- **valid_hint_count**: canonicalize 후 `polarity_hint in ("positive", "negative")` 인 힌트 개수.
- **pos_score**: `polarity_hint == "positive"` 인 힌트의 weight 합.
- **neg_score**: `polarity_hint == "negative"` 인 힌트의 weight 합.
- **total** = pos_score + neg_score.
- **margin** = |pos_score − neg_score|.
- **target_pol** = total·margin 통과 시: pos_score > neg_score → "positive", else "negative".

힌트는 `aspect_hints[aspect]`에서 옴. weight는 proposed_edits 기반(confirm_tuple/set_polarity 0.5, drop_tuple 0.8, CJ patch 0.8 등).

---

## 5. Adopt(Stage2 채택) + EV 게이트

Override 적용 여부와 별도로, **최종 출력을 Stage2로 채택할지**는 `_adopt_stage2_decision_with_ev`로 결정.

- **1단계** `_adopt_stage2_decision`:  
  Stage2 없음 → not adopted (low_signal).  
  Validator structural risk를 Stage2가 해소 → adopted.  
  그 외 규칙으로 adopt 여부·override_candidate 결정.
- **2단계** EV 게이트:  
  `ev_score = compute_ev_score(...)` (debate_support, validator_resolved, grounding_improvement, alignment_improvement 조합, 0..1).  
  **adopt==True 이지만 ev_score < ev_threshold** 이면 → adopt 취소, **reason = "ev_below_threshold"**.

즉, override가 gate를 통과해 APPLY여도, EV 점수가 ev_threshold 미만이면 **최종 adopt는 not_adopted**가 되고, 메타에는 `adopt_reason: "ev_below_threshold"` 등이 들어감.

---

## 6. 메타·집계 필드

- **gate_decision**: "APPLY" | "SKIP" (해당 샘플에서 한 번이라도 APPLY면 APPLY).
- **adopt_decision**: "adopted" | "not_adopted".
- **adopt_reason**: ev_below_threshold, low_signal, neutral_only, l3_conservative, action_ambiguity, no_evidence_span 등.
- **override_skipped_reason** / **override_evidence_gate_reason**: SKIP일 때 대표 skip 사유.
- **debate_override_stats**: applied, skipped_low_signal, skipped_neutral_only, skipped_conflict, skipped_already_confident, skipped_max_one_override_per_sample, skipped_no_evidence_span, skipped_evidence_span_*, ev_score, ev_adopted, ev_components 등.
- **debate_override_skip_reasons**: action_ambiguity, L3_conservative, implicit_soft_only, low_confidence, contradictory_memory 등 conflict 세부.

---

## 7. 무결성 검증(S3)과의 대응

`pipeline_integrity_verification`의 **S3**:

- **조건**: debate_summary.final_tuples ≠ final_result.final_tuples (debate_final_mismatch).
- **기대**: 이때는 반드시 **adopt_decision == not_adopted** 이고, **adopt_reason**이 허용 목록에 있어야 함.

**adopt_reason → ev_reason (검증용 정규화)**:

| adopt_reason (raw) | ev_reason (canon) |
|--------------------|-------------------|
| ev_below_threshold, low_signal, max_one_override_per_sample | low_ev |
| l3_conservative, conflict_blocked, action_ambiguity, implicit_soft_only | conflict |
| no_evidence_span, evidence_span_not_in_text, evidence_span_missing_trigger | no_evidence |
| contradictory_memory | memory_contradiction |

허용 ev_reason 집합: `{low_ev, conflict, no_evidence, memory_contradiction}`.

---

## 8. 요약 표

| 구분 | 내용 |
|------|------|
| **설정** | min_total, min_margin, min_target_conf, ev_threshold, l3_conservative |
| **Gate SKIP** | max_one_per_sample, neutral_only, evidence 3종, low_signal, action_ambiguity, l3_conservative, implicit_soft_only, already_confident |
| **Gate APPLY** | 새 tuple 추가 또는 polarity/confidence 보정 (DEBATE_OVERRIDE) |
| **Adopt** | _adopt_stage2_decision + ev_score ≥ ev_threshold |
| **산출** | override_gate_debug.jsonl, override_gate_debug_summary.json, meta debate_override_* |

이 문서는 `agents/supervisor_agent.py`, `scripts/pipeline_integrity_verification.py`, `docs/debate_protocol.md`, `experiments/configs/debate_override_thresholds.json` 기준으로 정리했습니다.
