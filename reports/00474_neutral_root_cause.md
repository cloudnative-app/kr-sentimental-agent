# 00474 |neutral 원인 확정 (1순위 버그)

## 현상

- **Triptych**: `final_pairs` = `|neutral` (aspect_term 빈 문자열).
- **Scorecard** (final_result.final_tuples 기준): `인정|neutral`.

→ **aspect_term 빈 문자열 유입**으로 tuple extractor 또는 정규화 단계에서 빈 문자열이 나오는 경로를 확정해야 함.

---

## 원인 후보

1. **Tuple extractor가 잘못된 필드를 읽는 경우**  
   - `_aspect_term_text(it)`: `it.get("aspect_term")`이 dict면 `term.get("term")`, str이면 그대로.  
   - `aspect_term`이 **null**이면 dict/str 둘 다 아니어서 `((it.get("opinion_term") or {}).get("term") or "").strip()` 등 fallback 후 **""** 반환.
2. **Normalize가 빈 문자열로 만드는 경우**  
   - `normalize_for_eval("")` = `""`.  
   - 이미 빈 문자열이 들어오면 그대로 유지.
3. **stage1_atsa에 "" key가 생기는 경우**  
   - **supervisor** `_aspect_polarity_sets`: `t = self._term_str(s)` 후 **`if not t: continue`** 로 빈 term은 **건너뜀**.  
   - 따라서 supervisor 코드 경로에서는 **"" key가 생성되지 않음**.  
   - 이전 보고서(override_apply_trace_02829.json)의 `{"": ["positive"]}`는 **null-aspect sentiment를 해석상 ""로 표기한 것**이며, 실제 `_aspect_polarity_sets` 출력에는 "" key가 없음.
4. **00474에서 triptych가 fallback을 쓰는 경우**  
   - `_extract_final_tuples_with_source(record)`:  
     - 1) `final_result.final_tuples` 있으면 사용.  
     - 2) 없으면 `final_aspects` → 3) 없으면 **inputs.aspect_sentiments**.  
   - 00474 record에서 **final_result.final_tuples가 비어 있거나 없으면** → **inputs.aspect_sentiments** 사용.  
   - inputs.aspect_sentiments에 **aspect_term=null**인 항목이 있으면 → `_aspect_term_text(null)` → **""** → tuple `("", "", "neutral")` → pairs `("", "neutral")` → 표시 `|neutral`.

---

## 결론: 확정 라인/경로

| 구분 | 위치 | 설명 |
|------|------|------|
| **빈 문자열 유입** | **inputs.aspect_sentiments** 항목 중 **aspect_term=null** (또는 term 없음) | ATSA stage1 출력이 null aspect인 경우 그대로 전달됨. |
| **추출** | `structural_error_aggregator._aspect_term_text(it)` / `metrics.eval_tuple` 동일 로직 | `aspect_term`이 null이면 dict/str 모두 아님 → fallback 후 **""** 반환. |
| **정규화** | `normalize_for_eval("")` = `""` | 빈 문자열을 만드는 주체는 **정규화가 아니라 null aspect_term**. |
| **Triptych fallback** | `_extract_final_tuples_with_source` | 00474 scorecard에 **final_result.final_tuples가 없거나 비어 있음** → inputs.aspect_sentiments 사용 → null 항목이 ""로 들어감. |

**한 줄 요약**:  
00474 |neutral은 **scorecard에 final_tuples가 없어** aggregator가 **inputs.aspect_sentiments**를 썼고, 그 안에 **aspect_term=null**인 항목이 있어** `_aspect_term_text`가 **""**를 반환**한 것이 직접 원인이다.

---

## 수정 권장 (이 라인만 잡으면 triptych/scorecard 흔들림 대폭 감소)

1. **Scorecard/파이프라인**: 00474를 포함한 모든 샘플에 대해 **final_result.final_tuples**가 채워지도록 보장 (moderator/build_final_aspects 경로에서 최종 tuple 리스트를 반드시 기록).
2. **Fallback 시 빈 term 필터(선택)**  
   - `_extract_final_tuples_with_source` 또는 `_tuples_from_list_of_dicts`에서 **aspect_term 정규화 후 ""인 항목**을 제외하거나,  
   - **inputs.aspect_sentiments** 사용 시 **aspect_term이 null/빈 문자열인 항목**을 건너뛰거나,  
   - 단, implicit(암시적) 평가가 있으면 **빈 aspect_term을 유지**해야 하는 요구가 있을 수 있으므로, 우선은 **final_tuples가 비어 있지 않게 하는 것**을 1순위로 권장.
3. **로그로 검증**  
   - 00474에 대해 `final_result.final_tuples` 존재 여부, `inputs.aspect_sentiments` 항목별 `aspect_term` 값 로그 → null/빈 문자열 유입 위치 확정.

이 라인만 잡으면 triptych/scorecard 불일치가 크게 줄어듭니다.
