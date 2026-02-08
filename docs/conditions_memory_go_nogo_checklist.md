# 조건 메모리 v1.1 — Go/No-Go 체크리스트 (점검 결과)

## 2.2 체크리스트 (Go/No-Go)

### A. 구조 고정 체크

| 항목 | 상태 | 비고 |
|------|------|------|
| C1/C2에서 에이전트 수/역할/토론 위치/Moderator 규칙 동일 | ✅ | conditions_memory_v1_1.yaml: pipeline.stages(ATE→ATSA→DEBATE→MODERATOR), moderator 정책 고정 |
| 프롬프트에 DEBATE_CONTEXT__MEMORY 슬롯이 항상 존재 | ✅ | InjectionController가 3조건 모두 동일 슬롯 구조 생성; C1/C2_silent는 retrieved=[] |
| 토론 라운드 수, stop 조건이 조건 간 동일(메모리로 인해 라운드 증가 금지) | ✅ | YAML global.pipeline.debate.max_rounds: 3 고정; 조건별 차이는 슬롯 내용만 |
| retrieval 호출 유무가 조건 간 결과 해석을 흐리지 않도록 통제(최소 "silent" 조건 포함) | ✅ | C2_silent로 retrieval 실행·주입 마스킹 통제; C1은 retrieval 미실행 |

---

### B. 누수/학습 논란 체크

| 항목 | 상태 | 비고 |
|------|------|------|
| raw input 문장 저장 금지(서명/구조 특징만) | ✅ | MemoryStore forbid_raw_text; EpisodicMemoryEntry에 raw_text 없음 |
| gold label/정답은 프롬프트로 절대 주입되지 않음 | ✅ | 스펙·스키마: gold/정답 주입 금지; evidence에 no_label_hint 강제 |
| "accuracy before→after", "correct/incorrect" 문구가 본문 메모리/권고 메시지에 없음 | ✅ | docs/advisory_and_memory_impact_spec.md: Successful/Failed advisory에서 accuracy 삭제, risk_before_tags/risk_after_tags 중심 |
| 모드결정(mode_decision)과 같은 "라벨 힌트" 노출 없음(권장) | ✅ | 스펙: Anchor advisory에서 mode_decision 출력 제거; evidence는 consistency/variance/n만 |

---

### C. 메트릭 타당성 체크

| 항목 | 상태 | 비고 |
|------|------|------|
| override_success는 "정답"이 아니라 "risk 감소 + 안전"으로 계산 | ✅ | structural_error_aggregator: override_success_rate = 적용 케이스 중 risk 개선 비율(stage2_risks < stage1_risks) |
| RQ1 지표는 risk/residual/conflict 중심으로 계산 | ✅ | risk_flagged_rate, residual_risk_rate, risk_resolution_rate (docs/rq_metrics_field_mapping.md) |
| RQ2는 반복추론 agreement/variance/flip-flop으로 계산 | ✅ | self_consistency_exact, flip_flop_rate, variance (merged run에서 계산) |
| RQ3는 applied/skipped + success/harm + coverage로 계산 | ✅ | override_applied_rate, override_success_rate, debate_mapping_coverage |
| 메모리 영향 분석은 자기보고가 아니라 로그 기반 사후 계산 | ✅ | docs/advisory_and_memory_impact_spec.md: MemoryImpactAnalysis risk-delta 기반(follow_rate, mean_delta_risk_*, harm_rate_*) |

---

### D. 리포팅/재현성 체크

| 항목 | 상태 | 비고 |
|------|------|------|
| seed, config hash, memory_mode 기록 | ✅ | RunMetaV1_1: seed, condition(C1/C2/C2_silent), memory_mode(off/on/silent); manifest에 cfg_hash 등 |
| memory retrieval top-k, 필터 조건 기록 | ✅ | conditions_memory_v1_1.yaml: retrieval.topk, filters; AdvisoryBundleMetaV1_1: topk |
| 메모리 주입 횟수(one-shot) 기록 | ✅ | YAML debate.injection.allow_multiple_injections: false; 로그에 advisories_present, advisories_ids 스펙 |

---

## 작업 1~6 반영 요약

| 작업 | 반영 내용 |
|------|-----------|
| 1) Anchor advisory | 스펙: mode_decision 제거, evidence=consistency/variance/n. EvidenceV1_1에 risk_before_tags, risk_after_tags, stats(Anchor용) |
| 2) Successful/Failed advisory | 스펙: accuracy/gold 제거, evidence=risk_before_tags, risk_after_tags, principle_id |
| 3) Stage2 통합 | 스펙: memory_advisory_impact 삭제, accepted/rejected reasoning 필수, advisories_present, advisories_ids 로그 |
| 4) MemoryImpactAnalysis | 스펙: decision['correct'] 제거, risk-delta 기반(follow_rate, mean_delta_risk_*, harm_rate_*) |
| 5) 슬롯 고정 | InjectionController + conditions YAML 이미 반영; RunMetaV1_1.memory_mode 추가; 문서화 |
| 6) RQ 메트릭 정렬 | residual_risk_rate, override_applied_rate, override_success_rate, flip_flop_rate, variance 추가; docs/rq_metrics_field_mapping.md, build_metric_report 갱신 |

위 체크리스트 항목은 현재 정의·스키마·스크립트 기준으로 충족된 상태입니다. 실제 ConfidenceAnchor/Stage2 통합/MemoryImpactAnalysis 구현 시 docs/advisory_and_memory_impact_spec.md를 따르면 됩니다.
