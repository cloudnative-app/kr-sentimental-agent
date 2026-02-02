# How to Run — 퀵스타트·파이프라인·데이터·설정

실험 실행 방법, `run_pipeline.py` 사용, **실험 무결성·데이터 누수 방지·실수 방지**를 위한 데이터 이용·분할·폴드·config 양식까지 한 문서에 정리합니다.

---

## 1. 퀵스타트 / Quick Start

### 1.1 환경 준비

```powershell
# UTF-8 (Windows)
chcp 65001
set PYTHONUTF8=1

# 의존성
pip install -r requirements.txt
```

- **run_id**: 공백·특수문자 없이 소문자/숫자/언더스코어만. PII·비밀정보 포함 금지.
- **API 키**: 실 모델 호출 시 `.env` 또는 환경변수 사용. 커밋·로그 노출 금지.

### 1.2 스모크(빠른 점검)

```powershell
# 스모크 (mock, 10건)
python scripts/schema_validation_test.py --mode proposed --n 10 --use_mock 1

# 파이프라인 스모크 프로파일 (실험 → 스냅샷 → HTML 리포트)
python scripts/run_pipeline.py --config experiments/configs/smoke_xlang.yaml --run-id smoke_test --mode proposed --profile smoke
```

- 스모크는 **동일 파일**을 train/valid/test로 재사용해도 됨. paper 테이블은 생성되지 않음.

### 1.3 본실험(paper) / 리허설(experiment_mini) 실행

- **정책**: 반복 단위는 **폴드가 아닌 seed**. 단일 고정 데이터셋 + N회 시드 반복. 자세한 내용은 `docs/seed_repeat_policy.md` 참고.

