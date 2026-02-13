# 토론(Debate) 프로토콜 정리

로컬 레포의 **Debate 레이어**가 어떻게 동작하는지, 파이프라인 내 위치·구성·산출물·설정·메트릭을 한 문서로 정리합니다.  
**최신 상태:** EPM → TAN → CJ 패치 기반(proposed_edits), pro/con 대결 없음.

---

## 1. 개요

- **목적:** Stage1 결과(ATE/ATSA/Validator)를 바탕으로 **EPM·TAN·CJ**가 **패치(proposed_edits)** 형태로 수정 제안을 하고, **CJ**가 **final_patch / final_tuples**로 일관된 aspect–polarity 집합을 만든다. 그 결과를 **Stage2 리뷰의 추가 컨텍스트**로 사용한다.
- **위치:** Stage1 **이후**, Stage2 **이전**.
- **활성화:** `enable_debate: true`(기본)일 때만 실행. `enable_debate_override`로 토론 기반 polarity override on/off 가능(기본 true).

---

## 2. 프로토콜 구성

### 2.1 발언자(페르소나) 3명: EPM, TAN, CJ

토론 단계에서 **발언자 3명**에게 `DebatePersona`가 부여된다. `DebateOrchestrator`가 `self.personas`를 읽어 각 발언 시 시스템 프롬프트에 `[PERSONA]\n{persona.model_dump_json()}` 형태로 주입한다.

| 페르소나(키) | 이름 | 역할 | 목표 |
|-------------|------|------|------|
| **epm** | EPM | Evidence–Polarity Mapper | 극성이 문장 내 증거로 뒷받침되는지 판단 |
| **tan** | TAN | Target–Aspect Normalizer | null/중복/정렬 오류 aspect 정리 |
| **cj** | CJ | Consistency Judge | aspect당 단일 극성, 증거 없는 판단 제거, 과편집 방지 |

- **stance / style:** deprecated(미사용). pro/con 대결이 아닌 **패치만 출력**.
- **설정 오버라이드:** config `debate.personas`, `debate.order`.
- **기본 발언 순서:** `order = ["epm", "tan", "cj"]`.
- **라운드 수:** `debate.rounds` (기본 **1**). conditions YAML의 `max_rounds`는 메타 정보이며, 실제 라운드 수는 `config.get("rounds", 1)`로 읽음.

### 2.2 발언 형식: proposed_edits(패치만)

각 발언자는 **proposed_edits** 리스트만 출력한다. Planning/Reflection/메시지는 선택(legacy 필드).

- **프롬프트:** `agents/prompts/debate_speaker.md`
- **스키마:** `DebateTurn`  
  - **주요:** `agent`, `proposed_edits` (List[ProposedEdit])  
  - **legacy:** `speaker`, `stance`, `planning`, `reflection`, `message`, `key_points`

**ProposedEdit:** `op`, `target`, `value`?, `evidence`?, `confidence`?

- **op:** `set_polarity` | `set_aspect_ref` | `merge_tuples` | `drop_tuple` | `confirm_tuple`
- **target:** 반드시 `aspect_ref`(Stage1 aspect term, 매핑용). 선택 `aspect_term`, `polarity`.

### 2.3 심판(Judge): CJ

모든 라운드 종료 후 **CJ(Consistency Judge)** 에이전트가 EPM/TAN의 proposed_edits를 취합해 **final_patch**, **final_tuples**, **sentence_polarity** 등을 출력한다.

- **프롬프트:** `agents/prompts/debate_judge.md`
- **스키마:** `DebateSummary`  
  - **주요:** `final_patch`, `final_tuples`, `unresolved_conflicts`, `sentence_polarity`, `sentence_evidence_spans`, `aspect_evidence`?  
  - **deprecated:** `winner`, `consensus`, `key_agreements`, `key_disagreements` (Rule E fallback에서만 텍스트 추론용)

---

## 3. 실행 흐름 (DebateOrchestrator)

