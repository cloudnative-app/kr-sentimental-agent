# How to Run — Conflict Review v1 (CR v1)

Conflict Review v1 실험 실행 방법, 통합 스크립트 사용법, 산출물 경로를 정리합니다.

**관련 문서**: [README_cr_v1.md](README_cr_v1.md) — CR v1 개요·에이전트·데이터 플로우 | [docs/how_to_run.md](how_to_run.md) — 전체 파이프라인

---

## 1. 퀵스타트

### 1.1 CR-M0/M1/M2 통합 스크립트 (권장)

```bash
# 전체 실행: run_pipeline → compute_irr → export_paper_metrics
python scripts/run_cr_m0_m1_m2_pipeline.py
```

**실행 순서**

1. **run_pipeline** (M0 → M1 → M2)  
   - `--mode proposed --profile paper --with_metrics --with_aggregate`
2. **compute_irr** (시드별)  
   - outputs.jsonl → irr/irr_sample_level.csv, irr_run_summary.json  
   - Process IRR (action agreement) + Measurement IRR (final_label agreement) — `docs/evaluation_cr_v2.md` 참고
3. **export_paper_metrics_md** (조건별)  
   - paper_metrics.md, paper_metrics.csv
4. **export_paper_metrics_aggregated** (조건별)  
   - aggregated_mean_std.csv → paper_metrics_aggregated.md

### 1.2 옵션

```bash
# 데이터가 이미 있으면 pipeline 생략
python scripts/run_cr_m0_m1_m2_pipeline.py --skip-pipeline

# IRR·paper metrics만 생략
python scripts/run_cr_m0_m1_m2_pipeline.py --skip-irr
python scripts/run_cr_m0_m1_m2_pipeline.py --skip-paper-metrics

# 특정 조건만 실행
python scripts/run_cr_m0_m1_m2_pipeline.py --conditions m0 m1
```

---

## 2. 수동 실행

### 2.1 run_pipeline (조건별)

```bash
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0.yaml --run-id cr_n50_m0 --mode proposed --profile paper --with_metrics --with_aggregate

python scripts/run_pipeline.py --config experiments/configs/cr_n50_m1.yaml --run-id cr_n50_m1 --mode proposed --profile paper --with_metrics --with_aggregate

python scripts/run_pipeline.py --config experiments/configs/cr_n50_m2.yaml --run-id cr_n50_m2 --mode proposed --profile paper --with_metrics --with_aggregate
```

### 2.2 compute_irr (시드별)

```bash
# 예: cr_n50_m0 (기본)
python scripts/compute_irr.py --input results/cr_n50_m0__seed42_proposed/outputs.jsonl --outdir results/cr_n50_m0__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m0__seed123_proposed/outputs.jsonl --outdir results/cr_n50_m0__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m0__seed456_proposed/outputs.jsonl --outdir results/cr_n50_m0__seed456_proposed/irr/

# CR v2: subset IRR (implicit/negation) 산출 시 --scorecards 필수
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v4__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v4__seed42_proposed/irr --scorecards results/cr_v2_n100_m0_v4__seed42_proposed/scorecards.jsonl
```

### 2.3 export_paper_metrics_md

```bash
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m0 --mode proposed
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m1 --mode proposed
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m2 --mode proposed
```

### 2.4 aggregate_seed_metrics (시드별 결과 머징·평균±표준편차)

```bash
# CR 조건별 시드 어그리게이트
python scripts/aggregate_seed_metrics.py --base_run_id cr_n50_m0 --mode proposed --seeds 42,123,456 --outdir results/cr_n50_m0_aggregated --metrics_profile paper_main

python scripts/aggregate_seed_metrics.py --base_run_id cr_n50_m1 --mode proposed --seeds 42,123,456 --outdir results/cr_n50_m1_aggregated --metrics_profile paper_main

python scripts/aggregate_seed_metrics.py --base_run_id cr_n50_m2 --mode proposed --seeds 42,123,456 --outdir results/cr_n50_m2_aggregated --metrics_profile paper_main
```

산출물: `results/<run_id>_aggregated/` — merged_scorecards.jsonl, aggregated_mean_std.csv, integrated_report.md

### 2.5 export_paper_metrics_aggregated

```bash
# 기본 (aggregated_mean_std.csv만 사용)
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv

# CR 논문용: conflict_detection_rate, IRR, review_nontrivial_action_rate, arb_nonkeep_rate 포함
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0__seed42_proposed results/cr_n50_m0__seed123_proposed results/cr_n50_m0__seed456_proposed --out-dir results/cr_n50_m0_paper
```

