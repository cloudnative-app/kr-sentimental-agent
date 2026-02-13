# 에피소드 메모리 파이프라인 검토

읽기(검색) 시점·쓰기 시점·주입 대상 등 파이프라인 내 에피소드 메모리 관련 설정을 정리한다.

---

## 1. 질문: 읽기가 토론 단계에서만 가능한가?

**예. 검색(retrieval)은 샘플당 1회, 토론(Debate) 직전에만 수행된다.**

| 항목 | 내용 |
|------|------|
| **호출 위치** | `SupervisorAgent.run()` 내, `enable_debate` 블록, **debate.run() 직전** |
| **호출 함수** | `EpisodicOrchestrator.get_slot_payload_for_current_sample()` |
| **호출 횟수** | 샘플당 **1회** |
| **다른 단계** | Stage1(ATE/ATSA/Validator), Stage2, Moderator에서는 **별도 retrieval 없음** |

Stage2에서 메모리를 쓰는 경우에도 **새 retrieval은 없고**, Debate 직전에 한 번 가져온 `_last_slot_dict`를 재사용한다.

---

## 2. 파이프라인 단계별 메모리 관련 동작

### 2.1 전체 흐름

```
Stage1 (ATE → ATSA → Validator)
    ↓
[메모리 검색 1회] ← get_slot_payload_for_current_sample()
    ↓
Debate (context에 DEBATE_CONTEXT__MEMORY 주입, C2·gate 통과 시)
    ↓
Stage2 (debate_context에 STAGE2_REVIEW_CONTEXT__MEMORY 추가 주입 가능, C2·stage2 gate 시)
    ↓
Moderator
    ↓
[메모리 쓰기 1회] ← append_episode_if_needed() (store_write 시)
```

### 2.2 읽기(Retrieval)

| 시점 | 호출 | 조건 |
|------|------|------|
| **Debate 직전** | `get_slot_payload_for_current_sample(text, stage1_ate, stage1_atsa, stage1_validator, lang)` | `retrieval_execute=true` (C2/C3/C2_eval) |

- **입력**: text, Stage1 결과(ate, atsa, validator), language_code  
- **내부 동작**: SignatureBuilder → store.load() → Retriever.retrieve() → (injection_mask=false면) AdvisoryBuilder → InjectionController  
- **반환**: slot_dict, memory_mode, memory_meta  
- **재사용**: `_last_slot_dict`, `_last_memory_meta`에 저장, Stage2에서 필요 시 참조

### 2.3 주입 대상

| 주입 위치 | 슬롯 키 | 시점 | 조건 |
|------------|---------|------|------|
| **Debate** | DEBATE_CONTEXT__MEMORY | Debate 직전 | C2 & exposed_to_debate & gate_ok |
| **Stage2** | STAGE2_REVIEW_CONTEXT__MEMORY | Stage2 직전 | C2 & should_inject_memory_for_stage2_with_reason |

- Debate: `exposed_to_debate=True`(C2만), `should_inject_advisory_with_reason()` 통과 시 주입  
- Stage2: `_last_slot_dict`를 그대로 `debate_context`(Stage2용)에 추가. **추가 retrieval 없음**

### 2.4 쓰기(Store)

| 시점 | 호출 | 조건 |
|------|------|------|
| **샘플 처리 종료 후** | `append_episode_if_needed(text, text_id, stage1, stage2, moderator_out, …)` | `store_write=true` (C2, C3) |

- **입력**: text, stage1/patched_stage2 결과, moderator_out, moderator_summary  
- **내부**: selective_storage gate → EpisodicMemoryEntryV1_1 구성 → MemoryStore.append()

---

## 3. 코드 호출 위치

| 역할 | 파일:라인 | 설명 |
|------|-----------|------|
| EpisodicOrchestrator 생성 | supervisor_agent.py:147-148 | config.episodic_memory 있으면 생성 |
| **get_slot_payload** (읽기) | supervisor_agent.py:425-428 | Debate 직전, enable_debate 블록 내 |
| Debate context 병합 | supervisor_agent.py:436-461 | exposed_to_debate & gate_ok 시 |
| Stage2 주입 | supervisor_agent.py:481-507 | C2이고 stage2 gate 통과 시 _last_slot_dict 재사용 |
| **append_episode** (쓰기) | supervisor_agent.py:703-709 | final_result 생성 직후, Moderator 이후 |

---

## 4. 조건별 요약

| 조건 | 검색 시점 | 검색 횟수 | Debate 주입 | Stage2 주입 | 쓰기 |
|------|-----------|-----------|------------|-------------|------|
| C1 | 호출 안 함 (retrieval_execute=false) | 0 | 없음 | 없음 | 없음 |
| C2 | Debate 직전 | 1 | ✅ (gate 통과 시) | ✅ (stage2 gate 통과 시) | ✅ |
| C3 | Debate 직전 | 1 | 없음 | 없음 | ✅ |
| C2_eval | Debate 직전 | 1 | 없음 | 없음 | 없음 |

---

## 5. 결론

1. **읽기(검색)**  
   - 파이프라인 전체에서 **Debate 직전 1회**만 호출됨.  
   - Stage1, Stage2, Moderator에서는 별도 retrieval 없음.

2. **주입**  
   - Debate: C2일 때만, gate 통과 시 DEBATE_CONTEXT__MEMORY로 주입.  
   - Stage2: C2일 때만, stage2 gate 통과 시 같은 슬롯을 STAGE2_REVIEW_CONTEXT__MEMORY로 재사용.

3. **쓰기**  
   - Moderator 이후, 샘플 처리 완료 시점에 1회. C2, C3만 수행.

4. **설계 의도**  
   - 메모리는 “토론 직전” 시점의 Stage1 결과를 기준으로 검색.  
   - Stage2는 Debate에서 이미 검색된 advisory를 재사용하여 추가 검색 비용을 피함.
