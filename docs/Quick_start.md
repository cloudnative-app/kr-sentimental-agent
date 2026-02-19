# 본실험 Quick Start — 필수 실행 스크립트 및 체크리스트

본실험(paper) 실행 시 **run_pipeline**을 통해 자동 실행되는 단계와, **반드시 수동으로 실행**해야 할 정합성·규약·메트릭 스크립트를 정리한다. 상세는 `docs/how_to_run.md` 참고.

---

## 1. 기본 설정 (본실험 기준)

| 항목 | 값 | 비고 |
|------|-----|------|
| override_profile | t1 | min_total=1.0, min_margin=0.5 |
| episodic_memory | C1 / C2 / C3 / C2_eval_only | 조건별 |
| seeds | [42, 123, 456] | seed 반복 |
| concurrency | 3 | 동시 시드 실행 수 |
| demo.k | 0 | 본실험 |
| run_purpose | paper | |
| profile | paper | run_pipeline |
| metrics_profile | paper_main | structural_error_aggregator |

- 데이터셋·config 구조는 betatest와 동일 패턴. 데이터 경로만 본실험용으로 변경.

---

## 1.5 본실험에서 정의해야 하는 데이터 경로

### 디렉터리 구조

본실험 데이터는 `experiments/configs/datasets/` 하위에 **데이터셋별 폴더**를 두고, config의 `data.dataset_root` 기준 **상대 경로**로 지정한다.

```
experiments/configs/datasets/
├── <데이터셋_이름>/          # 예: real, real_n50_seed1, betatest_n50
│   ├── train.csv
│   ├── valid.csv
│   └── valid.gold.jsonl
└── real/
    └── README.md             # 본실험 데이터 배치 안내
```

### Config에 정의할 경로

| config 키 | 필수 | 설명 | 예시 |
|-----------|------|------|------|
| `data.dataset_root` | ✓ | 데이터 루트. `allowed_roots`에 포함되어야 함 | `experiments/configs/datasets` |
| `data.allowed_roots` | ✓ | 허용 경로 목록. dataset_root 포함 | `["experiments/configs/datasets"]` |
| `data.train_file` | ✓ | train CSV. 상대 경로 (dataset_root 기준) | `real/train.csv` 또는 `real_n50_seed1/train.csv` |
| `data.valid_file` | ✓ | valid CSV. 상대 경로 | `real/valid.csv` |
| `data.text_column` | ✓ | 텍스트 컬럼명 | `text` |
| `data.label_column` | paper 시 | 라벨 컬럼. 본실험은 null | `null` |
| `data.input_format` | ✓ | 입력 형식 | `csv` |
| `eval.gold_valid_jsonl` | ✓ (골드 사용 시) | valid용 골드 JSONL. 상대 경로 | `real/valid.gold.jsonl` |

- **test_file**: paper 정책에서는 사용하지 않음 (`check_experiment_config --strict` 시 검사).
- **gold_test_jsonl**: valid만 평가 시 생략 가능. valid와 동일 골드 파일을 쓰면 `gold_valid_jsonl`만 지정.

### 파일 형식 요구사항

| 파일 | 최소 컬럼/필드 | 비고 |
|------|----------------|------|
| **train.csv** | `id`(또는 `uid`), `text` | 데모 풀용. k=0이면 미사용 |
| **valid.csv** | `id`(또는 `uid`), `text` | 평가용. **id/uid는 골드 매칭에 필수** |
| **valid.gold.jsonl** | `uid`, `gold_tuples` 또는 `gold_triplets` | 한 줄당 한 샘플. `uid`는 CSV의 `id`와 일치 |

**골드 JSONL** 한 줄 예 (gold_tuples 형식):

```json
{"uid": "nikluge-sa-2022-train-00149", "gold_tuples": [{"aspect_ref": "...", "aspect_term": "...", "polarity": "positive"}]}
```

- `gold_triplets`도 지원 (aspect_ref, opinion_term, polarity).
- `uid`가 valid.csv의 `id`/`uid`와 **정확히 일치**해야 scorecard에 gold가 주입됨.

### paper 정책 제약 (check_experiment_config --strict)

- `data.valid_file` 필수
- `data_roles.report_sources`: `["valid_file"]` 정확히
- `data.test_file` 없음
- `data_roles.blind_set` / `blind_sources` 빈 배열
- train/valid **파일 경로가 서로 달라야** 함 (동일 파일 재사용 금지)
- CSV에 `id` 또는 `uid` 컬럼 필수 (골드 매칭)

### 데이터 생성 스크립트 (선택)

