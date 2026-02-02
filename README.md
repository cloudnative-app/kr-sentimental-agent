# KR Sentiment Agent

한국어 **ABSA(Aspect-Based Sentiment Analysis)** 파이프라인입니다.  
Stage1(ATE/ATSA/Validator) → **토론(Debate)** → Stage2 리뷰 → Moderator 규칙 결정 흐름으로 동작합니다.

## ✨ 주요 특징

- 🎭 **토론 레이어**: 분석가/공감가/비평가 토론 + 심판 요약
- 🔁 **Stage1 → Debate → Stage2 리뷰** 구조
- 🧭 **Moderator 규칙**: Rule A–D + Rule E(토론 합의 힌트)
- 📊 **토론 매핑 품질 지표**: mapping coverage/실패 원인 집계
- 🧪 **Ablation 지원**: debate override on/off 비교

## 🚀 설치

```bash
git clone https://github.com/cloudnative-app/kr-sentimental-agent.git
cd kr-sentiment-agent
pip install -r requirements.txt
```

## 🔑 환경 설정

### 1) Backbone 설정

기본값은 mock입니다. 실제 모델 사용 시 아래 환경 변수를 설정하세요.

```bash
# 예: OpenAI
BACKBONE_PROVIDER=openai
BACKBONE_MODEL=gpt-4o-mini
OPENAI_API_KEY=your_openai_api_key
```

```bash
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_API_KEY=your_google_api_key
```

## 📊 사용법

### 통합 파이프라인 실행 (권장)

```bash
python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile smoke --with_metrics
```

## 🧪 실험 실행

### 실험 실행 (run_experiments)

```bash
python experiments/scripts/run_experiments.py \
    --config experiments/configs/default.yaml \
    --mode proposed \  # optional override; defaults to config run_mode or env RUN_MODE
    --run-id demo_run
```

### 스모크 테스트 (test_small.csv)

```bash
python experiments/scripts/run_experiments.py \
    --config experiments/configs/test_small.yaml \
    --run-id test_small \
    --mode proposed
```

### Debate override ablation (on/off 비교)

```bash
python scripts/run_debate_override_ablation.py --run-id debate_override_ablation --profile smoke
```

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
