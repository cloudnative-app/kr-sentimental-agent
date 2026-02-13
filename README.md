# KR Sentiment Agent

한국어 **ABSA(Aspect-Based Sentiment Analysis)** 파이프라인입니다.  
누구나 따라 할 수 있도록, 실행 순서와 결과 확인 방법을 단계별로 정리했습니다.  
기본 흐름은 Stage1(ATE/ATSA/Validator) → **토론(Debate)** → Stage2 리뷰 → Moderator 규칙 결정입니다.

## 👀 이 프로젝트가 하는 일 (한눈에 보기)

1) **문장에서 "무엇(Aspect)"을 찾아냅니다**  
   예: "서비스는 친절했지만 음식은 별로였어" → Aspect = 서비스, 음식  
2) **각 Aspect의 감정을 판단합니다**  
   예: 서비스=긍정, 음식=부정  
3) **에이전트들이 토론합니다**  
   분석가/공감가/비평가가 서로 반박·합의하고, 심판이 요약합니다.  
4) **토론 내용을 반영해 다시 리뷰합니다**  
   Stage2에서 보정/검증하고, Moderator가 최종 결론을 냅니다.

## ✨ 주요 특징

- 🎭 **토론 레이어**: 분석가/공감가/비평가 토론 + 심판 요약
- 🔁 **Stage1 → Debate → Stage2 리뷰** 구조
- 🧭 **Moderator 규칙**: Rule A–D + Rule E(토론 합의 힌트)
- 📊 **토론 매핑 품질 지표**: mapping coverage/실패 원인 집계
- 🧪 **Ablation 지원**: debate override on/off 비교
- 📐 **Tuple 평가**: gold_tuples 기반 (aspect_ref, aspect_term, polarity) F1; `docs/absa_tuple_eval.md` 참고

## 🚀 설치 (처음 1회)

```bash
git clone https://github.com/cloudnative-app/kr-sentimental-agent.git
cd kr-sentimental-agent
pip install -r requirements.txt
```

## 🔑 환경 설정 (처음 1회)

### 1) Backbone 설정

기본값은 **mock(가짜 모델)** 입니다.  
실제 LLM을 쓰려면 아래 환경 변수를 설정하세요.

```bash
# 예: OpenAI
BACKBONE_PROVIDER=openai
BACKBONE_MODEL=gpt-4o-mini
OPENAI_API_KEY=your_openai_api_key
```

다른 Provider를 쓰고 싶다면:
```bash
# Anthropic
BACKBONE_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key

# Google Gemini
BACKBONE_PROVIDER=google
GOOGLE_API_KEY=your_google_api_key
GENAI_API_KEY=your_genai_api_key
```

## ✅ 가장 쉬운 실행 방법 (권장)

```bash
# 단일 실행 (smoke)
python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile smoke --with_metrics

# 시드 반복 + 머징 (paper, mini2/mini3 등)
python scripts/run_pipeline.py --config experiments/configs/experiment_mini2.yaml --run-id experiment_mini2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --with_aggregate
```

실행 후 확인할 것:
- 결과 디렉터리: `results/experiment_mini_proposed/` (단일 실행) 또는 시드 반복 시 `results/experiment_mini__seed42_proposed/` 등
- 결과 파일: `results/experiment_mini_proposed/outputs.jsonl`, `scorecards.jsonl`
- 리포트 HTML: `reports/experiment_mini_proposed/metric_report.html`
- 시드 머징 후: `results/experiment_mini_aggregated/`, 머지 리포트 `reports/merged_run_experiment_mini/metric_report.html`

## 🧪 실험 실행 (조금 더 자세히)

### 1) 기본 실험 실행 (run_experiments)

```bash
python experiments/scripts/run_experiments.py \
    --config experiments/configs/default.yaml \
    --mode proposed \  # optional override; defaults to config run_mode or env RUN_MODE
    --run-id demo_run
```

### 2) 스모크 테스트 (test_small.csv)

