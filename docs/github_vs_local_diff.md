# GitHub 레포 vs 로컬 레포 차이 정리

이 문서는 [cloudnative-app/kr-sentimental-agent](https://github.com/cloudnative-app/kr-sentimental-agent) (origin/main)과 현재 로컬 레포지토리의 차이를 정리합니다.  
로컬 기준 설명은 `README0.md` 및 `docs/` 내 관련 문서를 참조했습니다.

---

## 1. 개요

| 구분 | GitHub (origin/main) | 로컬 (현재) |
|------|----------------------|-------------|
| **목적** | 한국어 **감성분석** (2단계 멀티 에이전트) | 한국어 **ABSA** (Aspect-Based Sentiment Analysis) |
| **태스크** | 문장 단위 감성 라벨 (긍정/부정 등) | 관점 추출(ATE) + 관점별 감성(ATSA) + 구조 검증 + 최종 집계 |
| **에이전트** | 분석가(Analyst), 공감가(Empath), 비평가(Critic) | ATE, ATSA, Validator, Moderator (+ 베이스라인 bl1/bl2/bl3) |
| **오케스트레이션** | `two_stage_supervisor` → 토론 후 최종 판단 | `supervisor_agent` → Stage1 → Stage2 리뷰 → 패치 → Moderator Rule A~D |
| **실행 진입점** | `agent_run.py --mode two_stage`, `run_experiments.py` | `scripts/run_pipeline.py` (통합 파이프라인), `run_experiments.py` |

---

## 2. 아키텍처·파이프라인

### 2.1 GitHub (origin/main)

- **2단계 프로세스**: (1) 독립적 의견수렴 → (2) 토론단계
- **3인 페르소나**: Analyst(데이터 분석), Empath(감정 맥락), Critic(비판·뉘앙스)
- **최종 결과**: 토론 결과를 종합한 `results['final'].label`
- **언급된 기술**: LangGraph 워크플로우, 이미지와 일치하는 아키텍처

### 2.2 로컬 (현재)

- **Stage1**: ATE(관점 추출) → ATSA(관점 감성) → Validator(구조 검증). 원문만 입력.
- **Stage2**: 동일 에이전트의 **리뷰 전용** (Validator 피드백 반영, 전체 재생성 없음).
- **패치 적용**: `_apply_stage2_reviews`에서 Validator proposal + ATE/ATSA review 순으로 적용.
- **Moderator**: Rule A~D, M, Z로 패치된 출력에 대해 최종 라벨 결정 (LLM 없음).
- 상세 호출 순서·규칙: `docs/pipeline_structure_and_rules.md` 참조.

---

## 3. 디렉터리·파일 차이

### 3.1 GitHub에만 있거나 GitHub 기준으로 사용 중인 것

| 경로 | 비고 |
|------|------|
| `agents/specialized_agents/analyst_agent.py` | 삭제됨 (로컬) |
| `agents/specialized_agents/empath_agent.py` | 삭제됨 (로컬) |
| `agents/specialized_agents/critic_agent.py` | 삭제됨 (로컬) |
| `agents/two_stage_supervisor.py` | 로컬에는 있으나 **legacy**, 미사용 |
| `guardrails/` (input_validation, output_filtering, safety_checks) | 로컬에서 삭제; 기능은 러너·스키마에 통합 |
| `observability/` (logging, metrics, tracing) | 로컬에서 삭제; 보존 여부는 README0 기준 legacy |
| `deployment/` (Dockerfile, docker-compose, k8s/, terraform/) | 로컬에서 삭제; README0 기준 **legacy**, 현재 실행 경로 미사용 |
| `examples/labeling/internal/*.json` | 로컬에서 삭제; README0 기준 **legacy**, 사용 자제 |
| `tools/classifier_wrapper.py` | 로컬에 있을 수 있으나 **unused** (prompt_classifier 미존재, 파이프라인 미호출) |
| `test_langgraph_integration.py` | 로컬에서 삭제 |

### 3.2 로컬에만 추가된 것 (현재 사용)

| 경로 | 비고 |
|------|------|
| `README0.md` | 로컬 프로젝트 설명·구조·파이프라인·주의사항 (본 차이 문서의 로컬 기준) |
| `docs/` | how_to_run, pipeline_structure_and_rules, schema_scorecard_trace, experiment_integrity_and_leakage_management, seed_repeat_policy 등 |
| `agents/specialized_agents/ate_agent.py` | 관점 추출 |
| `agents/specialized_agents/atsa_agent.py` | 관점 감성 |
| `agents/specialized_agents/validator_agent.py` | 구조 검증 |
| `agents/specialized_agents/moderator.py` | Rule 기반 최종 결정 |
| `agents/prompts/` | Stage1/2, Moderator, BL용 프롬프트 |
| `agents/baseline_runner.py` | bl1/bl2/bl3 실행 |
| `baselines/`, `baseline_wrappers/` | bl1, bl2, bl3 및 I/O 래퍼 |
| `scripts/run_pipeline.py` | 통합 파이프라인 (smoke/paper, --with_metrics 등) |
| `scripts/aggregate_seed_metrics.py` | N시드 머징·평균±표준편차·통합 보고서 |
| `scripts/experiment_results_integrate.py` | E2E 단일 런 통합 또는 merged 메트릭 |
| `scripts/check_experiment_config.py` | 실행 전 무결성·누수 검사 |
| `scripts/build_run_snapshot.py`, `build_paper_tables.py`, `build_html_report.py` | 스냅샷·논문 테이블·HTML 리포트 |
| `scripts/scorecard_from_smoke.py`, `structural_error_aggregator.py` | 스코어카드·구조 오류·메트릭 집계 |
| `schemas/` | Pydantic 스키마 (final_output, agent_outputs, metric_trace, baselines) |
| `metrics/` | contract, hard_subset |
| `data/datasets/` | 로더·경로 해석·allowlist 검증 |
| `resources/patterns/` | ko/en 패턴 (부정·대비·토픽) |
| `evaluation/baselines.py` | 베이스라인 평가 |
| `tests/` | 계약·회귀 테스트 (무결성, Moderator 규칙, Validator 등) |
| `tools/backbone_client.py`, `llm_runner.py`, `llm_clients.py`, `demo_sampler.py`, `pattern_loader.py`, `prompt_spec.py`, `aux_hf_runner.py` | LLM 래핑·데모·패턴·HF 보조 신호 |

---

## 4. 실행·사용법 차이

### 4.1 GitHub (README 기준)

```bash
# 단일 텍스트
python experiments/scripts/agent_run.py --mode two_stage --text "..." --llm-provider openai --model-name gpt-3.5-turbo

# 배치
python experiments/scripts/run_experiments.py --input data/test.csv --config experiments/configs/default.yaml --llm-provider openai --model-name gpt-3.5-turbo --outdir experiments/results
```

- Python API: `SupervisorAgent` → `run("...")` → `independent_analyst/empath/critic`, `deliberation_*`, `final.label`

### 4.2 로컬 (README0·how_to_run 기준)

- **통합 파이프라인**: `scripts/run_pipeline.py --config ... --run-id ... --mode proposed --profile smoke|paper` (선택: `--with_metrics`, `--with_integrity_check` 등)
- **실험만**: `experiments/scripts/run_experiments.py --config ... --run-id ... --mode proposed|bl1|bl2|bl3`
- **실행 전 검사**: `scripts/check_experiment_config.py --config <yaml> --strict`
- **N시드 머징**: `scripts/aggregate_seed_metrics.py --base_run_id ... --mode proposed --seeds ...`
- 상세: `docs/how_to_run.md`, `README0.md` §6

---

## 5. 설정·모드

| 항목 | GitHub | 로컬 |
|------|--------|------|
| **실험 모드** | `two_stage` | `proposed`, `bl1`, `bl2`, `bl3` |
| **설정** | default.yaml, llm-provider/model-name | experiments/configs/*.yaml (datasets, allowlist, latency_gate_config 등) |
| **반복** | README에 명시 없음 | **seed 반복** (폴드 아님). `experiment.repeat.mode: seed`, `seeds: [...]` |

---

## 6. 산출물·스키마

| 항목 | GitHub | 로컬 |
|------|--------|------|
| **주요 산출** | 실험 결과 디렉터리 (README에 경로만 간단 기술) | `results/<run_id>_<mode>/`: manifest.json, traces.jsonl, scorecards.jsonl, outputs.jsonl, ops_outputs, paper_outputs, derived/metrics |
| **스키마** | 에이전트별 라벨·토론 결과 | FinalOutputSchema, Agent 출력 스키마(Stage1/2), scorecard(trace), metric_trace. `docs/schema_scorecard_trace.md` 참조 |
| **배포** | Docker / Docker Compose / Kubernetes | deployment/ 삭제·legacy; 현재 실행 경로에서는 미사용 |

---

## 7. 안전장치·관찰 가능성

- **GitHub**: `guardrails` (InputValidator, OutputFilter, SafetyChecker), `observability` (SentimentLogger, MetricsCollector, TraceCollector)를 README에서 안내.
- **로컬**: guardrails/observability 디렉터리는 제거 또는 legacy.  
  - 무결성·누수: Leakage guard, allowed_roots, `check_experiment_config --strict`, run purpose(smoke/sanity/paper).  
  - 관찰: scorecards, traces, manifest, HTML 리포트, 메트릭(derived/metrics).  
  - 상세: `README0.md` §9, `docs/experiment_integrity_and_leakage_management.md`.

---

## 8. 참고 문서 (로컬)

| 문서 | 내용 |
|------|------|
| **README0.md** | 프로젝트 개요, 디렉터리 구조, 파이프라인 러너, 산출물, 기술 기여, 주의사항 |
| **docs/how_to_run.md** | 퀵스타트, run_pipeline 사용법, 데이터·설정·실험 무결성 |
| **docs/pipeline_structure_and_rules.md** | 에이전트 호출 순서, Validator 반영, Moderator 규칙 |
| **docs/experiment_integrity_and_leakage_management.md** | 데이터 역할, 데모·페이퍼 정책, 실행 전 검사 |
| **docs/schema_scorecard_trace.md** | 스키마·스코어카드·트레이스 |
| **docs/seed_repeat_policy.md** | 시드 반복 정책 |
| **docs/absa_tuple_eval.md** | Tuple 평가(gold_tuples, tuple_f1) 정의 |

---

## 9. 최근 로컬 변경 (origin 대비 반영 사항)

아래는 origin/main 대비 로컬에서 추가·변경된 기능·경로 요약입니다.

| 영역 | 변경 내용 |
|------|-----------|
| **평가 단위** | **Tuple** (aspect_ref, aspect_term, polarity). gold_tuples 포맷, tuple_f1_s1/tuple_f1_s2 메트릭. `docs/absa_tuple_eval.md`, `metrics/eval_tuple.py` 참고. |
| **Gold 로딩** | `run_experiments.py`: gold_tuples 우선, gold_triplets 하위호환. |
| **데이터 생성** | `make_mini_dataset.py`, `make_mini2_dataset.py`: valid.gold.jsonl에 gold_tuples 출력. `make_mini3_dataset.py`: train 570 / valid 30 (총 600). |
| **실험 설정** | `experiment_mini2.yaml`, `experiment_mini3.yaml` (mini3: 570/30, 시드 2개). |
| **머지 결과 경로** | 머지 디렉터리·리포트를 실험별로 분리: `results/<base_run_id>_aggregated/merged_run_<base_run_id>/`, `reports/merged_run_<base_run_id>/metric_report.html` (매 시행 덮어쓰기 방지). `aggregate_seed_metrics.py`에서 적용. |
| **채점·리포트** | `structural_error_aggregator.py`, `build_metric_report.py`, `build_paper_tables.py`: Tuple 추출·tuple_f1 표시. |

---

## 10. 요약

- **GitHub**는 “한국어 감성분석용 2단계 멀티 에이전트(분석가/공감가/비평가)” 프로젝트로, LangGraph·guardrails·observability·deployment를 전제로 한 구조입니다.
- **로컬**은 같은 레포를 베이스로 **ABSA 파이프라인(ATE → ATSA → Validator → Stage2 리뷰 → Moderator)** 으로 전환된 상태이며, 전용 스키마·스크립트·설정·문서(docs/, README0)가 추가되고, 감성 전용 에이전트·guardrails·observability·deployment는 제거되거나 legacy/unused로 표시되어 있습니다.
- **§9 최근 로컬 변경**: Tuple 평가(gold_tuples, tuple_f1), 머지 결과 경로 고유화(merged_run_<base_run_id>), mini3·make_mini2/make_mini3 등이 반영되어 있습니다.

이 차이를 반영해 GitHub와 로컬을 동기화할 때는 위 디렉터리·실행 경로·설정·문서 매핑 및 §9를 참고하면 됩니다.
