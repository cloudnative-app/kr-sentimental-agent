# gold_available 게이트 수정 및 Triptych after_rep 열 추가

## A. F1 N/A 원인: gold_available 게이트 수정

### 변경 사항 (structural_error_aggregator.compute_stage2_correction_metrics)

- **gold_available 정의**: `gold_available = (N_gold_total_pairs > 0)`  
  “gold가 explicit/implicit로 분리된 값이 있어야 true” 같은 조건 제거.
- **N_gold_* / N_pred_* 항상 산출**:  
  모든 행을 한 번 훑어 `N_gold_total_pairs`, `N_gold_explicit_pairs`, `N_gold_implicit_pairs`, `N_pred_used`, `N_pred_final_tuples` 등은 **gold 유무와 관계없이** 항상 계산.
- **게이트**: `gold_available == False`일 때만 F1/fix_rate/break_rate 등은 스킵하고, 그때 stderr에  
  `[aggregator] gold_available=False, skipping F1 (no gold pairs in scorecards).` 로그 출력.
- **기대**:  
  scorecard에 gold가 있으면 `gold_available=True`, `N_gold_total_pairs`/explicit_pairs/implicit_pairs 값 생성, `N_pred_used > 0`, `tuple_f1_s2_*`가 N/A가 아닌 실수로 출력.

## B. polarity_conflict 고착 대응: Triptych에 after_rep 열 추가

### 변경 사항 (structural_error_aggregator._triptych_row)

- **추가 열**  
  - `final_n_pairs_raw` / `final_pairs_raw`: 기존 final (raw tuples)와 동일.  
  - `final_n_pairs_after_rep` / `final_pairs_after_rep`: `select_representative_tuples(record)` 적용 후 pairs 개수·문자열.
- **기존 열 유지**  
  - `final_n_pairs` / `final_pairs`: raw와 동일 (하위 호환).  
  - `polarity_conflict_raw`, `polarity_conflict_after_rep`: 기존대로 판정용으로 유지.
- **설계**  
  - 대표 선택(after_rep)은 **판정**(polarity conflict after rep)에만 쓰이고,  
  - **출력**(F1/Triptych용 final pairs)은 여전히 raw tuples.  
  - Triptych에서 raw와 after_rep를 **둘 다** 볼 수 있도록 열만 추가했으며, pipeline 출력을 덮어쓰지 않음.

## 검증

- gold 있는 run에서 aggregator 재실행 후: `gold_available=True`, `N_gold_total_pairs`/explicit/implicit, `N_pred_used`, `tuple_f1_s2_*` 확인.
- Triptych TSV에 `final_pairs_raw`, `final_pairs_after_rep`, `final_n_pairs_after_rep` 열 존재 확인.
