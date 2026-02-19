# CR v2 n100 M0/M1 실행 및 후처리 명령어

v2 YAML 설정 기반. run_pipeline: 동시실행 3, paper, metrics, aggregator 포함. v3/v4 config 지원.

---

## 1. 파이프라인 실행 (M0, M1)

```powershell
# 환경 변수
$env:LLM_PROVIDER="openai"
$env:OPENAI_MODEL="gpt-4.1-mini"

# M0 (v3 config, run-id v4로 저장)
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n100_m0_v3.yaml --run-id cr_v2_n100_m0_v4 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3

# M1 (v3 config, run-id v4로 저장)
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n100_m1_v3.yaml --run-id cr_v2_n100_m1_v4 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3
```

**Config**: v3는 `cr_v2_n100_m0_v3.yaml`, `cr_v2_n100_m1_v3.yaml`. v4는 `cr_v2_n100_m0_v4.yaml`, `cr_v2_n100_m1_v4.yaml` (없으면 v3 사용).

---

## 2. Recheck Rate 확인

```powershell
# M0 v4
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m0_v4__seed42_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m0_v4__seed123_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m0_v4__seed456_proposed/outputs.jsonl

# M1 v4
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m1_v4__seed42_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m1_v4__seed123_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m1_v4__seed456_proposed/outputs.jsonl
```

---

## 3. IRR 계산 (시드별)

**CR v2 Paper Table**에서 subset IRR (conflict/implicit/negation)을 산출하려면 `--scorecards`로 gold_tuples를 병합해야 합니다.

```powershell
# M0 v4
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v4__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v4__seed42_proposed/irr --scorecards results/cr_v2_n100_m0_v4__seed42_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v4__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v4__seed123_proposed/irr --scorecards results/cr_v2_n100_m0_v4__seed123_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v4__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v4__seed456_proposed/irr --scorecards results/cr_v2_n100_m0_v4__seed456_proposed/scorecards.jsonl

# M1 v4
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v4__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v4__seed42_proposed/irr --scorecards results/cr_v2_n100_m1_v4__seed42_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v4__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v4__seed123_proposed/irr --scorecards results/cr_v2_n100_m1_v4__seed123_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v4__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v4__seed456_proposed/irr --scorecards results/cr_v2_n100_m1_v4__seed456_proposed/scorecards.jsonl
```

---

## 4. 시드별 메트릭 머지 및 집계

```powershell
# M0 v4
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n100_m0_v4__seed42_proposed,results/cr_v2_n100_m0_v4__seed123_proposed,results/cr_v2_n100_m0_v4__seed456_proposed --outdir results/cr_v2_n100_m0_v4_aggregated --metrics_profile paper_main

# M1 v4
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n100_m1_v4__seed42_proposed,results/cr_v2_n100_m1_v4__seed123_proposed,results/cr_v2_n100_m1_v4__seed456_proposed --outdir results/cr_v2_n100_m1_v4_aggregated --metrics_profile paper_main
```

**포함 메트릭**: break subtype (implicit/negation/simple), subset IRR (conflict/implicit/negation), subset_n (conflict/implicit/negation), event count (break_count, implicit_invalid_count, conflict_count).

---

## 5. Paper Metrics Export (M0 vs M1 비교, 선택)

```powershell
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_v2_n100_m0_v4_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_v2_n100_m1_v4_aggregated/aggregated_mean_std.csv --run-dirs results/cr_v2_n100_m0_v4__seed42_proposed results/cr_v2_n100_m0_v4__seed123_proposed results/cr_v2_n100_m0_v4__seed456_proposed --run-dirs-m1 results/cr_v2_n100_m1_v4__seed42_proposed results/cr_v2_n100_m1_v4__seed123_proposed results/cr_v2_n100_m1_v4__seed456_proposed --out-dir results/cr_v2_n100_v4_comparison_paper
```

---

## 6. CR v2 Paper Table 생성 (권장)

M0 vs M1 비교 논문용 테이블. Table 1 (F1), Table 2 (Schema/Error, IRR, subset IRR), Appendix 포함.

```powershell
python scripts/build_cr_v2_paper_table.py --agg-m0 results/cr_v2_n100_m0_v4_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n100_m1_v4_aggregated/aggregated_mean_std.csv --run-dirs-m0 results/cr_v2_n100_m0_v4__seed42_proposed results/cr_v2_n100_m0_v4__seed123_proposed results/cr_v2_n100_m0_v4__seed456_proposed --run-dirs-m1 results/cr_v2_n100_m1_v4__seed42_proposed results/cr_v2_n100_m1_v4__seed123_proposed results/cr_v2_n100_m1_v4__seed456_proposed --out reports/cr_v2_paper_table.md
```

**출력**: `reports/cr_v2_paper_table.md` — Table 1 (ATSA-F1, ACSA-F1, #attribute f1), Table 2 (Schema/Error, fix/break/net_gain, subset IRR, CDA, AAR), Appendix (seed-by-seed, bootstrap, break subtype, event count 등).

---

## 산출물 요약

| 항목 | 경로 |
|------|------|
| M0 aggregated | results/cr_v2_n100_m0_v4_aggregated/aggregated_mean_std.csv |
| M1 aggregated | results/cr_v2_n100_m1_v4_aggregated/aggregated_mean_std.csv |
| M0 vs M1 비교 | results/cr_v2_n100_v4_comparison_paper/paper_metrics_aggregated_comparison.md |
| CR v2 Paper Table | reports/cr_v2_paper_table.md |
| IRR (시드별) | results/cr_v2_n100_*_v4__seed*_proposed/irr/irr_run_summary.json, irr_subset_summary.json |
