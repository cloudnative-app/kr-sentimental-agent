# 정규화 규칙 및 발생 지점 정리

**목적**: 파이프라인·평가 전반에서 적용되는 정규화 규칙과 그 발생 지점을 일원화하여 정리.

## 정책 (P0–P2, Ghost change 제거 반영)

- **P0**: 평가 키는 (aspect_term, polarity)만 사용. aspect_ref는 부가 메타데이터(analysis용), F1/break/fix에 사용 안 함.
- **P1**: 파이프라인에서 aspect_ref를 덮어쓰지 않음. 원본 보존(SSOT).
- **P2**: Tier1+Tier2(strict)를 gold/parse/eval 전 경로에 공통 적용. Tier3(edit-distance)는 기본 OFF.

---

## 1. 정규화 규칙 요약

| 구분 | 규칙 | 함수/위치 | 적용 대상 |
|------|------|-----------|-----------|
| **문자열(aspect)** | strip, lower, 공백 축소, 앞뒤 구두점 제거 | `normalize_for_eval` | aspect_term, aspect_ref |
| **aspect_ref (eval)** | strip, 공백 축소, # 좌우 공백 제거. # 훼손 금지 | `normalize_ref_for_eval` | aspect_ref (eval만) |
| **극성(평가)** | pos→positive, neg→negative, neu→neutral | `normalize_polarity` | polarity (F1/changed) |
| **극성(파이프라인)** | whitelist + edit-distance 1~2 repair | `canonicalize_polarity_with_repair` | ATSA/Override |
| **극성 분포** | pos/neg/neu → positive/negative/neutral | `normalize_polarity_distribution` | polarity_distribution |
| **aspect_ref 통일** | 동일 aspect_term 그룹 내 첫 항목으로 통일 | `_finalize_normalize_ref` | final_tuples (CR만) |
| **span** | dict/list/str → {start, end} | `ASTETripletItem.normalize_span` | span 필드 |

---

## 2. 상세 규칙

### 2.1 `normalize_for_eval` (문자열)

**위치**: `metrics/eval_tuple.py`

**규칙**:
- `None` → `""`
- strip, lower
- 연속 공백 → 단일 공백
- 앞뒤 구두점 제거: `.,;:!?"'` 등

**적용 시점**: 평가 시 tuple 추출·pair 생성 시점 (gold, stage1, final 모두)

---

### 2.1b `normalize_ref_for_eval` (aspect_ref, # 보존)

**위치**: `metrics/eval_tuple.py`

**규칙**:
- strip, 연속 공백 → 단일 공백
- `#` 좌우 공백 제거: "제품 전체 # 품질" → "제품 전체#품질"
- **# 절대 훼손 금지**. 기호 삭제/치환 금지 (표면형 정리만)
- Gold는 allowlist 필터 금지; invalid_ref는 pred만 (진단)

**적용 시점**: `tuple_from_sent`, `tuples_to_ref_pairs`, `tuples_to_attr_pairs`, `_tuples_from_list_of_dicts` 등에서 aspect_ref 처리 시.

---

### 2.2 `normalize_polarity` (극성, 평가용)

**위치**: `metrics/eval_tuple.py`

**규칙**:
- `pos` → `positive`, `neg` → `negative`, `neu` → `neutral`
- `positive`, `negative`, `neutral`, `mixed` → 그대로
- 결측/빈 문자열 → `default_missing` (기본 `"neutral"`)

**적용 시점**: F1, changed, break_rate, tuple 추출 시

---

### 2.3 `canonicalize_polarity_with_repair` (극성, 파이프라인용)

**위치**: `schemas/agent_outputs.py`

**규칙**:
- Whitelist: pos/neg/neu, positive/negative/neutral (대소문자 무시) → canonical, `was_repaired=False`
- Edit distance 1~2 repair: `positve`→`positive`, `negatve`→`negative` 등 → `was_repaired=True`
- 그 외 → `(None, False)` (invalid)

**적용 시점**:
- ATSA Stage1 파싱 (`tools/llm_runner._normalize_atsa_stage1_parsed`)
- Override gate (`agents/supervisor_agent`)
- `AspectSentimentItem` validator

---

### 2.4 `normalize_polarity_distribution`

**위치**: `schemas/agent_outputs.py`

**규칙**: `pos`/`neg`/`neu` 키 → `positive`/`negative`/`neutral`로 통일, 값 합산

**적용 시점**: ATSA 파싱 시 `polarity_distribution` 필드

---

### 2.5 `_finalize_normalize_ref` (aspect_ref 통일)

