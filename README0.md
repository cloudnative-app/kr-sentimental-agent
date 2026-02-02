# KR Sentimental Agent — 프로젝트 설명 / Project Overview

한국어 텍스트 기반 ABSA(Aspect-Based Sentiment Analysis) 멀티에이전트 파이프라인입니다.  
Multi-stage, text-only ABSA pipeline: Stage1 (ATE, ATSA, Validator) → Stage2 reviews → Moderator aggregation.  
오케스트레이션: `agents/supervisor_agent.py`, LLM 래핑: `tools/llm_runner.py` / `tools/backbone_client.py`.

---

## 1. 프로젝트 구조 / Project Architecture

| 구분 | 설명 |
|------|------|
| **Stage1** | ATE(관점 추출), ATSA(관점 감성), Validator(구조 검증) — 원문만 입력 |
| **Stage2** | 동일 에이전트의 리뷰 전용(전체 재생성 없음) |
| **Moderator** | Rule A~D로 패치된 출력에 대해 최종 라벨 결정 (Validator/Moderator 판단에 HF 미사용) |
| **산출물** | `outputs.jsonl`, `traces.jsonl`, `scorecards.jsonl`, `manifest.json` |

---

## 2. 디렉토리 구조 (간단 버전) / Directory Map (Short)

```
kr-sentimental-agent/
├── agents/                    # current: 에이전트 러너 (supervisor_agent, baseline_runner, specialized_agents)
├── baselines/                 # current: bl1/bl2/bl3 규칙·간단 모델
├── baseline_wrappers/         # current: 베이스라인 I/O 래퍼
├── data/, data/datasets/      # current: 로더·경로 해석·allowlist 검증
├── deployment/                # legacy: 도커/쿠버/테라폼 예제 (미사용)
├── docs/                      # current: 스키마·CBL·classifier 비교 문서
├── evaluation/                # current: 평가·테스트 스위트
├── examples/                  # legacy: 예시 입력 (사용 자제)
├── experiments/               # current: configs, scripts, reports
├── guardrails/                # legacy: 입력/출력 필터 (러너에 통합됨)
├── guide/                     # current: 대회/가이드 PDF
├── metrics/                   # current: 메트릭 정의·계약
├── observability/             # legacy: 로깅·트레이싱 실험 (보존)
├── reports/                   # current: HTML 리포트 출력
├── resources/patterns/        # current: ko/en 패턴 (부정·대비·토픽)
├── results/                   # current: 런별 산출물 (manifest, traces, scorecards, outputs, ops_outputs, paper_outputs)
├── schemas/                   # current: Pydantic 스키마 (final_output, agent_outputs, metric_trace)
├── scripts/                   # current: 파이프라인·스냅샷·리포트·QA 스크립트
├── tests/                     # current: 계약·회귀 테스트
└── tools/                     # current: backbone_client, llm_runner, demo_sampler, pattern_loader, aux_hf_runner
                               # legacy/unused: classifier_wrapper (prompt_classifier 의존, 파이프라인 미사용)
```

---

## 3. 디렉토리 구조 (상세 버전) / Directory Map (Detailed)

<details>
<summary>펼치기: 전체 트리 + 기능 주석</summary>

