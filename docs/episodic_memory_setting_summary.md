# 에피소드 메모리 설정 정리

에피소드 메모리가 **어떤 정보를**, **언제**, **어떻게** 제공하는지 정리한다.

---

## 1. 어떤 정보를 제공하는가

### 1.1 제공되는 최종 형태: Advisory(조언) 번들

에이전트에게 주입되는 것은 **DEBATE_CONTEXT__MEMORY** 슬롯 하나이며, 그 내용은 `AdvisoryBundleV1_1` 스키마다.

| 필드 | 설명 |
|------|------|
| `memory_on` | 메모리 사용 여부 (C2에서만 true) |
| `retrieved` | **AdvisoryV1_1** 리스트 (최대 topk=3개) |
| `warnings` | 경고 문자열 리스트 |
| `meta` | memory_mode, topk, masked_injection, retrieval_executed |

각 **AdvisoryV1_1** 항목에는 다음이 포함된다.

| 필드 | 설명 |
|------|------|
| `advisory_id` | adv_000001 형식 |
| `advisory_type` | consistency_anchor 등 |
| `message` | **조언 본문** (최대 800자). corrective_principle + risk_type/action_taken/outcome_delta 요약, 필요 시 “과거 실패/리스크 악화” 경고 문구 |
| `strength` | weak / moderate / strong |
| `relevance_score` | 0~1 |
| `evidence` | source_episode_ids, risk_tags, principle_id (라벨/정답 힌트 없음) |
| `constraints` | no_label_hint, no_forcing, no_confidence_boost (항상 True로 고정) |

- **라벨/정답 직접 노출 금지**: message에 gold polarity나 정답 힌트를 넣지 않는다.
- **OPFB(Opposite Polarity Failed Block)**: 동일 aspect·polarity로 과거에 실패/리스크 악화가 있었던 에피소드는 advisory로 생성하지 않고 **블록**한다. 블록 통계는 `memory_blocked_episode_n`, `memory_blocked_advisory_n`, `memory_block_reason` 등으로 기록된다.

### 1.2 정보의 출처: 에피소드 저장소

- **저장 위치**: `memory/episodic_store.jsonl` (설정으로 변경 가능)
- **항목 스키마**: `EpisodicMemoryEntryV1_1`
  - `input_signature`: language, detected_structure, num_aspects, length_bucket 등 (원문/raw_text 저장 금지)
  - `case_summary`: target_aspect_type, symptom, rationale_summary
  - `stage_snapshot`: stage1 vs final의 aspects_norm, polarities, confidence
  - `correction`: corrective_principle, applicable_conditions
  - `evaluation`: risk_before, risk_after, override_applied, override_success, override_harm
  - `risk_type`, `action_taken`, `outcome_delta`: 리스크→액션 매핑(콘텐츠 강화용)

검색 시 **input_signature**(언어·구조·길이 등)와 **case_summary**(symptom, rationale_summary) 기반으로 유사 에피소드를 찾고, 그 결과를 Advisory로 변환해 제공한다.

---

## 2. 언제 제공하는가

### 2.1 토론 전: 검색·슬롯 생성·(조건부) 주입

| 시점 | 처리 |
|------|------|
| **토론 직전** | `EpisodicOrchestrator.get_slot_payload_for_current_sample()` 호출 |
| | 현재 샘플의 text, stage1(ate, atsa, validator), language_code로 **쿼리 시그니처** 생성 |
| | 조건이 retrieval을 실행하면 store 로드 → **Retriever.retrieve()** → **AdvisoryBuilder.build_from_episodes()** → **InjectionController**로 슬롯 JSON 생성 |
| | 반환: `(slot_dict, memory_mode, memory_meta)` |
| **슬롯을 debate context에 넣는 시점** | SupervisorAgent에서 **exposed_to_debate & slot_dict & gate_ok**일 때만 `debate_context`에 `DEBATE_CONTEXT__MEMORY` 병합 |
| | C2만 `exposed_to_debate=True`. C1/C2_silent/C2_eval_only는 병합하지 않음(프롬프트에 미포함). |

즉, **“언제”**는 **매 샘플의 Debate 단계 진입 직전**이고, **실제로 debate prompt에 들어가는 시점**은 C2이면서 **advisory injection gate**를 통과했을 때이다.

### 2.2 토론 후: 에피소드 저장(조건부)

| 시점 | 처리 |
|------|------|
| **샘플 처리 끝** | Stage2·모더레이터·EV 결정 등이 끝난 뒤 `SupervisorAgent`가 `append_episode_if_needed()` 호출 |
| | 조건이 **store_write=True**일 때만 에피소드 1건 구성 후 `MemoryStore.append()` |
| | C2·C2_silent만 store_write=True. C1·C2_eval_only는 저장하지 않음. |

정리하면:

- **제공(검색→슬롯 생성)**: 샘플마다 **토론 전** 한 번.
- **주입(debate context 병합)**: C2이고 injection gate 통과 시 **토론 전** (동일 호출 흐름 내).
- **저장**: **샘플 끝**에서, store_write가 켜진 조건일 때만.

---

## 3. 어떻게 제공하는가

### 3.1 설정 계층: 조건(C1/C2/C2_silent/C2_eval_only)

실험 설정에서 `episodic_memory.condition`(또는 `memory.enable`+`memory.mode`로 변환)으로 조건을 정한다. 실제 플래그는 `experiments/configs/conditions_memory_v1_1.yaml` 또는 `conditions_memory_v1_2.yaml`의 `conditions` 아래에 정의된다.

