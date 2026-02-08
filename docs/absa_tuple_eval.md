# ABSA Tuple 평가 정의 (Gold / Scoring 정합성)

## 1. 정의

### 1.1 Tuple (평가 단위)

- **Tuple**: `(aspect_ref, aspect_term, polarity)` 또는 최소형 `(aspect_term, polarity)`.
- **aspect_ref**: 카테고리/대상 참조 (예: `본품#다양성`).
- **aspect_term**: 문장 내 관점 표면형(term + span). 파이프라인 ATSA 출력은 `AspectTerm`(term, span)만 사용하며, 채점 시 (aspect_term.term, polarity) 쌍으로 매칭.
- **polarity**: `positive` | `negative` | `neutral`.

### 1.2 Gold 포맷

**신규 (권장)** — `gold_tuples`:

- 필드: `aspect_ref`(선택), `aspect_term`(필수, 빈 문자열 가능·암시적), `polarity`, `span`(선택, 문장 내 문자 구간).
- **span**: `{ "start": int, "end": int }` (원본에 있으면 골드 생성 스크립트에서 저장). 매칭은 (aspect_term, polarity)만 사용; span은 검증/보조용.

```json
{"uid": "...", "gold_tuples": [{"aspect_ref": "본품#다양성", "aspect_term": "마스크팩", "polarity": "positive"}]}
```

**span 포함 예** (선택):

```json
{"uid": "...", "gold_tuples": [{"aspect_ref": "본품#다양성", "aspect_term": "마스크팩", "polarity": "positive", "span": {"start": 0, "end": 3}}]}
```

**최소형** (aspect_ref 없음):

```json
{"uid": "...", "gold_tuples": [{"aspect_term": "마스크팩", "polarity": "positive"}]}
```

**기존 호환** — `gold_triplets`:

- 읽을 때: `aspect_term = gold_triplets[i].opinion_term.term` (없으면 `aspect_ref` 사용).
- 쓰는 쪽은 신규 생성 시 `gold_tuples`만 사용(상위 일관).

### 1.3 매칭 단위 (채점 기준)

- **채점에 사용하는 기준**: **(aspect_term, polarity)** 쌍만 사용. **aspect_ref는 채점에서 사용하지 않음.**
- **F1 매칭**: `(normalize(aspect_term), normalize(polarity))` 쌍 일치. aspect_ref는 무시.
- 정규화: 공백/대소문자/특수문자 정리, 극성은 pos→positive, neg→negative, neu→neutral 통일. (ATE 후처리와 중복 금지.)
- **Gold aspect_term이 ""(암시적 관점)인 경우**: 기본 규칙으로 **polarity만 맞으면 매칭**함. 골드 쌍 `("", polarity)`는 예측 쌍 중 동일 polarity를 가진 것 하나와 1:1 매칭 (같은 polarity가 여러 개여도 한 골드당 한 pred만 매칭). `metrics.eval_tuple.precision_recall_f1_tuple(..., match_empty_aspect_by_polarity_only=True)` 가 이 규칙을 구현함.

### 1.4 용어 정리

- **aspect_term**: 파이프라인 ATSA 스키마에서 문장 내 관점 표면형을 `AspectTerm`(term, span)으로 정의. 채점은 (aspect_term.term, polarity)만 사용.
- **aspect_ref**: 골드 포맷에서만 선택 사용(택소노미 등). 파이프라인 ATSA 출력에는 사용하지 않음.

---

## 2. 메트릭 명칭

- **tuple_f1_s1** / **tuple_f1_s2**: Stage1/Stage2+Mod 기준 Tuple(Aspect, Polarity) F1.
- **triplet_f1_s1** / **triplet_f1_s2**: deprecated alias. 동일 값으로 채워 호환 유지 가능.

**스테이지별 F1 데이터 출처**: 파이프라인(Supervisor)이 `FinalResult.stage1_tuples` / `FinalResult.final_tuples` 를 남기고, run_experiments가 scorecard에 `runtime.parsed_output`(전체 payload)로 넣음. structural_error_aggregator / build_metric_report 는 `_extract_stage1_tuples` / `_extract_final_tuples` 로 해당 필드를 읽어 gold와 (aspect_term, polarity) F1을 계산함. 자세한 진단은 `docs/stage_f1_and_tuple_scoring_diagnosis.md` 참고.

---

## 3. 영향 모듈 요약

| 구분 | 파일 | 비고 |
|------|------|------|
| Gold 생성 | `scripts/make_mini_dataset.py`, `scripts/make_mini2_dataset.py` | `gold_tuples` 출력 |
| Gold 로딩 | `experiments/scripts/run_experiments.py` | `gold_tuples` 우선, `gold_triplets` 하위호환 |
| 채점/집계 | `scripts/structural_error_aggregator.py` | Tuple 추출, tuple_f1, triplet alias |
| 리포트 | `scripts/build_metric_report.py` | tuple_f1 표시, 문구 Tuple(Aspect, Polarity) |
| Paper 테이블 | `scripts/build_paper_tables.py` | gold_tuples/triplets 읽기, tuple 추출 |
