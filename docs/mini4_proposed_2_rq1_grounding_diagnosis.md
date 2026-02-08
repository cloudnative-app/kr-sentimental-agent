# mini4_proposed_2__seed42_proposed RQ1 Grounding v2 진단 보고

## 1. 실행 개요

- **Run**: `mini4_proposed_2__seed42_proposed`
- **Scorecards**: `results/mini4_proposed_2__seed42_proposed/scorecards.jsonl`
- **진단 스크립트**: `scripts/diagnose_rq1_grounding_sample.py --input <scorecards> --index <i>`
- **샘플 수**: N = 10

## 2. Run 단위 메트릭 (structural_metrics)

| 구분 | 메트릭 | 값 |
|------|--------|-----|
| | n | 10 |
| | aspect_hallucination_rate | 0.8000 |
| | alignment_failure_rate | 0.8000 |
| | filter_rejection_rate | 0.0000 |
| | semantic_hallucination_rate | 0.0000 |
| | implicit_grounding_rate | 0.6000 |
| | explicit_grounding_rate | 0.2000 |
| | explicit_grounding_failure_rate | 0.2000 |
| | unsupported_polarity_rate | 0.0000 |
| | legacy_unsupported_polarity_rate | 0.8000 |
| | rq1_one_hot_sum | 1.0000 |

## 3. 샘플별 5줄 진단 (index 0 ~ 9)

| index | text_id | selected_judgement_idx | rq1_bucket | drop_reason (align / filter / semantic) |
|-------|---------|------------------------|------------|----------------------------------------|
| 0 | nikluge-sa-2022-train-02829 | 1 | **explicit** | 0 / 0 / 0 |
| 1 | nikluge-sa-2022-train-00797 | 3 | **implicit** | 2 / 0 / 0 |
| 2 | nikluge-sa-2022-train-00474 | 1 | **explicit** | 0 / 0 / 0 |
| 3 | nikluge-sa-2022-train-01065 | 3 | **implicit** | 2 / 0 / 0 |
| 4 | nikluge-sa-2022-train-01233 | 5 | **explicit_failure** | 3 / 0 / 0 |
| 5 | nikluge-sa-2022-train-01230 | 2 | **implicit** | 1 / 0 / 0 |
| 6 | nikluge-sa-2022-train-01089 | 4 | **implicit** | 4 / 0 / 0 |
| 7 | nikluge-sa-2022-train-00692 | 7 | **implicit** | 5 / 0 / 0 |
| 8 | nikluge-sa-2022-train-01557 | 2 | **explicit_failure** | 2 / 0 / 0 |
| 9 | nikluge-sa-2022-train-02917 | 2 | **implicit** | 4 / 0 / 0 |

- **selected_tuple**: 각 샘플은 (aspect_term_norm, polarity) 1개로 대표됨.
- **drop_reason**: alignment_failure / filter_rejection / semantic_hallucination 개수.