```powershell
# 실행 전 설정·fail-fast 검사 (권장)
python scripts/check_experiment_config.py --config experiments/configs/experiment_mini.yaml --strict

# 리허설(미니): paper 프로파일 + 메트릭
python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile paper --with_metrics --metrics_profile paper_main

# 본실험: experiment_real.yaml 사용 (데이터는 experiments/configs/datasets/real/ 에 배치)
python scripts/check_experiment_config.py --config experiments/configs/experiment_real.yaml --strict
python scripts/run_pipeline.py --config experiments/configs/experiment_real.yaml --run-id experiment_real --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

- 본실험 전에는 **데이터 정책·config 양식**(아래 §4·§5)을 준수하고, `check_experiment_config --strict`로 검사할 것.

---

## 2. run_pipeline.py 사용법

### 2.1 역할

`scripts/run_pipeline.py`는 **실험 실행 → 스냅샷 → (선택) 후처리/필터 → 논문 테이블(paper 시) → HTML 리포트 → (선택) 메트릭 생성**을 한 번에 돌리는 통합 CLI입니다. 기존 스크립트 동작은 바꾸지 않고 순서만 조합합니다.

### 2.2 프로파일

| 프로파일 | 단계 |
|----------|------|
| **smoke** | run_experiments → build_run_snapshot → build_html_report(ops) |
| **paper** | run_experiments → build_run_snapshot → build_paper_tables → build_html_report(paper) |

- smoke/sanity 런에서는 `build_paper_tables`가 `--force` 없이 거부됨. paper 테이블이 필요하면 config에 `run_purpose: paper`를 두고 train/valid/test를 **서로 다른 파일**로 두어야 함.

### 2.3 필수·선택 인자

| 인자 | 필수 | 설명 |
|------|------|------|
| `--config` | ✓ | 설정 YAML 경로 |
| `--run-id` | ✓ | 런 식별자 |
| `--mode` | ✓ | proposed, bl1, bl2, bl3 |
| `--profile` | ✓ | smoke \| paper |
| `--with_dry_run` | | 실행 전 provider_dry_run (실 API 점검) |
| `--with_postprocess` | | postprocess_runs (안정성·root-cause 태깅) |
| `--with_filter` | | filter_scorecards (derived/filtered) |
| `--with_payload` | | make_pretest_payload (derived/payload) |
| `--with_metrics` | | 메트릭 생성 → results/&lt;run_id&gt;_&lt;mode&gt;/derived/metrics/ |
| `--metrics_profile` | | structural_error_aggregator 프로파일: smoke \| regression \| paper_main (기본: paper_main) |
| `--force_paper_tables` | | smoke/sanity 런에서도 paper 테이블 생성 허용 (DO NOT REPORT 배너 추가) |
| `--seed` | | 시드 1개만 실행 (config에 experiment.repeat.seeds 있을 때). 예: `--seed 42` → results/&lt;run_id&gt;__seed42_&lt;mode&gt;/ |
| `--timeout` | | 스텝당 최대 초(선택). 환경 제한 시 사용. |
| `--seed_concurrency` | | 시드 2개 이상일 때 동시 실행 수 (기본 1=순차). config의 experiment.repeat.concurrency 덮어씀. |
| `--with_integrity_check` | | 실행 전 check_experiment_config.py --strict 실행 (무결성·누수 검사). 무겁다면 개별 실행 권장. |
| `--run_summary_fail_fast` | | 파이프라인 종료 후 run_summary에서 processing_splits/unique_uid 등 불일치 시 exit 1. |
| `--with_aggregate` | | 시드 반복 완료 후 aggregate_seed_metrics.py 자동 실행 (머징·평균±표준편차·통합 보고서). |

### 2.4 run_pipeline 실행 구조 (단일 vs seed 반복)

- **단일 실행**: config에 experiment.repeat 없거나 mode≠seed → `results/<run_id>_<mode>/` 한 개 생성.
- **Seed 반복**: config에 `experiment.repeat.mode: seed`, `experiment.repeat.seeds: [42, 123, …]` 있으면:
  - **--seed 미지정**: 시드 개수만큼 순차 실행. 각 시드마다 `run_id`가 `<run_id>__seed<N>`으로 붙어 **시드별 디렉터리** 생성 (덮어쓰기 없음). 예: `results/experiment_mini__seed42_proposed/`, `results/experiment_mini__seed123_proposed/`, …
  - **--seed N**: 해당 시드 1개만 실행 (장시간 일괄 실행 시 타임아웃 회피용).

**run_pipeline이 자동으로 수행하는 단계** (프로파일·옵션에 따라):  
check_experiment_config(--with_integrity_check 시) → provider_dry_run(선택) → run_experiments → postprocess_runs(선택) → filter_scorecards(선택) → build_run_snapshot → make_pretest_payload(선택) → build_paper_tables(paper 시) → build_html_report → structural_error_aggregator + build_metric_report(--with_metrics 시) → **run_summary (RUN SUMMARY 출력)**.  
**N개 시드 실행 후 시드 간 머지**는 `--with_aggregate`로 파이프라인에 통합 가능하며, 생략 시 §2.6대로 별도 실행.

### 2.5 실행 후 산출물

- **run_pipeline** (또는 run_experiments만) 실행 시: `results/<run_id>_<mode>/` (seed 반복 시 `<run_id>`에 `__seed42` 등 포함)  
  - manifest.json, traces.jsonl, scorecards.jsonl, outputs.jsonl  
  - ops_outputs/, (paper 프로파일 시) paper_outputs/  
  - (--with_metrics 시) derived/metrics/
- HTML 리포트: `reports/<run_id>_<mode>/index.html` (시드별로 생성됨)

### 2.6 N회(seed) 실행 후 결과 머징 및 보고서 생성

| 구분 | 담당 | 내용 |
|------|------|------|
| **run_pipeline이 하는 일** | 자동 | 시드별 실험 실행, 시드별 스냅샷·paper 테이블·HTML·메트릭. 결과는 시드별 디렉터리·시드별 리포트에 저장. |
| **머징·평균±표준편차·통합 보고서** | **자동** | `scripts/aggregate_seed_metrics.py` 한 번 실행으로 머지·머지 메트릭·시드별 평균±표준편차·통합 보고서(및 선택 시 메트릭 리포트 HTML)까지 생성. |

**절차 요약**

1. **run_pipeline 실행** (전체 시드 또는 `--seed N`으로 시드별 분리 실행).  
   완료 후: `results/experiment_mini__seed42_proposed/`, … 각각에 scorecards.jsonl, derived/metrics/ 등 존재.

2. **머징·평균±표준편차·통합 보고서**  
   - **파이프라인 통합**: 시드 반복 시 `--with_aggregate`를 주면 모든 시드 완료 후 `aggregate_seed_metrics.py`가 자동 실행됩니다.  
   - **개별 실행**: 아래처럼 한 번에 실행할 수도 있습니다.  
   `aggregate_seed_metrics.py`가 다음을 한 번에 수행합니다:  
   - 시드별 scorecards.jsonl 이어붙이기 → `merged_scorecards.jsonl`  
   - 머지 메트릭 생성 (structural_error_aggregator) → `merged_metrics/`  
   - 시드별 structural_metrics.csv 수집 → **평균±표준편차** 계산 → `aggregated_mean_std.csv`, `aggregated_mean_std.md`  
   - **통합 보고서** 작성 → `integrated_report.md`  
   - (선택) 머지 런용 메트릭 리포트 HTML → `--with_metric_report` 시 `reports/merged_run/metric_report.html`

   ```powershell
   # base_run_id + seeds 지정
   python scripts/aggregate_seed_metrics.py --base_run_id experiment_mini --mode proposed --seeds 42,123,456,789,101 --outdir results/experiment_mini_aggregated --metrics_profile paper_main --with_metric_report

   # 또는 이미 있는 런 디렉터리만 나열
   python scripts/aggregate_seed_metrics.py --run_dirs results/experiment_mini__seed42_proposed,results/experiment_mini__seed123_proposed --outdir results/experiment_mini_aggregated --with_metric_report
   ```

   시드별 CSV가 아직 없으면 `--ensure_per_seed_metrics`를 붙이면 각 시드에 대해 structural_error_aggregator를 먼저 실행합니다.

3. **수동 절차 (선택)**  
   스크립트 없이 하려면: 시드별 scorecards를 이어붙인 뒤 `experiment_results_integrate.py --merged_scorecards`로 머지 메트릭만 생성하고, 시드별 CSV의 평균·표준편차·통합 보고서는 엑셀/스크립트로 직접 계산·작성.

### 2.7 이미 실행된 런에서 스냅샷·리포트·메트릭만

실험은 이미 돌렸고, 스냅샷·paper 테이블·HTML·메트릭만 다시 만들 때:

```powershell
python scripts/experiment_results_integrate.py --run_dir results/<run_id>_proposed --with_metrics --metrics_profile paper_main
```

---

## 3. 실험 무결성·데이터 누수 방지·실수 방지

### 3.1 무결성·누수 방지 (달라진 점)

- **텍스트만 LLM 입력**: 정답 라벨/주석은 프롬프트에 넣지 않음. `pipeline.leakage_guard: true` 시 입력 텍스트/메타에 정답·라벨·주석 용어가 있으면 RuntimeError.
- **데모는 train만**: `data_roles.demo_pool: [train]`만 허용. valid/test를 데모 풀에 넣으면 **누수**. paper 런에서는 `forbid_hashes`로 valid/test 텍스트 해시를 데모에서 자동 제외.
- **manifest에 data_roles 기록**: run_experiments가 config의 data_roles를 manifest에 저장. build_paper_tables는 report_set을 manifest에서 읽음.
- **스플릿 중복 탐지**: build_run_snapshot에서 train/valid/test 간 `input_hash` 중복률(`split_overlap_any_rate`) 계산. paper 런에서는 0이어야 정상.
- **Run purpose**: smoke/sanity/paper/dev. smoke/sanity는 paper 테이블 빌더에서 `--force` 없이 거부.

### 3.2 실수 방지 — 실행 전 검사

paper/본실험 전에 **반드시** 아래 검사를 실행할 것:

```powershell
python scripts/check_experiment_config.py --config <your_config.yaml> --strict
```

검사 내용:

| 검사 | 내용 |
|------|------|
| **스키마 (E)** | paper 시 report_sources/blind_sources 명시, demo_pool∩eval 공집합, sources↔data.*_file 매핑 유효 |
| **데모/스플릿** | paper 시 train/valid/test 파일 경로가 서로 다름 |
| **경로 (F)** | data.dataset_root가 data.allowed_roots 중 하나의 하위 |
| **CSV id/uid (F)** | input_format=csv일 때 train/valid/test CSV에 `id` 또는 `uid` 컬럼 존재 (골드 매칭용) |

- 스모크처럼 골드를 쓰지 않는 설정: `--no-csv-id-check`로 CSV id 검사만 건너뛸 수 있음.
- 스키마만 건너뛸 때: `--skip-schema`.

---

## 4. 데이터 이용·분할·폴드

### 4.1 스플릿 역할

| 스플릿 | config 키 | 역할 |
|--------|------------|------|
| **train** | train_file | 데모 풀(demo_pool)로만 사용. LLM에 넣는 데모 예시는 여기서만 뽑음. |
| **valid** | valid_file | report_set. 메트릭·리포트에 포함되는 split. |
| **test** | test_file | blind_set. 블라인드 평가용. |

- **규칙**: 데모는 **train만** 사용. valid/test는 데모에 쓰이면 안 됨(UID·텍스트 해시로 자동 제외).
- **paper 런**: train/valid/test **파일 경로가 서로 달라야** 함. 같은 파일을 쓰면 스플릿 중복으로 run_snapshot에서 경고.

### 4.2 data_roles

| 키 | 의미 | 기본값 |
|----|------|--------|
| demo_pool | 데모로 쓸 수 있는 split (k=0이면 사실상 미사용) | [train] |
| report_set | 메트릭/리포트에 넣을 split (fallback) | [valid] |
| blind_set | 블라인드 평가용 split (fallback) | [test] |
| **report_sources** | **리포트에 쓸 데이터 소스(파일 키). paper 필수** | 없음 |
| **blind_sources** | **블라인드 평가용 데이터 소스(파일 키). paper 필수** | 없음 |
| tuning_pool | (미사용) | [] |

- **paper 런**: `report_sources`와 `blind_sources`를 반드시 명시. 예: `report_sources: ["valid_file"]` 또는 `["test_file"]`, `blind_sources: ["test_file"]` 또는 `[]`. 스플릿 이름(valid/test)이 아닌 **파일 소스**(train_file/valid_file/test_file)로 지정해 폴드·valid 없음 혼란을 없앰.
- report_sources ∪ blind_sources(있을 때) 또는 report_set ∪ blind_set에 해당하는 예제의 **텍스트 해시**가 데모 샘플링 시 제외(forbid_hashes)됨.

### 4.3 폴드(2-fold 예)

2-fold처럼 valid를 폴드별로 나누는 경우:

- **fold0**: train = fold0_train.csv, test(블라인드) = fold0_valid.csv, 골드 = fold0_valid.gold.jsonl  
- **fold1**: train = fold1_train.csv, test = fold1_valid.csv, 골드 = fold1_valid.gold.jsonl  

config는 **폴드마다 하나**. 예: `minitest60_gold_fold0.yaml`, `minitest60_gold_fold1.yaml`.

- **valid_file 없이** train_file / test_file만 쓸 수 있음. 이때 **report_sources: ["test_file"]**, **blind_sources: ["test_file"]**로 두면 test_file에서 로드된 행이 리포트·블라인드 모두에 사용됨. (스플릿 이름 fallback만 쓰면 report_set [valid]에 해당하는 행이 없어 혼란이 생김.)
- **골드**: eval.gold_test_jsonl (또는 gold_valid_jsonl)에 폴드별 gold JSONL 경로 지정. CSV의 `id`(또는 `uid`)와 gold JSONL의 `uid`가 **일치**해야 scorecard에 gold_triplets가 주입됨.

### 4.4 데이터 파일 준비

- **CSV**: 최소 컬럼 `id`(또는 `uid`), `text`. 골드 매칭을 위해 **id/uid 필수**. 라벨 컬럼은 넣지 않음(label_column: null).
- **골드 JSONL**: 한 줄에 한 샘플. `{"uid": "...", "gold_triplets": [{aspect_ref, opinion_term, polarity}, ...]}`. uid는 CSV의 id와 동일해야 함.
- **경로**: 데이터는 `data.dataset_root` 하위에 두고, `data.allowed_roots`에 dataset_root가 포함되도록 할 것. 일관성 위해 `experiments/configs/datasets/` 하위 사용 권장.

---

## 5. Config 양식

### 5.1 최소·권장 구조

```yaml
# 목적: paper | smoke | sanity | dev (본실험은 paper)
run_purpose: paper
run_id: my_run
run_mode: proposed

