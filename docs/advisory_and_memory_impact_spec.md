# Advisory 및 Memory Impact 스펙 (작업 1~5 정의)

## 작업 1) Anchor advisory — mode_decision 노출 제거

**대상**: ConfidenceAnchor.get_anchor_advisory() / _generate_advisory()  
**변경**:
- **mode_decision 출력 제거** (라벨 힌트 노출 금지)
- 메시지는 "일관성/분산/재점검 체크리스트" 중심으로 산출
- **advisory['evidence']**: consistency / variance / n 만 포함 (예: stats.consistency_score, stats.variance, stats.historical_count)

**산출**: Anchor용 evidence에는 `source_episode_ids`, `risk_tags`, `principle_id`, `stats: { historical_count, consistency_score, variance }` 만 사용. mode_decision 필드 없음.

---

## 작업 2) Successful/Failed advisory — gold/accuracy 문구 제거

**대상**: apply_successful_pattern(), avoid_failed_pattern()  
**변경**:
- **accuracy before/after 삭제**
- risk tags / 교정원리 중심으로 치환 산출
- **evidence**: risk_before_tags, risk_after_tags 또는 principle_id 포함

**산출**: evidence에는 `risk_before_tags`, `risk_after_tags`, `principle_id`, `source_episode_ids` 사용. "accuracy", "correct/incorrect", "gold" 문구 없음.

---

## 작업 3) Stage2 통합 출력 스키마 — memory_advisory_impact 제거

**대상**: _stage2_integration_advisory_only()의 final_prompt와 파서  
**변경**:
- **output schema에서 memory_advisory_impact 삭제**
- **accepted_changes / rejected_changes 의 reasoning 필수화**
- 로그에 **advisories_present: bool**, **advisories_ids: [...]** 별도 기록

**산출**: Stage2 통합 출력에는 memory_advisory_impact 없음. accepted_changes/rejected_changes 각 항목에 change_id, reasoning 필수. 메타 로그: advisories_present, advisories_ids.

---

## 작업 4) MemoryImpactAnalysis — risk delta 기반

**대상**: MemoryImpactAnalysis.analyze_advisory_impact()  
**변경**:
- **decision['correct'] 의존 제거** (메인 분석에서 정답 기준 사용 금지)
- risk_before/after와 followed/ignored로 통계 산출

**산출 메트릭**:
- **follow_rate**: 권고를 따른 비율 (followed / (followed + ignored))
- **mean_delta_risk_followed**: 권고 따른 케이스의 평균 risk 감소량 (risk_before - risk_after)
- **mean_delta_risk_ignored**: 권고 무시한 케이스의 평균 risk 변화
- **harm_rate_followed**: 권고 따른 케이스 중 harm 비율 (harm 플래그 기준)
- **harm_rate_ignored**: 권고 무시한 케이스 중 harm 비율

메모리 영향 분석은 **자기보고가 아니라 로그 기반 사후 계산**.

---

## 작업 5) 조건(C1/C2/C2-silent) — 슬롯 고정 + 호출 경로 고정

**대상**: 오케스트레이터(파이프라인)에서 DEBATE_CONTEXT__MEMORY 생성부  
**변경**:
- **C1도 동일 슬롯 주입** (빈 값; slot 구조 동일)
- **C2_silent**는 retrieval 수행 후 결과를 마스킹(0개 주입)

**산출**:
- 각 run에 **memory_mode: off | on | silent** 기록
- token/round 동일성 점검 로그

**현재 반영**: InjectionController(memory/injection_controller.py)와 conditions_memory_v1_1.yaml이 이미 슬롯 고정 및 C1/C2/C2_silent 마스킹을 정의함. 파이프라인 연동 시 run_meta.condition(C1/C2/C2_silent) 및 memory_mode 기록만 추가하면 됨.

---

## 스키마 요약 (v1.1)

- **Advisory evidence (Anchor)**: consistency, variance, n(stats) 중심; mode_decision 없음.
- **Advisory evidence (Successful/Failed)**: risk_before_tags, risk_after_tags, principle_id; accuracy/gold 없음.
- **Stage2 통합 출력**: memory_advisory_impact 없음; accepted_changes/rejected_changes.reasoning 필수; advisories_present, advisories_ids 로그.
- **CaseTrace / run 로그**: memory_mode, condition, seed, config_hash 기록.
