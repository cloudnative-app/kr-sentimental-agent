# 02829 회귀 테스트 명세 (필수)

## 목적

`_adopt_stage2_decision`의 **치환/대표선택 → 그 다음 conflict 체크** 순서 변경 후, 02829/피부톤 샘플에서 override가 정상 적용되는지 검증.

## 기대 결과

| 항목 | 기대값 |
|------|--------|
| **S0** (override 직전) | 피부톤 **neutral** 단일 |
| **S1** (override 직후 stage2_tuples, 대표 선택 반영) | 피부톤 **negative** 단일 |
| **S2** (moderator 이후 final_tuples) | 피부톤 **negative** |
| **conflict_blocked** | **false** |
| **override_effect_applied** | **true** (새 필드, stage2 채택 시 true) |

## 검증 방법

1. **실행**: C2 T1 (또는 동일 설정) run에서 02829 샘플 1건 처리.
2. **출력 확인**:
   - `final_result.stage1_tuples`: 해당 aspect만 필터 시 (피부톤, neutral).
   - `final_result.stage2_tuples`: 대표 선택 후 aspect당 1개라면 (피부톤, negative) 1개; 원시 patched_stage2는 (positive, negative) 둘 있을 수 있으나 conflict 판정은 **대표 선택 이후**만 사용.
   - `final_result.final_tuples`: (피부톤, negative).
   - `override_reason` ≠ "conflict_blocked".
   - `override_effect_applied` = true (meta.debate_override_stats 또는 동일 경로).
3. **회귀 테스트 스크립트** (선택): `tests/` 또는 `scripts/`에서 02829 text_id에 대해 위 필드 assert.

## 코드 변경 요약

- **conflict_blocked**: `patched_stage2_atsa`를 **대표 선택(치환/단일화) 이후** 형태로 만든 뒤 `_stage2_introduces_new_conflict` 호출.
- **대표 선택**: `_reduce_patched_stage2_to_one_per_aspect(patched_stage2_atsa, debate_output, correction_applied_log)` — override 적용 시 `resulting_polarity` 우선 사용.
- **최종 정렬**: override `resulting_polarity`를 debate_summary.final_tuples보다 우선하여 `pol_by_term`에 반영 → S2가 override 결과(negative)로 나오도록 함.
- **override_effect_applied**: `adopt_stage2`와 동일 값으로 meta에 추가.

## 5-2. conflict_blocked 기준 "대표 선택 이후"만 평가

- **코드**: `_adopt_stage2_decision`에서 `_stage2_introduces_new_conflict` 호출 전에  
  `patched_reduced = self._reduce_patched_stage2_to_one_per_aspect(...)` 호출하여 **patched_stage2를 aspect당 1개로 단일화**한 뒤, **patched_reduced**만 넘겨 충돌 여부 판단.
- **로그**: patched_stage2_atsa가 다중일 때 conflict check 전에 단일화되는지 확인 가능.

## 5-3. S1 불변식 재검증

(옵션1/옵션2 적용 후) S1 canon fail이 0으로 떨어져야 정상인지는 S1 정의에 따름. override 적용 시 final_result는 override 결과, debate_summary는 debate judge 결과이므로 의미를 바꾸지 않으면 S1은 계속 깨지는 것이 정상. 옵션: S1 검증 대상을 "override 미적용 샘플만"으로 한정.

## S1 불변식 관련

S1 불변식(debate_summary.final_tuples vs final_result.final_tuples)은 **debate_summary.final_tuples의 의미를 바꾸지 않으면** override 적용 후에도 계속 깨질 수 있음.  
(debate judge는 positive, override는 negative로 최종 반영되므로 양쪽이 다름.)  
옵션: S1을 “override 적용 시 final_result가 override 결과를 반영”으로 해석하거나, S1 검증 대상을 debate와 동일한 경우로 한정.