| 조건 | retrieval_execute | injection_mask | store_write | exposed_to_debate | 설명 |
|------|-------------------|----------------|-------------|-------------------|------|
| **C1** | false | true | false | false | 메모리 OFF. 검색 안 함, 슬롯 비움, 저장 안 함. |
| **C2** | true | false | true | **true** | 검색 후 advisory를 슬롯에 채우고, gate 통과 시 debate에 주입, 에피소드 저장. |
| **C2_silent** (C3) | true | true | true | false | 검색은 수행(비용/지연 유지), 슬롯은 비움(주입 마스킹), debate에는 미노출, 저장은 함. |
| **C2_eval_only** | true | true | false | false | C3와 동일하게 검색·마스킹·미노출, 저장만 안 함(평가 시 스토어 오염 방지). |

- `injection_mask=True` → slot의 `retrieved`를 빈 리스트로 만들어, 슬롯은 있어도 내용 없음.
- **supervisor는 `exposed_to_debate`로만** debate context에 slot을 병합할지 결정한다.

### 3.2 파이프라인 흐름(어떻게)

1. **run_experiments.py**  
   실험 YAML의 `memory` 또는 `episodic_memory`를 읽어 `pipeline_cfg["episodic_memory"]`에 `condition`을 넣고, 이 config로 SupervisorAgent(및 내부 EpisodicOrchestrator)를 생성한다.

2. **EpisodicOrchestrator** (`memory/episodic_orchestrator.py`)
   - `get_slot_payload_for_current_sample()`  
     - **SignatureBuilder**: text, language_code, num_aspects → `InputSignatureV1_1`  
     - **retrieval_execute**이면: **MemoryStore.load()** → **Retriever.retrieve(store_entries, query_sig)**  
       - 동일 언어, 구조 겹침 필터 + 시그니처/lexical 점수로 topk(기본 3) 선택  
     - **injection_mask**가 아니면: **AdvisoryBuilder.build_from_episodes(retrieved)**  
       - 에피소드별로 AdvisoryV1_1 생성, OPFB 적용(위험 (aspect, polarity) 조합은 블록)  
     - **InjectionController.build_slot_payload(condition, advisories)**  
       - `AdvisoryBundleV1_1` 형태로 슬롯 dict 생성 후 JSON 문자열로 반환  
     - 반환: slot_dict, memory_mode, memory_meta(retrieved_k, retrieved_ids, exposed_to_debate, memory_blocked_* 등)

3. **SupervisorAgent** (`agents/supervisor_agent.py`)
   - `exposed_to_debate and slot_dict and gate_ok`일 때만:
     - **should_inject_advisory_with_reason()**으로 gate 통과 여부 확인  
       - 통과 조건(OR): polarity_conflict_raw, validator_s1_risk 존재, alignment_failure≥2, explicit_grounding_failure 버킷  
     - 통과하면 `debate_context`(JSON)에 `slot_name` 키로 slot을 넣고, `memory_meta["prompt_injection_chars"]` 설정  
   - gate 실패 시 `advisory_injection_gated=True` 등 메타만 기록하고 주입은 하지 않음.

4. **에피소드 저장**  
   - 샘플 끝에서 `append_episode_if_needed()` 호출.  
   - **store_write**가 True일 때만 stage1/stage2/validator/모더레이터 결과와 moderator_summary로 `EpisodicMemoryEntryV1_1` 1건 구성 후 `MemoryStore.append()`.

### 3.3 Advisory injection gate(주입 게이트)

C2에서도 **다음 중 하나라도 만족할 때만** 실제로 debate context에 메모리 슬롯을 넣는다(OR 조건).

- **conflict**: 동일 aspect에 대해 stage1에서 극성 2개 이상(polarity_conflict_raw)
- **validator**: stage1 validator에 structural_risk가 1개 이상
- **alignment**: alignment_failure 드롭 수 ≥ 2
- **explicit_grounding_failure**: (근사) 명시적 aspect가 있는데, 드롭이 모두 alignment_failure인 경우

게이트를 통과하지 못하면 `exposed_to_debate`가 True여도 주입하지 않고, `advisory_injection_gated=True`, `prompt_injection_chars=0`으로 기록된다.

---

## 4. 요약 표

| 항목 | 내용 |
|------|------|
| **무엇을** | 과거 에피소드에서 뽑은 Advisory(조언) 번들. corrective_principle·risk/action 요약, OPFB 적용, 라벨/정답 노출 없음. |
| **언제(검색·슬롯)** | 샘플마다 **Debate 단계 직전** 한 번. |
| **언제(주입)** | C2이고 injection gate 통과 시, **같은 Debate 직전** 흐름에서 debate context에 병합. |
| **언제(저장)** | **샘플 처리 완료 후**, store_write=True 조건(C2, C2_silent)일 때만 1건 append. |
| **어떻게(검색)** | InputSignature + case_summary 기반 signature_lexical 검색, topk 3, 동일 언어·구조 겹침 필터. |
| **어떻게(변환)** | retrieved 에피소드 → AdvisoryBuilder → AdvisoryV1_1 리스트(OPFB로 일부 블록) → AdvisoryBundleV1_1 슬롯. |
| **어떻게(주입)** | Supervisor가 exposed_to_debate & slot_dict & should_inject_advisory_with_reason 통과 시 debate_context JSON에 DEBATE_CONTEXT__MEMORY 병합. |

이 문서는 `memory/episodic_orchestrator.py`, `memory/advisory_builder.py`, `memory/injection_controller.py`, `agents/supervisor_agent.py`, `experiments/configs/conditions_memory_v1_1.yaml`, `conditions_memory_v1_2.yaml`, `docs/c1_c2_c3_condition_definition.md`, `docs/c3_retrieval_only_spec.md`를 기준으로 정리했다.