| 용도 | 스크립트 | 출력 |
|------|----------|------|
| NIKLuge SA 2022 JSONL → CSV+gold | `make_mini_dataset.py --input <jsonl> --outdir <datasets>/real --valid_ratio 0.2 --seed 42` | train.csv, valid.csv, valid.gold.jsonl |
| betatest용 n50 추출 (seed=99) | `make_betatest_n50_dataset.py` | betatest_n50/ |
| real n50/n100 | `make_real_n100_seed1_dataset.py` 등 | real_n50_seed1/, real_n100_seed1/ |

- 상세: `experiments/configs/datasets/real/README.md`

---

## 2. run_pipeline이 자동 실행하는 스크립트

`run_pipeline.py`는 다음 순서로 스크립트를 호출한다.

| 순서 | 스크립트 | 조건 | 역할 |
|------|----------|------|------|
| 0 | `check_experiment_config.py` | `--with_integrity_check` 시 | config 무결성·누수 검사 |
| 1 | `experiments/scripts/run_experiments.py` | 항상 | 실험 실행 (scorecards, outputs, traces, override_gate_debug* 생성) |
| 2 | `postprocess_runs.py` | `--with_postprocess` 시 | 안정성·root-cause 태깅 |
| 3 | `filter_scorecards.py` | `--with_filter` 시 | derived/filtered |
| 4 | `build_run_snapshot.py` | 항상 | run_snapshot, ops_outputs |
| 5 | `make_pretest_payload.py` | `--with_payload` 시 | derived/payload |
| 6 | `build_paper_tables.py` | profile=paper 시 | paper_outputs |
| 7 | `build_html_report.py` | 항상 | HTML 리포트 |
| 8 | `structural_error_aggregator.py` | `--with_metrics` 시 | derived/metrics (structural_metrics.csv 등) |
| 9 | `build_metric_report.py` | `--with_metrics` 시 | metric_report.html |
| — | `run_summary.py` | 항상 | RUN SUMMARY 출력 |
| — | `aggregate_seed_metrics.py` | `--with_aggregate` 시 | 시드 머징·평균±std·통합 보고서 |

**run_experiments 내부에서 사용하는 스크립트**

- `scripts/scorecard_from_smoke.make_scorecard` → scorecard 생성 (직접 호출 아님, import 사용)

---

## 3. 본실험에서 반드시 실행해야 할 Python 스크립트

### 3.1 run_pipeline 통해 자동 실행 (필수 옵션)

```powershell
# 실행 전 검사 (권장)
python scripts/check_experiment_config.py --config experiments/configs/<본실험_config>.yaml --strict

# C1 실행 예
python scripts/run_pipeline.py --config experiments/configs/<본실험_c1>.yaml --run-id <base_run_id>_c1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

- `--with_metrics`: structural_error_aggregator + build_metric_report 자동 실행
- `--with_aggregate`: 시드 반복 완료 후 aggregate_seed_metrics.py 자동 실행
- `--seed_concurrency 3`: 시드 3개 동시 실행

### 3.2 수동 실행 필수 스크립트 (정합성·규약 검사)

run_pipeline **내부에는 포함되지 않으므로**, 본실험 정합성 확인을 위해 **별도 실행**해야 한다.

| 스크립트 | 실행 시점 | 명령 예 | 역할 |
|----------|------------|---------|------|
| **check_experiment_config.py** | 실행 전 | `python scripts/check_experiment_config.py --config <config> --strict` | config 무결성·스키마·데모/스플릿 검사 |
| **pipeline_integrity_verification.py** | 시드별 run 완료 후 | `python scripts/pipeline_integrity_verification.py --run_dir results/<run_id>_proposed --out reports/pipeline_integrity_verification_<run_id>.json` | E2E 레코드 수, S1/S2/S3/PJ1 불변식, override gate, memory, metrics_pred_consistency |
| **consistency_checklist.py** | 시드별·머지 run 후 | `python scripts/consistency_checklist.py --run_dir results/<run_id>_proposed --triptych_n 5` | source/gold/tuple path, sanity(gold→gold, final→final F1=1), inconsistency_flags |
| **aggregate_seed_metrics.py** | 시드 전부 완료 후 (run_pipeline --with_aggregate 없을 때) | `python scripts/aggregate_seed_metrics.py --base_run_id <base> --seeds 42,123,456 --mode proposed --outdir results/<base>_aggregated --metrics_profile paper_main --with_metric_report --ensure_per_seed_metrics` | 머징·평균±std·통합 보고서·머지 metric_report.html |

**pipeline_integrity_verification** 입력 요구사항:

- `scorecards.jsonl`, `outputs.jsonl`, `traces.jsonl`, `manifest.json`
- C2/C2_eval: `override_gate_debug.jsonl`, `override_gate_debug_summary.json` (SupervisorAgent가 run 시 생성)
- C1: override 파일 없을 수 있음 → 일부 검사 항목은 비어 있을 수 있음
- `derived/metrics/structural_metrics.csv` (structural_error_aggregator 실행 후)
- `derived/tables/triptych_table.tsv`: run_pipeline의 structural_error_aggregator는 기본으로 triptych를 내보내지 않음. metrics_pred_consistency 검사에 필요하면 aggregator를 `--export_triptych_table`로 별도 실행하거나, consistency_checklist가 triptych를 사용함

---

## 4. 조건별 실행 순서 (C1 → C2 → C3 → C2_eval_only)

### 4.1 데이터셋 준비

```powershell
# betatest 패턴: make_betatest_n50_dataset.py
# 본실험: experiments/configs/datasets/real/ 등에 train.csv, valid.csv, valid.gold.jsonl 배치
# 상세: experiments/configs/datasets/real/README.md
```

### 4.2 조건별 run_pipeline

```powershell
# C1 (episodic memory OFF)
python scripts/run_pipeline.py --config experiments/configs/<본실험_c1>.yaml --run-id <base>_c1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate

