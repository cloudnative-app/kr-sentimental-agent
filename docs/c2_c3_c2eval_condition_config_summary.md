# C2 / C3 / C2_eval_only 조건 설정 차이 정리

기억(episodic memory) 사용·읽기·쓰기 등 조건별 설정 차이.

---

## 1. 요약 표

| 항목 | C2 | C3 (C2_silent) | C2_eval_only |
|------|----|----------------|--------------|
| **조건 파일** | conditions_memory_v1_1 | conditions_memory_v1_1 | conditions_memory_v1_2 |
| **실험 설정** | `episodic_memory.condition: C2` | `memory.enable: true`, `memory.mode: silent` | `episodic_memory.condition: C2_eval_only` |
| **retrieval_execute** (읽기) | ✅ true | ✅ true | ✅ true |
| **injection_mask** (주입 마스킹) | ❌ false | ✅ true | ✅ true |
| **store_write** (쓰기) | ✅ true | ✅ true | ❌ false |
| **exposed_to_debate** (Debate 프롬프트 주입) | ✅ true | ❌ false | ❌ false |

---

## 2. 상세 설명

### 2.1 retrieval_execute (읽기)

| 조건 | 값 | 의미 |
|------|----|------|
| C2 | true | store load + retriever.retrieve 실행 |
| C3 | true | 동일 |
| C2_eval_only | true | 동일 |

세 조건 모두 **에피소드 저장소에서 검색(retrieval)을 수행**한다. 비용·지연·retrieved_ids 로깅은 공통.

---

### 2.2 injection_mask (Debate 프롬프트에 주입 여부)

| 조건 | 값 | 의미 |
|------|----|------|
| C2 | false | retrieval 결과를 advisory로 빌드하여 **DEBATE_CONTEXT__MEMORY** 슬롯에 채움 → Supervisor가 debate prompt에 병합 |
| C3 | true | advisories=[]로 마스킹 → slot은 생성하나 내용 비움, **Debate에 노출 안 함** |
| C2_eval_only | true | C3와 동일 |

- **injection_mask=false**: 검색된 에피소드 → AdvisoryBuilder → debate context에 주입 (C2만 해당)
- **injection_mask=true**: slot의 retrieved=[] → exposed_to_debate=false → debate prompt에 DEBATE_CONTEXT__MEMORY 미포함

---

### 2.3 store_write (쓰기)

| 조건 | 값 | 의미 |
|------|----|------|
| C2 | true | 샘플 끝에 selective gate 통과 시 **episodic_store.jsonl에 에피소드 1건 append** |
| C3 | true | 동일 |
| C2_eval_only | false | **저장하지 않음** (로그 오염 감소, 평가 전용 ablation) |

- C2, C3: run 중 처리된 샘플이 store에 쌓여 이후 샘플의 retrieval에 영향을 줄 수 있음 (실제론 run 별 store 경로가 다름)
- C2_eval_only: store_write=false → `store_decision=skipped`, `store_skip_reason=store_write_disabled`

---

### 2.4 exposed_to_debate

| 조건 | 값 | 코드 |
|------|----|------|
| C2 | true | `exposed_to_debate = (self.condition == "C2")` |
| C3 | false | condition ≠ C2 |
| C2_eval_only | false | condition ≠ C2 |

SupervisorAgent는 `exposed_to_debate and slot_dict`일 때만 debate_context에 DEBATE_CONTEXT__MEMORY를 병합.  
C2만 true이므로 **C2만 debate에 메모리(advisory)가 노출**된다.

---

## 3. 설정 파일·코드 위치

| 항목 | 위치 |
|------|------|
| 조건 플래그 정의 | `experiments/configs/conditions_memory_v1_1.yaml`, `conditions_memory_v1_2.yaml` |
| 조건 로딩·플래그 적용 | `memory/episodic_orchestrator.py` (`_condition_flags`, `get_slot_payload_for_current_sample`, `append_episode_if_needed`) |
| debate 병합 | `agents/supervisor_agent.py` (`exposed_to_debate`일 때만) |
| C2 실험 | `experiments/configs/beta_n50_c2.yaml` (`episodic_memory.condition: C2`) |
| C3 실험 | `experiments/configs/beta_n50_c3.yaml` (`memory.enable: true`, `memory.mode: silent`) |
| C2_eval_only 실험 | `experiments/configs/beta_n50_c2_eval_only.yaml` (`condition: C2_eval_only`, `conditions_path: .../conditions_memory_v1_2.yaml`) |

---

## 4. 한 줄 비교

| 조건 | 한 줄 |
|------|-------|
| **C2** | 기억 **읽기 + Debate 주입 + 쓰기** (full memory) |
| **C3** | 기억 **읽기 + 쓰기**, Debate 주입 없음 (retrieval-only control) |
| **C2_eval_only** | 기억 **읽기만**, Debate 주입 없음, 쓰기 없음 (평가 전용 ablation) |

---

## 5. conditions YAML 원문 (v1_2)

```yaml
# C2
  C2:
    episodic_memory:
      memory_mode: "on"
      retrieval_execute: true
      injection_mask: false
      store_write: true

# C3 (C2_silent)
  C2_silent:
    episodic_memory:
      memory_mode: "silent"
      retrieval_execute: true
      injection_mask: true
      store_write: true

# C2_eval_only (v1_2만)
  C2_eval_only:
    episodic_memory:
      memory_mode: "silent"
      retrieval_execute: true
      injection_mask: true
      store_write: false
```