1. **context_json 생성:** Supervisor가 `_build_debate_context`로 Stage1 결과(ate, atsa, validator) 및 (C2 시) DEBATE_CONTEXT__MEMORY 슬롯을 JSON으로 넘긴다.
2. **라운드별 발언:**  
   - `rounds`만큼 반복(기본 1).  
   - 매 라운드마다 `order` 순서대로 각 페르소나가 한 번씩 발언.  
   - 시스템 프롬프트: `debate_speaker` + `[TOPIC]` + `[PERSONA]` + `[SHARED_CONTEXT_JSON]` + `[HISTORY]`.  
   - LLM → `DebateTurn` 파싱(agent, proposed_edits). HISTORY는 `agent: op target=... value=... evidence=...` 형식.
3. **Judge 호출:** `debate_judge` 프롬프트 + `[ALL_TURNS]`로 `DebateSummary` 생성 (final_patch, final_tuples, sentence_polarity, sentence_evidence_spans 등).
4. **산출물:** `DebateOutput` (topic, personas, rounds, summary).

---

## 4. Stage2로의 전달: Debate Review Context

Supervisor의 `_build_debate_review_context`가 토론 결과를 Stage2 ATE/ATSA가 사용할 **Debate Review Context(JSON)** 로 만든다.

- **입력:** `debate_output.rounds`(각 턴의 proposed_edits), `debate_output.summary`(final_patch, final_tuples).
- **포함 내용:**  
  - `summary` (DebateSummary model_dump)  
  - `rebuttal_points` (speaker, stance, key_points, message, proposed_edits, aspect_terms, weight, polarity_hint, provenance_hint 등)  
  - `aspect_terms`, `synonym_hints`  
  - `aspect_hints` (aspect별 speaker/stance/weight/polarity_hint 리스트) — **proposed_edits의 op별로 생성**(set_polarity, confirm_tuple, drop_tuple 등)  
  - `mapping_stats`, `mapping_fail_reasons`, `review_guidance`, `fallback_mapping_policy`

- **aspect 매핑:**  
  - Stage1 ATE/ATSA의 aspect_terms를 기준으로 **정규화 매칭**(공백·구두점 제거).  
  - **동의어 확장** (`resources/patterns/ko.json`, `_expand_synonyms`).  
  - **proposed_edits**가 있으면 op·target·value에서 aspect_ref/aspect_term, polarity 추출해 hint_entries 구성.  
  - proposed_edits가 없으면 legacy: message/key_points + speaker stance 기반 fallback.

- **Stance → 가중치/극성 (legacy 턴용):**  
  - `_stance_weight`: neutral=0.6, pro/con=1.0, 그 외=0.8  
  - `_stance_to_polarity`: pro→positive, con→negative, 그 외→neutral  

- **매핑 실패 원인:** `mapping_fail_reasons` (no_aspects, no_match, neutral_stance, fallback_used)가 scorecard·리포트에 기록된다.

---

## 5. Stage2 적용 순서와 Debate Override

`_apply_stage2_reviews` 내에서:

1. Validator correction_proposals (FLIP_POLARITY, DROP_ASPECT, REVISE_SPAN)  
2. ATE aspect_review (revise_span, drop, add)  
3. ATSA sentiment_review (maintain, flip_polarity, drop, add)  
4. **Debate override** (토론 힌트 기반 polarity 보정) — `enable_debate_override=true`일 때만

### 5.1 Debate Override 조건

- **설정 파일:** `experiments/configs/debate_override_thresholds.json`  
  - `min_total`: 1.6 (총 신호 최소)  
  - `min_margin`: 0.8 (양쪽 차이 최소)  
  - `min_target_conf`: 0.7 (목표 confidence)

- **로직 요약:**  
  - `aspect_hints`에서 aspect별 pos_score / neg_score 계산.  
  - `total < min_total` → skipped_low_signal  
  - `|pos - neg| < min_margin` → skipped_conflict  
  - 해당 aspect에 sentiment가 없으면 새로 추가하고 applied.  
  - 이미 `confidence >= min_target_conf`이고 polarity가 일치하면 skipped_already_confident.  
  - 그 외에는 polarity를 토론 쪽으로 보정하고 correction_applied_log에 `DEBATE_OVERRIDE` 기록.

- **집계:** `_override_stats` (applied, skipped_low_signal, skipped_conflict, skipped_already_confident)가 메타·리포트에 기록된다.

---