pipeline:
  enable_stage2: true
  enable_validator: true
  leakage_guard: true   # 본실험 시 true 유지

data:
  dataset_root: experiments/configs/datasets
  allowed_roots: ["experiments/configs/datasets"]
  input_format: csv
  train_file: valid/fold0_train.csv
  valid_file: valid/fold0_valid.csv   # 없으면 생략 가능(2-fold는 test_file만 쓸 수 있음)
  test_file: valid/fold0_valid.csv
  text_column: text
  label_column: null
  target_column: null
  max_length: 192

# 골드가 있을 때만
eval:
  gold_valid_jsonl: valid/fold0_valid.gold.jsonl   # valid 쪽 골드
  gold_test_jsonl: valid/fold0_valid.gold.jsonl     # test 쪽 골드 (동일 파일 가능)

backbone:
  provider: openai
  model: gpt-4.1-mini

data_roles:
  demo_pool: ["train"]
  tuning_pool: []
  report_set: ["valid"]
  blind_set: ["test"]
  report_sources: ["valid_file"]   # paper 필수
  blind_sources: ["test_file"]     # paper 필수 ([] 가능)

demo:
  k: 0
  seed: 42
  enabled_for: []
  force_for_proposed: false
  hash_filter: true   # paper 시 자동 on이지만 명시 권장