```
kr-sentimental-agent/
├── agents/                              # current: 핵심 에이전트 러너
│   ├── prompts/                         # current: Stage1/2, Moderator, BL 프롬프트
│   ├── specialized_agents/              # current: ate_agent, atsa_agent, validator_agent, moderator
│   ├── supervisor_agent.py              # current: 전체 오케스트레이션 진입점
│   ├── baseline_runner.py               # current: BL1/BL2/BL3 실행기
│   ├── base_agent.py                    # current: 에이전트 공통 베이스
│   └── two_stage_supervisor.py          # legacy: 초기 2단계 슈퍼바이저 (미사용)
├── baselines/                           # current: bl1, bl2, bl3
├── baseline_wrappers/                   # current: bl1_wrapper
├── data/                                # current: 데이터 로더·헬퍼
│   ├── datasets/                        # current: loader, 경로 해석, allowlist 검증
│   └── test_small.csv                   # legacy: 소규모 예제
├── deployment/                          # legacy: Docker/K8s/Terraform 예제 (미사용)
├── docs/                                # current: schema_scorecard_trace, CBL_DELIVERABLES, classifier_wrapper 비교
├── evaluation/                          # current: baselines, metrics, test_suite
├── examples/                            # legacy: 라벨 포함 가능 예시 (사용 자제)
├── experiments/
│   ├── configs/                         # current: YAML 설정, allowlist, datasets, latency_gate_config
│   ├── reports/                         # legacy: manifest 백업
│   ├── results/                         # legacy/통합 중: 일부 스크립트 출력 경로
│   └── scripts/                         # current: run_experiments, agent_run, evaluate, prepare_from_json
├── guardrails/                          # legacy: input_validation, output_filtering, safety_checks (러너에 통합)
├── guide/                               # current: NIKL_ABSA 대회 PDF
├── metrics/                             # current: contract, hard_subset
├── observability/                       # legacy: logging, metrics, tracing (보존)
├── reports/                             # current: <run_id>_<mode>/index.html
├── resources/patterns/                   # current: ko.json, en.json (부정·대비·토픽)
├── results/                             # current: 메인 실행 산출물
│   └── <run_id>_<mode>/
│       ├── manifest.json                 # 설정/해시/purpose/integrity
│       ├── traces.jsonl                  # uid/split/input_hash/prompt_hash/stages
│       ├── scorecards.jsonl             # run_id, profile, ate, atsa, validator, moderator, stage_delta, latency, flags, aux_signals
│       ├── outputs.jsonl                 # FinalOutputSchema
│       ├── ops_outputs/                  # run_snapshot, ops_table, top_issues
│       ├── paper_outputs/                # paper 테이블 (paper 프로파일만)
│       └── derived/                     # run_pipeline --with_* 산출물 (filtered, postprocess, payload, metrics)
├── schemas/                             # current: final_output, agent_outputs, metric_trace, baselines
├── scripts/
│   ├── run_pipeline.py                  # current: 통합 파이프라인 (smoke/paper, --with_metrics)
│   ├── check_experiment_config.py       # current: 실행 전 무결성·누수 검사 (--config, --strict)
│   ├── experiment_results_integrate.py # current: E2E 단일 런 통합 또는 merged 메트릭만
│   ├── aggregate_seed_metrics.py       # current: N시드 머징·평균±표준편차·통합 보고서 자동 생성
│   ├── build_run_snapshot.py            # current: ops_outputs
│   ├── build_paper_tables.py            # current: paper_outputs
│   ├── build_html_report.py             # current: HTML 리포트 (ops/paper, latency gate WARN-only)
│   ├── scorecard_from_smoke.py          # current: outputs → scorecards (latency, validator, moderator, stage_delta, aux_signals)
│   ├── structural_error_aggregator.py  # current: merged_scorecards → 구조 오류·HF 지표 집계
│   ├── filter_scorecards.py            # current: 필터/슬라이스
│   ├── postprocess_runs.py             # current: root-cause·안정성 태깅
│   ├── make_pretest_payload.py          # current: smoke+scorecards+입력 번들
│   ├── provider_dry_run.py             # current: 실 제공자 사전 점검
│   ├── schema_validation_test.py       # current: 스키마 스모크
│   ├── report_rules.yaml                # current: 게이트 규칙/임계값
│   ├── ops_rules.yaml                   # current: ops 프로파일 규칙
│   └── paper_rules.yaml                 # current: paper 프로파일 규칙
├── tests/                               # current: test_integrity_features, test_validator_negation_gate, test_moderator_rules 등
└── tools/
    ├── backbone_client.py               # current: LLM 백본 클라이언트
    ├── llm_runner.py                    # current: run_structured, 스키마 기반 출력
    ├── llm_clients.py                   # current: create_client (provider별)
    ├── demo_sampler.py                  # current: 데모 샘플링, forbid_hashes
    ├── pattern_loader.py                # current: 언어별 패턴 로드
    ├── prompt_spec.py                   # current: PromptSpec, DemoExample
    ├── aux_hf_runner.py                 # current: HF 보조 신호 (aux_signals.hf, Validator/Moderator 무영향)
    ├── classifier_wrapper.py            # legacy/unused: HFClassifier (prompt_classifier 의존, 파이프라인 미사용)
    └── data_tools/                      # current: data_loader, label_schema (InternalExample, load_datasets 등)
```

