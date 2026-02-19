# CR Break Root Cause Analysis Report

**Source**: C:\Users\wisdo\Documents\kr-sentimental-agent\results\cr_v2_n100_m0_v4_aggregated\merged_scorecards.jsonl

---

## 1. S1✓ S2✗ 샘플 20개 추출 및 원인 분류

---

## 2. 액션 유형별 break 기여도

| 액션 | break 건수 | 비율 (%) |
|------|------------|----------|
| DROP | 0 | 0.0% |
| MERGE | 0 | 0.0% |
| FLIP (polarity 변경) | 0 | 0.0% |
| 기타 (대표선택 등) | 0 | 0.0% |

---

## 3. Implicit vs Explicit F1

| 구분 | S1 F1 | S2 F1 | Δ |
|------|-------|-------|---|
| explicit | 0.4075 | 0.3960 | -0.0115 |
| implicit | 0.9144 | 0.9352 | +0.0208 |

**해석**: explicit/implicit 하락 패턴 확인

---

## 4. Review action과 correctness 관계

| 구분 | 건수 | 비율 (changed 대비) |
|------|------|---------------------|
| changed ∧ improved | 19 | 100.0% |
| changed ∧ degraded | 0 | 0.0% |

**changed 총계**: 19 (전체 300 중)

---

## 5. 요약

- **break_rate**: 0.00% (n_break=0, n_keep=79)
- **break 원인 1순위**: DROP 0.0%, MERGE 0.0%, FLIP 0.0%
- **changed∧degraded**: 0.0% (변경된 샘플 중)
