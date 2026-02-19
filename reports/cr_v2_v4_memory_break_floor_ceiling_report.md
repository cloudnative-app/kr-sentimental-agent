# CR v2 M0/M1 v4: 메모리 사용·Break·바닥/천장 효과 점검 보고서

## 1. 메모리 '사용' 실제 발생 여부

### 1.1 Retrieval Hit Rate (검색 성공률)

| 조건 | 시드 | N | retrieved_k>0 | Retrieval Hit Rate |
|------|-----|---|---------------|-------------------|
| M0 | 42, 123, 456 | 100×3 | 0 | **0.00** |
| M1 | 42 | 100 | 99 | **0.99** |
| M1 | 123 | 100 | 99 | **0.99** |
| M1 | 456 | 100 | 99 | **0.99** |

**결론**: M1에서 retrieval은 거의 항상 성공(99%). 메모리가 거의 안 쓰인 것이 아님.

### 1.2 Injection / exposed_to_debate (메타 정의 이슈)

| 항목 | M0 | M1 |
|------|-----|-----|
| memory_used_rate (aggregated) | 0.00 | 0.00 |
| exposed_to_debate (scorecard meta) | 0 | 0 |
| prompt_injection_chars | 0 | 0 |

**원인**: `EpisodicOrchestrator`가 `exposed_to_debate = (condition == "C2")`로만 설정. M1/M2는 C2가 아니므로 meta에 `exposed_to_debate=false`가 기록됨. **CR 파이프라인은 Debate gate 없이 `memory_context`를 Review 에이전트에 직접 전달**하므로, 실제로는 M1에서 retrieved_k>0일 때 advisory가 주입됨. `memory_used_rate` 정의가 Debate 파이프라인(C2) 기준이라 CR에서는 0으로 집계됨.

**실제 사용 여부**: M1에서 retrieved_k>0인 샘플(99%)은 slot_dict에 advisory가 채워져 Review 프롬프트에 전달됨. **메모리는 실제로 사용되고 있음** (meta 정의 불일치).

### 1.3 Injection Length / 압축

- `prompt_injection_chars`가 meta에 기록되지 않아 길이/압축 분석 불가.
- CR은 `_format_memory_context(slot_dict)`로 JSON 문자열 전달. AdvisoryBundleV1_1 스키마 사용.

### 1.4 Recheck-trigger 빈도 및 적용률

| 조건 | 시드 | recheck_triggered_rate | samples_with_recheck |
|------|------|------------------------|----------------------|
| M0 | 42 | 0.41 | 41/100 |
| M0 | 123 | 0.37 | 37/100 |
| M0 | 456 | 0.46 | 46/100 |
| M1 | 42 | 0.38 | 38/100 |
| M1 | 123 | 0.43 | 43/100 |
| M1 | 456 | 0.42 | 42/100 |

Recheck는 M0/M1 모두 37~46% 샘플에서 트리거됨. 메모리 유무와 무관하게 동작.

---

## 2. Break 오류 타입 태깅 (1페이지 표)

### 2.1 Break 발생 요약

| 조건 | n_break | n_keep | break_rate | break 샘플 |
|------|---------|--------|------------|------------|
| M0 | 0 | 79 (merged) | **0.00%** | 없음 |
| M1 | 1 | 85 (merged) | **1.16%** | 1건 (seed123) |

### 2.2 Break 사례 태깅 (암묵/부정-대조/그라뉼러리티/레퍼런스 오버랩)

| text_id | input_text | action | implicit | negation-contrast | granularity | ref_overlap | memory_retrieved |
|---------|------------|--------|----------|--------------------|-------------|-------------|------------------|
| nikluge-sa-2022-train-01649 | 리무버 없이 물로도 지울 수 있어 손톱 손상이 없어요~ | FLIP | ✓ | ✓ | — | — | 3 |

**태깅 근거**:
- **implicit**: gold `aspect_term=""` (암시적 관점)
- **negation-contrast**: "손상이 없어요" (부정 표현)
- **granularity**: 해당 없음
- **ref_overlap**: 해당 없음
- **memory_retrieved**: 3 (해당 샘플에서 메모리 3건 검색됨)

### 2.3 해석

| 구간 | 판단 |
|------|------|
| **메모리가 도움이 되는 구간** | M1에서 implicit_invalid_pred_rate↓, polarity_conflict_rate↓. 대부분의 changed는 improved(95%). |
| **메모리가 위험한 구간** | 유일한 break 사례는 **implicit + negation** 케이스. 메모리 3건 주입 상태에서 FLIP으로 오판 강화 가능성. |

**Discussion 방어력**: break 1건이 implicit+negation에 집중되어 있어, "메모리가 negation/implicit 구간에서 노이즈 증폭 위험"으로 논의 가능.

---

## 3. 지표 정의의 바닥/천장 효과 점검

### 3.1 M0 break=0 지속

| 항목 | 값 | 해석 |
|------|-----|------|
| M0 break_rate | 0.00 | n=300(merged)에서 break 0건 |
| break 정의 | S1✓ S2✗ (correct_s1 and wrong_s2) | 보수적: S1 정답인 샘플만 분모 |
| 표본 | n_keep≈79 (M0), 85 (M1) | S1 정답 샘플 수가 적음 |

**가능성**:
1. **break 정의가 보수적**: S1 정답인 샘플에서만 break 카운트. 표본에서 파손 사건이 희귀할 수 있음.
2. **M0는 메모리 미사용**: Review만 수행. M1 대비 변경 자극이 적어 break 발생 확률이 낮을 수 있음.

### 3.2 aar_majority_rate ≈ 0.96

| 조건 | aar_majority_rate |
|------|-------------------|
| M0 | 0.9656 ± 0.0079 |
| M1 | 0.9632 ± 0.0078 |

**천장 효과**: 0.96 수준이면 AAR 다수결 일치가 이미 높음. IRR/재현성 지표에서 더 올리기 어려운 천장에 근접.

### 3.3 권장: subset(복잡 케이스)에서 IRR 해석

- **전체 평균 IRR**만으로는 신호가 묻힐 수 있음.
- **복잡 케이스 subset** (conflict 존재, negation-contrast, implicit gold 등)에서만 IRR을 해석하는 것이 적절.
- 예: `conflict_vs_no_conflict` 분리, implicit gold 샘플만 IRR 계산.

---

## 4. 요약

| 질문 | 답 |
|------|-----|
| 메모리 사용 실제 발생? | **예**. M1 retrieval hit rate 99%. meta의 memory_used_rate=0은 CR용 정의 불일치. |
| break가 어떤 오류 타입? | **1건**: implicit + negation-contrast, FLIP. 메모리 3건 주입 상태. |
| break 정의 보수적? | S1✓만 분모. 표본에서 파손 희귀 가능. |
| aar_majority 천장? | 0.96 수준으로 천장 근접. |
| IRR 해석 권장? | **복잡 케이스 subset**에서만 해석 권장. |