```

### 5.2 블록별 요약

| 블록 | 필수/선택 | 설명 |
|------|------------|------|
| run_purpose | 권장 | paper / smoke / sanity / dev. 미지정 시 config 경로 basename에서 smoke/sanity 추론, 나머지는 dev. |
| run_id, run_mode | config에서 지정 또는 CLI에서 덮어씀 | run_id는 런 식별자. run_mode는 proposed, bl1, bl2, bl3. |
| pipeline | 권장 | leakage_guard: true(본실험), enable_stage2, enable_validator. |
| data | 필수 | dataset_root, allowed_roots, input_format, train_file, (valid_file), test_file, text_column, label_column: null. |
| eval | 골드 있을 때 | gold_valid_jsonl, gold_test_jsonl. 상대 경로는 dataset_root 기준. |
| backbone | 필수 | provider, model. 스모크는 provider: mock, model: mock-model. |
| data_roles | 권장(paper 필수) | demo_pool: [train], report_set/blind_set(fallback), **report_sources/blind_sources**(paper 필수). |
| demo | 권장 | k: 0(본실험), seed: 42, hash_filter: true(paper). |

### 5.3 스모크 vs 본실험(paper)

| 항목 | 스모크 | 본실험(paper) |
|------|--------|----------------|
| run_purpose | smoke (또는 생략, 파일명에 smoke 포함) | paper |
| train/valid/test 파일 | 동일 파일 재사용 가능 | **서로 다른 파일** 필수 |
| CSV id/uid | 없어도 됨 (--no-csv-id-check) | **필수** (골드 매칭) |
| dataset_root | allowed_roots 하위 | 동일 |
| check_experiment_config | 선택 | **--strict 권장** |

### 5.4 2-fold 설정 예 (minitest60_gold_fold0)

- valid_file 없이 train_file + test_file만 사용.
- test_file이 곧 “이 폴드의 평가용 split” CSV. 골드는 같은 행에 대한 gold JSONL을 eval.gold_test_jsonl에 지정.

```yaml
run_purpose: paper
run_id: minitest60_fold0
run_mode: proposed

