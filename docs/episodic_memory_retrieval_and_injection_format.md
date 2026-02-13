# 에피소드 메모리 조회양식·주입양식

에피소드 메모리의 **조회(검색)에 쓰는 양식**과 **Debate에 주입되는 양식**을 스키마·코드 기준으로 정리한다.

---

## 1. 조회양식 (Retrieval / Query format)

### 1.1 쿼리 생성

- **시점**: 샘플마다 **토론 직전** `EpisodicOrchestrator.get_slot_payload_for_current_sample()` 호출 시.
- **입력**: `text`, `stage1_ate`, `stage1_atsa`, `stage1_validator`, `language_code`.
- **쿼리 객체**: `SignatureBuilder.build(raw_text, language=..., num_aspects=...)` → **InputSignatureV1_1**.

### 1.2 InputSignatureV1_1 (쿼리 시그니처)

| 필드 | 타입 | 설명 |
|------|------|------|
| `language` | str | `"ko"` \| `"en"` \| `"other"` |
| `detected_structure` | List[str] | `["negation"`, `"contrast"`, `"irony"`, `"none"`] 중 해당하는 것. `SignatureBuilder`가 원문에서 패턴으로 검출. |
| `contrast_marker` | Optional[str] | (선택) |
| `has_negation` | Optional[bool] | negation 포함 여부 |
| `num_aspects` | int | Stage1 ATE aspect 개수 (≥0) |
| `length_bucket` | str | `"short"`(\<50자) \| `"medium"`(\<200자) \| `"long"` |

- **원문/raw_text**: 쿼리·저장 모두에 **저장하지 않음**. 시그니처만 사용.

### 1.3 검색 동작 (Retriever.retrieve)

- **입력**: `store_entries`(episodic_store.jsonl 항목들), `query_signature`(InputSignatureV1_1 또는 dict), `query_lexical=None`(선택).
- **필터**:
  - `require_same_language=True`: `entry.input_signature.language` == 쿼리 `language`.
  - `require_structure_overlap=True`: 쿼리 `detected_structure`와 entry 시그니처 구조가 하나라도 겹침 (또는 entry가 `"none"`).
- **점수/정렬**: (signature 겹침 개수, lexical 겹침 비율). lexical은 entry의 `case_summary.symptom`, `case_summary.rationale_summary` 토큰과 쿼리 토큰 겹침 비율(현재 `query_lexical` 미전달 시 0).
- **출력**: 상위 **topk**(1~3)개 **store entry**(EpisodicMemoryEntryV1_1 형태 dict) 리스트.

즉, **조회양식**은 **InputSignatureV1_1** 하나로, 언어·구조·aspect 수·길이 버킷만으로 검색한다.

---

## 2. 주입양식 (Injection format)

### 2.1 슬롯 이름 및 배치

- **슬롯 이름**: `DEBATE_CONTEXT__MEMORY` (config `io.slot_memory_name`으로 변경 가능).
- **배치**: Supervisor가 `debate_context`(JSON)에 **키 하나**로 병합.  
  `debate_context[slot_name] = AdvisoryBundleV1_1.model_dump()`.

### 2.2 AdvisoryBundleV1_1 (주입되는 슬롯 본문)

| 필드 | 타입 | 설명 |
|------|------|------|
| `schema_version` | Literal["1.1"] | `"1.1"` |
| `memory_on` | bool | C2이고 injection_mask=False일 때만 True. 실제로 메모리 내용이 켜져 있음. |
| `retrieved` | List[AdvisoryV1_1] | 최대 3개. C1/마스킹 시 빈 리스트. |
| `warnings` | List[str] | 최대 5개. 경고 문자열. |
| `meta` | AdvisoryBundleMetaV1_1 | 아래 참고. |

**AdvisoryBundleMetaV1_1**

| 필드 | 설명 |
|------|------|
| `memory_mode` | `"off"` \| `"on"` \| `"silent"` |
| `topk` | 0~3 |
| `masked_injection` | True면 retrieved를 비워서 주입(실제 내용 미노출). |
| `retrieval_executed` | 검색 수행 여부. |

### 2.3 AdvisoryV1_1 (retrieved 한 건)

| 필드 | 타입 | 설명 |
|------|------|------|
| `schema_version` | Literal["1.1"] | `"1.1"` |
| `advisory_id` | str | `adv_000001` 형식. |
| `advisory_type` | str | `successful_override` \| `failed_override_warning` \| `consistency_anchor` |
| `message` | str | 조언 본문 (최대 800자). 라벨/정답 힌트 없음. |
| `strength` | str | `weak` \| `moderate` \| `strong` |
| `relevance_score` | float | 0~1 |
| `evidence` | EvidenceV1_1 | source_episode_ids, risk_tags, principle_id 등 (라벨/정답 없음). |
| `constraints` | AdvisoryConstraintsV1_1 | no_label_hint, no_forcing, no_confidence_boost (항상 True). |

### 2.4 조건별 주입 내용

| 조건 | retrieval_executed | injection_mask | retrieved | debate prompt에 노출 |
|------|--------------------|----------------|-----------|----------------------|
| C1 | False | True | [] | 슬롯은 있으나 비어 있음(memory_on=false). |
| C2 | True | False | AdvisoryBuilder 결과(최대 topk) | 노출. 단, advisory injection gate 통과 시에만 context에 병합. |
| C2_silent | True | True | [] (마스킹) | 슬롯은 있으나 비어 있음(memory_on=false). |

- **실제 병합**: Supervisor에서 `exposed_to_debate and slot_dict and gate_ok`일 때만 `debate_context`에 `DEBATE_CONTEXT__MEMORY`를 넣는다.  
  C2여도 `should_inject_advisory_with_reason(...)`이 False면 debate prompt에는 넣지 않는다.

---

## 3. 요약

| 구분 | 양식 | 스키마/위치 |
|------|------|-------------|
| **조회** | 쿼리 = 현재 샘플의 시그니처(언어·구조·aspect 수·길이 버킷) | InputSignatureV1_1. SignatureBuilder.build → Retriever.retrieve. |
| **주입** | Debate context 한 슬롯 = 메모리 번들(메타 + advisory 리스트) | AdvisoryBundleV1_1 (retrieved: List[AdvisoryV1_1]). InjectionController.build_slot_payload → debate_context에 병합. |

- **저장 형식**: 에피소드 저장 시에는 EpisodicMemoryEntryV1_1 (input_signature, case_summary, stage_snapshot, correction, evaluation, provenance 등).  
  조회 시 이 entry 리스트를 쿼리 시그니처로 필터/정렬하고, 선택된 entry를 AdvisoryBuilder가 AdvisoryV1_1로 변환해 주입 양식으로 쓴다.
