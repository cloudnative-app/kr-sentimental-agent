# Polarity hint / override gate 조치 보고

## 0) 증상 요약

**override_gate_debug.jsonl에서 pos/neg/total/margin=0이 다수 발생하며, 원인 분류상 (B) 힌트는 있는데 polarity_hint가 neutral/None이라 점수 누적이 0이 됨.**

---

## 1) polarity_hint가 "neutral로 덮어써지는" 정확한 지점 및 조치

### 1-1. per-edit vs turn-level 동시 출력

- **`_build_debate_review_context()`** 에서 동일 턴에 대해 다음을 함께 로깅하도록 추가함.
  - **hint_entries(per-edit)** 의 polarity_hint: `per_edit_polarity_hints=[...]`
  - **rebuttal_points(turn-level)** 의 polarity_hint: `turn_level_polarity_hint=...`
- 로그 형식:  
  `[debate_review_context] speaker=%s per_edit_polarity_hints=%s turn_level_polarity_hint=%s gate_source=aspect_hints(from_hint_entries_then_aspect_map_fallback)`

### Gate가 참조하는 소스

- **게이트는 `debate_review_context["aspect_hints"]`만 사용함.**
- `aspect_hints` 구성:
  1. **hint_entries(per-edit)** 로 먼저 채움: set_polarity → value, drop_tuple → "negative", set_aspect_ref → None/0 등.
  2. **aspect_map(turn-level)** 은 “aspect가 아직 aspect_hints에 없을 때만” fallback으로 추가.
- 따라서 **게이트 점수화는 per-edit hint_entries 기반이면 정상**이고, rebuttal_points(turn-level) polarity_hint는 fallback 채우기에만 쓰이며, **stance="" → neutral이 게이트에 직접 들어가면 total=0으로 죽는 구조**였음.

### 1-2. 조치 내용 (덮어쓰기 방지)

- **target 정규화**: edit의 `target`이 Pydantic 등 객체일 때 `.model_dump()`로 dict로 바꾼 뒤 사용.  
  → target이 dict가 아니어서 편집을 통째로 스킵하던 경우를 제거해, **per-edit hint_entries가 제대로 쌓이도록** 함.
- **turn-level polarity 우선순위 명시**  
  - set_polarity(value) / confirm_tuple → pos/neg  
  - drop_tuple만 있으면 → turn_level polarity_hint = "negative"  
  - set_aspect_ref 등 → polarity_hint=None, weight=0 (점수 제외)  
  - proposed_edits가 있으면 **stance="" 여도 turn-level은 위 규칙만 사용**, neutral 고정 덮어쓰기 제거.

---

## 2) stance="" → neutral이 게이트 점수화에 끼어드는 것 차단

- **우선순위를 코드/주석에 명시** (이미 반영):
  1. set_polarity(value) → pos/neg  
  2. drop_tuple(target.polarity) → anti-neutral을 neg로  
  3. set_aspect_ref 등 → polarity_hint=None, weight=0  
  4. 아무 것도 없고 stance도 없으면 → neutral (점수화에서는 유효 힌트 수 0으로 처리).
- proposed_edits에 set_polarity/drop_tuple이 있으면 그걸 우선하고, stance 빈 문자열이어도 turn-level polarity는 위 규칙으로만 정해지도록 수정 완료.

---

## 3) EPM proposed_edits가 비어 있는 케이스 점검 (데이터 품질/파싱)

- **진단 스크립트 추가**: `scripts/diagnose_epm_proposed_edits.py`
  - `--run_dir` 또는 `--traces`/`--scorecards` 로 해당 런의 trace/scorecard 지정.
  - debate 단계 EPM 턴에 대해  
    - `output.proposed_edits` 길이  
    - `raw_response`에 `set_polarity`(또는 patch 형태) 포함 여부  
  로 **“실제로 빈 응답” vs “파서 누락”** 구분.
- **기존 C2 T0 결과에 대한 실행 결과**  
  - 10샘플 모두 EPM proposed_edits 비어 있지 않음 (non_empty: 10, parser suspect: 0, agent empty: 0).  
  - 즉, **현재 데이터에서는 “EPM이 edits를 안 낸다”가 정상 시나리오로 나오는 케이스는 없고, 파서 누락도 없음.**  
- 정리:  
  - **정상(EPM이 edits 없음)** 이면 해당 턴의 polarity_hint는 neutral이어도 되고, **valid_hint_count=0 분기(neutral_only)** 로 점수화에서 제외되도록 이미 반영됨.  
  - **비정상(파서 누락)** 이면 진단 스크립트로 “empty_but_raw_has_set_polarity”가 나오므로, 그때 파서/스키마 수리 대상으로 삼으면 됨.

---

## 4) 게이트 입력을 “힌트 수”가 아니라 “유효 힌트 수”로 변경

- **valid_hint_count**  
  - `polarity_hint in {"positive", "negative"}` 인 힌트만 카운트.
- **valid_hint_count == 0**  
  - `low_signal`로 처리하되, **skip_reason = "neutral_only"** 로 별도 태깅.  
  - `_override_stats["skipped_neutral_only"]` +1, `skipped_low_signal`도 +1 (기존 low_signal 집계 유지).
- **override_gate_debug.jsonl**  
  - 각 레코드에 `valid_hint_count` 필드 추가.  
  - `skip_reason`에 `neutral_only` 사용.
- **override_gate_debug_summary.json**  
  - `skipped_neutral_only_n`  
  - `low_signal_breakdown`: `{"neutral_only": N, "low_signal": M}`  
  추가하여 집계표에서 neutral_only vs 그 외 low_signal 구분 가능.

---

## C2 T0를 다른 run_id로 실행하는 커맨드

동일 설정으로 run_id만 바꿔서 결과 디렉터리를 분리하려면:

```bash
python experiments/scripts/run_experiments.py --config experiments/configs/experiment_mini4_validation_c2_t0.yaml --run-id experiment_mini4_validation_c2_t0_v2
```

- 결과 디렉터리: `results/experiment_mini4_validation_c2_t0_v2_proposed`
- 리포트/매니페스트: `experiments/reports/experiment_mini4_validation_c2_t0_v2_proposed` 등.

다른 이름 예:

```bash
python experiments/scripts/run_experiments.py --config experiments/configs/experiment_mini4_validation_c2_t0.yaml --run-id c2_t0_YYYYMMDD
```

---

## 변경 파일 요약

| 파일 | 변경 내용 |
|------|------------|
| `agents/supervisor_agent.py` | target 정규화(dict), per-edit vs turn-level 로그, polarity_first에 drop_tuple→negative 반영, valid_hint_count·neutral_only 분기, skipped_neutral_only·low_signal_breakdown |
| `scripts/diagnose_epm_proposed_edits.py` | 신규: EPM proposed_edits empty vs raw_response 진단 |
| `reports/polarity_hint_fix_report.md` | 본 보고서 |

재실행 후 `[debate_review_context]` 로그에서 per_edit_polarity_hints에 positive/negative가 나오고, override_gate_debug.jsonl에서 total > 0, skip_reason이 neutral_only vs low_signal로 구분되는지 확인하면 됨.
