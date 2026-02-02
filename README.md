# KR Sentiment Agent

한국어 감성분석을 위한 **2단계 멀티 에이전트 시스템**입니다. 전문적인 페르소나를 가진 3개의 에이전트가 독립적 의견수렴과 토론단계를 거쳐 정확한 감성분석을 수행합니다.

## ✨ 주요 특징

- 🎭 **전문 페르소나 기반 에이전트**: 분석가, 공감가, 비평가
- 🔄 **2단계 프로세스**: 독립적 의견수렴 → 토론단계
- 🤖 **LLM 기반**: OpenAI, Anthropic, Google 지원
- 📊 **LangGraph 워크플로우**: 구조화된 에이전트 협업
- 🎯 **이미지 구조 일치**: 제공된 이미지와 정확히 일치하는 아키텍처

## 🚀 설치

```bash
git clone https://github.com/your-repo/kr-sentiment-agent.git
cd kr-sentiment-agent
pip install -r requirements.txt
```

## 🔑 환경 설정

`.env` 파일을 생성하고 API 키를 설정하세요:

```bash
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_API_KEY=your_google_api_key
```

## 📊 사용법

### 2단계 멀티 에이전트 시스템 (권장)

```python
from agents.supervisor_agent import SupervisorAgent

# 2단계 조정자 생성 (기본값)
supervisor = SupervisorAgent(llm_provider="openai", model_name="gpt-3.5-turbo")

# 2단계 멀티 에이전트 감성분석
results = supervisor.run("참 잘하는 짓이다... 정말 대단해!")

# 1단계: 독립적 의견수렴 (각 에이전트가 독립적으로 분석)
print(f"독립적 분석가: {results['independent_analyst'].label}")
print(f"독립적 공감가: {results['independent_empath'].label}")
print(f"독립적 비평가: {results['independent_critic'].label}")

# 2단계: 토론단계 (기존 에이전트들이 서로 토론하며 의견 교환)
print(f"토론 후 분석가: {results['deliberation_analyst'].label}")
print(f"토론 후 공감가: {results['deliberation_empath'].label}")
print(f"토론 후 비평가: {results['deliberation_critic'].label}")

# 최종 결과 (토론 결과를 종합한 최종 판단)
print(f"최종 결과: {results['final'].label}")
```

## 🧪 실험 실행

### 단일 텍스트 분석

```bash
python experiments/scripts/agent_run.py \
    --config experiments/configs/default.yaml \
    --mode proposed \  # or bl1|bl2|bl3 (CLI > RUN_MODE env > config run_mode)
    --text "참 잘하는 짓이다... 정말 대단해!"
```

### 배치 실험

```bash
python experiments/scripts/run_experiments.py \
    --config experiments/configs/default.yaml \
    --mode proposed \  # optional override; defaults to config run_mode or env RUN_MODE
    --run-id demo_run
```

## 🔧 실험 조건

### LLM 기반 페르소나 방식 (권장)
1. **Two-Stage**: 2단계 구조 (이미지와 일치, 기본값)

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

## 🛡️ 안전장치

### 입력 검증
```python
from guardrails.input_validation import InputValidator

validator = InputValidator()
result = validator.validate("분석할 텍스트")
if result["valid"]:
    # 안전한 텍스트 처리
    pass
```

### 출력 필터링
```python
from guardrails.output_filtering import OutputFilter

filter = OutputFilter()
filtered_output = filter.filter_output(agent_output)
```

### 안전 검사
```python
from guardrails.safety_checks import SafetyChecker

checker = SafetyChecker()
safety_result = checker.check_safety("텍스트")
if not safety_result["blocked"]:
    # 안전한 텍스트 처리
    pass
```

## 📈 관찰 가능성

### 로깅
```python
from observability.logging import SentimentLogger

logger = SentimentLogger()
logger.log_prediction("텍스트", "긍정", 0.85, "분석가")
```

### 메트릭 수집
```python
from observability.metrics import MetricsCollector

collector = MetricsCollector()
collector.record_prediction("텍스트", "긍정", 0.85, "분석가", 0.5)
```

### 분산 추적
```python
from observability.tracing import TraceCollector

tracer = TraceCollector()
trace_id = tracer.start_trace("sentiment_analysis")
# ... 분석 수행 ...
tracer.finish_trace(trace_id)
```

## 🐳 배포

### Docker
```bash
docker build -f deployment/Dockerfile -t kr-sentiment-agent .
docker run -p 8000:8000 kr-sentiment-agent
```

### Docker Compose
```bash
docker-compose -f deployment/docker-compose.yml up
```

### Kubernetes
```bash
kubectl apply -f deployment/k8s/
```

## 📁 프로젝트 구조

```
kr-sentiment-agent/
├── agents/                          # 에이전트 시스템
│   ├── base_agent.py               # 기본 인터페이스
│   ├── supervisor_agent.py         # 통합 조정자
│   ├── two_stage_supervisor.py     # 2단계 조정자
│   └── specialized_agents/         # 전문 페르소나 기반 에이전트들
│       ├── analyst_agent.py        # 📊 데이터 중심 분석가
│       ├── empath_agent.py         # 💝 감정 공감가
│       └── critic_agent.py         # 🔍 비판적 검토자
├── tools/                          # 도구들
│   ├── classifier_wrapper.py       # HuggingFace 모델 래퍼
│   └── data_tools/                 # 데이터 처리 도구들
├── experiments/                    # 실험 관련 (config run_mode 기본값, CLI --mode, env RUN_MODE로 override)
│   ├── configs/
│   ├── results/
│   └── scripts/                    # 실험 스크립트들
├── evaluation/                     # 평가 도구들
├── guardrails/                     # 안전장치
├── observability/                  # 관찰 가능성
└── deployment/                     # 배포 관련
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

- 프로젝트 링크: [https://github.com/your-repo/kr-sentiment-agent](https://github.com/your-repo/kr-sentiment-agent)
- 이슈 리포트: [https://github.com/your-repo/kr-sentiment-agent/issues](https://github.com/your-repo/kr-sentiment-agent/issues)
## Provider dry-run (real backbone quick check)

```bash
python scripts/provider_dry_run.py --text "서비스는 친절했지만 음식은 별로였어" --mode proposed
```

Required env vars (names only):
- OpenAI: OPENAI_API_KEY (OPENAI_BASE_URL optional)
- Anthropic: ANTHROPIC_API_KEY (ANTHROPIC_BASE_URL optional)
- Google Gemini: GOOGLE_API_KEY, GENAI_API_KEY
