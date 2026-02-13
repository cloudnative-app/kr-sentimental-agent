# 토론 에이전트 설정·프롬프트·페르소나 정리

토론(Debate) 단계의 에이전트 설정, 사용 프롬프트, 페르소나 정의를 한 문서에 정리한다.  
**최신 상태:** EPM → TAN → CJ 패치 기반(proposed_edits), pro/con 대결 없음.

---

## 1. 설정 (config)

**위치**: `agents/debate_orchestrator.py` — `DebateOrchestrator(config=self.config.get("debate"))`  
**소스**: 실험 YAML의 `pipeline.debate` 또는 conditions YAML의 `pipeline.debate`.

| 키 | 기본값 | 설명 |
|----|--------|------|
| **rounds** | **1** | 토론 라운드 수 (한 라운드 = order 순서대로 EPM → TAN → CJ 한 턴씩) |
| **order** | **`["epm", "tan", "cj"]`** | 매 라운드마다 발언 순서 (키 이름) |
| **personas** | (아래 기본 3종) | 키별 페르소나 정의. 있으면 override. |

conditions YAML 예시 (`experiments/configs/conditions_memory_v1_1.yaml`, `conditions_memory_v1_2.yaml`):

```yaml
pipeline:
  debate:
    enabled: true
    max_rounds: 3
    injection:
      strategy: "during_debate_one_shot"
      trigger: "deadlock_obs2of4"
      allow_multiple_injections: false
```

- `max_rounds`는 conditions 쪽 **메타 정보**이며, **실제 라운드 수는 DebateOrchestrator에서 `config.get("rounds", 1)`**로 읽음.  
- 실험 YAML에서 `pipeline.debate.rounds`, `pipeline.debate.order`, `pipeline.debate.personas`를 주면 그대로 사용됨.

---

## 2. 페르소나 (personas)

**스키마**: `schemas/agent_outputs.py` — `DebatePersona(name, role, goal, stance?, style?)`  
**기본값** (config에 `personas` 없을 때, `agents/debate_orchestrator.py`):

| 키 | name | role | goal |
|----|------|------|------|
| **epm** | EPM | Evidence–Polarity Mapper | Determine polarity only when supported by explicit textual evidence |
| **tan** | TAN | Target–Aspect Normalizer | Resolve null, duplicate, or misaligned aspect targets |
| **cj** | CJ | Consistency Judge | Produce a single, consistent set of aspect–polarity tuples |

- **stance / style:** deprecated(미사용). pro/con 대결 없음.  
- **order** 기본값은 **`["epm", "tan", "cj"]`** → 매 라운드마다 EPM → TAN → CJ 순으로 한 턴씩 발언.

실험 YAML에서 override 예시:

```yaml
pipeline:
  debate:
    rounds: 1
    order: ["epm", "tan", "cj"]
    personas:
      epm:
        name: "EPM"
        role: "Evidence–Polarity Mapper"
        goal: "Determine polarity only when supported by explicit textual evidence"
        stance: ""
        style: ""
      tan:
        name: "TAN"
        role: "Target–Aspect Normalizer"
        goal: "Resolve null, duplicate, or misaligned aspect targets"
        stance: ""
        style: ""
      cj:
        name: "CJ"
        role: "Consistency Judge"
        goal: "Produce a single, consistent set of aspect–polarity tuples"
        stance: ""
        style: ""
```

---

## 3. 프롬프트

**경로**: `agents/prompts/` — `load_prompt("debate_speaker")`, `load_prompt("debate_judge")`  
**파일**: `debate_speaker.md`, `debate_judge.md`

### 3.1 발언용: `debate_speaker.md`

- **역할**: 토론 참가자(EPM/TAN/CJ) 한 명이 한 턴 발언할 때 사용. **패치(proposed_edits)만 출력**.
- **삽입 변수** (orchestrator에서 조합):
  - `[TOPIC]`: 원문 문장
  - `[PERSONA]`: 해당 페르소나 JSON (`DebatePersona.model_dump_json()`)
  - `[SHARED_CONTEXT_JSON]`: Stage1 결과·validator·(C2 시) 메모리 슬롯 등 JSON
  - `[HISTORY]`: 지금까지의 턴 목록 (`- agent: op target=... value=... evidence=...`)

