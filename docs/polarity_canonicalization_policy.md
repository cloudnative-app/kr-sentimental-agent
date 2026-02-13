# Polarity Canonicalization Policy (Strict Typo)

파서에 들어가기 전 polarity 문자열은 **화이트리스트(완전 일치)** 또는 **편집거리 1~2 repair**만 허용. 그 외는 invalid로 카운트하고, invalid여도 샘플만 invalid 처리하고 run은 계속.

---

## 1. 정책

- **허용 (화이트리스트)**: `positive`, `negative`, `neutral`, `pos`, `neg`, `neu` (대소문자 무관, **완전 일치**) → repair 아님.
- **Repair**: 편집거리(Levenshtein) 1 또는 2로 **유일하게** 매칭되는 canonical(positive/negative/neutral)만 수리.
  - 예: `positve` → positive (repair), `negatve` → negative (repair), `neutal` → neutral (repair).
  - 동일 거리로 두 canonical에 매칭되면 수리하지 않음 (ambiguous).
- **Invalid**: 화이트리스트·repair 모두 불가 → `None`으로 기록, **invalid 카운트**, run은 계속 (재시도/중단 없음).
  - 예: `positiveitive` → invalid (수리하지 않음).

---

## 2. 적용 위치

| 위치 | 함수 | 동작 |
|------|------|------|
| **Override gate (debate hints)** | `canonicalize_polarity_with_repair(s)` | `None` → 해당 힌트 제외, `override_hint_invalid_total`·`override_hint_repair_total` 집계. |
| **ATSA Stage1 파서** | `_normalize_atsa_stage1_parsed` | `canonicalize_polarity_with_repair` 사용; invalid → polarity `None`, `polarity_invalid_count` 증가, **run 계속**. |

---

## 3. 구현

- **`schemas/agent_outputs.py`**
  - `canonicalize_polarity_with_repair(s) -> Tuple[Optional[str], bool]`: (canonical, was_repaired). 화이트리스트·편집거리 1~2만 수리.
  - `canonicalize_polarity(s) -> Optional[str]`: 위 함수 래퍼; 첫 번째 값만 반환.
  - `_normalize_polarity_value(v) -> Optional[str]`: invalid 시 `None` 반환 (raise 없음).

---

## 4. 메트릭 (SSOT·정합성)

- **polarity_repair_rate**, **polarity_invalid_rate**: aggregator가 row meta + override_gate_summary에서 집계.
  - `polarity_repair_n` = Σ row.meta.polarity_repair_count + override_hint_repair_total
  - `polarity_invalid_n` = Σ row.meta.polarity_invalid_count + override_hint_invalid_total
  - `polarity_repair_rate` = polarity_repair_n / (polarity_repair_n + polarity_invalid_n), `polarity_invalid_rate` 동일 분모.
- structural_metrics.csv / structural_metrics_table.md에 포함.

---

## 5. DO NOT

- **Neutral fallback**: invalid/missing polarity를 neutral로 묵시 매핑하지 않음.
- **Prefix/typo beyond 1~2**: 편집거리 3 이상 또는 ambiguous는 수리하지 않음.
- **Invalid 시 중단**: invalid여도 샘플만 invalid 처리하고 run은 계속 (retry/abort 없음).
