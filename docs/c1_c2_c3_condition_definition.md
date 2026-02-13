# C1 / C2 / C3 조건 정의 (파이프라인 설계값)

실험에서 메모리 조건을 지정하는 방법과, 파이프라인 내부에서 C1/C2/C3가 어떻게 정의·사용되는지 정리한다.

---

## 1. 실험 설정에서 조건 지정 (두 가지 방식)

### 방식 A: `episodic_memory.condition` (직접 지정)

실험 YAML에서 조건 이름을 직접 준다.

```yaml
episodic_memory:
  condition: C1   # 또는 C2, C2_silent
```

- **C1**: 메모리 OFF (b1 스타일)
- **C2**: 메모리 ON, advisory 노출 (proposed 스타일)
- **C2_silent**: C3. retrieval-only (retrieval 수행, 프롬프트 미주입)

**예**: `experiment_real_b1.yaml`, `experiment_real_proposed.yaml`

---

### 방식 B: `memory.enable` + `memory.mode` (도메인 옵션)

실험 YAML에서 `memory` 블록으로 켜기/모드만 주면, run_experiments가 `episodic_memory.condition`으로 변환한다.

```yaml
memory:
  enable: true    # false면 C1
  mode: silent    # advisory | silent. enable=false면 mode 무시 → C1
```

**매핑** (`experiments/scripts/run_experiments.py`):

| memory.enable | memory.mode | → condition   |
|---------------|-------------|---------------|
| false         | (무시)      | **C1**        |
| true          | advisory    | **C2**        |
| true          | silent      | **C2_silent** (C3) |

**예**: `experiment_mini4_c3_silent.yaml`, `experiment_real_n100_seed1_c1/c2/c3.yaml`

---

## 2. 조건별 설계값 (conditions_memory_v1_1.yaml)

실제 동작 플래그는 `experiments/configs/conditions_memory_v1_1.yaml`의 `conditions` 아래에 정의되어 있다.  
EpisodicOrchestrator는 `condition` 이름으로 이 파일을 읽어 `_flags`를 채운다.

| 조건       | memory_mode | retrieval_execute | injection_mask | store_write | 설명 |
|------------|-------------|-------------------|----------------|------------|------|
| **C1**     | off         | false             | true           | false      | Debate는 있음, 메모리 OFF. 슬롯은 비움. |
| **C2**     | on          | true              | false          | true       | Retrieval 수행 + debate prompt에 advisory 주입 + 에피소드 저장. |
| **C2_silent** (C3) | silent | true              | true           | true       | Retrieval 수행(비용/지연 유지), 프롬프트에는 넣지 않음. 에피소드 저장. |

- **retrieval_execute**: store.load + retriever.retrieve 실행 여부  
- **injection_mask**: true면 slot의 retrieved를 빈 값으로 만들어, supervisor가 병합해도 내용 없음; **supervisor는 `exposed_to_debate`로만 병합 여부 결정** (C2일 때만 병합).  
- **store_write**: 샘플 끝에 에피소드 append 여부  

---

## 3. 파이프라인에서의 사용 흐름

1. **run_experiments.py**  
   - 실험 YAML의 `memory` 또는 `episodic_memory`를 읽어  
   - `pipeline_cfg["episodic_memory"]`에 `condition: "C1"|"C2"|"C2_silent"` 를 넣고  
   - 이 config로 runner(SupervisorAgent) 생성.

2. **SupervisorAgent**  
   - `config.get("episodic_memory")`로 EpisodicOrchestrator를 만들 때  
   - `episodic_memory.condition`을 그대로 전달.

3. **EpisodicOrchestrator** (`memory/episodic_orchestrator.py`)  
   - `self.condition = config.get("condition") or "C1"` (C1/C2/C2_silent만 허용)  
   - `conditions_memory_v1_1.yaml`을 로드해 `_condition_flags(conditions_cfg, self.condition)`으로  
     `retrieval_execute`, `injection_mask`, `store_write` 를 가져옴.  
   - `get_slot_payload_for_current_sample()`:  
     - `_flags["retrieval_execute"]`이면 retrieval 실행  
     - `_flags["injection_mask"]`이면 advisories=[] 로 slot 생성  
     - `exposed_to_debate = (self.condition == "C2")` → C2일 때만 true.

4. **InjectionController** (`memory/injection_controller.py`)  
   - C1/C2/C2_silent에 따라 `memory_mode`, `retrieval_executed`, `injection_mask`를 정하고  
   - slot(DEBATE_CONTEXT__MEMORY) JSON 생성.  
   - 실제 “프롬프트에 넣을지”는 orchestrator가 아니라 **supervisor**에서 결정.

5. **SupervisorAgent (debate 직전)**  
   - `slot_dict, _, memory_meta = orchestrator.get_slot_payload_for_current_sample(...)`  
   - **`exposed_to_debate and slot_dict`일 때만** `debate_context`에 slot_dict 병합.  
   - C1·C2_silent는 `exposed_to_debate=False` 이므로 **debate prompt에 DEBATE_CONTEXT__MEMORY가 들어가지 않음.**

---

## 4. 요약 표

| 조건 | 실험 설정 예 | retrieval | prompt 주입 | store_write |
|------|----------------|-----------|-------------|-------------|
| **C1** | episodic_memory.condition: C1 / memory.enable: false | 하지 않음 | 하지 않음 | 하지 않음 |
| **C2** | episodic_memory.condition: C2 / memory.enable: true, mode: advisory | 함 | 함 | 함 |
| **C3** (C2_silent) | episodic_memory.condition: C2_silent / memory.enable: true, mode: silent | 함 | 하지 않음 | 함 |

- **설계값 정의 위치**: `experiments/configs/conditions_memory_v1_1.yaml`  
- **조건 이름 → 플래그 로딩**: `memory/episodic_orchestrator.py` (`_condition_flags`)  
- **프롬프트 주입 여부**: `agents/supervisor_agent.py` (`exposed_to_debate`일 때만 context에 병합)
