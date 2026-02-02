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

## 🚀 설치 (처음 1회)

```bash
git clone https://github.com/cloudnative-app/kr-sentimental-agent.git
cd kr-sentiment-agent
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
python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile smoke --with_metrics
```

실행 후 확인할 것:
- 결과 파일: `results/experiment_mini/outputs.jsonl`
- 점수카드: `results/experiment_mini/scorecards.jsonl`
- 리포트 HTML: `reports/experiment_mini/metric_report.html`

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

### 3) Debate override ablation (on/off 비교)

```bash
python scripts/run_debate_override_ablation.py --run-id debate_override_ablation --profile smoke
```

실행 후 확인할 것:
- 결과 폴더: `results/debate_override_ablation_*`
- 리포트 폴더: `reports/debate_override_ablation_*`

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

## 🔧 실험 조건

### 토론 및 Stage2 리뷰
자세한 구조는 `docs/pipeline_structure_and_rules.md`를 참고하세요.

## 🎭 에이전트 페르소나

### 📊 분석가 (Analyst)
- **역할**: 데이터 중심의 객관적 분석
- **특징**: 건조하고 기계적인 보고체
- **전문성**: 언어적 데이터, 문법적 요소, 객관적 사실
- **말투**: "텍스트의 명시적 감정 표현 키워드를 분석한 결과..."

### 💝 공감가 (Empath)
- **역할**: 감정적 이해와 인간적 맥락 파악
- **특징**: 따뜻하고 감성적인 어조
- **전문성**: 감정적 신호, 숨은 의도, 인간적 맥락
- **말투**: "사용자의 현재 감정 상태를 파악해보면..."

### 🔍 비평가 (Critic)
- **역할**: 비판적 검토와 뉘앙스 탐지
- **특징**: 날카롭고 논리적인 어조
- **전문성**: 반어법, 풍자, 중의적 표현, 논리적 오류
- **말투**: "분석가의 '긍정' 판단에 대해 의문을 제기합니다..."

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
kr-sentiment-agent/
├── agents/                          # 에이전트 시스템
│   ├── supervisor_agent.py         # 통합 오케스트레이터
│   ├── debate_orchestrator.py      # 토론 레이어
│   └── specialized_agents/         # ATE/ATSA/Validator/Moderator
├── tools/                          # 도구들
│   ├── classifier_wrapper.py       # HuggingFace 모델 래퍼
│   └── data_tools/                 # 데이터 처리 도구들
├── experiments/                    # 실험 관련
│   ├── configs/
│   ├── results/
│   └── scripts/                    # 실험 스크립트들
├── evaluation/                     # 평가 도구들
└── scripts/                        # 리포트/메트릭/유틸
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
## Provider dry-run (real backbone quick check)

```bash
python scripts/provider_dry_run.py --text "서비스는 친절했지만 음식은 별로였어" --mode proposed
```

Required env vars (names only):
- OpenAI: OPENAI_API_KEY (OPENAI_BASE_URL optional)
- Anthropic: ANTHROPIC_API_KEY (ANTHROPIC_BASE_URL optional)
- Google Gemini: GOOGLE_API_KEY, GENAI_API_KEY
