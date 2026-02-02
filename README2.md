# KR Sentiment Agent - 로컬 개발 버전 특징

이 문서는 로컬 개발 환경에서 추가/개선된 기능과 GitHub 저장소와의 차이점을 정리합니다.

## 🆕 로컬 버전의 주요 특징

### 1. **ATE/ATSA 에이전트 시스템** (신규)

로컬 버전은 GitHub README에 명시되지 않은 **Aspect 기반 감성분석 에이전트 시스템**을 포함합니다:

- **ATEAgent** (Aspect-agnostic Sentiment Agent)
  - 관점에 구애받지 않는 감성분석
  - 2단계 프로세스: Stage1 (초기 분석) → Stage2 (재분석)
  - Validator 출력을 고려한 재분석

- **ATSAAgent** (Aspect/Target-Specific Sentiment Agent)
  - 특정 관점/대상에 대한 감성분석
  - 2단계 프로세스로 정확도 향상
  - Stage1 결과와 Validator 출력을 통합한 Stage2 분석

### 2. **ValidatorAgent** (신규)

- **역할**: ATE와 ATSA 출력 간 일관성 검증
- **기능**:
  - 구조적 검증 (Structural Validation)
  - 위험 요소 탐지 (negation, irony, contrast 등)
  - 제안 라벨 및 신뢰도 제공
  - 2단계 검증 프로세스

### 3. **Moderator** (신규)

- **역할**: 규칙 기반 조정자 (LLM 없이 동작)
- **규칙 시스템**:
  - **Rule A**: Span alignment boost (IoU > 0.8일 때 신뢰도 향상)
  - **Rule B**: Stage2 선호 (신뢰도 하락 < 0.2일 때)
  - **Rule C**: Validator veto (중요 위험 시 Validator 제안 채택)
  - **Rule D**: 최종 라벨 결정 로직

### 4. **BackboneClient** (통합 LLM 클라이언트)

- **목적**: 모든 LLM 호출을 단일 진입점으로 통합
- **지원 프로바이더**:
  - OpenAI (GPT 모델)
  - Anthropic (Claude 모델)
  - Google (Gemini 모델)
  - Mock (테스트용)
- **특징**:
  - 환경 변수 기반 설정 (`BACKBONE_PROVIDER`, `BACKBONE_MODEL`)
  - JSON/텍스트 응답 형식 지원
  - 직접 LLM 클라이언트 사용 금지 (아키텍처 강제)

### 5. **프롬프트 시스템** (개선)

- **위치**: `agents/prompts/`
- **형식**: 마크다운 파일 기반 프롬프트 관리
- **프롬프트 파일**:
  - `ate_stage1.md`, `ate_stage2.md`
  - `atsa_stage1.md`, `atsa_stage2.md`
  - `validator_stage1.md`, `validator_stage2.md`
  - `moderator.md`
  - `bl2.md`
- **장점**: 코드와 프롬프트 분리, 버전 관리 용이

### 6. **스키마 시스템** (구조화된 출력)

- **위치**: `schemas/`
- **주요 스키마**:
  - `agent_outputs.py`: 에이전트 출력 구조
  - `baselines.py`: 베이스라인 출력 구조
  - `final_output.py`: 최종 출력 구조
  - `metric_trace.py`: 메트릭 추적 구조
- **기술**: Pydantic 기반 타입 안전성 보장

### 7. **베이스라인 시스템**

- **구현된 베이스라인**:
  - `bl1.py`: 베이스라인 1 구현
  - `bl3.py`: 베이스라인 3 구현
  - `bl2.md`: 베이스라인 2 프롬프트
- **래퍼**: `baseline_wrappers/bl1_wrapper.py`

### 8. **실험 모드 확장**

- **지원 모드**:
  - `proposed`: 제안된 멀티 에이전트 시스템
  - `bl1`, `bl2`, `bl3`: 베이스라인 모드
- **우선순위**: CLI `--mode` > 환경 변수 `RUN_MODE` > 설정 파일 `run_mode`
- **설정 파일**: `experiments/configs/default.yaml`

### 9. **테스트 시스템** (강화)

- **계약 테스트**:
  - `test_schema_contract.py`: 스키마 계약 검증
  - `test_agent_input_contract.py`: 에이전트 입력 계약
  - `test_metric_contract.py`: 메트릭 계약
