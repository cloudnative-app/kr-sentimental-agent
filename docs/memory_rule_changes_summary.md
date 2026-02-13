# 메모리 규칙 변화 정리

기존 문서에 기록된 **메모리·어드바이저·조건(C1/C2/C3)** 관련 규칙·스펙·변경사항을 한 문서에 요약한다. 상세는 각 문서 참조.

---

## 1. 관련 문서

| 문서 | 내용 |
|------|------|
| **docs/memory_changes_apply_to_new_runs_only.md** | 메모리 관련 수정은 **새 런에만** 적용; 기존 결과에는 적용 불가 |
| **docs/c1_c2_c3_condition_definition.md** | C1/C2/C3 조건 정의, 실험 설정·플래그·파이프라인 사용 흐름 |
| **docs/c3_retrieval_only_spec.md** | C3(retrieval-only) 동작 명세, 검증 필드 |
| **docs/advisory_and_memory_impact_spec.md** | Advisory·Memory Impact 스펙(작업 1~5) |
| **docs/conditions_memory_v1_1_checklist_report.md** | v1.1 체크리스트 검토, YAML·스키마·구현 모듈 |
| **docs/conditions_memory_go_nogo_checklist.md** | Go/No-Go 체크리스트, 작업 1~6 반영 요약 |
| **docs/advisory_injection_gate.md** | C2 advisory 주입 게이트 (polarity_conflict_raw \| validator_s1_risk \| alignment_failure>=2 \| explicit_grounding_failure) |

---

## 2. 조건별 규칙 (C1 / C2 / C3)

설계값: **experiments/configs/conditions_memory_v1_1.yaml**. EpisodicOrchestrator가 `condition` 이름으로 플래그를 읽는다.

| 조건 | memory_mode | retrieval_execute | injection_mask | store_write | 설명 |
|------|-------------|-------------------|----------------|------------|------|
| **C1** | off | false | true | false | Debate 있음, 메모리 OFF. 슬롯은 비움. |
| **C2** | on | true | false | true | Retrieval 수행 + debate prompt에 advisory 주입 + 에피소드 저장. |
| **C2_silent** (C3) | silent | true | true | true | Retrieval 수행(비용/지연 유지), **프롬프트에는 넣지 않음**. 에피소드 저장. |

- **retrieval_execute**: store.load + retriever.retrieve 실행 여부  
- **injection_mask**: true면 slot의 retrieved를 빈 값으로 만들어 debate에 주입하지 않음  
- **store_write**: 샘플 끝에 에피소드 append 여부  
- **프롬프트 주입**: SupervisorAgent에서 `exposed_to_debate and slot_dict`일 때만 DEBATE_CONTEXT__MEMORY 병합 → **C2만** advisory가 debate에 들어감.

---

## 3. Advisory·메모리 영향 규칙 변화 (작업 1~6)

### 3.1 Anchor advisory (작업 1)

- **mode_decision 출력 제거** (라벨 힌트 노출 금지)
- evidence: **consistency / variance / n** 만 포함; mode_decision 없음

### 3.2 Successful/Failed advisory (작업 2)

- **accuracy before/after, gold/정답 문구 제거**
- evidence: **risk_before_tags, risk_after_tags, principle_id** 중심

### 3.3 Stage2 통합 출력 (작업 3)

- **memory_advisory_impact 삭제**
- **accepted_changes / rejected_changes** 에 **reasoning 필수**
- 로그: **advisories_present**, **advisories_ids**

### 3.4 MemoryImpactAnalysis (작업 4)

- **decision['correct'] 의존 제거** (정답 기준 사용 금지)
- **risk-delta 기반**: follow_rate, mean_delta_risk_followed/ignored, harm_rate_followed/ignored

### 3.5 위험 polarity 조언 금지/강등 (retrieved episode 기반)

