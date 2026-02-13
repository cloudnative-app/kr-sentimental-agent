# Scorecard 경로 분리 및 정합성 체크리스트

## A. 덮어쓰기 금지: 경로 분리

**규칙**: `results/<run_id>/scorecards.jsonl`은 **원본(run_experiments)** 전용. 덮어쓰지 않음.

**Smoke 재생성**:
- 출력 경로: `results/<run_id>/derived/scorecards/scorecards.smoke.jsonl` (gold 없음)
- Gold 주입 시: `results/<run_id>/derived/scorecards/scorecards.smoke.gold.jsonl`

**조치**:
- `scorecard_from_smoke.py`에 **`--out`** 옵션 추가. 재생성 시 반드시 `--out`으로 위 경로 지정.
- 예:  
  `python scripts/scorecard_from_smoke.py --smoke results/<run_id>/outputs.jsonl --out results/<run_id>/derived/scorecards/scorecards.smoke.jsonl`  
  `python scripts/scorecard_from_smoke.py --smoke results/<run_id>/outputs.jsonl --gold .../valid.gold.jsonl --out results/<run_id>/derived/scorecards/scorecards.smoke.gold.jsonl`

## B. meta 필드 강제 (traceability)

재생성/원본 모두 다음 필드를 넣음:

| 필드 | 설명 |
|------|------|
| `meta.scorecard_source` | `"run_experiments"` \| `"scorecard_from_smoke"` |
| `meta.gold_injected` | bool |
| `meta.gold_path` | gold JSONL 경로 또는 null |
| `meta.outputs_sha256` | (선택) 해당 행 outputs 해시 |

- **run_experiments**: `make_scorecard(..., meta_extra={...})` 로 주입.
- **scorecard_from_smoke**: `make_scorecard(..., meta_extra={...})` 로 주입.

## C. stage_delta 정책 (smoke 재생성)

- **run_experiments**: 기존대로 `_build_stage_delta(entry)`로 계산.
- **scorecard_from_smoke**: **entry에 이미 `stage_delta`가 있으면 재계산하지 않고 그대로 사용.** 없을 때만 `_build_stage_delta(entry)` 호출.  
  → triptych(pairs 비교)와 stage_delta.changed 불일치(B/C 플래그) 방지.

## D. Triptych gold audit 열

- **gold_n_explicit_pairs**, **gold_n_implicit_pairs**: 행별 explicit/implicit pair 개수.
- **gold_audit_verdict**: `gold_type` (explicit | implicit)과 동일.
- “gold 있는데 N_gold_explicit/implicit = 0” 원인 파악용.

## E. 한 번에 끝내는 체크리스트 (한 커맨드)

```bash
python scripts/consistency_checklist.py --run_dir results/experiment_real_n100_seed1_c1_1__seed1_proposed --triptych_n 5
```

**필수 체크 (GO/NO-GO)**:
1. **source**: `meta.scorecard_source` 존재 및 기대값 (선택: `--expect_source run_experiments` 등).
2. **gold**: `gold_injected==true`인 행이 있으면, `inputs.gold_tuples`가 1개 이상인 행이 최소 1개.
3. **tuple path**: `structural_metrics.csv`의 N_pred_final_tuples / final_aspects / inputs 비율 (fallback 급증 시 경고).
4. **sanity**: gold→gold F1=1, final→final F1=1 (aggregator `run_sanity_checks` 호출).
5. **inconsistency_flags == 0**: `derived/diagnostics/inconsistency_flags.tsv` 행 수 0 (B/C 유형 0).
6. **triptych**: `derived/tables/triptych_table.tsv` 존재 및 상위 n행 점검 (stage1_pairs, final_pairs, gold_pairs, matches, risk_ids, memory 등).

**종료 코드**: 0 = GO, 1 = NO-GO.