**위치**: `agents/conflict_review_runner.py`

**규칙**:
- `aspect_term`(또는 `aspect_ref`) 기준으로 그룹화
- 그룹 내 첫 항목의 `(aspect_term or aspect_ref)`를 `canonical_ref`로 설정
- 해당 그룹의 모든 항목에 `aspect_ref = canonical_ref` 덮어쓰기

**적용 시점**: CR 파이프라인, `_apply_review_actions` 직후, `final_tuples` 생성 전

---

### 2.6 `_gold_aspect_term` (gold aspect_term)

**위치**: `metrics/eval_tuple.py` (gold_row_to_tuples 내부)

**규칙**:
- `aspect_term == ""` (명시적 빈 문자열) → `""` 유지 (aspect_ref로 채우지 않음)
- `aspect_term` 또는 `opinion_term.term` 있음 → strip 후 반환
- 없음 → `aspect_ref` 또는 `term` fallback

---

### 2.7 Span 정규화

**위치**: `schemas/protocol_conflict_review.ASTETripletItem.normalize_span`

**규칙**:
- dict → 그대로 (start, end 검증)
- [start, end] → {start, end}
- `"12,18"`, `"12-18"` 등 문자열 → {start, end}
- 잘못된 값 → None

---

## 3. 발생 지점별 정리

### 3.1 파이프라인 (런타임)

| 지점 | 파일 | 함수/위치 | 적용 규칙 |
|------|------|-----------|-----------|
| ATSA 파싱 | `tools/llm_runner.py` | `_normalize_atsa_stage1_parsed` | canonicalize_polarity_with_repair, normalize_polarity_distribution, aspect_term fallback |
| CR finalize | `agents/conflict_review_runner.py` | `_finalize_normalize_ref` | aspect_ref 통일 (동일 term 그룹) |
| Override gate | `agents/supervisor_agent.py` | polarity 처리 | canonicalize_polarity_with_repair |
| Perspective triplet | `schemas/protocol_conflict_review.py` | `ASTETripletItem` | span normalize_span |

### 3.2 Gold 로딩

| 지점 | 파일 | 함수 | 적용 규칙 |
|------|------|------|-----------|
| Gold JSONL 로드 | `run_experiments.py`, `scorecard_from_smoke.py` | `gold_row_to_tuples` | normalize_polarity, _gold_aspect_term |
| Scorecard gold | `metrics/eval_tuple.py` | `gold_tuple_set_from_record` → `gold_row_to_tuples` → `tuples_from_list` | normalize_for_eval, normalize_polarity |

### 3.3 평가/집계

| 지점 | 파일 | 함수 | 적용 규칙 |
|------|------|------|-----------|
| Tuple 추출 | `structural_error_aggregator.py` | `_tuples_from_list_of_dicts`, `_extract_*` | normalize_for_eval, normalize_polarity |
| Pair 생성 (changed) | `tuples_to_pairs` | `metrics/eval_tuple.py` | (aspect_term, polarity) — aspect_term에 normalize_for_eval |
| Pair 생성 (F1 pred) | `tuples_to_pairs_ref_fallback` | `metrics/eval_tuple.py` | (aspect_ref or aspect_term) — normalize_for_eval |
| F1 계산 | `precision_recall_f1_tuple` | `metrics/eval_tuple.py` | gold: tuples_to_pairs, pred: tuples_to_pairs_ref_fallback |
| stage_delta.changed | `scorecard_from_smoke._build_stage_delta` | s1_pairs != s2_pairs | tuples_to_pairs (aspect_term만) |

---

## 4. 정규화 경로 불일치 (Ghost Change 원인)

| 용도 | Pair key | aspect_ref 사용 |
|------|----------|-----------------|
| **changed** (stage_delta, stage1_to_final_changed) | `tuples_to_pairs` | 사용 안 함 (aspect_term만) |
| **F1** (precision_recall_f1_tuple, pred) | `tuples_to_pairs_ref_fallback` | 사용 (aspect_ref or aspect_term) |

→ aspect_term 동일·aspect_ref 상이 시: changed=False, F1은 달라질 수 있음.

---

## 5. SSOT 정리

| 데이터 | 정규화 적용 시점 | 비고 |
|--------|------------------|------|
| 파이프라인 출력 (final_tuples) | 저장 시점에는 미적용. 평가 시 `_extract_*` → normalize | |
| Gold | `gold_row_to_tuples` 로드 시 normalize_polarity, _gold_aspect_term | |
| F1/changed | `_extract_*` → `tuples_to_pairs` / `tuples_to_pairs_ref_fallback` 시 normalize | |