# C2 (episodic memory ON, advisory)
python scripts/run_pipeline.py --config experiments/configs/<본실험_c2>.yaml --run-id <base>_c2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate

# C3 (retrieval-only / silent)
python scripts/run_pipeline.py --config experiments/configs/<본실험_c3>.yaml --run-id <base>_c3 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate

# C2_eval_only (평가 전용)
python scripts/run_pipeline.py --config experiments/configs/<본실험_c2_eval>.yaml --run-id <base>_c2_eval_only --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

### 4.3 정합성 검사 (각 조건·시드 또는 머지 run)

```powershell
# pipeline integrity (시드 1개 예: seed42)
python scripts/pipeline_integrity_verification.py --run_dir results/<base>_c1__seed42_proposed --out reports/pipeline_integrity_verification_<base>_c1__seed42.json

# consistency checklist (시드별 또는 머지 run)
python scripts/consistency_checklist.py --run_dir results/<base>_c1__seed42_proposed --triptych_n 5
python scripts/consistency_checklist.py --run_dir results/<base>_c1_aggregated/merged_run_<base>_c1 --triptych_n 5
```

---

## 5. 필수 실행 스크립트 요약표

| 구분 | 스크립트 | run_pipeline 포함 | 본실험 필수 |
|------|----------|-------------------|-------------|
| 실행 전 | check_experiment_config.py | `--with_integrity_check` 시 | ✅ |
| 실험 | run_experiments.py | ✅ | ✅ |
| 스냅샷 | build_run_snapshot.py | ✅ | ✅ |
| paper | build_paper_tables.py | profile=paper | ✅ |
| 리포트 | build_html_report.py | ✅ | ✅ |
| 메트릭 | structural_error_aggregator.py | `--with_metrics` | ✅ |
| 메트릭 | build_metric_report.py | `--with_metrics` | ✅ |
| 집계 | aggregate_seed_metrics.py | `--with_aggregate` | ✅ (시드 반복 시) |
| 정합성 | pipeline_integrity_verification.py | ❌ | ✅ 수동 |
| 정합성 | consistency_checklist.py | ❌ | ✅ 수동 |
| 논문 테이블 | build_paper_tables.py | ❌ | ✅ (논문 작성 시) |
| CR v2 Paper Table | build_cr_v2_paper_table.py | ❌ | ✅ (CR v2 M0 vs M1) |
| RUN 요약 | run_summary.py | ✅ | ✅ |

---

## 6. Config 예시 (본실험, betatest 패턴 기준)

데이터 경로는 §1.5 참고. `train_file`/`valid_file`/`gold_valid_jsonl`은 `dataset_root` 기준 **상대 경로**이다.

```yaml
run_purpose: paper
run_id: <base_run_id>_c1
run_mode: proposed
override_profile: t1

pipeline:
  temperature: 0
  enable_stage2: true
  enable_validator: true
  enable_debate: true
  enable_debate_override: true
  leakage_guard: true

episodic_memory:
  condition: C1   # C2, C3, C2_eval_only 조건별로 변경

data:
  dataset_root: experiments/configs/datasets
  allowed_roots: ["experiments/configs/datasets"]
  input_format: csv
  train_file: real/train.csv       # 또는 real_n50_seed1/train.csv 등
  valid_file: real/valid.csv
  text_column: text
  label_column: null
  target_column: null
  max_length: 192

eval:
  gold_valid_jsonl: real/valid.gold.jsonl

data_roles:
  demo_pool: ["train"]
  report_set: ["valid"]
  report_sources: ["valid_file"]

demo:
  k: 0
  seed: 42
  enabled_for: []
  force_for_proposed: false
  hash_filter: false   # betatest 스타일; paper에서는 true 권장

experiment:
  repeat:
    mode: seed
    seeds: [42, 123, 456]
  concurrency: 3
```

---