</details>

---

## 4. 격리·미사용 구조 / Isolated or Unused Structure

| 경로 | 상태 | 비고 |
|------|------|------|
| `agents/two_stage_supervisor.py` | legacy | 초기 2단계 슈퍼바이저, 현재 `supervisor_agent` 사용 |
| `tools/classifier_wrapper.py` | unused | HFClassifier; `prompt_classifier` 미존재, 파이프라인에서 미호출 |
| `deployment/` | legacy | 도커/쿠버/테라폼 예제, 현재 실행 경로에서 미사용 |
| `guardrails/` | legacy | 입력/출력 검증은 러너·스키마에 통합됨 |
| `observability/` | legacy | 로깅·트레이싱 실험용, 보존 |
| `examples/` | legacy | 라벨 포함 가능 예시, 실험 시 사용 자제 |
| `data/raw`, `data/old_annotations`, `experiments/data/tmp_*` | blocked | 사용 금지 (BlockedDatasetPathError) |

---

## 5. 주의사항 / Cautions

- **인코딩**: Windows에서 세션마다 `chcp 65001`, `set PYTHONUTF8=1` 권장.
- **run_id**: 공백·특수문자 없이 소문자/숫자/언더스코어만 사용. PII·비밀정보 포함 금지.
- **경로**: `allowed_roots` 밖 경로, 레거시 경로(`data/raw` 등) 사용 시 BlockedDatasetPathError.
- **API 키**: 실 모델 호출 시 커밋·로그 노출 금지. `.env` 또는 환경변수 사용.
- **Stage2**: 리뷰 전용(전체 재생성 없음). scorecards/process_trace로 검증.
- **Paper 테이블**: smoke/sanity 런에서는 `build_paper_tables`가 `--force` 없이 거부.
- **Paper/본실험 전**: `scripts/check_experiment_config.py --config <yaml> --strict`로 설정·누수 검사 권장. 스키마(E)·데모/스플릿·경로(F)·CSV id/uid(F) 검사 포함. `--skip-schema` / `--no-csv-id-check`로 일부 검사 비활성화 가능.

---

## 6. 파이프라인 러너 사용법 / Pipeline Runner Usage

### 6.1 역할

`scripts/run_pipeline.py`는 **실험 실행 → 스냅샷 → (선택) 후처리/필터 → 논문 테이블(paper 프로파일) → HTML 리포트 → (선택) 메트릭 생성**을 한 번에 실행하는 통합 CLI입니다. 기존 스크립트 동작은 바꾸지 않고 순서만 조합합니다.

### 6.2 프로파일

| 프로파일 | 단계 |
|----------|------|
| **smoke** | run_experiments → build_run_snapshot → build_html_report(ops) |
| **paper** | run_experiments → build_run_snapshot → build_paper_tables → build_html_report(paper) |

### 6.3 인자

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
| `--with_metrics` | | **메트릭 생성**: structural_error_aggregator → results/&lt;run_id&gt;_&lt;mode&gt;/derived/metrics/ |
| `--metrics_profile` | | structural_error_aggregator 프로파일: smoke \| regression \| paper_main (기본: paper_main) |
| `--force_paper_tables` | | smoke/sanity 런에서도 paper 테이블 생성 허용 |
| **`--seed`** | | **시드 1개만 실행** (config에 experiment.repeat.seeds 있을 때). 런타임 초과 회피용. 예: `--seed 42` → results/&lt;run_id&gt;__seed42_&lt;mode&gt;/ |
| **`--timeout`** | | 스텝당 최대 초(선택). 기본 없음(무제한). 환경 제한 시 사용 가능. |

