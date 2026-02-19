# CR Break Root Cause Analysis Report

**Source**: C:\Users\wisdo\Documents\kr-sentimental-agent\results\cr_v2_n100_m1_v4__seed123_proposed\scorecards.jsonl

---

## 1. S1✓ S2✗ 샘플 20개 추출 및 원인 분류

### 1. nikluge-sa-2022-train-01649

- **input_text**: 리무버 없이 물로도 지울 수 있어 손톱 손상이 없어요~
- **원인**: **polarity_change**
- **arb_actions**: ['KEEP', 'KEEP', 'FLIP']
- gold_n=1, s1_n=2, s2_n=3

---

## 2. 액션 유형별 break 기여도

| 액션 | break 건수 | 비율 (%) |
|------|------------|----------|
| DROP | 0 | 0.0% |
| MERGE | 0 | 0.0% |
| FLIP (polarity 변경) | 1 | 100.0% |
| 기타 (대표선택 등) | 0 | 0.0% |

---

## 3. Implicit vs Explicit F1

| 구분 | S1 F1 | S2 F1 | Δ |
|------|-------|-------|---|
| explicit | 0.4333 | 0.4121 | -0.0212 |
| implicit | 0.9097 | 0.9236 | +0.0139 |

**해석**: explicit/implicit 하락 패턴 확인

---

## 4. Review action과 correctness 관계

| 구분 | 건수 | 비율 (changed 대비) |
|------|------|---------------------|
| changed ∧ improved | 6 | 85.7% |
| changed ∧ degraded | 1 | 14.3% |

**changed 총계**: 7 (전체 100 중)

---

## 5. 요약

- **break_rate**: 3.45% (n_break=1, n_keep=28)
- **break 원인 1순위**: DROP 0.0%, MERGE 0.0%, FLIP 100.0%
- **changed∧degraded**: 14.3% (변경된 샘플 중)