- **규칙**: retrieved episode 안에, **동일 aspect_term_norm**에 대해 **“(현재 변경하려는 polarity)로 갔다가 실패/리스크 악화”** 기록이 있으면 → 그 polarity로 바꾸는 조언을 **금지**하거나 **evidence 필수로 강등**한다.
- **의미**: 메모리가 “결정”을 내리는 것이 아니라, 위험한 조언을 프롬프트에 올리지 않거나, 올리더라도 **금지/경고 태그**를 붙이는 수준이다. 논문의 “메모리는 의사결정을 강제하지 않는다” 문장과 충돌하지 않는다.
- **구현**: `memory/advisory_builder.py`
  - **실패/리스크 악화** 판정: `episode_type == "harm"` 또는 `override_applied and (not override_success or override_harm)` 또는 `risk_after.severity_sum > risk_before.severity_sum`
  - **dangerous_pairs**: 위 조건을 만족하는 에피소드들의 `stage_snapshot.final` (aspect_term_norm, polarity) 집합
  - **강등(기본)**: 해당 조언 메시지에 `[경고: 이 조언과 동일한 aspect·polarity 조합으로 과거 실패/리스크 악화 사례가 있습니다. 증거 확인 권장.]` 추가
  - **금지**: `build_from_episodes(..., prohibit_dangerous=True)` 시 해당 조언은 주입 목록에서 제외

### 3.5 슬롯·조건 고정 (작업 5)

- C1/C2/C2_silent 모두 **동일 DEBATE_CONTEXT__MEMORY 슬롯 구조** (C1·C2_silent는 retrieved=[])
- RunMeta: **memory_mode**(off|on|silent), **condition**(C1|C2|C2_silent) 기록

### 3.6 RQ 메트릭 정렬 (작업 6)

- override_success: "정답"이 아니라 **risk 감소 + 안전** 기준
- RQ1: risk/residual/conflict 중심  
- RQ2: agreement/variance/flip-flop  
- RQ3: applied/skipped + success/harm + coverage  
- **docs/rq_metrics_field_mapping.md**, build_metric_report 반영

---

## 4. 적용 범위 (새 런에만)

- **에피소드 스키마 변경**, Advisory 빌드 방식, **C1/C2/C3 플래그**, 모더레이터 규칙, override/debate 설정 등은 **추론 시점(파이프라인 실행 시)** 에만 동작한다.
- 기존 scorecards/traces/outputs에는 **나중에 적용할 수 없음**. 새 동작을 반영하려면 **파이프라인을 다시 실행**해야 한다.
- 집계/리포트만 바꾼 경우(예: structural_metrics 계산, HTML)는 기존 scorecards로 **재집계·리포트만** 재생성 가능.

---

## 5. Advisory 주입 게이트 (C2)

C2에서 advisory를 debate에 넣을 때 **게이팅** 적용: 다음 중 하나라도 만족할 때만 주입 (OR).

- polarity_conflict_raw == 1 (stage1 동일 aspect에 ≥2 극성)
- validator_s1_risk_ids not empty
- alignment_failure_count >= 2
- explicit_grounding_failure bucket (런타임 근사: 모든 drop이 alignment_failure)

구현: `memory/advisory_injection_gate.py` (`should_inject_advisory`), `agents/supervisor_agent.py` (C2 시 slot 병합 전 gate_ok 체크). 상세: **docs/advisory_injection_gate.md**.

---

## 6. 정의·구현 위치 요약

| 항목 | 위치 |
|------|------|
| 조건 플래그 정의 | `experiments/configs/conditions_memory_v1_1.yaml` |
| 조건 로딩·슬롯 생성 | `memory/episodic_orchestrator.py`, `memory/injection_controller.py` |
| Debate에 주입 여부 | `agents/supervisor_agent.py` (`exposed_to_debate` + **advisory_injection_gate**) |
| Advisory 주입 게이트 | `memory/advisory_injection_gate.py` |
| Advisory 빌드·위험 polarity 금지/강등 | `memory/advisory_builder.py` |
| 스키마 v1.1 | `schemas/memory_v1_1.py`, `schemas/json/episodic_memory_entry_v1_1.json` 등 |
| 실험 YAML 조건 | `memory.enable` + `memory.mode` → C1/C2/C2_silent (`run_experiments.py` 매핑) |

---

## 7. C3 검증 필드 (retrieval-only 확인)

- **memory.exposed_to_debate**: C3에서는 false  
- **memory.prompt_injection_chars**: C3에서는 0  
- **memory.retrieved_k**, **memory.retrieved_ids**: retrieval 수행 결과 기록

위가 scorecard/trace에 반영되면 C3(retrieval-only) 동작이 정상이다.