## 6. Moderator 취합규칙

Moderator는 **규칙 기반(LLM 미사용)** 으로 Stage1/Stage2 ATE·ATSA, Validator, (선택) 토론 요약을 취합해 **최종 문장 레이블·신뢰도·rationale**을 결정한다.  
구현: `agents/specialized_agents/moderator.py`.

### 6.1 입력

| 입력 | 설명 |
|------|------|
| `stage1_ate` | Stage1 ATE 집계 결과 (label, confidence) |
| `stage1_atsa` | Stage1 ATSA 집계 결과 (label, confidence, span 등) |
| `stage2_ate` | Stage2 ATE 집계 결과 (없을 수 있음) |
| `stage2_atsa` | Stage2 ATSA 집계 결과 |
| `validator` | Validator 집계 (issues, suggested_label, confidence) |
| `final_aspect_sentiments` | patched Stage2 ATSA의 aspect_sentiments (final_aspects 생성용) |
| `debate_summary` | 토론 CJ 요약 (Rule E용, 선택) |

### 6.2 적용 순서

규칙은 아래 **적용 순서**대로 평가하며, 앞선 규칙에서 정해진 `final_label`/`confidence`가 뒤 규칙의 입력이 된다.

1. **Rule Z** — 신호 부족 시 즉시 종료  
2. **Rule B** — Stage2 선호 여부 및 drop_guard 결정  
3. **Rule M** — Stage1 vs Stage2 레이블 충돌 시 mixed  
4. **Rule C** — Validator veto  
5. **Rule A** — Span 정렬 보정 (drop_guard가 아닐 때만)  
6. **Rule D** — ATE vs ATSA 신뢰도 타이브레이크  
7. **Rule E** — 토론 합의 힌트 (저신뢰/혼합 시 override). **추론 우선순위:** `sentence_polarity` → `final_tuples` → consensus/rationale/key_* 텍스트

### 6.3 규칙별 설명

| 규칙 | 내용 | 조건·동작 |
|------|------|-----------|
| **Rule Z** | 신호 부족 | `stage1_ate.confidence == 0` **그리고** `stage2_ate.confidence == 0` 이면 즉시 **final_label="neutral", confidence=0**, rationale "RuleZ: insufficient signal (both confidences 0)." 반환. 이후 규칙 미적용. |
| **Rule B** | Stage2 선호 | Stage2 없으면 Stage1 유지. Stage2가 있으면 **Stage2 선호**. 단, **stage1_ate.confidence - stage2_ate.confidence ≥ 0.2** 이면 **drop_guard=True**, Stage1 유지(Stage2 거부). Rationale: "RuleB: Stage2 drop>=0.2; keep Stage1." / "RuleB: Stage2 preferred." |
| **Rule M** | Stage1↔Stage2 충돌 | Stage2가 있고 **stage1_ate.label ≠ stage2_ate.label** 이면 **final_label="mixed"**, confidence=max(stage1, stage2). Rationale: "RuleM: conflicting stage1/stage2 labels -> mixed." |
| **Rule C** | Validator veto | `validator.suggested_label`이 있고, **(critical risk** 또는 **validator.confidence ≥ current_conf)** 이면 final_label을 validator 제안으로 덮고 confidence 상향. Critical: issues 중 negation/irony/contrast 또는 severity:high. Rationale: "RuleC: Validator critical veto." |
| **Rule A** | Span 정렬 보정 | **drop_guard가 False일 때만** 적용. candidate_atsa와 stage1_atsa의 **span IoU ≥ 0.8** 이고 **candidate_atsa.label == final_label** 이면 confidence를 두 신뢰도의 평균으로 보정. Rationale: "RuleA: IoU>=0.8 span aligned." |
| **Rule D** | 신뢰도 타이브레이크 | 현재 final_label(ATE 쪽)과 candidate_atsa.label(ATSA 쪽)이 다를 때: **|ate_conf - atsa_conf| < 0.1** 이면 문장 ATE 우선(ATE 레이블·신뢰도 유지); 그렇지 않으면 **신뢰도 큰 쪽**의 레이블·신뢰도로 결정. Rationale: "RuleD: diff<0.1 conflict -> sentence ATE." / "RuleD: diff>=0.1 ATSA wins." / "RuleD: diff>=0.1 ATE wins." |
| **Rule E** | 토론 합의 힌트 | `debate_summary`에서 `_infer_label_from_debate`로 레이블 추론. **우선순위:** (1) `sentence_polarity` (2) `final_tuples` 극성 집계 (3) consensus/rationale/key_agreements/key_disagreements 텍스트 키워드. **추론값이 있고** **현재 final_label과 다르며**, **(confidence < 0.55 또는 final_label == "mixed")** 이면 final_label을 토론 쪽으로 덮음. block 시: label_unchanged, confidence_too_high, inferred_empty. Rationale: "RuleE: debate consensus -> {inferred}." |

