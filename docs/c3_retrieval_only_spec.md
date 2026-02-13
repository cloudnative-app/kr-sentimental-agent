# C3 (retrieval-only) 동작 명세

C3는 **retrieval-only** 조건이다: 메모리 검색은 수행(비용/지연/컨텍스트 길이 영향 유지)하되 **프롬프트에 넣지 않음**.

---

## 요구 사항

| 항목 | 요구 | 구현 |
|------|------|------|
| Retrieval 수행 | store.load + retriever.retrieve 실행 | C2_silent: `retrieval_execute: true` → orchestrator에서 동일 경로 실행 |
| 비용/지연 유지 | C2와 동일한 retrieval 경로로 비용·지연 발생 | store load, retriever.retrieve 호출 유지 |
| 프롬프트 미주입 | debate context에 DEBATE_CONTEXT__MEMORY 미포함 | supervisor: `exposed_to_debate=false` 시 `slot_dict`를 context에 병합하지 않음 |

---

## 코드 경로

1. **conditions_memory_v1_1.yaml**  
   - C2_silent: `retrieval_execute: true`, `injection_mask: true`, `store_write: true`

2. **memory/episodic_orchestrator.py**  
   - `get_slot_payload_for_current_sample`: C2_silent일 때 retrieval 실행(store.load, retriever.retrieve), `injection_mask=True`로 advisories=[] → slot은 생성하나 retrieved=[]  
   - `memory_meta["exposed_to_debate"] = False` (C2만 True)

3. **agents/supervisor_agent.py**  
   - `exposed_to_debate and slot_dict`일 때만 `debate_context`에 slot 병합  
   - C3에서는 `exposed_to_debate=False`이므로 **병합하지 않음** → debate prompt의 context_json에 DEBATE_CONTEXT__MEMORY 키 없음

4. **검증 필드 (scorecard/trace)**  
   - `memory.retrieved_k`, `memory.retrieved_ids`: retrieval 수행 결과 기록  
   - `memory.exposed_to_debate`: C3에서는 false  
   - `memory.prompt_injection_chars`: C3에서는 0  

C3 실행 시 `exposed_to_debate=false`, `prompt_injection_chars=0`이면 retrieval-only가 정상 동작한 것이다.
