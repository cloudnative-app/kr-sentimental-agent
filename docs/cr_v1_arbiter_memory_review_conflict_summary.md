# CR v1: Arbiter·에피소드 메모리·리뷰 에이전트·충돌 플래깅 정리

---

## 1. Arbiter 규칙

**위치**: `agents/conflict_review_runner._arbiter_vote`, `agents/prompts/review_arbiter_action.md`  
**구현**: 코드(LLM 아님). A/B/C 합의만 수행.

### 1.1 규칙 요약

| Rule | 조건 | 결과 |
|------|------|------|
| **Rule 1** | ≥2 동일 액션 | 해당 액션 채택 |
| **Rule 2** | 전원 다름 (tie) | KEEP + FLAG (reason_code: POLARITY_UNCERTAIN) |
| **Rule 3** | 1 FLIP + 1 DROP + 1 KEEP | FLIP의 reason_code가 structural(NEGATION_SCOPE, CONTRAST_CLAUSE, STRUCTURAL_INCONSISTENT) → FLIP; 아니면 FLAG |
| **Rule 4** | MERGE vote | KEEP으로 대체 (Arbiter는 MERGE 출력 안 함) |

### 1.2 액션 공간

| 액션 | 설명 |
|------|------|
| KEEP | 유지 |
| DROP | 제거 |
| FLIP | polarity 변경 (new_value.polarity) |
| FLAG | 유지 + 불확실 표시 |

- MERGE는 Arbiter에서 출력하지 않음. (Finalize 단계로 이동, 현재 P1은 no-op)

### 1.3 Structural reason 코드

`_STRUCTURAL_REASON_CODES = {"NEGATION_SCOPE", "CONTRAST_CLAUSE", "STRUCTURAL_INCONSISTENT"}`

Rule 3에서 1 FLIP + 1 DROP + 1 KEEP일 때, FLIP의 reason_code가 이 집합에 있으면 FLIP 채택.

---

## 2. 에피소드 메모리 Read/Write 양식

### 2.1 Read (검색·주입)

| 단계 | 양식 | 스키마/위치 |
|------|------|-------------|
| **쿼리** | InputSignatureV1_1 | language, detected_structure, has_negation, num_aspects, length_bucket |
| **Retriever** | store_entries → topk | require_same_language, require_structure_overlap |
| **주입 슬롯** | AdvisoryBundleV1_1 | DEBATE_CONTEXT__MEMORY 슬롯 |
| **주입 내용** | List[AdvisoryV1_1] | retrieved (최대 topk=3) |

**AdvisoryBundleV1_1** (retrieved 주입 시):

```json
{
  "schema_version": "1.1",
  "memory_on": true,
  "retrieved": [
    {
      "advisory_id": "adv_000001",
      "advisory_type": "successful_override|failed_override_warning|consistency_anchor",
      "message": "조언 본문 (최대 800자)",
      "strength": "weak|moderate|strong",
      "relevance_score": 0.0~1.0,
      "evidence": { "source_episode_ids", "risk_tags", "principle_id" },
      "constraints": { "no_label_hint": true, "no_forcing": true, "no_confidence_boost": true }
    }
  ],
  "warnings": [],
  "meta": { "memory_mode", "topk", "masked_injection", "retrieval_executed" }
}
```

**CR 리뷰 프롬프트 주입**: `_format_memory_context` → `"Memory advisory (from similar past cases):\n- {message}"` 형태로 문자열 변환.

### 2.2 Write (에피소드 저장)

| 양식 | 스키마 | 설명 |
|------|--------|------|
| **저장 단위** | EpisodicMemoryEntryV1_1 | JSONL 1건/줄 |
| **episode_id** | epi_NNNNNN | 패턴 |
| **episode_type** | success \| harm \| neutral | structural_risks 유무로 결정 |
| **input_signature** | InputSignatureV1_1 | language, detected_structure, num_aspects, length_bucket |
| **case_summary** | CaseSummaryV1_1 | target_aspect_type, symptom, rationale_summary |
| **stage_snapshot** | StageSnapshotPairV1_1 | stage1/final: aspects_norm, polarities, confidence |
| **correction** | CorrectionV1_1 | corrective_principle, applicable_conditions |
| **evaluation** | EvaluationV1_1 | risk_before, risk_after, override_applied, override_success, override_harm |
| **provenance** | ProvenanceV1_1 | created_from_split, timestamp, version |

**금지 필드**: raw_text, raw_text_hash, gold, gold_label, gold_polarity, cot, chain_of_thought

---

## 3. 리뷰 스테이지 에이전트 작업규칙

### 3.1 에이전트별 역할·프롬프트

| 에이전트 | 프롬프트 | 역할 | 우선순위 |
|----------|----------|------|----------|
| **Review A** | review_pneg_action | NEGATION/CONTRAST VALIDATOR | negation/contrast 구조적 polarity 검증 |
| **Review B** | review_pimp_action | IMPLICIT INFERENCE VALIDATOR | 암시적 추론 정당성 검증 |
| **Review C** | review_plit_action | EXPLICIT EVIDENCE VALIDATOR | 문자적 근거·리터럴 grounding 검증 |