**내용 요약**:

- Annotation corrector. **Output ONLY proposed_edits.** 라벨/정답 직접 노출 금지.
- EPM: 극성이 문장 내 증거로 뒷받침되는지, opinion span omission/excess, polarity over-interpretation 등.
- TAN: aspect_term=null, 중복 aspect, aspect span 불일치 등.
- CJ: aspect당 단일 극성, 증거 없는 판단 제거, 과편집 방지.
- **출력 JSON**: `agent`, `proposed_edits` (각 항목: `op`, `target`, `value`?, `evidence`?, `confidence`?).  
  - op: `set_polarity` | `set_aspect_ref` | `merge_tuples` | `drop_tuple` | `confirm_tuple`  
  - target: 반드시 `aspect_ref`(Stage1 aspect term). 선택 `aspect_term`, `polarity`.

### 3.2 심판용: `debate_judge.md`

- **역할**: 모든 라운드 종료 후, CJ가 EPM/TAN의 proposed_edits를 취합해 **final_patch**, **final_tuples**, **sentence_polarity** 등 출력.
- **삽입 변수**:
  - `[TOPIC]`: 원문
  - `[SHARED_CONTEXT_JSON]`: 위와 동일
  - `[ALL_TURNS]`: 전체 턴 이력 (agent + proposed_edits 형식)

**내용 요약**:

- Consistency Judge (CJ). TOPIC, SHARED_CONTEXT_JSON, ALL_TURNS를 읽고 **final_patch**(Stage2-ready), **final_tuples**(단일 일관 집합), **unresolved_conflicts** 출력.
- **sentence_polarity**: 문장 수준 전체 극성 (positive | negative | neutral | mixed).
- **sentence_evidence_spans**: TOPIC에서 결론을 뒷받침하는 **정확한 부분문자열** 1개 이상 (필수).
- **출력 JSON**: `final_patch`, `final_tuples`, `unresolved_conflicts`, `sentence_polarity`, `sentence_evidence_spans`, `aspect_evidence`?, `rationale`?.  
  - winner/consensus/key_agreements/key_disagreements는 deprecated( Rule E fallback에서만 텍스트 추론용).

---

## 4. 실행 흐름 (orchestrator)

1. **라운드 루프** (`rounds`회, 기본 1):
   - **order** 순서대로 각 `speaker_key`(epm, tan, cj)에 대해:
     - `persona = personas[speaker_key]`
     - `system_prompt = debate_speaker.md + [TOPIC] + [PERSONA] + [SHARED_CONTEXT_JSON] + [HISTORY]`
     - LLM 호출 → `DebateTurn` 파싱(agent, proposed_edits) → 턴을 `turns`/해당 라운드에 추가, `process_trace`에 기록
2. **judge 1회**:
   - `judge_prompt = debate_judge.md + [TOPIC] + [SHARED_CONTEXT_JSON] + [ALL_TURNS]`
   - LLM 호출 → `DebateSummary` 파싱 (final_patch, final_tuples, sentence_polarity, sentence_evidence_spans 등) → `DebateOutput.summary` 및 trace에 기록
3. **반환**: `DebateOutput(topic, personas, rounds, summary)`.

---

## 5. 관련 파일

| 항목 | 경로 |
|------|------|
| 오케스트레이터 | `agents/debate_orchestrator.py` |
| 발언 프롬프트 | `agents/prompts/debate_speaker.md` |
| 심판 프롬프트 | `agents/prompts/debate_judge.md` |
| 페르소나/토론 스키마 | `schemas/agent_outputs.py` (ProposedEdit, DebatePersona, DebateTurn, DebateRound, DebateSummary, DebateOutput) |
| 토론 사용처 | `agents/supervisor_agent.py` (enable_debate, _build_debate_context, debate.run, _build_debate_review_context → Stage2/override) |
| 조건/실험 debate 설정 | `experiments/configs/conditions_memory_v1_1.yaml`, `conditions_memory_v1_2.yaml`, 실험 YAML `pipeline.debate` |