### 6.4 run_pipeline 실행 구조 (단일 vs seed 반복)

- **단일 실행**: config에 experiment.repeat 없거나 mode≠seed 이면, `--run-id` 하나에 대해 파이프라인 1회 실행 → `results/<run_id>_<mode>/`.
- **Seed 반복**: config에 **experiment.repeat.mode: seed**, **experiment.repeat.seeds: [42, 123, 456, …]** 가 있으면:
  - **--seed 미지정**: 시드 개수만큼 **순차 실행**. 각 시드마다 run_id가 **&lt;run_id&gt;__seed&lt;N&gt;** 로 붙어 결과 디렉터리가 분리됨 (덮어쓰기 없음). 예: `experiment_mini__seed42_proposed`, `experiment_mini__seed123_proposed`, …
  - **--seed N 지정**: 해당 시드 **1개만** 실행. 장시간 5시드 일괄 실행 시 환경 타임아웃을 피하려면 시드별로 나눠 실행할 때 사용.

**run_pipeline이 자동으로 수행하는 단계** (프로파일·옵션에 따라):

| 순서 | 단계 | 조건 |
|------|------|------|
| 0 | provider_dry_run | --with_dry_run 시 (mock 아님일 때) |
| 1 | run_experiments | 항상 |
| 2 | postprocess_runs | --with_postprocess 시 |
| 3 | filter_scorecards | --with_filter 시 |
| 4 | build_run_snapshot | 항상 |
| 5 | make_pretest_payload | --with_payload 시 |
| 6 | build_paper_tables | profile=paper 시 (smoke/sanity는 exit 2로 스킵) |
| 7 | build_html_report | 항상 |
| 8 | structural_error_aggregator + build_metric_report | --with_metrics 시 |

- **각 시드마다** 위 순서가 한 번씩 수행되며, 결과는 **시드별 디렉터리**에 저장됨. **N개 시드 실행 후 시드 간 머지·집계·통합 보고서**는 run_pipeline 범위 밖이며, 아래 §6.6에서 안내.

### 6.5 본실험 권장 절차 (메트릭 산출까지)

논문/본실험 시 **실행 → 스냅샷 → 논문 테이블 → HTML 리포트 → 메트릭**까지 한 번에 돌리려면 아래 한 줄로 충분합니다.

```powershell
# paper 프로파일 + 메트릭 생성 (권장). experiment_mini/experiment_real 사용 시 seed 반복 자동.
python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

또는 단계를 나눌 경우:

```powershell
# 1) 실험 실행
python experiments/scripts/run_experiments.py --config experiments/configs/experiment_mini.yaml --run-id my_run --mode proposed

