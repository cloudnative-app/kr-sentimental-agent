# CR v1 Spec 및 규약

Conflict Review v1 프로토콜의 명세와 규약을 통합 정리합니다.  
**참조**: [README_cr_v1.md](README_cr_v1.md) — CR v1 개요·에이전트·데이터 플로우

---

## 0. 작업 원칙 (Conventions)

| 원칙 | 내용 |
|------|------|
| **Gold 필터 금지** | Gold는 절대 allowlist(ALLOWED_REFS)로 필터링하지 않는다. invalid_ref는 pred만 대상(진단용). |
| **정규화 범위** | 표면형 정리(strip/공백축약/대소문)까지만. aspect_ref에서 `#` 절대 훼손 금지. |
| **Smoke 테스트** | n=10~50으로 빠르게 돌려 "깨짐"만 확인. |
| **완료 기준** | ref_hash_preserved_fail_count=0, gold_ref_filtered_suspect_flag=False, sanity gold→gold F1=1.0 |

---

## 1. 프로토콜 명세 (Protocol Spec)

### 1.1 에이전트 워크플로우

```
text
  │
  ├─► P-NEG (Stage1) ──► triplets (negation/contrast 관점)
  ├─► P-IMP (Stage1) ──► triplets (implicit 관점)
  └─► P-LIT (Stage1) ──► triplets (literal/explicit 관점)
       │
       ▼
  Merge: A(r_neg) + B(r_imp) + C(r_lit) → candidates (tuple_id, origin_agent)
       │
       ▼
  conflict_flags = _compute_conflict_flags(candidates)
       │
       ├─► ReviewA ──► review_actions
       ├─► ReviewB ──► review_actions
       └─► ReviewC ──► review_actions
       │
       ▼
  Arbiter ──► arb_actions (다수결 + Rule 3)
       │
       ▼
  _apply_review_actions → _finalize_normalize_ref → FinalResult
```

**에이전트**: P-NEG, P-IMP, P-LIT (6 LLM) + Arbiter (코드). Validator, Debate, Moderator 없음.

### 1.2 Arbiter 규칙

| 규칙 | 조건 | 최종 액션 |
|------|------|-----------|
| Rule 1 | ≥2 identical vote | 해당 액션 채택 |
| Rule 2 | A/B/C 전부 상이 | KEEP + FLAG |
| Rule 3 | 1 FLIP + 1 DROP + 1 KEEP | FLIP reason ∈ {NEGATION_SCOPE, CONTRAST_CLAUSE, STRUCTURAL_INCONSISTENT} → FLIP; else FLAG |
| Rule 4 | MERGE vote | KEEP으로 대체 |

### 1.3 Review 액션 타입

`DROP | MERGE | FLIP | KEEP | FLAG`  
reason_code: NEGATION_SCOPE, CONTRAST_CLAUSE, IMPLICIT_ASPECT, ASPECT_REF_MISMATCH, SPAN_OVERLAP_MERGE, DUPLICATE_TUPLE, WEAK_EVIDENCE, POLARITY_UNCERTAIN, FORMAT_INCOMPLETE, KEEP_BEST_SUPPORTED, WEAK_INFERENCE, EXPLICIT_NOT_REQUIRED, STRUCTURAL_INCONSISTENT

---

## 2. 정규화 규약 (Normalization)

### 2.1 aspect_ref — `normalize_ref_for_eval`

**위치**: `metrics/eval_tuple.py`

- strip, 공백 축소, `#` 좌우 공백 제거
- **# 절대 훼손 금지**. 기호 삭제/치환 금지
- 적용: `tuple_from_sent`, `tuples_to_ref_pairs`, `tuples_to_attr_pairs`, `_tuples_from_list_of_dicts`

### 2.2 aspect_term — `normalize_for_eval`

- strip, lower, 공백 축소, 앞뒤 구두점 제거
- aspect_term 전용. aspect_ref는 `normalize_ref_for_eval` 사용

### 2.3 polarity — `normalize_polarity`

- pos→positive, neg→negative, neu→neutral
- 결측→default_missing (기본 "neutral")

### 2.4 분해 규칙 — `tuples_to_attr_pairs`

- 반드시 `split("#", 1)` 사용
- `#` 없으면 attribute="" 처리, `attr_split_missing_hash` 카운트(진단)

**상세**: [normalization_rules_and_locations.md](normalization_rules_and_locations.md)

