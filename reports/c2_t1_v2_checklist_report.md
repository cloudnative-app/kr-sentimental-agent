# C2 T1 v2 체크리스트 점검 결과

**목표**: “게이트 APPLY가 final에 반영되는가” 확정.

**검증 기준 run**: `results/experiment_mini4_validation_c2_t1_proposed`  
(v2 run 디렉터리 `experiment_mini4_validation_c2_t1_v2_proposed` 없음 → T1 run으로 점검)

---

## 1. E2E 레코드 수

| 파일 | 기대 | 실제 | 결과 |
|------|------|------|------|
| outputs.jsonl | 10 | 10 | ✓ |
| scorecards.jsonl | 10 | 10 | ✓ |
| traces.jsonl | 10 | 10 | ✓ |

**결과**: **PASS** (10/10/10)

---

## 2. 02829/피부톤 타임라인

| 단계 | 기대 | 실제 (c2_t1_proposed) | 결과 |
|------|------|------------------------|------|
| S0 (stage1_tuples 피부톤) | neutral | neutral | ✓ |
| S1 (stage2_tuples 피부톤, override 직후) | negative 단일 | neutral + positive (negative 없음) | **✗** |
| S2 (final_tuples 피부톤) | negative | neutral | **✗** |

**결과**: **FAIL** — 게이트 APPLY가 S1/S2에 반영되지 않음.  
현재 outputs.jsonl 기준 02829는 `stage2_tuples`에 피부톤 negative가 없고, `final_tuples`는 피부톤 neutral.

---

## 3. conflict_blocked / override_effect_applied

- **conflict_blocked**: scorecard 02829 `override_reason` = `"debate_action"` → conflict_blocked 아님 ✓  
- **override_effect_applied**: scorecard 02829 `override_effect_applied: true`  
- 단, **debate_override_stats.applied**: 02829 레코드에서 `0`으로 기록됨 (다른 샘플에서 2건 적용).  
- 즉, **메타는 override_effect_applied=true인데, 실제 final_result에는 override 반영이 안 된 상태** → adopt/SoT/scorecard 채움 불일치.

**결과**: 메타 플래그는 기대에 부합하나, **최종 산출물(stage2_tuples/final_tuples)과 불일치** → **FAIL**로 간주.

---

## 4. override_gate_debug_summary.json

| 항목 | 기대 | 실제 | 결과 |
|------|------|------|------|
| decision_applied_n | > 0 | 2 | ✓ |

**결과**: **PASS**

---

## 5. S1 불변식 (정의 확정)

- **정의**: “S1 불변식은 **override 미적용 샘플만** 대상으로 재검증한다.”  
  - override가 적용된 샘플: stage2_tuples에 debate override 결과가 반영되어야 함.  
  - override 미적용 샘플: stage2_tuples는 stage1 + stage2 review만 반영 (debate override 제외).

- **현재 run**: 02829는 override 적용 후보(override_effect_applied=true)이지만, **실제 stage2_tuples/final_tuples에는 override가 반영되지 않음**.  
  → “override 적용 샘플”로 간주할 경우, **반영 자체가 누락**이므로 S1 불변식 검증 전에 **adopt/SoT/scorecard 채움**을 먼저 맞춰야 함.

**결과**: 정의 확정함. **현재는 adopt 단계에서 final 반영이 깨져 있어, override 미적용만 대상으로 한 S1 불변식 검증을 적용할 수 없음.**

---

## 6. 터미널 실패 항목 처리

- **test_anchor_enforcement**:  
  - `_apply_stage2_reviews` 반환값 4-tuple로 unpack 수정 (`patched_ate, patched_atsa, issues, _`).  
  - unanchored 전부 drop 시 neutral placeholder 미추가하도록 supervisor 수정 → drop_unmatched 테스트 통과.
- **test_integrity_features (test_check_experiment_config_eval_splits_from_sources)**:  
  - `scripts/check_experiment_config.py`에 `_eval_splits_from_roles(roles)` 추가 (report_sources/blind_sources 또는 report_set/blind_set → eval split 이름 집합).

---

## 7. 종합 판정 및 권고

| 항목 | 결과 |
|------|------|
| E2E 레코드 수 10/10/10 | PASS |
| 02829 S0/S1/S2 타임라인 | **FAIL** (S1/S2에 negative 미반영) |
| conflict_blocked=false, override_effect_applied=true | 메타는 만족, 산출물과 불일치 → **FAIL** |
| decision_applied_n > 0 | PASS |
| S1 불변식 (override 미적용만 대상) | 정의 확정; 현재 run은 adopt 단계 이슈로 검증 유보 |

**종합**: **FAIL**

**권고** (요청하신 대로):

- **T0/T1/T2 추가 실험은 보류.**
- **우선 수정할 것**: **adopt / SoT / scorecard 채움**  
  - 게이트 APPLY가 결정된 경우, `final_result.stage2_tuples` 및 `final_result.final_tuples`에 override 극성이 반영되도록 adopt 단계 수정.  
  - scorecard의 `override_effect_applied` 및 `debate_override_stats.applied`가 실제 반영 여부와 일치하도록 채움.  
- 위 수정 후 C2 T1 (또는 v2) 재실행 → 02829 타임라인 및 S1 불변식 재점검.

---

*작성: C2 T1 v2 체크리스트 점검 및 터미널 실패 항목 반영 후*