```bash
python experiments/scripts/run_experiments.py \
    --config experiments/configs/test_small.yaml \
    --run-id test_small \
    --mode proposed
```

### 3) 토론 온/오프 · Debate override 비교

**한 런에서 토론 온/오프를 동시에 볼 수 없습니다.** 한 번 실행 시 config 하나만 적용되므로, 토론 켜기/끄기 비교를 하려면 **서로 다른 config로 두 번 따로 실행**한 뒤 결과를 비교해야 합니다.

| 비교 목적 | 시행 방법 |
|-----------|-----------|
| **토론 단계 자체 온 vs 오프** | (1) 토론 ON: `experiment_mini2.yaml` 등 `enable_debate: true` config로 실행 → (2) 토론 OFF: `experiments/configs/abl_no_debate.yaml` 로 **같은 데이터·시드**로 한 번 더 실행. run_id를 구분해 두면 됨(예: `experiment_mini2` vs `abl_no_debate`). |
| **Debate override ON vs OFF** (토론은 둘 다 켜고, Moderator가 토론 힌트만 쓰는지 여부) | `scripts/run_debate_override_ablation.py` 한 번 실행. 내부에서 override ON config와 `abl_no_debate_override.yaml`(override OFF)을 각각 실행 후 메트릭·리포트 생성. |

**토론 완전 오프 예시 (mini2 데이터):**
```bash
# 토론 ON (기본)
python scripts/run_pipeline.py --config experiments/configs/experiment_mini2.yaml --run-id experiment_mini2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main

# 토론 OFF (ablation)
python scripts/run_pipeline.py --config experiments/configs/abl_no_debate.yaml --run-id abl_no_debate --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```
이후 `results/experiment_mini2_proposed/` vs `results/abl_no_debate_proposed/` (또는 시드 반복 시 각각 `*__seed42_proposed` 등)의 derived/metrics·리포트를 비교하면 됩니다.

**Override만 비교 (토론은 둘 다 ON):**
```bash
python scripts/run_debate_override_ablation.py --run-id debate_override_ablation --profile smoke
```
- 결과: `results/debate_override_ablation_override_on_proposed/`, `results/debate_override_ablation_override_off_proposed/`

## 📂 결과·경로 규칙

- **단일 실행**: `results/<run_id>_<mode>/`, `reports/<run_id>_<mode>/`
- **시드 반복**: `results/<run_id>__seed<N>_<mode>/` (덮어쓰기 없음)
- **머징 후**: `results/<run_id>_aggregated/` (merged_scorecards.jsonl, merged_metrics/), 머지 리포트는 `reports/merged_run_<run_id>/metric_report.html`
- **Scorecard 덮어쓰기 금지**: `results/<run_id>/scorecards.jsonl`은 **원본(run_experiments)** 전용. smoke 재생성 시 반드시 `--out results/<run_id>/derived/scorecards/scorecards.smoke.jsonl` (또는 `scorecards.smoke.gold.jsonl`) 사용. 상세: `docs/scorecard_path_and_consistency_checklist.md`

## 📂 결과를 읽는 방법

### 1) `outputs.jsonl`
각 문장에 대해 **최종 감정 결과**가 들어있습니다.  
`debate` 항목에는 토론 요약이 포함됩니다.

### 2) `scorecards.jsonl`
각 샘플의 **상세 점수/매핑 품질**이 들어있습니다.  
`debate.mapping_coverage`가 높을수록 토론-리뷰 연결이 잘 된 것입니다.

### 3) `metric_report.html`
브라우저로 열어 **전체 지표와 경고**를 확인합니다.  
KPI 카드에 경고(LOW/HIGH)가 뜨면 개선이 필요합니다.

## 🧭 용어 간단 설명