- **아키텍처 테스트**:
  - `test_no_direct_llm_clients.py`: 직접 LLM 클라이언트 사용 금지 검증
- **기능 테스트**:
  - `test_moderator_rules.py`: Moderator 규칙 검증
  - `test_hard_subset.py`: Hard subset 필터 테스트
  - `test_bl3_not_applicable.py`: BL3 비적용 케이스

### 10. **메트릭 시스템**

- **Hard Subset**: `metrics/hard_subset.py`
  - 어려운 케이스 필터링
  - 평가 정확도 향상
- **Contract**: `metrics/contract.py`
  - 메트릭 계약 정의

### 11. **실험 스크립트** (개발 도구)

- **체크리스트**: `scripts/checklist_summary.py`
  - LLM 클라이언트 단일 진입점 검증
  - Smoke outputs 존재 확인
  - 에러 로그 확인
  - Hard subset 필터 확인
  - 스키마 계약 테스트 확인
- **스키마 검증**: `scripts/schema_validation_test.py`
- **에러 검사**: `scripts/error_inspector.py`

### 12. **플로우 다이어그램 문서**

- **파일**: `agent_flow_diagram.md`
- **내용**:
  - 2단계 멀티 에이전트 시스템 플로우
  - LangGraph 워크플로우
  - LangChain 에이전트 플로우
  - 전통적 멀티 에이전트 시스템
  - 통합 아키텍처 개요
  - 실험 실행 플로우
- **형식**: Mermaid 다이어그램

### 13. **데이터 로더 확장**

- **내부 JSON 로더**: `load_internal_json_dir()`
- **NIKL 데이터셋**: `load_nikluge_sa2022()`
- **CSV 로더**: `load_csv_dataset()`, `load_csv_examples()`
- **데이터 분할**: `load_split_examples()`

### 14. **버전 정보**

- **패키지 버전**: `2.0.0` (로컬 `__init__.py`)
- **주요 Export**:
  ```python
  from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator
  from agents.supervisor_agent import SupervisorAgent
  from agents.two_stage_supervisor import TwoStageSupervisorAgent
  ```

## 📁 추가/변경된 디렉토리 구조

```
kr-sentiment-agent/
├── agents/
│   ├── prompts/                    # ✨ 신규: 프롬프트 파일들
│   │   ├── ate_stage1.md
│   │   ├── ate_stage2.md
│   │   ├── atsa_stage1.md
│   │   ├── atsa_stage2.md
│   │   ├── validator_stage1.md
│   │   ├── validator_stage2.md
│   │   ├── moderator.md
│   │   └── bl2.md
│   ├── specialized_agents/
│   │   ├── ate_agent.py            # ✨ 신규
│   │   ├── atsa_agent.py           # ✨ 신규
│   │   ├── validator_agent.py      # ✨ 신규
│   │   └── moderator.py            # ✨ 신규
│   └── baseline_runner.py          # ✨ 신규
├── baselines/                      # ✨ 신규
│   ├── bl1.py
│   └── bl3.py
├── baseline_wrappers/              # ✨ 신규
│   └── bl1_wrapper.py
├── schemas/                        # ✨ 신규
│   ├── agent_outputs.py
│   ├── baselines.py
│   ├── final_output.py
│   └── metric_trace.py
├── tools/
│   ├── backbone_client.py          # ✨ 신규: 통합 LLM 클라이언트
│   └── llm_runner.py               # ✨ 신규: 구조화된 LLM 실행
├── scripts/                        # ✨ 신규: 개발 도구
│   ├── checklist_summary.py
│   ├── error_inspector.py
│   └── schema_validation_test.py
├── tests/                          # ✨ 확장: 계약 테스트 추가
│   ├── test_schema_contract.py
│   ├── test_agent_input_contract.py
│   ├── test_metric_contract.py
│   ├── test_no_direct_llm_clients.py
│   ├── test_moderator_rules.py
│   └── test_hard_subset.py
├── metrics/                        # ✨ 신규
│   ├── contract.py
│   └── hard_subset.py
├── agent_flow_diagram.md           # ✨ 신규: 상세 플로우 다이어그램
└── data/
    ├── datasets/                   # ✨ 신규
    └── nikluge-sa-2022-train.jsonl # ✨ 신규: NIKL 데이터셋
```

