# 토론(Debate) 규칙·에이전트 역할·출력물·참고 정보출처 정리

파이프라인 내 **Debate 레이어**의 토론 규칙, 참여 에이전트 역할, 출력물, 토론 시 참고하는 정보출처를 코드·프롬프트·스키마 기준으로 정리한 보고서입니다.

---

## 1. 토론 규칙(프로토콜)

### 1.1 위치·활성화

- **위치**: Stage1(ATE·ATSA·Validator) **이후**, Stage2 **이전**.
- **활성화**: `enable_debate: true`일 때만 실행. `enable_debate_override`로 토론 기반 polarity override on/off(기본 true).

### 1.2 발언 규칙

- **발언 순서**: config `debate.order` (기본 `["epm", "tan", "cj"]`) 순서대로, 매 라운드마다 각 에이전트가 1회씩 발언.
- **라운드 수**: config `debate.rounds` (기본 1). 라운드 × 3명 = 총 발언 횟수.
- **형식**: 각 발언자는 **proposed_edits**만 출력. 감정은 원문에 근거한 경우에만 허용(프롬프트: "Do NOT introduce sentiment not grounded in the text").
- **역할 분담** (에이전트별 담당 오류만 처리):
  - **EPM**: 극성이 문장에 실제로 표현되어 있는지, 어디에 있는지 — opinion span 누락/과다, 극성 과해석, 근거 없는 neutral/negative, 질문 초점.
  - **TAN**: 해당 감성이 어떤 aspect에 속하는지 — aspect_term=null, 중복 aspect, aspect span 불일치.
  - **CJ**: aspect당 정확히 하나의 극성인지, 근거 없는 판단 제거 — aspect당 다중 극성, 근거 없는 극성, 과도한 편집.

### 1.3 심판(Judge) 규칙

- **시점**: 모든 라운드 발언 종료 후 **1회** 호출.
- **역할**: EPM/TAN의 proposed_edits를 소비해 **단일·일관된 aspect–polarity 집합**을 산출. 승자/합의 서사 없음.
- **출력**: `final_patch`(Stage2 적용용), `final_tuples`(최종 일관 집합), `unresolved_conflicts`(수렴 시 빈 리스트).

### 1.4 Moderator 규칙(토론 결과 활용)

Moderator는 **규칙 기반(LLM 미사용)** 으로 Stage1/Stage2·Validator·**토론 요약**을 취합해 최종 문장 레이블·신뢰도를 결정합니다.

| 규칙 | 내용 | 조건·동작 |
|------|------|-----------|
| **Rule Z** | 신호 부족 | stage1·stage2 confidence 모두 0 → 즉시 final_label=neutral, confidence=0, 이후 규칙 미적용. |
| **Rule B** | Stage2 선호 | Stage2 없으면 Stage1 유지. Stage2 있으면 Stage2 선호. 단 confidence 하락 ≥0.2면 drop_guard=True, Stage1 유지. |
| **Rule M** | Stage1↔Stage2 충돌 | Stage2 있고 stage1.label ≠ stage2.label → final_label=mixed. |
| **Rule C** | Validator veto | critical risk 또는 validator.confidence ≥ current_conf → final_label을 validator 제안으로 덮음. |
| **Rule A** | Span 정렬 보정 | drop_guard가 False일 때만. candidate와 stage1 span IoU≥0.8이고 레이블 일치 시 confidence 보정. |
| **Rule D** | 신뢰도 타이브레이크 | ATE vs ATSA 레이블 불일치 시 \|ate_conf−atsa_conf\|<0.1이면 문장 ATE 우선, 아니면 신뢰도 큰 쪽 채택. |
| **Rule E** | 토론 합의 힌트 | debate_summary의 **final_tuples**에서 레이블 추론. 추론값이 있고 현재와 다르며 (confidence<0.55 또는 mixed)이면 final_label을 토론 쪽으로 덮음. |

---

## 2. 토론에 참여하는 에이전트 역할

### 2.1 발언자 3명 (EPM, TAN, CJ)

토론 단계에서만 **동일 백본(LLM)** 에 **debate_speaker** 프롬프트 + **페르소나(JSON)** 를 넣어 호출합니다. 별도 에이전트 클래스가 아니라 “debate_speaker 1회 호출 × 페르소나만 바꿔가며 3명”입니다.

| 키 | 이름 | 역할(role) | 목표(goal) |
|----|------|------------|------------|
| **EPM** | Evidence–Polarity Mapper | Evidence–Polarity Mapper | 극성이 명시적 문장 근거로만 지지될 때만 확정 |
| **TAN** | Target–Aspect Normalizer | Target–Aspect Normalizer | null·중복·어긋난 aspect 대상을 정리 |
| **CJ** | Consistency Judge | Consistency Judge | aspect당 하나의 극성, 근거 없는 판단 제거, 단일 일관 집합 산출 |

- **설정**: config `debate.personas`, `debate.order`로 오버라이드 가능.
- **스키마**: `schemas/agent_outputs.py` — `DebatePersona(name, role, goal, stance, style)` (stance/style은 미사용).

### 2.2 심판(Judge)

- **역할**: 모든 라운드 턴을 읽고 **CJ**로서 최종 **final_patch**, **final_tuples**, **unresolved_conflicts**를 출력.
- **프롬프트**: `agents/prompts/debate_judge.md`.
- **호출**: 1회(LLM), 스키마 `DebateSummary`.

### 2.3 Moderator(토론 외부, 토론 결과만 참조)

- **역할**: 토론 **참여자 아님**. Stage1/Stage2 ATE·ATSA, Validator, (선택) **토론 요약(debate_summary)** 을 규칙(Z→B→M→C→A→D→E)으로 취합해 최종 문장 레이블·신뢰도 결정.
- **구현**: `agents/specialized_agents/moderator.py`, LLM 미사용.