## 7. 논문용 테이블 생성 (Tables 1–4)

### 7.1 Legacy / C1–C3 파이프라인

모든 조건(C1, C2, C3, C2_eval)의 시드 실행 및 `aggregate_seed_metrics` 완료 후, IP&M 스타일 논문 테이블을 생성한다:

```powershell
# beta_n50 실험 기준
python scripts/build_paper_tables.py --base_run_id beta_n50 --report md --out reports/paper_tables_beta_n50.md

# 본실험(real n50) 기준
python scripts/build_paper_tables.py --base_run_id finalexperiment_n50_seed1 --report md --out reports/paper_tables_finalexperiment.md
```

- **입력**: 각 조건별 `results/<base_run_id>_c1__seed42_proposed`, … 등 시드별 `derived/metrics/structural_metrics.csv`
- **출력**: Table 1 (RQ1 Structural Error Control), Table 2 (RQ2 Inference Stability), Table 3 (Explicit-only F1), Table 4 (Implicit Subset) — mean (SD) over seeds, 최우수 조건 **굵게**
- **사전 요구**: `aggregate_seed_metrics`는 테이블 생성에 불필요. 시드별 `structural_metrics.csv`만 있으면 됨.

### 7.2 CR (Conflict Review) 파이프라인

CR 실험 시 `export_paper_metrics_aggregated.py` 사용:

```powershell
# CR 논문용: ref-pol F1, Process/Measurement IRR, Grounding 진단 포함
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0__seed42_proposed results/cr_n50_m0__seed123_proposed results/cr_n50_m0__seed456_proposed --out-dir results/cr_n50_m0_paper
```

**테이블 구성**: Table 1 (ref-pol F1) | Table 1b (Grounding) | Table 2A (Process IRR) | Table 2B (Measurement IRR) | Table 3 (Process Evidence)

**사전 요구**: `compute_irr.py` 시드별 실행 → `irr/irr_run_summary.json`에 Process + Measurement IRR 키 존재. 상세: `docs/how_to_run_cr_v1.md`, `docs/evaluation_cr_v2.md`

### 7.3 CR v2 Paper Table (M0 vs M1)

CR v2 M0 vs M1 비교 논문용 테이블. aggregate + compute_irr (--scorecards) 완료 후 실행.

```powershell
python scripts/build_cr_v2_paper_table.py --agg-m0 results/cr_v2_n100_m0_v4_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n100_m1_v4_aggregated/aggregated_mean_std.csv --run-dirs-m0 results/cr_v2_n100_m0_v4__seed42_proposed results/cr_v2_n100_m0_v4__seed123_proposed results/cr_v2_n100_m0_v4__seed456_proposed --run-dirs-m1 results/cr_v2_n100_m1_v4__seed42_proposed results/cr_v2_n100_m1_v4__seed123_proposed results/cr_v2_n100_m1_v4__seed456_proposed --out reports/cr_v2_paper_table.md
```

**출력**: `reports/cr_v2_paper_table.md` — Table 1 (F1), Table 2 (Schema/Error, fix/break/net_gain, subset IRR, subset_n, CDA, AAR), Appendix (A~G: seed-by-seed, bootstrap, break subtype, event count 등).

**사전 요구**: `compute_irr.py --scorecards` 시드별 실행 (subset IRR implicit/negation용). 상세: `docs/run_cr_v2_n100_m0_m1_v3_commands.md`

---

## 8. 산출물 경로

| 산출물 | 경로 |
|--------|------|
| 시드별 결과 | `results/<run_id>__seed<N>_proposed/` |
| derived/metrics | `derived/metrics/structural_metrics.csv`, `structural_metrics_table.md` |
| derived/tables | `derived/tables/triptych_table.tsv` |
| metric_report | `reports/<run_id>_proposed/metric_report.html` |
| 머지 결과 | `results/<base>_aggregated/` |
| pipeline_integrity | `reports/pipeline_integrity_verification_<run_id>.json` |

---

## 9. 참고 문서

- **실행 방법 상세**: `docs/how_to_run.md`
- **CR 실행**: `docs/how_to_run_cr_v1.md`
- **CR v2 M0 vs M1**: `docs/run_cr_v2_n100_m0_m1_v3_commands.md`
- **CR 평가 정의**: `docs/evaluation_cr_v2.md` (ref-pol, IRR, ΔF1)
- **본실험 데이터 배치**: `experiments/configs/datasets/real/README.md`
- **Betatest**: `docs/run_betatest_commands.md`
- **Seed 반복 정책**: `docs/seed_repeat_policy.md`
- **Scorecard·정합성**: `docs/scorecard_path_and_consistency_checklist.md`
- **Fallback 정리**: `docs/fallback_summary.md`
- **파이프라인 흐름**: `docs/pipeline_stages_data_and_metrics_flow.md`