---

## 3. 평가 규약 (Evaluation)

### 3.1 F1 매칭

- **ref-pol (CR v2 주평가)**: `(aspect_ref, polarity)` — `tuples_to_ref_pairs`, `match_by_aspect_ref=True`
- **ote-pol (Surface)**: `(aspect_term, polarity)` — `tuples_to_pairs`, `match_by_aspect_ref=False`
- **attr-pol (진단)**: `(attribute, polarity)` — `tuples_to_attr_pairs`

### 3.2 Gold 정책

- Gold는 allowlist 적용 금지
- `precision_recall_f1_tuple` docstring: "Gold is never filtered by allowlist"
- invalid_ref_count는 pred만 대상

### 3.3 튜플 소스 (SSOT)

| 구분 | 필드 | CR 의미 |
|------|------|---------|
| stage1 | final_result.stage1_tuples | pre_review (merge 후) |
| final | final_result.final_tuples | post_review (Arbiter 적용 후) |

---

## 4. Taxonomy 규약

- **SSOT**: `schemas/taxonomy.py`
- **ALLOWED_REFS**: `entity#attribute` 형식. 패키지/구성품 gold 호환 포함
- **is_valid_ref**: pred 진단용. gold에는 적용 안 함

**상세**: [taxonomy_nikluge_v1.md](taxonomy_nikluge_v1.md)

---

## 5. Debug 카운터 (structural_error_aggregator)

| 카운터 | 의미 | 통과 기준 |
|--------|------|-----------|
| ref_hash_preserved_fail_count | raw에 # 있었는데 norm 후 # 사라진 건수 | 0 |
| pred_ref_empty_count | pred tuple aspect_ref=="" 건수 | (진단) |
| pred_ref_invalid_count | pred aspect_ref 채웠지만 ALLOWED_REFS 밖 | (진단) |
| attr_split_missing_hash_count | ref에 # 없어 attribute 분해 실패 | 0 이상적 |
| gold_ref_filtered_suspect_flag | gold unique ref 급변 경고 | False |

---

## 6. Sanity 모드 (structural_error_aggregator)

```bash
# gold→gold: F1=1.0 확인
python scripts/structural_error_aggregator.py --input <scorecards> --outdir <out> --sanity-mode gold_gold --sanity-sample-n 20

# pred→pred: delta=0 확인
python scripts/structural_error_aggregator.py --input <scorecards> --outdir <out> --sanity-mode pred_pred --sanity-sample-n 20

# ref_split: join-back 동일성 체크
python scripts/structural_error_aggregator.py --input <scorecards> --outdir <out> --sanity-mode ref_split --sanity-sample-n 20
```

산출: `derived/metrics/sanity_checks.md`. 실패 시 exit 1.

---

## 7. 데이터 플로우

```
outputs.jsonl (FinalOutputSchema)
       │
       ▼
scorecards.jsonl (make_scorecard)
       │
       ▼
structural_error_aggregator → structural_metrics.csv
       │
       ▼
aggregate_seed_metrics → aggregated_mean_std.csv (시드 반복 시)
       │
       ▼
export_paper_metrics_aggregated → paper_metrics_aggregated.md
```

---

## 8. Paper Metrics 3-Level

| Level | 정의 | Table |
|-------|------|-------|
| Surface | OTE–polarity (aspect_term, polarity) | Table 1B |
| Projection | entity#attribute–polarity (aspect_ref, polarity) | Table 1A |
| Error Control | fix/break/net_gain, CDA, AAR, IRR | Table 3A/B/C |

---

## 9. 참조 문서

| 문서 | 설명 |
|------|------|
| [README_cr_v1.md](README_cr_v1.md) | CR v1 개요 |
| [cr_v1_workflow_metrics_and_rules.md](cr_v1_workflow_metrics_and_rules.md) | 에이전트 워크플로우·Arbiter 규칙 |
| [cr_branch_metrics_spec.md](cr_branch_metrics_spec.md) | 메트릭 명세·데이터 플로우 |
| [normalization_rules_and_locations.md](normalization_rules_and_locations.md) | 정규화 규칙·발생 지점 |
| [taxonomy_nikluge_v1.md](taxonomy_nikluge_v1.md) | Taxonomy SSOT |
| [how_to_run_cr_v1.md](how_to_run_cr_v1.md) | 실행 방법 |
