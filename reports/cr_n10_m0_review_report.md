# CR-M0 (cr_n10) 검토 보고서

**Run ID:** `cr_n10_m0__seed42_proposed`  
**실험:** Conflict Review Protocol v1, n=10, seed=42  
**검토 일시:** 2026-02-12  
**목적:** 구조가 설계대로 동작하는지, 교정(pre→post)과 SSOT 필드가 채워지는지 확인

---

## 1. 산출물 체크리스트 (필수 파일)

| 파일 | 존재 | 레코드/크기 | 비고 |
|------|------|-------------|------|
| `results/cr_n10_m0__seed42_proposed/outputs.jsonl` | ✅ | 10 레코드 | 정상 |
| `results/cr_n10_m0__seed42_proposed/scorecards.jsonl` | ✅ | 10 레코드 | 정상 |
| `results/cr_n10_m0__seed42_proposed/derived/metrics/structural_metrics.csv` | ✅ | 존재 | 정상 |
| `results/cr_n10_m0__seed42_proposed/metric_report.html` | ❌ | - | 미생성 (있으면 표시) |

---

## 2. SSOT 필드 체크 (샘플 검증)

### 체크리스트 vs 실제 출력

| 체크리스트 필드 | 실제 출력 | 상태 |
|-----------------|-----------|------|
| `meta.stage1_perspective_aste` (A/B/C 존재) | ❌ 없음 | **미구현** – `process_trace` 내 P-NEG/P-IMP/P-LIT의 `output.triplets`에 A/B/C에 해당하는 데이터는 있으나 top-level SSOT 필드로 추출되지 않음 |
| `final_result.final_tuples_pre_review` | ❌ 없음 | **동등 필드 있음** – `stage1_tuples` (review 적용 전) |
| `final_result.final_tuples_post_review` | ❌ 없음 | **동등 필드 있음** – `final_tuples` (Arbiter 적용 후) |
| `analysis_flags.review_actions` | ❌ 없음 | **데이터 있음** – `process_trace` 내 ReviewA/B/C `output.review_actions` |
| `analysis_flags.arb_actions` | ❌ 없음 | **데이터 있음** – `process_trace` 내 Arbiter `output.review_actions` |
| `stage1_validator` / `stage2_validator` | N/A | conflict_review_v1에서는 validator 미사용 |

### 샘플 1개 확인 (text_id: nikluge-sa-2022-train-01393)

- **stage1_tuples (pre):** 2개 – `versatility|positive`, `간식그릇|positive`
- **final_tuples (post):** 2개 – `versatility|positive` (aspect_ref=간식그릇), `간식그릇|positive` (aspect_ref=간식그릇)
- **pre vs post:** aspect_ref가 MERGE로 갱신됨 → 교정 발생
- **process_trace:** P-NEG, P-IMP, P-LIT (stage1) → ReviewA, ReviewB, ReviewC, Arbiter (review) 7개 trace 존재

### 결론 (SSOT)

- **설계대로 동작:** P-NEG/P-IMP/P-LIT → ReviewA/B/C → Arbiter 흐름 정상, `stage1_tuples` → `final_tuples` 변화 있음
- **체크리스트 명시 필드:** `stage1_perspective_aste`, `final_tuples_pre_review`, `final_tuples_post_review`, `review_actions`, `arb_actions`는 top-level 미구현
- **동등 데이터:** `stage1_tuples`≈pre, `final_tuples`≈post, review/arb actions는 `process_trace`에 존재

---

## 3. 합격/불합격 기준 (Phase 0)

### 합격 조건 (ALL)

| 조건 | 결과 | 비고 |
|------|------|------|
| parse_generate_failure_rate == 0 | ✅ | structural_metrics: 0.0 |
| missing_required_field_rate == 0 | ⚠️ 수동 | SSOT 필드 명시 필드가 없으나 동등 데이터는 존재 |
| n=10 중 최소 1개 pre != post | ✅ | 5개 샘플에서 pre≠post (change_rate 0.5) |
| pre_to_post_change_rate >= 0.10 | ✅ | 0.5 >= 0.10 |

### 불합격 조건 (ANY)

| 조건 | 결과 | 비고 |
|------|------|------|
| outputs.jsonl 필수 필드 누락 | ⚠️ | 명시 SSOT 필드 없음, 동등 필드 있음 |
| pre/post 전 샘플 동일 (교정율 0) | ✅ | 아니요 – 5/10에서 교정 발생 |
| scorecard/aggregator 재현 실패 | ✅ | 아니요 – scorecards 10개, structural_metrics 생성됨 |

---

## 4. 구조 동작 검증

### 플로우

1. **Stage1:** P-NEG, P-IMP, P-LIT → 각각 triplets → `output.triplets`에 저장 (span 이상 시 `span=None` 처리)
2. **Merge:** A/B/C → candidates with tuple_id
3. **Review:** ReviewA, ReviewB, ReviewC → review_actions
4. **Arbiter:** 최종 review_actions → `_apply_review_actions` 적용
5. **출력:** `stage1_tuples` (pre), `final_tuples` (post)

### 교정 발생 사례

- text_id `nikluge-sa-2022-train-01393`: MERGE로 aspect_ref 갱신
- text_id `nikluge-sa-2022-train-00089`: Arbiter DROP으로 t4 제거 → stage1 5개 → final 4개

---

## 5. 종합 판정

| 항목 | 판정 |
|------|------|
| **구조 설계대로 동작** | ✅ |
| **교정(pre→post) 발생** | ✅ (5/10, 50%) |
| **Phase 0 합격** | ⚠️ **조건부 합격** |

### 조건부 합격 이유

- **합격:** parse_generate_failure_rate=0, 교정율 0.5≥0.10, scorecard/aggregator 정상
- **미충족:** `meta.stage1_perspective_aste`, `final_tuples_pre_review`, `final_tuples_post_review`, `review_actions`, `arb_actions`가 top-level SSOT 필드로 없음
- **동등 데이터:** `stage1_tuples`≈pre, `final_tuples`≈post, review/arb actions는 `process_trace`에 존재

### 권장 사항

1. **체크리스트 엄격 준수:** `conflict_review_runner.py`에서 SSOT 필드 추가
   - `meta.stage1_perspective_aste`: A/B/C triplets (from P-NEG/P-IMP/P-LIT)
   - `final_result.final_tuples_pre_review` = stage1에서 merge 후, review 적용 전
   - `final_result.final_tuples_post_review` = Arbiter 적용 후
   - `analysis_flags.review_actions`: [A actions, B actions, C actions]
   - `analysis_flags.arb_actions`: Arbiter actions

2. **metric_report.html:** `--with_metrics`로 재실행 시 생성 여부 확인 (현재 없음)