- **ABSA**: Aspect(대상)별 감성 분석  
- **ATE**: Aspect Extraction (대상을 찾는 단계)  
- **ATSA**: Aspect-Target Sentiment Analysis (대상별 감정 판단)  
- **Validator**: 구조 검증  
- **Debate**: 에이전트 토론/합의 단계  
- **Stage2 리뷰**: 토론 결과를 반영한 재검토  
- **Moderator**: 최종 규칙 결정

## 🔧 실험 조건·데이터

### 토론 및 Stage2 리뷰
자세한 구조는 `docs/pipeline_structure_and_rules.md`를 참고하세요.

### 소규모 데이터셋 (mini / mini2 / mini3)
- **mini**: `scripts/make_mini_dataset.py` → `experiments/configs/datasets/mini/` (train/valid, gold_tuples)
- **mini2**: `scripts/make_mini2_dataset.py` → `experiments/configs/datasets/mini2/` (시드 2개용)
- **mini3**: `scripts/make_mini3_dataset.py` → `experiments/configs/datasets/mini3/` (train 570, valid 30)
- 골드 포맷: `gold_tuples` (aspect_ref, aspect_term, polarity). 정의: `docs/absa_tuple_eval.md`

## 🎭 에이전트·스키마·프롬프트 (현재 파이프라인)

파이프라인은 **Stage1 → (선택) Debate → Stage2 리뷰 → Moderator** 순서로 동작합니다.

**페르소나 부여**: **토론 단계(Debate)에서만** 페르소나가 부여됩니다. 발언자 3명(분석가/공감가/비평가 패널)에게만 `DebatePersona`가 주입되며, Stage1/Stage2의 **ATE·ATSA·Validator에는 페르소나가 없고** 각각 고정된 역할(단일 프롬프트)만 가집니다.

**API 호출 횟수** (샘플당, `enable_stage2=true`, `enable_debate=true`, 기본 설정):  
Stage1(ATE·ATSA·Validator 각 1회) **3** + Debate(라운드 2× 발언자 3명 **6** + Judge **1**) **7** + Stage2(ATE·ATSA·Validator 각 1회) **3** = **총 13회**. Moderator는 LLM 미사용(규칙 기반).

**토론 발언자 vs Stage 에이전트**: 토론에 참가하는 발언자(분석가/공감가/비평가 패널)는 **ATE·ATSA·Validator와 다른 독립적인 에이전트**입니다. Stage1/Stage2는 `ATEAgent`, `ATSAAgent`, `ValidatorAgent`가 각각 `ate_stage1/2`, `atsa_stage1/2`, `validator_stage1/2` 프롬프트와 구조화 스키마로 호출되고, 토론은 `DebateOrchestrator`가 **동일 백본(LLM)**에 **debate_speaker** 프롬프트 + 발언자별 페르소나(JSON)를 넣어 호출하며, 출력 스키마는 `DebateTurn`(planning/reflection/message)입니다. 즉, 토론 3인은 별도 에이전트 클래스가 아니라 “debate_speaker 1회 호출 × 페르소나만 바꿔가며 3명분”입니다.

### ABSA 파이프라인 에이전트 (Stage1/Stage2, 페르소나 없음)