# 2) 스냅샷 + 논문 테이블 + HTML 리포트 + 메트릭 (E2E 통합 스크립트)
python scripts/experiment_results_integrate.py --run_dir results/my_run_proposed --with_metrics --metrics_profile paper_main
```

### 6.6 N회(seed) 실행 후 결과 머징 및 보고서 생성

**run_pipeline으로 끝나는 작업**: 시드별 디렉터리·시드별 HTML·시드별 메트릭 생성.  
**머징·평균±표준편차·통합 보고서**: **`scripts/aggregate_seed_metrics.py` 한 번 실행으로 자동 생성** (머지 scorecards, 머지 메트릭, 시드별 평균±표준편차 CSV/MD, 통합 보고서 integrated_report.md, 선택 시 머지용 metric_report.html).

1. **run_pipeline 실행** (전체 시드 또는 시드별 분리 실행)
   - 전체: `python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile paper --with_metrics`
   - 시드 1개만: `python scripts/run_pipeline.py ... --seed 42` → `results/experiment_mini__seed42_proposed/` 등 생성.

2. **머징·평균±표준편차·통합 보고서 한 번에 자동 실행 (권장)**
   ```powershell
   python scripts/aggregate_seed_metrics.py --base_run_id experiment_mini --mode proposed --seeds 42,123,456,789,101 --outdir results/experiment_mini_aggregated --metrics_profile paper_main --with_metric_report
   ```
   또는 이미 있는 런만 지정: `--run_dirs results/experiment_mini__seed42_proposed,results/experiment_mini__seed123_proposed`  
   산출: `outdir/merged_scorecards.jsonl`, `outdir/merged_metrics/`, `outdir/aggregated_mean_std.csv`, `outdir/aggregated_mean_std.md`, `outdir/integrated_report.md`, (--with_metric_report 시) `reports/merged_run/metric_report.html`.

3. **수동 절차 (선택)**  
   스크립트 없이 하려면 시드별 scorecards 이어붙이기 → `experiment_results_integrate.py --merged_scorecards`로 머지 메트릭만 생성 후, 시드별 CSV 평균·표준편차·통합 보고서는 엑셀/스크립트로 직접 작성.

### 6.7 E2E 통합 스크립트 (experiment_results_integrate.py)

실험 **이미 실행된 뒤** 산출물·레포트·메트릭을 일원화할 때 사용합니다.

| 패턴 | 용도 | 예시 |
|------|------|------|
| **단일 런** | 스냅샷 + paper 테이블 + HTML 리포트 + (선택) 메트릭 | `--run_dir results/my_run_proposed --with_metrics` |
| **N회 merged** | merged scorecards만으로 메트릭 생성 (시드 머지 후) | `--merged_scorecards .../scorecards_all_seeds.jsonl --outdir results/merged_metrics` |

```powershell
# 단일 런: 스냅샷 + paper 테이블 + HTML + 메트릭
python scripts/experiment_results_integrate.py --run_dir results/my_run_proposed --with_metrics