---

## 3. 출력물

### 3.1 발언 1턴 (DebateTurn)

| 필드 | 설명 |
|------|------|
| **agent** | "EPM" \| "TAN" \| "CJ" |
| **proposed_edits** | 패치 연산 목록. 각 항목: `op`, `target`, `value`?, `evidence`?, `confidence`? |
| **speaker** | 레거시; agent와 동일 사용 |
| **message** / **planning** / **reflection** / **key_points** | 선택; preferred는 proposed_edits |

**op 종류**: `set_polarity` \| `set_aspect_ref` \| `merge_tuples` \| `drop_tuple` \| `confirm_tuple`

### 3.2 심판 요약 (DebateSummary)

| 필드 | 설명 |
|------|------|
| **final_patch** | Stage2에 넘길 패치 목록. e.g. drop_tuple, confirm_tuple. |
| **final_tuples** | 단일 일관 aspect–polarity 집합. `[{ "aspect_term", "polarity" }]` |
| **unresolved_conflicts** | 미해결 충돌 목록(수렴 시 []) |
| **rationale** | CJ 판단 근거(선택) |
| winner, consensus, key_agreements, key_disagreements | deprecated; 사용 안 함 |

### 3.3 토론 전체 (DebateOutput)

| 필드 | 설명 |
|------|------|
| **topic** | 원문 텍스트 |
| **personas** | EPM/TAN/CJ 페르소나 dict |
| **rounds** | 라운드별 `DebateRound`(round_index, turns) |
| **summary** | DebateSummary(judge 출력) |

### 3.4 Stage2·Override로의 전달

Supervisor의 `_build_debate_review_context`가 토론 결과를 **Debate Review Context(JSON)** 로 만듭니다.

- **포함**: summary, rebuttal_points(proposed_edits 기반), aspect_terms, synonym_hints, **aspect_hints**(aspect별 polarity_hint, weight, speaker), mapping_stats, mapping_fail_reasons, review_guidance, fallback_mapping_policy.
- **용도**: Stage2 ATE/ATSA 리뷰 프롬프트의 `extra_context`, 및 **Debate override** 시 aspect별 pos/neg 점수 산출에 사용.

---

## 4. 토론에 참고하는 정보출처

### 4.1 공통 컨텍스트 (SHARED_CONTEXT_JSON)

Supervisor의 `_build_debate_context`가 생성하는 JSON에 다음이 포함됩니다.

| 출처 | 필드 | 설명 |
|------|------|------|
| **원문** | `text` | 판단 대상 입력 문장 |
| **Stage1 ATE** | `stage1_aspects` | 추출된 속성(term, span, normalized, syntactic_head, confidence, rationale) |
| **Stage1 ATSA** | `stage1_aspect_sentiments` | 속성별 감성( aspect_term, polarity, evidence, confidence 등) |
| **Stage1 Validator** | `stage1_structural_risks` | 구조적 리스크 목록 |
| **Stage1 Validator** | `stage1_correction_proposals` | 수정 제안(FLIP_POLARITY, DROP_ASPECT 등) |

즉, 토론의 **기본 참고 정보**는 **Stage1 결과(ATE, ATSA, Validator)** 와 **원문**입니다.

### 4.2 조건부 주입: 에피소드 메모리(C2/C3)

- **조건**: episodic_memory 조건(C2/C3 등)에서 **exposed_to_debate** 이고, 검색된 메모리 슬롯(slot_dict)이 있으며, **advisory_injection_gate** 통과 시.
- **동작**: `debate_context`(위 JSON)에 **슬롯 이름**(예: `DEBATE_CONTEXT__MEMORY`)으로 메모리 객체를 추가한 뒤, 이 확장된 JSON을 `context_json`으로 debate에 전달.
- **결과**: 토론 참여자(EPM/TAN/CJ)와 Judge는 **동일 SHARED_CONTEXT_JSON** 안에서 Stage1 결과 + (조건 충족 시) **에피소드 메모리**를 함께 참고합니다.

### 4.3 발언 시 주입되는 변수

- **TOPIC**: 원문 텍스트.
- **PERSONA**: 해당 턴 에이전트의 `DebatePersona` JSON.
- **SHARED_CONTEXT_JSON**: 위 4.1(및 4.2 적용 시 메모리 포함) JSON 문자열.
- **HISTORY**: 이전 턴들의 요약(에이전트명 + proposed_edits 또는 message).

Judge 호출 시에는 **TOPIC**, **SHARED_CONTEXT_JSON**, **ALL_TURNS**(전체 턴 이력)가 주입됩니다.

---

## 5. 관련 파일 요약

| 구분 | 경로 |
|------|------|
| 토론 오케스트레이션 | `agents/debate_orchestrator.py` |
| 발언 프롬프트 | `agents/prompts/debate_speaker.md` |
| 심판 프롬프트 | `agents/prompts/debate_judge.md` |
| Moderator(규칙·Rule E) | `agents/specialized_agents/moderator.py` |
| 컨텍스트 생성·메모리 주입 | `agents/supervisor_agent.py` (_build_debate_context, debate.run 직전 메모리 주입) |
| 스키마 | `schemas/agent_outputs.py` (DebatePersona, DebateTurn, DebateRound, DebateSummary, DebateOutput) |
| 문서 | `docs/debate_protocol.md`, `docs/debate_agent_setting_prompts_personas.md` |

---

*이 보고서는 `agents/debate_orchestrator.py`, `agents/supervisor_agent.py`, `agents/specialized_agents/moderator.py`, `agents/prompts/debate_speaker.md`, `agents/prompts/debate_judge.md`, `schemas/agent_outputs.py`, `docs/debate_protocol.md`를 기준으로 작성했습니다.*
