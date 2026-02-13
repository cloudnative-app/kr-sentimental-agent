# Conflict Review v1: 메모리 설정·에피소드 메모리 부재·Validator 기능 흡수 보고

---

## 1. 메모리 설정 (M0/M1/M2)과 conflict_review_v1 동작

### 1.1 M0/M1/M2와 conditions 매핑

| 설정 | conditions | retrieval_execute | injection_mask | store_write | 설명 |
|------|------------|-------------------|----------------|-------------|------|
| **M0** | C1 | false | true | false | 메모리 OFF (retrieve/store 모두 없음) |
| **M1** | C2_eval_only, C2_silent | true | true | false(C2_eval) / true(C2_silent) | read-only retrieve (주입 마스킹) |
| **M2** | C2 | true | false | true | retrieve + inject + write(최종 post 저장) |

### 1.2 conflict_review_v1에서의 실제 동작

**핵심: conflict_review_v1는 `episodic_memory` 설정을 전혀 사용하지 않습니다.**

```
SupervisorAgent.run(example):
  if protocol_mode == "conflict_review_v1":
      return run_conflict_review_v1(...)   # ← 여기서 즉시 return
  # 아래 코드는 실행되지 않음
  stage1 = self._run_stage1(...)
  if self._episodic_orchestrator:        # ← EpisodicOrchestrator 호출 없음
      slot_dict, _, memory_meta = self._episodic_orchestrator.get_slot_payload_for_current_sample(...)
  ...
  if self._episodic_orchestrator:
      self._episodic_orchestrator.append_episode_if_needed(...)  # ← store_write 호출 없음
```

- `run_conflict_review_v1`는 `agents/conflict_review_runner.py`에서만 실행되며, **EpisodicOrchestrator를 import/호출하지 않음**.
- config의 `episodic_memory.condition: C1`(또는 C2/C3)는 **conflict_review 경로에서는 읽히지 않음**.
- 따라서 M0/M1/M2 설정과 무관하게 **항상 메모리 없음(none)**으로 동작합니다.

### 1.3 에피소드 메모리가 없다고 나오는 이유

1. **경로 분기**: `protocol_mode == "conflict_review_v1"`일 때 `SupervisorAgent`는 legacy 경로(stage1/debate/stage2/moderator)를 타지 않고 바로 `run_conflict_review_v1` 결과를 반환합니다.
2. **EpisodicOrchestrator 미호출**: EpisodicOrchestrator는 `SupervisorAgent` __init__에서 `episodic_cfg`로 생성되지만, conflict_review 경로에서는 `get_slot_payload_for_current_sample`, `append_episode_if_needed`가 한 번도 호출되지 않습니다.
3. **meta.memory 부재**: conflict_review_runner는 `meta`에 `memory`를 넣지 않습니다. `meta = { input_text, run_id, text_id, mode, protocol_mode, ... }`만 설정합니다.
4. **scorecard 기본값**: `make_scorecard`는 `meta.memory`가 없으면 `mem = {}`로 두고, `retrieved_k=0`, `exposed_to_debate=False` 등 기본값을 사용합니다. 그래서 “에피소드 메모리가 없다”로 보입니다.

**결론**: conflict_review_v1에서 config의 episodic_memory(M0/M1/M2)는 **무시**되며, 에피소드 메모리는 항상 OFF 상태입니다.

---

## 2. Legacy Validator 기능의 흡수 위치

### 2.1 Legacy Validator 역할

| 기능 | 산출물 | 용도 |
|------|--------|------|
| structural_risks | NEGATION_SCOPE, CONTRAST_CLAUSE, IMPLICIT_ASPECT, ASPECT_REF_MISMATCH 등 | Stage2 ATE/ATSA 프롬프트에 포함 |
| correction_proposals | FLIP_POLARITY, DROP_ASPECT, REVISE_SPAN | `_apply_stage2_reviews`에서 코드로 적용 |

### 2.2 conflict_review_v1에서의 위치

**conflict_review_v1에는 별도 Validator 에이전트가 없습니다.** 대신 다음처럼 역할이 나뉘어 있습니다.

#### (1) 구조적 위험 탐지 → `_compute_conflict_flags` + Review 프롬프트

| Legacy Validator | conflict_review_v1 |
|-----------------|---------------------|
| structural_risks (polarity 충돌 등) | `_compute_conflict_flags(candidates)` → `conflict_flags` |
| 기타 risk 타입 | Review 에이전트 프롬프트에 역할로 인코딩 |

- `_compute_conflict_flags`: 동일 aspect_term에 서로 다른 polarity가 있으면 `polarity_mismatch`로 플래그.
- `validator_risks`는 **항상 빈 리스트 `[]`**로 전달되며, Legacy Validator의 structural_risks가 대체되지 않음.

#### (2) 교정 제안 → Review A/B/C + Arbiter

| Legacy Validator | conflict_review_v1 |
|-----------------|---------------------|
| correction_proposals (FLIP_POLARITY, DROP_ASPECT, REVISE_SPAN) | Review A/B/C의 `review_actions` (DROP, FLIP, MERGE, KEEP) |
| 코드로 적용 | `_apply_review_actions(candidates, arb.review_actions)` |

- Legacy: Validator의 proposal을 `_apply_stage2_reviews`에서 코드로 적용.
- conflict_review: Review A/B/C가 제안한 actions를 Arbiter가 합의한 뒤, `_apply_review_actions`에서 코드로 적용.

### 2.3 역할별 수행 위치

| 역할 | 수행 위치 | 비고 |
|------|-----------|------|
| polarity conflict 탐지 | `conflict_review_runner._compute_conflict_flags` | automated, LLM 없음 |
| negation/contrast 보정 | Review A (P-NEG) 프롬프트 | `review_pneg_action` |
| implicit aspect/aspect_ref | Review B (P-IMP) 프롬프트 | `review_pimp_action` |
| explicit evidence/중복 제거 | Review C (P-LIT) 프롬프트 | `review_plit_action` |
| 최종 교정 제안 | Arbiter | `review_arbiter_action` |
| 실제 적용 | `_apply_review_actions` | DROP/FLIP/MERGE/KEEP |

### 2.4 Legacy Validator와의 차이

- Legacy Validator: rule/pattern 기반으로 structural_risks와 correction_proposals를 **구조적으로** 생성.
- conflict_review: `conflict_flags`는 rule 기반, 교정은 **Review A/B/C + Arbiter LLM**이 담당.
- `validator_risks`는 conflict_review에서 항상 `[]`이므로, Legacy Validator의 structural_risks는 conflict_review 경로에 **직접 연결되지 않음**.

---

## 3. 요약

| 항목 | conflict_review_v1 |
|------|---------------------|
| episodic_memory (M0/M1/M2) | **사용 안 함** (config 무시) |
| EpisodicOrchestrator | **호출 안 함** |
| meta.memory | **설정 안 함** |
| scorecard memory | retrieved_k=0, exposed_to_debate=False (기본값) |
| Legacy Validator | **별도 에이전트 없음** |
| conflict 탐지 | `_compute_conflict_flags` |
| 교정 제안 | Review A/B/C + Arbiter |
| 교정 적용 | `_apply_review_actions` |
