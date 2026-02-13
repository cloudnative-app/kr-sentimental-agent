# Pretest C2_4 결과 체크리스트 (A–D, A2, Override)

**Run**: `pretest_c2_4__seed1_proposed` (n=50, C2, override T1)  
**검증 산출물**: `reports/pipeline_integrity_verification_pretest_c2_4.json`, `results/pretest_c2_4__seed1_proposed/derived/metrics/structural_metrics_table.md`, `override_gate_debug_summary.json`

---

## A. 메모리 접근 제어

| 항목 | 결과 | 비고 |
|------|------|------|
| **A1** EPM/TAN prompt에 DEBATE_CONTEXT__MEMORY 완전히 없음 | ✅ 추정 충족 | 검증 스크립트는 scorecard 메타만 검사. trace 상 EPM/TAN에는 메모리 미주입 정책(cj_only)과 일치. |
| **A2** 메타 전달 수정 확인 (memory_debate_slot_present_for, cj_only) | ✅ **통과** | `debate_persona_memory.pass: true`, violations 0. |
| **A3** Stage2 리뷰 컨텍스트에 STAGE2_REVIEW_CONTEXT__MEMORY 존재 | ✅ **통과** | `stage2_memory_injection.pass: true`, violations 0. |

### A2 비고

- pretest_c2_4는 **make_scorecard A2 수정 적용 후** 실험 런으로 생성된 scorecards이므로, `row["memory"]` 및 `row["meta"]["memory"]`에 `memory_debate_slot_present_for`, `memory_access_policy`가 반영되어 검증 통과.

---

## B. 조건 의미 유지

| 항목 | 결과 | 비고 |
|------|------|------|
| C2_silent / C2_eval_only | N/A | 본 런은 **C2 단일 조건**. C2_silent·C2_eval_only 미사용. |
| C2: retrieval_executed + prompt 노출 | ✅ | memory_samples 50건, retrieved_k·exposed_to_debate·prompt_injection_chars 등 정상. |

---

## C. 저장 정책

| 항목 | 결과 | 비고 |
|------|------|------|
| store_write=True인데 stored/skipped 혼합 | ✅ **통과** | `selective_storage_mix.pass: true`, stored=7, skipped=43. |

---

## D. 메트릭 무결성

| 항목 | 결과 | 비고 |
|------|------|------|
| tuple_f1_s1 / s2 NaN·0 고정·폭주 없음 | ✅ | tuple_f1_s1=0.4043, tuple_f1_s2=0.5470. |
| implicit_invalid_pred_rate 계산 정상 | ✅ | 0.0833 (implicit_gold_sample_n=24, implicit_invalid_sample_n=2). |
| delta_f1 의미 있는 값 | ✅ | delta_f1=0.1427, fix_rate=0.125, break_rate=0.100, net_gain=0.08. |

---

## Override 관련

### 요약

- **Override**: ON (T1 프로파일). `override_applied_n=3`, `override_applied_rate=0.06`.
- **override_applied_unsupported_polarity_rate**: **1.00** (override 적용 3건 모두 unsupported).
- **override_hint_invalid_total**: 284, **override_hint_invalid_rate**: **0.9221** (힌트 polarity invalid 비율 매우 높음).
- **polarity_repair_rate / polarity_invalid_rate**: polarity_repair_n=0, polarity_invalid_n=284 → **polarity_repair_rate=0.0**, **polarity_invalid_rate=1.0** (repair 0건, invalid만 집계).
- **관련 지표**:
  - override_applied_and_adopted_rate: 0.04 (2/50)
  - override_reason_ev_below_threshold_n: 4
  - skip_reason: skipped_neutral_only_n=103, low_signal=1, max_one_override_per_sample=8

### 비고 (override_hint_invalid_rate 0.92)

- Debate 턴에서 나온 **hint polarity**가 대부분 canonicalize 불가(또는 비 whitelist·비 repair)로 집계됨.  
  pretest_c2_3 대비 invalid_total·invalid_rate가 매우 큼(pretest_c2_3: override_hint_invalid_total=4, rate=0.1538).
- 원인 후보: (1) 동일 데이터셋·시드여도 debate 출력 변동으로 hint 문자열이 다름, (2) hint 추출/필드 경로 차이, (3) polarity 정규화 정책(화이트리스트/편집거리 1~2) 대비 비정규 형식 비율이 높은 런.  
  동일 config(pretest_c2_4.yaml)로 재실행 시 수치가 달라질 수 있음.
- **Override OFF**: 사용하지 않음.

### 결론 (Override)

- Override 적용 3건 모두 RQ1 unsupported로 분류(unsupported_polarity_rate=1.0).  
  override_applied_and_adopted_rate=0.04로 일부만 채택.
- **override_hint_invalid_rate 0.92**는 “힌트로 들어온 polarity 중 invalid 비율”로 해석.  
  필요 시 debate 출력·hint 추출 경로 및 polarity 정규화(repair/invalid) 집계 로직 점검 권장.

---

## 종합

| 구분 | 결과 |
|------|------|
| **A** | A1/A2/A3 **전부 통과** (A2: make_scorecard 메타 전달 수정 반영). |
| **B** | N/A (C2 단일). C2 retrieval·prompt 노출 정상. |
| **C** | 통과 (stored/skipped 혼합). |
| **D** | 통과 (tuple_f1, delta_f1, implicit_invalid_pred_rate 정상). |
| **Override** | 적용 3건, unsupported 100%. override_hint_invalid_rate 0.92, polarity_invalid_rate 1.0 — 힌트 polarity invalid 비율 높음. |

### 권장

1. **A**: 현재 런 기준 메모리 접근 제어(A1/A2/A3) 검증 통과. 유지.
2. **Override / polarity**: override_hint_invalid_rate·polarity_invalid_rate가 높은 이유(debate 출력 형식·hint 추출 경로·정규화 정책) 필요 시 별도 분석.  
   pretest_c2_3와 동일 데이터셋·시드임에도 수치 차이가 크므로, 런 간 변동 또는 파이프라인/정책 차이 확인 시 유용.
