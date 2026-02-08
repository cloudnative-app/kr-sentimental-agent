# 파이프라인에서 Hallucination Rate 계산 방식

이 문서는 **aspect_hallucination_rate**가 무엇으로, 어떻게 계산되는지 정리합니다.

---

## 1. 최종 지표 정의

| 항목 | 값 |
|------|-----|
| **지표 이름** | `aspect_hallucination_rate` |
| **출처** | `structural_error_aggregator.py` → `structural_metrics.csv` / 리포트 |
| **의미** | **샘플당** “홀루시네이션으로 판정된 샘플” 비율 (분모 = N, 분자 = 해당 샘플 수) |

---

## 2. 샘플이 “홀루시네이션”으로 세는 조건 (코드 경로)

집계기는 **다음 두 소스 중 하나라도 만족하면** 해당 샘플을 “hallucinated”로 셉니다.

### 2.1 소스 A: `ate.hallucination_flag === True`

- **위치**: scorecard 필드 `record["ate"]["hallucination_flag"]`
- **설정 시점**: `scorecard_from_smoke.py`의 `make_scorecard()` → `ate_score(filtered)` 내부.

```python
# scripts/scorecard_from_smoke.py
def ate_score(filtered):
    keeps = [f for f in filtered if f["action"] == "keep"]
    drops = [f for f in filtered if f["action"] == "drop"]
    hallucination_flag = len(drops) > 0 and len(filtered) > 0  # canonical: hallucinated aspect
    return { ..., "hallucination_flag": hallucination_flag }
```

- **의미**: `filtered` 리스트가 있고, 그 중 **최소 1개가 `action == "drop"`** 이면 `hallucination_flag = True`.

### 2.2 소스 B: `inputs.ate_debug.filtered` 에 drop 1개 이상

- **위치**: scorecard 필드 `record["inputs"]["ate_debug"]["filtered"]`
- **집계기 판정** (`structural_error_aggregator.py`):

```python
def has_hallucinated_aspect(record: Dict[str, Any]) -> bool:
    ate = record.get("ate") or record.get("ate_score") or {}
    if record.get("ate", {}).get("hallucination_flag") is True:
        return True
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    drops = [f for f in filtered if f.get("action") == "drop"]
    return len(drops) > 0 and len(filtered) > 0
```

- **의미**: `ate.hallucination_flag`가 없거나 False여도, **ate_debug.filtered**에 `action == "drop"`인 항목이 1개 이상 있고 `filtered`가 비어 있지 않으면 “hallucinated”로 셈.

실제 파이프라인에서는 `make_scorecard()`가 동일한 `filtered`로 `ate`와 `inputs.ate_debug`를 채우므로, **실질적으로는 “drop이 1개 이상 있는 샘플 비율”**이 hallucination rate와 같습니다.

---

## 3. “Drop”이 나오는 조건: `build_filtered_aspects` (ATE 후처리)

`filtered`와 각 항목의 `action`(keep/drop)은 **ATE 단계 출력(aspects)**을 `build_filtered_aspects(text, aspects)`로 걸러서 만듭니다.

- **입력**: 원문 `text`, Stage1 ATE가 낸 `aspects` (각 항목: `term`, `span` 등).
- **출력**: `raw`, `filtered`, `kept_terms`, `dropped_terms`.  
  `filtered`의 각 항목: `term`, `span`, `action` ("keep" | "drop"), `drop_reason`.

### 3.1 항목별 판정 (한 aspect가 drop인 조건)

```python
# scripts/scorecard_from_smoke.py — build_filtered_aspects()
for a in aspects:
    term = a.get("term", "")
    span = a.get("span", {})
    span_txt = text[span["start"]:span["end"]]   # 원문 해당 구간 문자
    span_ok = (term == span_txt)                # term이 원문 span과 정확히 일치하는지
    is_valid = (term in allowlist) or (
        (len(term) >= 2) and ((term not in STOP_ASPECT_TERMS) or (term in allowlist))
    )
    action = "keep" if (is_valid and span_ok) else "drop"
    drop_reason = None if action == "keep" else "other_not_target"
```

- **drop** 되는 경우:
  1. **span_ok == False**: 모델이 준 `term`과 원문 해당 구간 문자 `span_txt`가 다름 (span 불일치).
  2. **is_valid == False**: 허용 목록(allowlist)에 없고, (길이 &lt; 2 이거나 stopword 등) 유효 타깃 조건 미충족.

즉, 이 파이프라인에서의 “hallucination”은  
- **완전한 원문 외 표현(out-of-text)** 뿐 아니라  
- **원문에는 있지만 term과 span이 안 맞는 경우(span 정렬 오류)**  
- **그리고 “유효 타깃” 규칙에 안 걸리는 경우**  
까지 모두 한꺼번에 “drop” → “hallucination”으로 집계됩니다.

---

## 4. 집계: aspect_hallucination_rate

```python
# scripts/structural_error_aggregator.py — aggregate_single_run()
hallucinated = sum(1 for r in rows if has_hallucinated_aspect(r))
...
"aspect_hallucination_rate": _rate(hallucinated, N),   # hallucinated / N
```

- **분모**: 프로필 필터 적용 후 샘플 수 `N`.
- **분자**: `has_hallucinated_aspect(r)`가 True인 샘플 수.

---

## 5. 분석 결과 예시 (구조만)

실제 run(예: experiment_mini4_proposed__seed42_proposed)의 scorecard에서:

- **hallucination_flag=True** 인 샘플에서는 `inputs.ate_debug.filtered`에 `action: "drop"` 항목이 있음.
- drop 항목 구조 예:
  - `term`: 모델이 준 aspect 문자열
  - `span`: `{ "start": int, "end": int }`
  - `action`: `"drop"`
  - `drop_reason`: `"other_not_target"` (keep이 아닐 때)

예시(의미만): “한 샘플에서 term A가 span [15,20]과 불일치로 drop, term B가 [22,25]에서 drop” → 해당 샘플 1개가 hallucination 카운트에 포함되고, 이와 같은 샘플 비율이 **aspect_hallucination_rate**가 됨.

---

## 6. 요약 표

| 단계 | 위치 | 역할 |
|------|------|------|
| ATE 후처리 | `scorecard_from_smoke.build_filtered_aspects()` | 원문·aspects로 span_ok / is_valid 판정 → `action` keep/drop, `drop_reason` |
| Scorecard | `ate_score(filtered)` | drop 1개 이상이면 `ate.hallucination_flag = True` |
| Scorecard | `inputs.ate_debug.filtered` | 동일한 filtered 리스트 저장 (term, span, action, drop_reason) |
| 집계 | `structural_error_aggregator.has_hallucinated_aspect()` | `ate.hallucination_flag` 또는 ate_debug.filtered drop 존재 → True |
| 지표 | `aggregate_single_run()` | `aspect_hallucination_rate = (hallucinated 샘플 수) / N` |

**한 줄 요약**:  
Hallucination rate는 **“ATE가 낸 aspect 중, 원문 span과 불일치(term≠span_txt)이거나 유효타깃 규칙에 걸려서 drop된 것이 1개라도 있는 샘플”**의 비율입니다.  
순수 “원문에 없는 표현”만이 아니라 **span 정렬 오류·타깃 필터**까지 포함된 넓은 정의라는 점은 해석/논문 시 유의하면 됩니다 (세부 분리는 `docs/work_spec_guided_change_ignored_s2_hallucination.md`의 H1/H2 제안 참고).
