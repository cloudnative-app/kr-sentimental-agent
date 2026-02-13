# Advisory 주입 게이트 (C2)

C2에서 메모리(advisory)를 debate prompt에 넣을 때 **불필요한 케이스까지 흔들지 않도록** 게이팅을 적용한다.

---

## 규칙 (OR)

Advisory를 **주입**하는 것은 다음 네 조건 중 **하나라도 만족할 때만** 한다.

| 조건 | 의미 |
|------|------|
| **polarity_conflict_raw == 1** | Stage1 aspect_sentiments에서 동일 aspect_term에 극성이 2종 이상 (충돌) |
| **validator_s1_risk_ids not empty** | Stage1 Validator structural_risks가 1건 이상 |
| **alignment_failure_count >= 2** | ATE filtered 기준 alignment_failure drop이 2건 이상 |
| **explicit_grounding_failure bucket** | 해당 샘플이 explicit_grounding_failure 케이스 (런타임 근사: 모든 drop이 alignment_failure) |

위 네 가지를 **OR**로 묶어서, 하나라도 참이면 주입, 모두 거짓이면 **주입하지 않음** (slot은 비움).

---

## 구현 위치

- **판단**: `memory/advisory_injection_gate.py` — `should_inject_advisory(text, stage1_ate, stage1_atsa, stage1_validator)`
- **적용**: `agents/supervisor_agent.py` — C2일 때 `exposed_to_debate and slot_dict and gate_ok`일 때만 `debate_context`에 slot 병합

게이트에 걸려서 주입이 막힌 경우 `memory_meta["advisory_injection_gated"] = True` 로 기록한다 (trace/scorecard에서 확인 가능).

---

## 런타임 근사

- **polarity_conflict_raw**: Stage1 `aspect_sentiments`만 사용 (최종 tuple 없이 동일 정의).
- **alignment_failure_count**: `scorecard_from_smoke`와 동일한 규칙으로 stage1_ate + text로 filtered를 계산해 alignment_failure drop 수를 센다 (`memory/advisory_injection_gate.py` 내부 로직).
- **explicit_grounding_failure bucket**: 파이프라인 런타임에는 `sentiment_judgements`가 없으므로, “모든 aspect가 drop이고, 그 drop이 전부 alignment_failure”인 경우를 explicit_grounding_failure 버킷 근사로 사용한다.

---

## 관련 문서

- **조건 정의**: `docs/c1_c2_c3_condition_definition.md`
- **메모리 규칙 요약**: `docs/memory_rule_changes_summary.md`
- **RQ1 grounding / drop_reason**: `docs/metric_spec_rq1_grounding_v2.md`, `scripts/structural_error_aggregator.py` (risk_flagged, triptych)