pipeline:
  enable_stage2: true
  enable_validator: true
  leakage_guard: true

data:
  dataset_root: experiments/configs/datasets
  allowed_roots: ["experiments/configs/datasets"]
  input_format: csv
  train_file: valid/fold0_train.csv
  test_file: valid/fold0_valid.csv
  text_column: text
  label_column: null
  target_column: null
  max_length: 192

eval:
  gold_test_jsonl: valid/fold0_valid.gold.jsonl

data_roles:
  demo_pool: ["train"]
  tuning_pool: []
  report_set: ["valid"]
  blind_set: ["test"]
  report_sources: ["test_file"]   # valid_file 없으므로 평가 행 = test_file
  blind_sources: ["test_file"]

demo:
  k: 0
  seed: 42
  hash_filter: true
```

- 폴드 1은 동일 구조로 train_file: valid/fold1_train.csv, test_file: valid/fold1_valid.csv, gold_test_jsonl: valid/fold1_valid.gold.jsonl, report_sources/blind_sources 동일, run_id: minitest60_fold1 등으로 config를 하나 더 두면 됨.

### 5.5 experiment_mini / experiment_real (단일 고정 데이터 + seed 반복, 폴드 없음)

- **정책 전환**: 반복 단위는 **폴드가 아닌 seed**. 동일 데이터셋에서 시드만 바꿔 N회 실행 후 seed 기준 집계. 상세: `docs/seed_repeat_policy.md`.

**experiment_mini (리허설)**

- **데이터 생성**: 단일 분할(폴드 없음). `experiments/configs/datasets/train/valid.jsonl` → 80/20 train/valid.
- **스크립트**: `python scripts/make_mini_dataset.py` → `experiments/configs/datasets/mini/`에 `train.csv`, `valid.csv`, `valid.gold.jsonl` 생성.
- **설정**: `experiment_mini.yaml`. train_file: `mini/train.csv`, valid_file: `mini/valid.csv`, report_sources: `["valid_file"]`, experiment.repeat.mode: `seed`, seeds: `[42, 123, 456, 789, 101]`.
- **실행 전**: `python scripts/check_experiment_config.py --config experiments/configs/experiment_mini.yaml --strict`.

**experiment_real (본실험)**

- **데이터 위치**: `experiments/configs/datasets/real/`에 `train.csv`, `valid.csv`, `valid.gold.jsonl` 배치.
- **생성·이용 안내**: `experiments/configs/datasets/real/README.md` 참고 (어디에 저장·어떻게 생성할지).
- **설정**: `experiment_real.yaml`. 동일 정책(valid만 평가, seed 반복).

---

## 6. 요약 체크리스트

1. **데이터**: CSV에 `id`(또는 `uid`), `text` 포함. 골드 사용 시 JSONL의 uid와 일치.
2. **경로**: dataset_root는 allowed_roots 하위. 데이터 파일은 dataset_root 기준 상대 경로.
3. **data_roles**: `report_set`은 split label, **`report_sources`는 실제 파일 키(ground truth)**. paper에서는 report_sources: `["valid_file"]`만 사용.
4. **paper 런**: valid_file만 평가. demo는 비활성(k=0, enabled_for=[], force_for_proposed=false). run_purpose: paper.
5. **실행 전**: `python scripts/check_experiment_config.py --config <config.yaml> --strict`.
6. **실행**: `python scripts/run_pipeline.py --config <config> --run-id <id> --mode proposed --profile paper --with_metrics`. seed 반복 시 run_id에 `__seed42` 등이 자동 붙어 덮어쓰기 방지.
7. **N회 실행 후**: 시드 간 머지·평균±표준편차·통합 보고서는 `scripts/aggregate_seed_metrics.py` 한 번으로 자동 생성. §2.6 참고.

**운영 5줄** (상세: `docs/seed_repeat_policy.md` §8): (1) 본 연구는 학습/튜닝 없음(Zero-shot only). (2) 평가는 valid_file(+gold)에서만. (3) 리허설(mini)과 본실험(real)은 동일 파이프라인·데이터만 다름. (4) 반복은 seed 기반, seed별 run_id 분리 저장. (5) mini split은 파이프라인 점검용, 라벨은 gold JSONL에만 존재.

---

## 7. 더 보기

- **Seed 반복 정책 (Fold → Seed 전환)**: `docs/seed_repeat_policy.md`
- **실험 무결성·누수 관리 상세**: `docs/experiment_integrity_and_leakage_management.md`
- **본실험 데이터 배치·생성**: `experiments/configs/datasets/real/README.md`
- **README0**: `README0.md` (§6 파이프라인 러너·실행 구조·N회 머징, §7 빠른 실행, §8 기술적 기여사항)
- **변경리포트 (A·C·D·E·F)**: `docs/change_report_A_C_D.md`
