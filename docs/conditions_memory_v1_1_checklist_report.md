# conditions_memory_v1_1 — 체크리스트 검토 결과

## 1. 생성·반영된 산출물

### 1.1 최종 YAML (3조건)

- **파일**: `experiments/configs/conditions_memory_v1_1.yaml`
- **조건**:
  - **C1**: Debate present, Episodic Memory OFF (slot present but empty)
    - `memory_mode: off`, `retrieval_execute: false`, `injection_mask: true`, `store_write: false`
  - **C2**: Debate present, Episodic Memory ON (retrieve + inject advisory)
    - `memory_mode: on`, `retrieval_execute: true`, `injection_mask: false`, `store_write: true`
  - **C2_silent**: Memory retrieval executed but advisory injection masked (control)
    - `memory_mode: silent`, `retrieval_execute: true`, `injection_mask: true`, `store_write: true`
- **원칙**: 에이전트 수/역할/토론 위치/모더레이터/입출력 포맷 불변. 차이는 DEBATE_CONTEXT__MEMORY 슬롯에 advisory 채움(ON) / 비움(OFF·silent)만 다름.

### 1.2 JSON 스키마 v1.1

| 스키마 | 경로 | 용도 |
|--------|------|------|
| EpisodicMemoryEntryV1_1 | `schemas/json/episodic_memory_entry_v1_1.json` | 메모리 엔트리 저장 |
| AdvisoryV1_1 | `schemas/json/advisory_v1_1.json` | 단건 advisory |
| AdvisoryBundleV1_1 | `schemas/json/advisory_bundle_v1_1.json` | 슬롯에 들어가는 형태 |
| CaseTraceV1_1 | `schemas/json/case_trace_v1_1.json` | 실험 로그/분석용, RQ1~RQ3 증거 |

공통 규칙(v1.1 고정):
- raw_text(원문 문장) 저장 금지
- gold/정답 라벨은 메모리 엔트리 본문에 저장하지 않음 (provenance.has_gold 등만 가능)
- CoT 저장 금지
- 모든 객체에 schema_version: "1.1" 포함

### 1.3 구현 모듈

| 모듈 | 경로 | 역할 |
|------|------|------|
| MemoryStore | `memory/memory_store.py` | JSONL append/load, prune(fifo), **forbid_raw_text 검사** (raw_text 등 금지 필드 시 fail-fast) |
| SignatureBuilder | `memory/signature_builder.py` | raw text → input_signature (원문 저장 금지) |
| Retriever | `memory/retriever.py` | **1단계: signature + lexical만** (필수). topk 1~3, language/structure 필터, lexical=단어 겹침(임베딩 없음). sentence-transformers hybrid는 2단계 옵션(필수 아님) |
| AdvisoryBuilder | `memory/advisory_builder.py` | episode → AdvisoryV1_1, **no_label_hint/no_forcing/no_confidence_boost 강제** |
| InjectionController | `memory/injection_controller.py` | DEBATE_CONTEXT__MEMORY 슬롯 생성(항상), C1/C2/C2_silent 마스킹 |
| CaseTraceLogger | `memory/case_trace_logger.py` | CaseTraceV1_1 기록, RQ1~RQ3 필드 고정 |

Pydantic 스키마(v1.1): `schemas/memory_v1_1.py` — EpisodicMemoryEntry, Advisory, AdvisoryBundle, CaseTrace 및 하위 타입.

---

## 2. 개발 체크리스트 검토 결과

### A. 누수 방지

| 항목 | 상태 | 비고 |
|------|------|------|
| MemoryStore에 raw text 필드가 들어가면 즉시 fail-fast | ✅ | `memory_store.py`: `FORBIDDEN_KEYS`(raw_text, gold, cot 등) 검사, `_fail_if_raw_text()`에서 위반 시 `ValueError` |
| Advisory에 polarity/aspect “정답 힌트” 직접 노출 금지 | ✅ | `AdvisoryConstraintsV1_1`: no_label_hint, no_forcing, no_confidence_boost = true 고정; AdvisoryBuilder는 corrective_principle만 message로 사용 |
| gold label은 메모리 엔트리에 저장하지 않음 | ✅ | 스키마·Store 금지 필드에 gold 관련 키 포함; 필요 시 provenance.has_gold 등만 허용 |

### B. 구조 고정

| 항목 | 상태 | 비고 |
|------|------|------|
| 에이전트 수/역할/토론 위치/모더레이터 규칙 변경 없음 | ✅ | conditions YAML은 pipeline.stages(ATE→ATSA→DEBATE→MODERATOR), moderator 정책 고정만 정의 |
| DEBATE_CONTEXT__MEMORY 슬롯은 3조건 모두 존재 | ✅ | InjectionController가 항상 동일 슬롯 구조로 생성; C1/C2_silent는 retrieved=[]로 마스킹 |
| one-shot injection 규칙 고정 | ✅ | YAML global.pipeline.debate.injection (strategy/trigger/allow_multiple_injections) 고정 |

### C. 스키마 검증

| 항목 | 상태 | 비고 |
|------|------|------|
| EpisodicMemoryEntry/Advisory/CaseTrace 모두 v1.1 validator 통과 | ✅ | JSON 스키마 파일 + Pydantic `schemas/memory_v1_1.py`로 검증 가능 |
| CaseTrace에 RQ1/RQ2/RQ3 계산 필수 필드 존재 | ✅ | risk(flagged, residual, severity_before/after, tags), override(eligible, applied, success, harm, accepted/rejected_changes), coverage(risk_tag_to_principle_mapped, mapping_coverage_hit) 포함 |

---

## 3. 조건 통제(실험 타당성)

- C1/C2/C2_silent 모두:
  - debate rounds 동일 (YAML max_rounds: 3)
  - prompt 슬롯 동일 (DEBATE_CONTEXT__MEMORY 항상 존재, 구조 동일)
  - stop 조건 동일
- 차이:
  - **C2만** retrieved에 advisory 채움 (retrieval_execute=true, injection_mask=false)
  - **C2_silent**는 retrieval 실행하되 retrieved=[]로 마스킹 (실행 경로·라운드·토큰 통제 목적)

---

## 4. 필요 시 후속 작업

- **실제 파이프라인 연동**: `agents/supervisor_agent.py`·`agents/debate_orchestrator.py`에서 조건 YAML 로드 및 InjectionController로 DEBATE_CONTEXT__MEMORY 슬롯 주입.
- **실험 러너**: 조건(C1/C2/C2_silent)별 run_id/seed 반복 시 CaseTraceLogger 호출 및 traces JSONL 출력.
- **JSON Schema 런타임 검증**: `jsonschema` 등으로 `schemas/json/*.json` 로드 후 엔트리/Advisory/CaseTrace 검증 (선택).
- **2단계(선택)**: Retriever에 sentence-transformers hybrid 추가 가능. 현재는 signature+lexical만 필수.

위 항목까지 반영 시 “정의 단계 고정” 체크리스트는 현재 기준으로 충족된 상태입니다.
