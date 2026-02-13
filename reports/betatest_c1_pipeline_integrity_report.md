# Betatest C1 pipeline_integrity_verification 결과 보고

**실행**: `python scripts/pipeline_integrity_verification.py --run_dir results/betatest_c1__seed42_proposed --out reports/pipeline_integrity_verification_betatest_c1__seed42.json`  
**산출**: `reports/pipeline_integrity_verification_betatest_c1__seed42.json`, `...__seed123.json`

---

## 1. 요약 (시드별)

| 항목 | seed42 | seed123 |
|------|--------|---------|
| **e2e_record_count** | ✅ pass (50/50) | ✅ pass (50/50) |
| **invariant_s3_fail** | 0건 | 0건 |
| **metrics_pred_consistency** | ✅ pass | ✅ pass |
| **debate_persona_memory** | ✅ pass | ✅ pass |
| **stage2_memory_injection** | ✅ pass | ✅ pass |
| **selective_storage_mix** | ⚠️ pass=false | ⚠️ pass=false |
| **invariant_s1_expected** | 8건 | 10건 |
| **aggregator_source_fallback** | 2건 | 2건 |

---

## 2. E2E 레코드 수

- outputs, scorecards, traces 모두 50건 일치 (expected_count=50).
- 정상.

---

## 3. 불변식 (Invariants)

### 3.1 S1 (EXPECTED) — debate_summary ≠ final_result

- **의미**: debate summary와 final_result가 다른 것은 허용/기대.
- **seed42**: 8건
- **seed123**: 10건
- **평가**: 기대 동작.

### 3.2 S2 (EXPECTED) — final_tuples ↔ final_aspects 불일치

- **seed42, seed123**: 0건.
- **평가**: 이 검사에서 별도 이슈 없음.

### 3.3 S3 (FAIL)

- **seed42, seed123**: 0건.
- **평가**: 정합성 위반 없음.

---

## 4. Aggregator source fallback

- **의미**: `final_tuples`·`final_aspects` 없을 때 `inputs.aspect_sentiments` 사용.
- **seed42/seed123 공통**: text_id `01525`, `02691` 2건.
- **평가**: fallback 사용은 설계상 허용. final_pred_source_aspects_path_unused_flag (final_aspects 경로 미사용)와 연관 가능.

---

## 5. Override 적용·힌트 증거

- **seed42**: 2건 (01469, 02557)
- **seed123**: 6건 (01398, 00672, 01339, 00320, 02581, 00735)
- **평가**: T1 조건에서 override 적용 건수 차이는 시드별 예측 차이로 이해 가능.

---

## 6. selective_storage_mix (C1 특이)

- **pass**: false
- **note**: "store_write=True run must have both stored and skipped (no 100% store)."
- **store_decision_counts**: skipped=50 (전부 skipped)
- **해석**: C1은 episodic memory OFF이므로 `store_write=false`. 저장 의사결정이 전부 skipped인 것은 C1에서 기대되는 동작. `selective_storage_mix` 검사가 C2(store_write=true)를 전제로 하므로, **C1에서는 오탐(false positive)** 가능성 있음.

---

## 7. metrics_pred_consistency

- **pass**: true
- **mismatches**: []
- **triptych_n**: 0 (triptych 테이블 미생성 — aggregator N_pred_final_aspects 경고로 미실행)
- **평가**: scorecards와 structural_metrics pred 일치. triptych 3-way 비교는 triptych 미생성으로 미수행.

---

## 8. 결론

| 항목 | 판정 |
|------|------|
| E2E 레코드 | ✅ 통과 |
| S3 불변식 | ✅ 위반 없음 |
| Pred 일관성 | ✅ 통과 |
| Memory/Injection | ✅ 통과 (C1에서는 memory 미사용) |
| selective_storage_mix | ⚠️ C1에서는 검사 목적과 불일치 가능 (C2 전용 검사로 추정) |

**종합**: Betatest C1 두 시드 모두 pipeline_integrity_verification에서 핵심 정합성 항목은 통과. C1 특성상 `selective_storage_mix` 실패는 검사 전제가 C2용이라면 무시 가능.
