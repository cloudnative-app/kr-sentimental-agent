# Triplet → Tuple 전환 및 Gold/Scoring 정합성 변경 로그

## 영향 지점 (수정 대상)

| 구분 | 파일 | 함수/키 |
|------|------|---------|
| Gold 생성 | `scripts/make_mini_dataset.py` | `annotation_to_gold_triplets` → `annotation_to_gold_tuples`, 출력 `gold_tuples` |
| Gold 생성 | `scripts/make_mini2_dataset.py` | 동일 |
| Gold 로딩 | `experiments/scripts/run_experiments.py` | `_load_eval_gold`: `gold_tuples` 우선, `gold_triplets` 하위호환 → 정규화 후 `gold_tuples`로 주입 |
| 채점/집계 | `scripts/structural_error_aggregator.py` | `_triplet_*` → `_tuple_*`, `tuple_f1_s1/s2`, `triplet_f1_*` alias |
| 리포트 | `scripts/build_metric_report.py` | `_extract_gold_triplets` → gold_tuples 호환, `tuple_f1_*` 표시 |
| Paper 테이블 | `scripts/build_paper_tables.py` | extract_gold_triplets → gold_tuple_set_from_record (gold_tuples/triplets 호환) |
| 정의/상수 | `docs/absa_tuple_eval.md` | 신규 |
| 평가 계약 | `metrics/eval_tuple.py` | 신규: Tuple 타입, gold_row_to_tuples, gold_tuples_from_record |

## 변경 요약

- **정의**: Tuple = (aspect_ref, aspect_term, polarity). aspect_term = 표면형(기존 opinion_term.term 재해석).
- **Gold**: `gold_tuples` 출력; 읽기 시 `gold_tuples` 우선, `gold_triplets` 시 opinion_term.term → aspect_term 변환.
- **메트릭**: `tuple_f1_s1`, `tuple_f1_s2`, `delta_f1` 사용; `triplet_f1_*`는 deprecated alias로 동일 값 유지.
- **매칭**: (normalize(aspect_ref), normalize(aspect_term), normalize(polarity)).
