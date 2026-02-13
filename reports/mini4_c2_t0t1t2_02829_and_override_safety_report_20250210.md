# Mini4 C2 T0/T1/T2 검증 보고서 (20250209 결과 기준)

**대상:** nikluge-sa-2022-train-02829 / aspect **피부톤**, 및 T0/T1/T2 전 구간 override·low_signal·safety 지표.

**결과 경로:** `results/experiment_mini4_validation_c2_{t0,t1,t2}_proposed/` (override_gate_debug_summary.json, override_gate_debug.jsonl, scorecards.jsonl, derived/metrics/structural_metrics.csv).

---

## 1. 샘플 02829 / 피부톤 상세

### 1.1 조건 (A): hints=3개 이상이면 최소 1개는 pos/neg

| Run | aspect_hints 개수 (피부톤) | pos/neg 개수 | 충족 |
|-----|---------------------------|--------------|------|
| T0  | 2 (EPM neutral, CJ neutral) | 0 | N/A (hints&lt;3) / 조건 미충족 |
| T1  | 4 (EPM neutral, CJ neg/neu/neg) | 2 (negative) | ✓ |
| T2  | 4 (동일 구조) | 2 (negative) | ✓ |

- **T0:** rebuttal은 EPM pos, TAN neu, CJ neg이지만 **aspect_hints**에는 EPM·CJ만 매핑되고 둘 다 neutral로 집계됨 → **hints 2개, pos/neg 0개**. (hints≥3 조건은 미달이지만, “최소 1개 pos/neg” 관점에서는 불충족.)
- **T1/T2:** aspect_hints에 CJ negative 포함, 3개 이상 중 최소 1개 pos/neg **충족**.

### 1.2 조건 (B): pos_score / neg_score / total / margin ≠ 0

| Run | override_gate_debug (02829/피부톤) | pos/neg/total/margin | 충족 |
|-----|-----------------------------------|----------------------|------|
| T0  | 2건 low_signal(0/0/0/0), 1건 neutral_only(valid_hint_count=0, 0/0/0/0) | 모두 0 | ✗ |
| T1  | 2건 low_signal(0/0/0/0), 1건 **APPLY** (valid_hint_count=2, pos=0, neg=1.6, total=1.6, margin=1.6) | APPLY 행에서 ≠0 | ✓ (해당 경로) |
| T2  | 2건 low_signal(0/0/0/0), 1건 **APPLY** (동일 수치) | APPLY 행에서 ≠0 | ✓ (해당 경로) |

- **T0:** 02829/피부톤에 대해 모든 행이 0/0/0/0 또는 valid_hint_count=0 → **(B) 불충족.**
- **T1/T2:** 동일 aspect에 대해 **APPLY** 행이 있어 total/margin=1.6 ≠ 0 → (B) 충족. (동일 run 내 일부 행은 여전히 0/0/0/0.)

### 1.3 (A/B/C 재분류)에서 (B) 급감 여부

- **(B)** 여기서: “해당 aspect에 대해 pos/neg/total/margin이 전부 0인 케이스”.
- **T0:** 02829/피부톤 = neutral_only + low_signal만 존재 → (B) 유형 **해당**.
- **T1/T2:** 02829/피부톤에 대해 APPLY 경로가 있어 “점수 0만 있는 (B) 유형”이 **해당 aspect에서는** 줄어듦.
- **Run 단위:** override_gate_debug_summary 기준  
  - neutral_only: T0 22 → T1 22 → T2 **13**  
  - low_signal: T0 5 → T1 3 → T2 **0**  
  → T2로 갈수록 **low_signal 0**, neutral_only도 감소 → **(B)에 해당하는 “점수 0” 비중이 T0→T1→T2로 감소** ✓

---

## 2. T0 vs T1 vs T2: override_applied_rate

**override_gate_debug_summary.json 기준 (aspect 단위):**

| 조건 | n_aspects | decision_applied_n | override_applied_rate |
|------|-----------|--------------------|------------------------|
| T0   | 32        | 5                  | 5/32 ≈ **15.6%**      |
| T1   | 28        | 3                  | 3/28 ≈ **10.7%**      |
| T2   | 27        | 14                 | 14/27 ≈ **51.9%**     |

- **기대:** T0 < T1 < T2  
- **실제:** T0 (15.6%) **>** T1 (10.7%) < T2 (51.9%)  
- **결론:** **override_applied_rate T0 < T1 < T2 불충족** (T1이 T0보다 낮음).

---

## 3. low_signal 비중

| 조건 | low_signal (건수) | neutral_only | skip 전체 | low_signal 비중 |
|------|-------------------|--------------|-----------|-----------------|
| T0   | 5                 | 22           | 27        | 5/32 ≈ **15.6%** |
| T1   | 3                 | 22           | 25        | 3/28 ≈ **10.7%** |
| T2   | 0                 | 13           | 13        | **0%**          |

- **결론:** **low_signal 비중 T0 → T1 → T2 감소** ✓

---

## 4. Safety 메트릭 변동 (Conflict / L3 / Explicit grounding failure)

**derived/metrics/structural_metrics.csv (샘플 10건 집계):**

| 지표 | T0 | T1 | T2 |
|------|----|----|-----|
| polarity_conflict_rate | 0.0 | 0.0 | 0.0 |
| severe_polarity_error_L3_rate | 0.1 | 0.2 | 0.2 |
| explicit_grounding_failure_rate | 0.2 | 0.2 | 0.1 |

- **Conflict:** 전 구간 0, 변동 없음.
- **L3:** T0 0.1 → T1·T2 0.2로 소폭 상승.
- **Explicit grounding failure:** T0·T1 0.2 → T2 0.1로 **감소**.

---

## 5. 요약 체크리스트

| 항목 | 결과 |
|------|------|
| 02829/피부톤 (A) hints≥3이면 최소 1개 pos/neg | T0 조건 미충족(힌트 2개·pos/neg 0), T1/T2 충족 |
| 02829/피부톤 (B) pos/neg/total/margin ≠ 0 | T0 불충족(전부 0), T1/T2 APPLY 경로에서 충족 |
| (B) 유형 급감 (T0→T1→T2) | ✓ (neutral_only·low_signal 감소, T2에서 low_signal 0) |
| override_applied_rate T0 < T1 < T2 | ✗ (T1 < T0 < T2) |
| low_signal 비중 감소 | ✓ (15.6% → 10.7% → 0%) |
| Safety: Conflict | 0 유지 |
| Safety: L3 | T1/T2에서 0.1→0.2로 소폭 상승 |
| Safety: Explicit grounding failure | T2에서 0.2→0.1로 감소 |

---

## 6. 결론 및 권장

- **02829/피부톤:** T0에서는 힌트 매핑/집계 때문에 pos·neg가 aspect_hints에 없고 점수도 0으로만 나옴. T1/T2에서는 동일 샘플에 대해 pos/neg 힌트와 비영 점수(total=1.6)가 나오고 APPLY 경로가 존재하나, **scorecard 기준** 02829는 T1/T2 모두 **override_applied=false, conflict_blocked** 로 최종 적용은 막혀 있음.
- **override_applied_rate:** 현재 결과에서는 **T0 < T1 < T2** 가 아니며, T1에서 적용 건수가 T0보다 적음. 역치 완화만으로는 T1에서 적용률이 선형 증가하지 않는 것으로 보임.
- **low_signal 비중 감소**와 **explicit_grounding_failure 감소(T2)** 는 목표와 부합함.
- **L3_rate** 소폭 상승은 T1/T2에서 역치 완화·override 증가에 따른 트레이드오프로 해석 가능; 모니터링 권장.