**테이블 구성**:
- Table 1 (RQ1) — ref-pol F1: tuple_f1_s1_refpol, tuple_f1_s2_refpol, delta_f1_refpol, fix_rate_refpol, break_rate_refpol, net_gain_refpol
- Table 1b (Grounding) — tuple_f1_explicit, invalid_target_rate, invalid_language_rate, invalid_ref_rate
- Table 2A (Process IRR) — irr_fleiss_kappa, irr_cohen_kappa_mean, irr_perfect_agreement_rate, irr_majority_agreement_rate
- Table 2B (Measurement IRR) — meas_fleiss_kappa, meas_cohen_kappa_mean, meas_perfect_agreement_rate, meas_majority_agreement_rate
- Table 3 (Process Evidence) — conflict_detection_rate, pre_to_post_change_rate, review_nontrivial_action_rate, arb_nonkeep_rate

---

## 3. Config·데이터

| 조건 | config | run_id | seeds |
|------|--------|--------|-------|
| M0 | cr_n50_m0.yaml | cr_n50_m0 | 42, 123, 456 |
| M1 | cr_n50_m1.yaml | cr_n50_m1 | 42, 123, 456 |
| M2 | cr_n50_m2.yaml | cr_n50_m2 | 42, 123, 456 |

**데이터셋**: `experiments/configs/datasets/beta_n50/`  
- train.csv, valid.csv, valid.gold.jsonl  
- 없으면: `python scripts/make_beta_n50_dataset.py --outdir experiments/configs/datasets/beta_n50 --valid_size 50 --seed 77`

---

## 4. 산출물 경로

| 산출물 | 경로 |
|--------|------|
| outputs | `results/<run_id>__seed<N>_proposed/outputs.jsonl` |
| scorecards | `results/<run_id>__seed<N>_proposed/scorecards.jsonl` |
| 메트릭 | `results/<run_id>__seed<N>_proposed/derived/metrics/structural_metrics.csv` |
| IRR | `results/<run_id>__seed<N>_proposed/irr/irr_sample_level.csv`, `irr_run_summary.json` (Process + Measurement IRR) |
| Paper metrics (seed) | `results/<run_id>_paper/paper_metrics.md`, `paper_metrics.csv` |
| Paper metrics (agg) | `results/<run_id>_paper/paper_metrics_aggregated.md` |
| Aggregated | `results/<run_id>_aggregated/` — merged_scorecards.jsonl, aggregated_mean_std.csv, integrated_report.md |
| 리포트 | `reports/<run_id>__seed<N>_proposed/metric_report.html` |

---

## 5. CR v2 (M0 vs M1)

CR v2는 메모리 OFF(M0) vs 메모리 ON(M1) 비교 실험입니다. Recheck, 에피소딕 메모리, subset IRR 포함.

| 항목 | 설명 |
|------|------|
| **Config** | `cr_v2_n100_m0_v3.yaml`, `cr_v2_n100_m1_v3.yaml` (run-id v4) |
| **실행 순서** | run_pipeline → compute_irr (--scorecards, subset IRR용) → aggregate_seed_metrics → build_cr_v2_paper_table |
| **Paper Table** | `scripts/build_cr_v2_paper_table.py` → `reports/cr_v2_paper_table.md` (Table 1 F1, Table 2 Schema/Error/IRR/subset IRR, Appendix) |
| **명령어** | [run_cr_v2_n100_m0_m1_v3_commands.md](run_cr_v2_n100_m0_m1_v3_commands.md) |

---

## 6. 참고 문서

| 문서 | 설명 |
|------|------|
| [README_cr_v1.md](README_cr_v1.md) | CR v1 개요·에이전트·데이터 플로우 |
| [run_cr_m0_m1_m2_commands.md](run_cr_m0_m1_m2_commands.md) | CR-M0/M1/M2 실행 명령 |
| [run_cr_v2_n100_m0_m1_v3_commands.md](run_cr_v2_n100_m0_m1_v3_commands.md) | CR v2 M0 vs M1 실행·IRR·aggregate·paper table |
| [cr_branch_metrics_spec.md](cr_branch_metrics_spec.md) | CR 메트릭·데이터 플로우 명세 |
| [evaluation_cr_v2.md](evaluation_cr_v2.md) | CR v2 평가 정의 (ref-pol, IRR, ΔF1 해석) |
| [protocol_conflict_review_vs_legacy_comparison.md](protocol_conflict_review_vs_legacy_comparison.md) | CR vs Legacy 워크플로우·데이터 플로우 |
| [how_to_run.md](how_to_run.md) | 전체 파이프라인 실행 가이드 |
