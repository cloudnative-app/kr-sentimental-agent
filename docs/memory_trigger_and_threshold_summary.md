# 메모리 트리거 조건 및 역치 설정 요약

"memory ON but never used" 관찰 시 참고용.

---

## 1. CR(Conflict-Review) M1에서 "memory ON but never used" 원인

### 1.1 CR M1 동작

| 항목 | M1 설정 |
|------|---------|
| retrieval_execute | true |
| injection_mask | false |
| store_write | false |
| memory_mode | on |

- `conflict_review_runner.py`가 `episodic_orchestrator.get_slot_payload_for_current_sample()` 호출
- `memory_context = _format_memory_context(slot_dict)` → Review A/B/C에 전달
- **CR 경로에는 advisory injection gate 없음** — retrieval 결과가 있으면 그대로 전달

### 1.2 "never used"가 나오는 이유

1. **스토어가 비어 있음 (가장 흔함)**  
   - M1은 read-only(frozen) — `memory/episodic_store.jsonl`에서 읽기만 함  
   - M2/C2 선행 실행 없이 M1만 돌리면 스토어가 비어 있어 `retrieved_k=0`  
   - `retrieved=[]` → `memory_context=""` → Review 프롬프트에 메모리 미주입

2. **Retriever 필터**  
   - `require_same_language=True`, `require_structure_overlap=True`  
   - 매칭되는 에피소드가 없으면 빈 리스트 반환

3. **AdvisoryBuilder 차단**  
   - `_is_failure_or_risk_worsened` 등으로 일부 에피소드가 advisory 생성에서 제외될 수 있음  
   - 이 경우에도 `retrieved` 자체는 있으나 advisory가 비어 있을 수 있음

### 1.3 해결 방향

- M1 실행 전에 **M2 또는 C2로 스토어를 채우는 선행 실행** 필요  
- 또는 `episodic_memory.store_path`를 이미 채워진 스토어 경로로 지정

---

## 2. Legacy C2 메모리 트리거 조건 (Advisory Injection Gate)

**적용 경로**: `SupervisorAgent` → Debate/Stage2 (Legacy 파이프라인만)  
**CR 경로에는 미적용**

### 2.1 Debate Gate (보수적)

`memory/advisory_injection_gate.py` — `should_inject_advisory_with_reason`:

| 조건 | 역치 | 설명 |
|------|------|------|
| polarity_conflict_raw | 1 | 동일 aspect_term에 ≥2개 서로 다른 polarity |
| validator_s1_risk_ids | not empty | Stage1 Validator structural_risks ≥ 1 |
| alignment_failure_count | **≥ 2** | aspect term–span 정렬 실패 드롭 수 |
| explicit_grounding_failure | bucket | 모든 aspect가 alignment_failure로 드롭 |

**OR 조건**: 위 네 가지 중 하나라도 만족하면 주입.

### 2.2 Stage2 Gate (완화)

`should_inject_memory_for_stage2_with_reason`:

| 조건 | 역치 | 설명 |
|------|------|------|
| validator_s1_risk | not empty | 동일 |
| polarity_conflict_raw | 1 | 동일 |
| alignment_failure_count | **≥ 1** | Debate gate보다 완화 |
| neutral_only | ≤ 1 non-neutral | aspect_sentiments가 거의 전부 neutral |
| explicit_grounding_failure | bucket | 동일 |

### 2.3 CR 경로와의 차이

- CR은 `advisory_injection_gate`를 사용하지 않음  
- CR은 `memory_context`를 gate 없이 Review A/B/C에 직접 전달  
- CR에서 "never used"는 gate 때문이 아니라, **retrieval 결과가 비어 있기 때문**

---

## 3. 관련 역치 설정

### 3.1 conditions YAML (`conditions_memory_v1_1.yaml`, `v1_2`)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| retrieval.topk | 3 | 검색 반환 상위 k개 |
| retrieval.mode | signature_lexical | 검색 모드 |
| retrieval.filters.require_same_language | true | 동일 언어만 |
| retrieval.filters.require_structure_overlap | true | 구조 겹침 필수 |

### 3.2 SupervisorAgent config

| 설정 | 기본 | 설명 |
|------|------|------|
| memory_prompt_injection_chars_cap | None | 0이면 주입 안 함, 300/600/1000 등은 최대 문자 수 |

### 3.3 EpisodicOrchestrator

| 설정 | 기본 | 설명 |
|------|------|------|
| condition | C1 | C1/C2/C2_silent/C2_eval_only/M0/M1/M2 |
| conditions_path | conditions_memory_v1_1.yaml | 조건 정의 파일 |
| store_path | memory/episodic_store.jsonl | 에피소드 스토어 경로 |

### 3.4 exposed_to_debate (Legacy 전용)

`episodic_orchestrator.py` 130행:

```python
exposed_to_debate = self.condition == "C2"
```

- **C2만** `exposed_to_debate=True`  
- M1/M2는 `exposed_to_debate=False` (Legacy Supervisor 경로 기준)  
- CR은 이 플래그를 사용하지 않고, `memory_context`를 직접 Review에 전달

---

## 4. 요약

| 구분 | CR M1 | Legacy C2 |
|------|-------|-----------|
| 메모리 트리거 | 없음 (retrieval 결과 있으면 그대로 사용) | advisory injection gate (4가지 OR) |
| "never used" 주된 원인 | 스토어 비어 있음 (retrieved_k=0) | gate 미통과 또는 retrieved=0 |
| 역치 | topk=3, retriever 필터 | alignment_failure ≥2(Debate), ≥1(Stage2) |
| store_write | M1: false, M2: true | C2: true |

**CR M1에서 메모리를 쓰려면**: M2/C2로 먼저 스토어를 채운 뒤 M1을 실행하거나, 이미 채워진 스토어 경로를 지정해야 함.