## 🔄 GitHub 저장소와의 주요 차이점

### 추가된 기능

1. **ATE/ATSA 에이전트 시스템**: GitHub README에는 언급되지 않음
2. **ValidatorAgent & Moderator**: 검증 및 조정 시스템
3. **BackboneClient**: 통합 LLM 클라이언트 아키텍처
4. **프롬프트 파일 시스템**: 마크다운 기반 프롬프트 관리
5. **스키마 시스템**: Pydantic 기반 구조화된 출력
6. **베이스라인 구현**: bl1, bl2, bl3
7. **계약 테스트**: 스키마, 입력, 메트릭 계약 검증
8. **개발 도구**: 체크리스트, 스키마 검증, 에러 검사 스크립트
9. **플로우 다이어그램**: 상세한 시스템 아키텍처 문서

### 개선된 부분

1. **실험 모드**: proposed, bl1, bl2, bl3 지원
2. **데이터 로더**: 내부 JSON, NIKL 데이터셋 지원
3. **테스트 커버리지**: 아키텍처 및 계약 테스트 추가
4. **메트릭 시스템**: Hard subset, Contract 정의

## 🚀 사용 예시

### ATE/ATSA 에이전트 사용

```python
from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator
from tools.backbone_client import BackboneClient

# BackboneClient 초기화
backbone = BackboneClient(provider="openai", model="gpt-3.5-turbo")

# 에이전트 초기화
ate = ATEAgent(backbone=backbone)
atsa = ATSAAgent(backbone=backbone)
validator = ValidatorAgent(backbone=backbone)
moderator = Moderator()

# Stage1 실행
text = "이 제품은 정말 좋아요!"
ate_stage1 = ate.run_stage1(text, run_id="test", text_id="1")
atsa_stage1 = atsa.run_stage1(text, run_id="test", text_id="1")
validator_stage1 = validator.run_stage1(text, run_id="test", text_id="1")

# Stage2 실행 (재분석)
ate_stage2 = ate.run_stage2(text, ate_stage1, validator_stage1, run_id="test", text_id="1")
atsa_stage2 = atsa.run_stage2(text, atsa_stage1, validator_stage1, run_id="test", text_id="1")
validator_stage2 = validator.run_stage2(text, validator_stage1, run_id="test", text_id="1")

# Moderator로 최종 결정
final = moderator.run(
    stage1_ate=ate_stage1,
    stage2_ate=ate_stage2,
    stage1_atsa=atsa_stage1,
    stage2_atsa=atsa_stage2,
    validator=validator_stage2
)
```

### 실험 실행 (확장된 모드)

```bash
# Proposed 모드
python experiments/scripts/run_experiments.py \
    --config experiments/configs/default.yaml \
    --mode proposed \
    --run-id demo_run

# 베이스라인 모드
python experiments/scripts/run_experiments.py \
    --config experiments/configs/default.yaml \
    --mode bl1 \
    --run-id baseline_run
```

### 체크리스트 실행

```bash
python scripts/checklist_summary.py
```

## 📊 실험 결과 구조

로컬 버전은 다음과 같은 실험 결과 구조를 생성합니다:

```
experiments/results/
├── proposed/
│   └── smoke_outputs.jsonl
├── bl1/
│   └── smoke_outputs.jsonl
├── bl2/
│   └── smoke_outputs.jsonl
├── bl3/
│   └── smoke_outputs.jsonl
├── errors.jsonl
└── schema_smoke_summary.json
```

## 🛡️ 아키텍처 강제 사항

1. **LLM 클라이언트 단일 진입점**: 모든 LLM 호출은 `BackboneClient`를 통해서만 수행
2. **스키마 계약**: 모든 출력은 정의된 스키마를 준수해야 함
3. **에러 로깅**: 모든 에러는 `errors.jsonl`에 기록
4. **Smoke 테스트**: 각 모드별 smoke outputs 필수

## 📝 참고사항

- 로컬 버전은 GitHub 저장소의 기본 기능을 모두 포함하며, 추가 기능을 확장한 형태입니다.
- `agent_flow_diagram.md`는 시스템 아키텍처를 이해하는 데 유용한 참고 자료입니다.
- 모든 새로운 기능은 테스트로 검증되었습니다.