| 에이전트 | 역할 | 프롬프트 | 스키마 (schemas/agent_outputs.py) |
|----------|------|----------|-----------------------------------|
| **ATE** (Aspect Extraction) | 입력 텍스트에서 **명시적 속성(Explicit Aspect Terms)** 추출. 명사/명사구 단위 span, 지배소(서술어) 파악. | `agents/prompts/ate_stage1.md`, `ate_stage2.md` | `AspectExtractionStage1Schema` (aspects: term, span, normalized, syntactic_head, confidence, rationale), Stage2: `AspectExtractionReviewItem` |
| **ATSA** (Aspect Sentiment) | 각 속성별 **감성 극성(positive/negative/neutral)** 결정. Opinion Term·부정/대조/조건 반전·확률 분포. | `agents/prompts/atsa_stage1.md`, `atsa_stage2.md` | `AspectSentimentStage1Schema` (aspect_sentiments: aspect_ref, polarity, opinion_term, evidence, confidence), Stage2: `SentimentReviewItem` |
| **Validator** (Structural) | 구조적 위험(부정/대조/반어) 검증. Risk scope(인덱스 범위), 일관성 점수, **Correction Proposal**(FLIP_POLARITY 등). | `agents/prompts/validator_stage1.md`, `validator_stage2.md` | `StructuralValidatorStage1Schema` (structural_risks, consistency_score, correction_proposals) |
| **Moderator** | **규칙 기반**(LLM 미사용). Stage1/Stage2/Validator 결과를 Rule A~D, M, E로 종합해 최종 라벨·confidence·rationale 결정. | `agents/prompts/moderator.md` | Rule A: Stage2 신뢰도 급락 시 Stage1 유지 / Rule B: Validator 제안 우선 고려 / Rule C: 위험·제안 시 Validator veto / Rule D: 신뢰도 타이브레이크 / Rule M: Stage1↔Stage2 충돌 시 mixed / Rule E: Debate 합의 힌트 반영 |

### Debate 레이어 (선택, `enable_debate: true` 시) — 여기서만 페르소나 부여

토론 단계에서 **발언자 3명**에게만 `DebatePersona`가 부여됩니다. `DebateOrchestrator`가 `self.personas`(analyst/empath/critic)를 읽어, 각 발언 시 시스템 프롬프트에 `[PERSONA]\n{persona.model_dump_json()}` 형태로 주입합니다. 프롬프트: `agents/prompts/debate_speaker.md`, `debate_judge.md`. 스키마: `DebatePersona`, `DebateTurn`, `DebateSummary` (schemas). 설정 오버라이드: config `debate.personas`, `debate.order`.

| 페르소나 (발언자) | stance | 역할·스타일 | 목표 |
|------------------|--------|-------------|------|
| **분석가 패널** | neutral | 건조하고 근거 중심 | 증거 기반으로 중립적 판단 제시 |
| **공감가 패널** | pro | 따뜻하고 감성적 | 긍정/지지적 맥락 강화 |
| **비평가 패널** | con | 날카롭고 논리적 | 부정/비판적 맥락 강화 |

발언은 Planning → Reflection → Action 순으로 생성되며, 심판(Judge)이 winner/consensus/key_agreements·key_disagreements/rationale을 요약합니다. 이 요약은 Stage2 리뷰 컨텍스트와 Moderator Rule E에 사용됩니다.

## 📈 관찰/지표
리포트 및 지표는 `scripts/scorecard_from_smoke.py`, `scripts/structural_error_aggregator.py`, `scripts/build_metric_report.py`로 생성됩니다.

## 🆘 자주 겪는 문제

1) **실행이 너무 빠르게 끝나요**
- mock 모델일 수 있습니다. 실제 모델을 쓰려면 환경 변수를 설정하세요.

2) **에러: leakage_guard**
- `test_small.csv`처럼 라벨이 있는 데이터는 기본적으로 막힙니다.  
  `experiments/configs/test_small.yaml`을 사용하세요.

3) **HTML 리포트가 안 열려요**
- 브라우저에서 `reports/.../metric_report.html`을 직접 열어보세요.

## 📁 프로젝트 구조

