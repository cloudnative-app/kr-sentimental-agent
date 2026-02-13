# Explicit/Implicit Gold 메트릭 점검

## (1) structural_metrics.csv 컬럼 — 구현 완료

**정의 (Gold 분모 분리)**

- `N_gold_total`: gold가 있는 샘플 수 (기존 N_gold와 동일 정의).
- `N_gold_explicit`: gold 중 최소 1개 explicit pair가 있는 샘플 수.
- `N_gold_implicit`: gold 중 최소 1개 implicit pair(빈 aspect_term)가 있는 샘플 수.

**F1 분리**

- `tuple_f1_s2_overall`: 전체 gold 기준 macro F1 (참고용).
- `tuple_f1_s2_explicit_only`: explicit gold만 있는 샘플에 대해, 해당 샘플의 explicit gold pair만으로 계산한 macro F1 → **메인 성능 지표**.

**산출 위치**

- `scripts/structural_error_aggregator.py`: `_split_gold_explicit_implicit()`, `compute_stage2_correction_metrics()`, CANONICAL_METRIC_KEYS.
- `scripts/build_metric_report.py`: KPI 및 Table 2에서 explicit_only 우선 표시.

---

## (2) Triptych: gold_type / f1_eval_note — 구현 완료

- **gold_type**: `explicit` | `implicit` (해당 행 gold에 implicit pair가 하나라도 있으면 `implicit`).
- **f1_eval_note**: implicit 행에 한해 `"not evaluated for explicit F1"` (사람이 봐도 직관적).

F1 매칭 컬럼(matches_stage1_vs_gold, matches_final_vs_gold 등)은 implicit 행에도 계산·기록되나, explicit-only F1 집계에는 해당 행이 포함되지 않음. TSV/CSV에서는 회색 처리 대신 `f1_eval_note`로 구분.

---

## (3) Triptych 규칙 확인 로그 (gold_pairs에 |positive)

- `write_triptych_table()` 내부에서, `gold_pairs`에 `|positive`가 포함된 **한 줄**을 골라 로그로 출력.
- 해당 행이 N_gold에 포함되는지, matches_final_vs_gold 계산에 포함되는지 확인용.
