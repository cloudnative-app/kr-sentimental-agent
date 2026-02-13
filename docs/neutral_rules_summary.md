# 중립(neutral) 규칙 정리

파이프라인 전반에서 neutral이 어떻게 정의·처리되는지 규칙을 집약한 문서.

---

## 1. 정의 및 기본 원칙

| 구분 | 내용 |
|------|------|
| **neutral 정의** | 텍스트에 명시적 pos/neg 평가가 없음 (또는 문장 전체가 사실/설명). |
| **핵심 원칙** | **neutral ≠ missing** — 결측(missing)을 neutral로 대체하지 않음. |
| **허용 표현** | `positive`, `negative`, `neutral`, `pos`, `neg`, `neu` (화이트리스트, 대소문자 무관). |
| **conflict vs neutral** | 동일 aspect에서 pos/neg가 동시에 성립하면 neutral이 아니라 `mixed`/`ambivalent`/`conflict`로 별도 라벨. |

**참고:** 상세 정책은 `docs/neutral_conflict_missing_policy.md`, `docs/polarity_canonicalization_policy.md`.

---

## 2. 적용 위치별 규칙

### 2.1 스키마 (`schemas/agent_outputs.py`)

| 규칙 | 내용 |
|------|------|
| polarity 기본값 | `Optional[str] = None` — 기본값을 neutral이 아님. |
| neutral 사용 | 실제로 텍스트가 중립일 때만 `polarity="neutral"` 명시. |
| 결측 시 | `polarity=None` 유지, neutral로 대체하지 않음. |
| neutral_reason | `polarity=neutral` 또는 backfill 시 사유 기록 (예: `missing_atsa_for_aspect`, `stage2_placeholder_no_sentiments`). |
| is_backfilled | ATE만 있고 ATSA 없는 aspect 채움 시 `True`. |

### 2.2 평가 (`metrics/eval_tuple.py`)

| 규칙 | 내용 |
|------|------|
| normalize_polarity | `default_missing=None`이면 결측 시 `None` 반환. |
| gold 결측 | `eval_excluded`로 별도 집계 (neutral 처리 안 함). |
| pred 결측 | `invalid_pred`로 별도 집계. |
| 금지 | invalid/missing polarity를 neutral로 묵시 매핑하지 않음. |

### 2.3 Supervisor (`agents/supervisor_agent.py`)

| 규칙 | 내용 |
|------|------|
| 결측 처리 | `item.get("polarity") or "neutral"` 제거 — `None` 유지, 로깅. |
| final_tuples 계약 | CONTRACT-SUP-1: 모든 polarity는 `{positive, negative, neutral}` 중 하나. None은 final_tuples에 쓰지 않음. |
| rationale | polarity `None`이면 `[missing polarity]` 등으로 표기. |

### 2.4 Debate Override Gate (`override_rules.md`)

| 규칙 | 내용 |
|------|------|
| valid_hint_count | `polarity_hint in ("positive", "negative")`만 유효. **neutral은 유효 힌트로 간주하지 않음.** |
| neutral_only SKIP | `valid_hint_count == 0`이면 skip_reason=`neutral_only`, override 미적용. |
| Debate hint 없음 | `"neutral"`이 아닌 `None`, 스코어링에서 0 가중치/no-op. |

### 2.5 Polarity Canonicalization (`polarity_canonicalization_policy.md`)

| 규칙 | 내용 |
|------|------|
| 허용 | `positive`/`negative`/`neutral`, `pos`/`neg`/`neu` — 완전 일치. |
| Repair | 편집거리 1~2로 유일 매칭되는 경우만 수리 (예: `neutal`→neutral). |
| Invalid | 화이트리스트·repair 불가 → `None`, invalid 카운트, **neutral로 매핑 안 함**. |

### 2.6 Moderator / Debate Protocol (`debate_protocol.md`, `moderator.py`)

| 규칙 | 내용 |
|------|------|
| **Rule Z** | `stage1_ate.confidence == 0` **그리고** `stage2_ate.confidence == 0` → **final_label="neutral", confidence=0**. |
| sentence_polarity | 문장 수준 극성: `positive | negative | neutral | mixed`. |
| _stance_to_polarity | pro→positive, con→negative, 그 외→neutral. |
| stance="" | turn-level stance가 비어 있으면 pos/neg override 안 함 (neutral 유지). |
| 모호 키워드 | "중립", "neutral", "모호" 등이 문장에 있으면 neutral 반환 가능. |

### 2.7 Advisory/Memory Injection Gate (`memory/advisory_injection_gate.py`)

| 규칙 | 내용 |
|------|------|
| _is_neutral_only_stage1 | Stage1 aspect_sentiments가 거의 전부 neutral(0~1개만 non-neutral)이면 True. |
| 메모리 주입 | neutral_only일 때 debate/Stage2 주입 게이트 통과 조건之一. |

### 2.8 Debate Mapping 실패

| fail_reason | 의미 |
|-------------|------|
| neutral_stance | per-edit polarity가 모두 None이거나 neutral — `debate_fail_neutral_stance_rate` 집계. |
| neutral_warn/high | `debate_thresholds.json`의 경고 임계값. |

---

## 3. 금지 사항 (DO NOT)

1. **Neutral fallback**: invalid/missing polarity를 neutral로 묵시 매핑하지 않음.
2. **스키마 기본값**: `polarity`에 기본값 `"neutral"` 부여하지 않음.
3. **평가 시 대체**: gold/pred 결측을 평가 시 neutral로 치환하지 않음.
4. **Debate 힌트**: 힌트 없음/모호를 `"neutral"` 문자열로 저장하지 않음 — `None`.

---

## 4. Backfill·Placeholder

| 상황 | 표기 |
|------|------|
| ATE만 있고 ATSA 없음 | `is_backfilled=True`, `neutral_reason="missing_atsa_for_aspect"`. |
| Stage2 sentiments 전부 없음 | `neutral_reason="stage2_placeholder_no_sentiments"`, polarity=neutral. |
| 평가 | backfill/placeholder는 별도 분리·집계 가능. |

---

## 5. 관련 문서

| 문서 | 내용 |
|------|------|
| `docs/neutral_conflict_missing_policy.md` | neutral vs conflict vs missing 정의, 적용 위치. |
| `docs/polarity_canonicalization_policy.md` | 극성 문자열 화이트리스트·repair·invalid 처리. |
| `docs/override_rules.md` | Debate override gate, neutral_only SKIP. |
| `docs/debate_protocol.md` | Rule Z, sentence_polarity, mapping fail. |
| `schemas/agent_outputs.py` | AspectSentimentItem, polarity, neutral_reason. |