```
kr-sentimental-agent/
├── agents/                          # 에이전트 시스템
│   ├── supervisor_agent.py         # 통합 오케스트레이터
│   ├── prompts/                    # ATE/ATSA/Validator/Debate/Moderator 프롬프트
│   └── specialized_agents/         # ATE, ATSA, Validator, Moderator
├── tools/                           # LLM·데이터·데모
│   ├── backbone_client.py          # LLM 백본
│   ├── llm_runner.py                # 구조화 출력·재시도
│   ├── data_tools/                  # CSV/JSONL 로더, 라벨 스키마
│   └── demo_sampler.py              # 데모 샘플링
├── data/                            # 데이터 로더
│   └── datasets/                    # load_datasets, 경로 해석
├── memory/                          # 에피소딕 메모리 (C1/C2/C3)
│   ├── episodic_orchestrator.py    # 검색·주입
│   ├── retriever.py                 # 시그니처·유사도
│   └── advisory_builder.py         # 어드바이저 텍스트
├── metrics/                         # Tuple 평가
│   └── eval_tuple.py                # gold_tuples, tuples_to_pairs, F1
├── schemas/                         # 에이전트 출력 스키마
│   └── agent_outputs.py            # AspectExtraction, Sentiment, Validator
├── evaluation/                      # 베이스라인·평가
│   └── baselines.py                 # make_runner, resolve_run_mode
├── experiments/                     # 실험 설정·실행
│   ├── configs/                     # YAML 설정 (mini, real, real_n100_seed1_c1/c2/c3, abl_*)
│   │   └── datasets/                # mini, mini2, mini3, real_n100_seed1, valid/ 폴드 등
│   └── scripts/
│       └── run_experiments.py       # 실험 루프, scorecards(원본), gold 주입
├── scripts/                         # 파이프라인·메트릭·진단
│   ├── run_pipeline.py             # 통합 CLI (실험 → 스냅샷 → 리포트 → 메트릭)
│   ├── scorecard_from_smoke.py       # outputs → scorecards (--out 필수로 원본 덮어쓰기 방지)
│   ├── structural_error_aggregator.py  # structural_metrics, triptych, inconsistency_flags
│   ├── build_metric_report.py       # metric_report.html
│   ├── aggregate_seed_metrics.py    # 시드 머징, 평균±표준편차
│   ├── consistency_checklist.py    # GO/NO-GO 정합성 체크리스트
│   └── run_real_n100_c1_c2_c3.ps1   # real n100 C1→C2→C3 순차 + 머지
├── analysis/                        # 메모리 성장·플롯
├── docs/                            # 실행·평가·정책 문서
├── results/                         # 런별 산출물 (run_id별 디렉터리)
│   └── <run_id>_<mode>/
│       ├── manifest.json, outputs.jsonl, scorecards.jsonl, traces.jsonl
│       ├── derived/                 # metrics, diagnostics, tables, scorecards(smoke 재생성)
│       ├── paper_outputs/
│       └── ops_outputs/
└── reports/                         # HTML 리포트 (run_id별)
```

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 📞 연락처

- 프로젝트 링크: [https://github.com/cloudnative-app/kr-sentimental-agent](https://github.com/cloudnative-app/kr-sentimental-agent)
- 이슈 리포트: [https://github.com/cloudnative-app/kr-sentimental-agent/issues](https://github.com/cloudnative-app/kr-sentimental-agent/issues)

## 📚 관련 문서

- **실행·설정**: `docs/how_to_run.md` (run_pipeline, 시드 반복, 머징·경로, real n100 C1/C2/C3)
- **Tuple 평가**: `docs/absa_tuple_eval.md` (gold_tuples, tuple_f1)
- **Scorecard 경로·정합성**: `docs/scorecard_path_and_consistency_checklist.md` (덮어쓰기 금지, meta.source, consistency_checklist)
- **실제 런 명령어 (real n100)**: `docs/run_real_n100_c1_c2_c3_commands.md`
- **mini2/mini3**: `docs/experiment_mini2_two_seeds_two_runs.md`, `experiments/configs/experiment_mini3.yaml`
- **origin vs 로컬 차이**: `docs/github_vs_local_diff.md`

## Provider dry-run (real backbone quick check)

```bash
python scripts/provider_dry_run.py --text "서비스는 친절했지만 음식은 별로였어" --mode proposed
```

Required env vars (names only):
- OpenAI: OPENAI_API_KEY (OPENAI_BASE_URL optional)
- Anthropic: ANTHROPIC_API_KEY (ANTHROPIC_BASE_URL optional)
- Google Gemini: GOOGLE_API_KEY, GENAI_API_KEY
