# 논문에 사용한 메트릭 (Outcome vs Process)

논문 RQ 결론은 **Outcome (RQ)** 지표만으로 주장한다. Process 지표는 Validator 수준 진단용이며 outcome-level 오류 감소로 해석하지 않는다.

- **공식 메트릭 정의·집계 공식**: `docs/official_metrics.md` (Official). polarity_repair_rate / polarity_invalid_rate 미집계, override_hint_invalid_rate 등.

---

## 논문 메트릭 분류 표 (최종 기준)

| Category | Metric | Role |
|----------|--------|------|
| **Outcome (RQ)** | SeverePolarityErrorRate (L3) | 핵심 |
| **Outcome (RQ)** | polarity_conflict_rate | 핵심 |
| **Outcome (RQ)** | generalized_f1@0.95 | 보수적 보조 |
| **Outcome (RQ2)** | tuple_agreement_rate | 핵심 |
| **Outcome (RQ)** | tuple_f1_s2_explicit_only | Gold 기준 F1 (explicit만; primary quality metric) |
| **Outcome (RQ)** | tuple_f1_s2_overall | Gold 기준 F1 전체 (참고용) |
| **Process** | risk_resolution_rate / validator_clear_rate | 진단 (Validator-level; not outcome) |
| **Process** | validator_residual_risk_rate | 내부 점검 |

---

## Outcome (RQ) 정의 요약

- **severe_polarity_error_L3_rate**: Aspect boundary는 gold와 매칭, polarity만 불일치. L4/L5 제외 (보수적).
- **polarity_conflict_rate**: 동일 aspect span 내 대표 선택 후에도 상충 극성이 남는 비율.
- **generalized_f1_theta** (θ=0.95): Neveditsin et al. (NAACL-SRW 2025) 변형. embedding + Hungarian, θ=0.95 고정. (구현은 stub; embedding 미사용 시 N/A.)
- **tuple_agreement_rate**: 동일 입력 N회 실행 시 최종 튜플 집합이 완전 일치하는 비율. n_trials≥2일 때만 산출.
- **tuple_f1_s2_explicit_only**: Explicit gold만 사용한 Tuple F1 (메인 성능 지표). Implicit 케이스는 다른 추론 태스크이므로 별도.
- **tuple_f1_s2_overall**: 전체 gold(implicit+explicit) 기준 Tuple F1 (참고용).

**논문 방어 문장**:  
"We report explicit-only tuple F1 as the primary quality metric, since implicit cases constitute a different inference task."

---

## Process 지표 문구 (리포트 툴팁)

- **risk_resolution_rate** / **validator_clear_rate**:  
  "Validator-level diagnostic. Not an outcome metric. This metric reflects validator-level resolution and is not interpreted as an outcome-level error reduction."

---

## 산출 위치

- **Aggregator**: `scripts/structural_error_aggregator.py` — Outcome 키는 CANONICAL_METRIC_KEYS 상단, Process는 그 다음.
- **테이블**: `structural_metrics_table.md` — **Outcome Metrics (RQ)** / **Process Control Metrics (Internal)** 섹션 구분.
- **리포트**: `scripts/build_metric_report.py` — KPI 및 RQ3 테이블에 Outcome / Process 시각적 분리, Process 행에 tooltip.