### 6.4 출력

- **ModeratorOutput:** `final_label`, `confidence`, `rationale`(또는 `decision_reason`), `selected_stage`(stage1/stage2), `applied_rules`, `arbiter_flags`.
- **ArbiterFlags:** `stage2_rejected_due_to_confidence`(drop_guard), `validator_override_applied`, `confidence_margin_used`, **`rule_e_fired`**, **`rule_e_block_reason`**, **`rule_b_applied`**, **`rule_e_attempted_after_b`**.
- **final_aspects:** `build_final_aspects(final_aspect_sentiments)`로 patched Stage2 ATSA의 aspect_sentiments를 리스트로 변환해 FinalResult에 넣음.

---

## 7. 스키마·파일 위치

| 구분        | 파일/위치 |
|------------|-----------|
| 오케스트레이터 | `agents/debate_orchestrator.py` |
| 발언 프롬프트 | `agents/prompts/debate_speaker.md` |
| 심판 프롬프트 | `agents/prompts/debate_judge.md` |
| 스키마      | `schemas/agent_outputs.py`: `ProposedEdit`, `DebatePersona`, `DebateTurn`, `DebateRound`, `DebateSummary`, `DebateOutput` |
| 최종 결과   | `FinalOutputSchema.debate` (DebateOutput) |

---

## 8. 설정 요약

| 설정 | 의미 | 기본 |
|------|------|------|
| `enable_debate` | 토론 단계 실행 여부 | true |
| `enable_debate_override` | Debate override(4단계) 적용 여부 | true |
| `debate.rounds` | 라운드 수 | **1** |
| `debate.order` | 발언 순서 | **["epm", "tan", "cj"]** |
| `debate.personas` | 페르소나 오버라이드 | 기본 3종(epm, tan, cj) |
| `debate_override` (또는 `debate_override_thresholds.json`) | min_total, min_margin, min_target_conf | 1.6, 0.8, 0.7 |

- **conditions YAML** (`conditions_memory_v1_1.yaml` 등)의 `pipeline.debate.max_rounds`는 메타 정보이며, **실제 라운드 수는 실험 YAML 또는 오케스트레이터 config의 `rounds`**로 결정됨 (기본 1).

---

## 9. 메트릭·경고

- **Debate 매핑:**  
  - `debate_mapping_coverage`, `debate_mapping_direct_rate`, `debate_mapping_fallback_rate`, `debate_mapping_none_rate`  
  - `debate_fail_no_aspects_rate`, `debate_fail_no_match_rate`, `debate_fail_neutral_stance_rate`, `debate_fail_fallback_used_rate`

- **Debate override:**  
  - `debate_override_applied`, `debate_override_skipped_low_signal`, `debate_override_skipped_conflict`, `debate_override_skipped_already_confident`, `debate_override_skipped_already_confident_rate`

- **경고 임계값:** `experiments/configs/debate_thresholds.json`  
  - coverage_warn/high, no_match_warn/high, neutral_warn/high  
  - KPI/리포트에서 이 임계값을 넘으면 경고 문구·팁이 출력된다.

---

이 문서는 `agents/debate_orchestrator.py`, `agents/supervisor_agent.py`, `agents/specialized_agents/moderator.py`, `schemas/agent_outputs.py`, `agents/prompts/debate_speaker.md`, `agents/prompts/debate_judge.md`, `experiments/configs/conditions_memory_v1_1.yaml`(v1_2) 기준으로 정리했습니다.