### 3.2 공통 규칙 (A/B/C)

- 새 tuple 생성 금지
- conflict_flags 또는 validator_risks에 있는 tuple_id만 대상
- 허용 액션: DROP, MERGE, FLIP, KEEP, FLAG
- 불확실 시: KEEP + FLAG
- 여러 ref가 있어도 DROP 금지: ref가 taxonomy 위반 또는 evidence mismatch일 때만 DROP
- contrast로 인한 polarity 반대: mixed/keep both 고려

### 3.3 에이전트별 세부 규칙

**Review A (P-NEG)**:
- negation: polarity가 올바르게 뒤집혔는지 확인 → 잘못되면 FLIP
- contrast: 양쪽 모두 표현되었는지 확인 → 누락 시 FLAG (CONTRAST_CLAUSE)
- 구조적 문제 없으면 KEEP
- 순수 암시적 케이스만으로 DROP 금지
- 명시적 evidence 부족만으로 DROP 금지

**Review B (P-IMP)**:
- 추론이 약하거나 근거 부족: FLAG (WEAK_INFERENCE)
- aspect_ref 모호: MERGE 또는 FLAG (ASPECT_REF_MISMATCH)
- 추론이 명백히 부당: DROP
- 정당하면 KEEP
- polarity는 추론이 논리적으로 모순될 때만 변경

**Review C (P-LIT)**:
- 명시적 opinion word와 연결: KEEP
- 명시적 evidence 없이 암시적: FLAG (EXPLICIT_NOT_REQUIRED)
- evidence 주장했으나 실제 없음: DROP (WEAK_EVIDENCE)
- 유효한 암시적 추론 덮어쓰지 않음
- 문자적 grounding 오류만 대상

### 3.4 ReviewActionItem 스키마

- action_type: DROP | MERGE | FLIP | KEEP | FLAG
- target_tuple_ids: [tuple_id]
- new_value: (optional) FLIP 시 {"polarity": "..."}, MERGE 시 {"normalized_ref": "..."}
- reason_code: 표준 코드
- actor: "A" | "B" | "C"

---

## 4. 충돌 플래깅 (Conflict Flagging) Read/Write 양식

### 4.1 Write (생성)

**위치**: `agents/conflict_review_runner._compute_conflict_flags`

**입력**: candidates (List[Dict]), conflict_mode, semantic_conflict_enabled

**출력**: List[Dict] — flags

### 4.2 Flag 구조 (Write 양식)

**Primary (aspect_ref 기준)**:

```json
{
  "aspect_ref": "제품 전체#품질",
  "aspect_term": "품질",
  "tuple_ids": ["t0", "t1", "t2"],
  "conflict_type": "ref_polarity_mismatch"
}
```

- **조건**: 동일 aspect_ref에 대해 polarity가 2개 이상
- **conflict_mode**: "primary" | "primary_secondary"

**Secondary (aspect_term 기준, ref 비어 있을 때)**:

```json
{
  "aspect_ref": "",
  "aspect_term": "품질",
  "tuple_ids": ["t0", "t1"],
  "conflict_type": "term_polarity_mismatch"
}
```

- **조건**: conflict_mode가 "primary_secondary"이고, ref가 비어 있는 tuple들 중 동일 aspect_term에 서로 다른 polarity

**Semantic (선택)**:

```json
{
  "aspect_ref": "제품 전체#품질",
  "aspect_term": "품질A|품질B",
  "tuple_ids": ["t0", "t1"],
  "conflict_type": "semantic_conflict_candidate"
}
```

- **조건**: semantic_conflict_enabled=True, 동일 ref, 반대 polarity, OTE 유사도 ≥ θ(0.6)

### 4.3 Read (리뷰 프롬프트 주입)

**위치**: `review_agents._run_review` → `conflict_flags_json`

```python
conflict_flags_json = json.dumps(conflict_flags, ensure_ascii=False)
```

**프롬프트 변수**: `{conflict_flags_json}`

리뷰에 전달되는 JSON: 위의 flags 배열 그대로 문자열화.

---

## 5. 참조 요약

| 항목 | 파일 |
|------|------|
| Arbiter | `conflict_review_runner._arbiter_vote`, `review_arbiter_action.md` |
| 에피소드 메모리 Read | `episodic_orchestrator.py`, `memory/advisory_builder.py`, `injection_controller.py` |
| 에피소드 메모리 Write | `episodic_orchestrator.append_episode_if_needed`, `schemas/memory_v1_1.py` |
| 리뷰 에이전트 | `review_pneg_action.md`, `review_pimp_action.md`, `review_plit_action.md` |
| 충돌 플래깅 | `conflict_review_runner._compute_conflict_flags` |