# N회(seed) 머지 후: 메트릭만
python scripts/experiment_results_integrate.py --merged_scorecards results/experiment_mini_scorecards_all_seeds.jsonl --outdir results/experiment_mini_merged_metrics --profile paper_main
```

### 6.8 산출물 정리

- **run_pipeline** (또는 run_experiments만) 실행 시: `results/<run_id>_<mode>/` 에 manifest, traces, scorecards, outputs, ops_outputs, (paper 프로파일 시) paper_outputs, (--with_metrics 시) derived/metrics.
- **run_pipeline** 로그: `results/<run_id>_<mode>/derived/*.log`
- HTML 리포트: `reports/<run_id>_<mode>/index.html`
- 메트릭 CSV/MD: `results/<run_id>_<mode>/derived/metrics/` 또는 `--outdir` 지정 경로.

---

## 7. 빠른 실행 / Quick Commands

```powershell
# UTF-8 (Windows)
chcp 65001
set PYTHONUTF8=1

# 의존성
pip install -r requirements.txt

# 스모크 (mock)
python scripts/schema_validation_test.py --mode proposed --n 10 --use_mock 1

# 스모크 (실제, 소량)
python scripts/schema_validation_test.py --mode proposed --n 10 --use_mock 0

# 파이프라인 스모크 프로파일
python scripts/run_pipeline.py --config experiments/configs/smoke_xlang.yaml --run-id smoke_test --mode proposed --profile smoke

# 파이프라인 paper 프로파일 (메트릭 포함)
python scripts/run_pipeline.py --config experiments/configs/proposed.yaml --run-id paper_run --mode proposed --profile paper --with_metrics

# 실행 전 검사 (paper 런 권장)
python scripts/check_experiment_config.py --config experiments/configs/minitest60_gold_fold0.yaml --strict

# 실험만 실행 (스냅샷/리포트 없음)
python experiments/scripts/run_experiments.py --config experiments/configs/smoke_xlang.yaml --run-id my_run --mode proposed

# 스냅샷 → HTML 리포트
python scripts/build_run_snapshot.py --run_dir results/<run_id>_proposed
python scripts/build_html_report.py --run_dir results/<run_id>_proposed --out_dir reports/<run_id>_proposed --profile ops

# 구조 오류·HF 지표 집계
python scripts/structural_error_aggregator.py --input results/<run_id>_proposed/scorecards.jsonl --outdir results/metrics --profile paper_main
```

---

## 8. 기술적 기여사항 / Technical Contributions

- **CBL(Critique-Based Loop)**: Validator 구조 리스크 → Stage2 리뷰 → Moderator Rule A~D. Stage2 채택/기각 이유는 `moderator.applied_rules`, `arbiter_flags`로 기록.
- **Latency gate**: 프로파일별(smoke, regression, paper_main) `latency_gate_config.yaml`, WARN만 사용(FAIL 없음). scorecard에 `latency.total_ms`, `gate_threshold_ms`, `gate_status`, `profile` 포함.
- **Scorecard/Trace 스키마**: `run_id`, `profile`, `ate`, `atsa`, `validator`(stage1/stage2 동일 스키마), `moderator`(applied_rules, arbiter_flags), `stage_delta`, `latency`, `flags`, `aux_signals`. Trace에 `prompt_hash` 기록.
- **HF 보조 신호**: `aux_signals.hf`는 Validator/Moderator에 무영향. scorecard에만 기록. `pipeline.aux_hf_enabled`, `aux_hf_checkpoint`로 켜기/끄기.
- **Structural error aggregator**: `structural_error_aggregator.py` — 구조 오류 유형별 발생률, HF–LLM 불일치율, HF Disagreement Coverage of Structural Risks, Conditional Improvement Gain(골드 있을 때) 등 논문용 CSV/표 생성.
- **실험 무결성**: 텍스트만 LLM 입력, 데모는 train만, `demo_k=0` 기본. RunManifest에 cfg_hash, prompt versions, allowed_roots, integrity, **data_roles** 기록. CaseTrace에 uid, input_hash, call_metadata.
- **스플릿 중복 탐지**: `build_run_snapshot`에서 `split_overlap_any_rate` 계산. paper 프로파일에서 0이어야 pass.
- **데모 누수 방지**: `forbid_hashes`로 valid/test와 텍스트 해시 중복 제거. paper 런에서 자동 활성화.
- **실행 전 검사**: paper/본실험 전 `scripts/check_experiment_config.py --config <yaml> --strict` 실행 권장. 스키마(E)·데모/스플릿·경로(F)·CSV id/uid(F) 검사 포함. `--skip-schema` / `--no-csv-id-check`로 일부 검사 비활성화 가능.

---

## 9. 안전장치 / Safeguards

- **Leakage guard**: 정답 라벨/주석은 프롬프트에 넣지 않음. 데이터 로드 시 label/target/span/annotation 메타 검출 시 RuntimeError.
- **경로 allowlist**: `allowed_roots` 밖 데이터셋 경로 사용 시 BlockedDatasetPathError.
- **Run purpose**: manifest에 `purpose` (smoke/sanity/paper/dev). smoke/sanity 런은 paper 테이블 빌더에서 `--force` 없이 거부.
- **Latency gate**: WARN만 사용(FAIL 없음). `experiments/configs/latency_gate_config.yaml`에서 프로파일별 임계값.
- **Span 무결성**: `strict_integrity` 시 span이 원문 범위 밖이면 RuntimeError.

---

## 10. 더 보기 / See Also

- **GitHub vs 로컬 차이**: `docs/github_vs_local_diff.md` (origin/main과 로컬 레포의 아키텍처·디렉터리·실행·설정 차이 정리).
- **실행 방법·설정 양식·N회 머징**: `docs/how_to_run.md` (퀵스타트, run_pipeline.py 사용, N회(seed) 실행 후 결과 머징·보고서 절차, 무결성·config 양식).
- **실험 무결성·누수 관리**: `docs/experiment_integrity_and_leakage_management.md` (데이터 역할, 데모·페이퍼 정책, 경로·골드·CSV 규칙, 실행 전 검사). 
