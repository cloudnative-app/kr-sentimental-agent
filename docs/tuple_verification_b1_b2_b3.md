# Triptych / structural_metrics / metric_report 동일 규칙 검증 (B1/B2/B3)

목표: Triptych, structural_metrics, metric_report가 **동일한 튜플·정규화·매칭 규칙**으로 계산되는지 검증.

---

## B1) Sanity Check 3종 (필수, fail-fast)

- **gold→gold F1 = 1.0** (gold 튜플 집합으로 F1 계산 시 1.0)
- **stage1→stage1 F1 = 1.0** (권장: stage1 추출/정규화 일관성)
- **final→final F1 = 1.0** (final 튜플 집합으로 F1 계산 시 1.0)

**실패 시**: "채점 로직/정규화/추출 경로 충돌"로 확정하고 **중단** (exit 1).

**실행**: aggregator 실행 시 `--sanity_check` 또는 `--diagnostics_dir`를 주면 B1을 먼저 수행하고, 실패 시 즉시 종료.

```bash
python scripts/structural_error_aggregator.py --input <scorecards.jsonl> --outdir <outdir> [--sanity_check]
# 또는
python scripts/structural_error_aggregator.py --input <scorecards.jsonl> --outdir <outdir> --diagnostics_dir <run_dir>/derived/diagnostics
```

---

## B2) Tuple source coverage audit (필수)

**--log_tuple_sources**와 동일한 추출 경로로 **전체 샘플**을 돌려 다음을 집계:

| 지표 | 의미 |
|------|------|
| final_fallback_aspect_sentiments_rate | final_tuple_source가 `inputs.aspect_sentiments`로 떨어지는 비율 |
| stage1_fallback_trace_atsa_rate | stage1_tuple_source가 `trace_atsa` fallback으로 가는 비율 |
| gold_missing_rate | gold가 누락되는 비율 (gold_source 없음) |

**산출물**: `derived/diagnostics/tuple_source_coverage.csv` (run당 1행)

**판정**:
- final이 inputs.aspect_sentiments fallback이 **많으면** → final_result.final_tuples/final_aspects 생성·저장 경로 문제 가능성
- stage1이 trace fallback이 **많으면** → stage1_tuples 기록 누락 가능성

---

## B3) "changed/guided 모순" 자동 검출 (필수)

Triptych에서 아래 조건을 찾아 리스트업:

| 플래그 | 조건 |
|--------|------|
| flag_delta_nonzero_changed_zero | delta_pairs_count != 0 인데 stage1_to_final_changed == 0 |
| flag_changed_one_delta_zero | stage1_to_final_changed == 1 인데 stage_delta.changed == 0 (있다면) |
| flag_stage2_no_guided_unguided | moderator_selected_stage == stage2 인데 guided_change==0 and unguided_drift==0 |
| flag_risk_resolution_but_stage2_risk | risk_resolution==1 인데 stage2_structural_risk==1 (정의: resolution ⇒ S2 clear) |

**산출물**: `derived/diagnostics/inconsistency_flags.tsv`

**판정**: **1건이라도 있으면** → scorecard.stage_delta 주입/정의 또는 triptych 계산이 깨진 것. ("명확하지 않음"의 핵심 원인)

---

## C2) Memory usage summary (C2 memory on 검증)

C2(memory on)가 **on이기만 한 상태**인지, 실제로 retrieval/주입/사용이 되었는지 확인.

**Triptych 열**: memory_enabled, memory_retrieved_n, memory_used, memory_injected_chars, memory_ids_or_hash

**산출물**: `derived/diagnostics/memory_usage_summary.csv` (run당 1행)

| 지표 | 의미 |
|------|------|
| retrieved_n_p50 / retrieved_n_p90 | retrieved_n 분포 (중앙/90%ile) |
| memory_used_rate | used 비율 (프롬프트 삽입 등) |
| memory_used_but_changed_zero_rate | used인데 stage1_to_final_changed==0 비율 |
| memory_used_but_risk_resolution_zero_rate | used인데 risk_resolution==0 비율 |

**판정**:
- **retrieved_n가 대부분 0** → retriever 실패 / 인덱스 없음 / 키 불일치
- **retrieved_n>0인데 used=0** → 주입 경로 / 프롬프트 템플릿 누락
- **used=1인데 변화 없음** → 메모리가 설계상 영향 없는 정보이거나 stage2가 RuleB 등으로 고정 (정책 문제)

---

## 한 번에 실행 (B1+B2+B3+C2)

```bash
python scripts/structural_error_aggregator.py --input <scorecards.jsonl> --outdir <run_dir>/derived/metrics --diagnostics_dir <run_dir>/derived/diagnostics
```

- B1: sanity check 실패 시 즉시 exit 1
- B2: `diagnostics_dir/tuple_source_coverage.csv` 생성
- B3: `diagnostics_dir/inconsistency_flags.tsv` 생성
- C2: `diagnostics_dir/memory_usage_summary.csv` 생성

---

## 최종 정합성 점검 6개 (순서대로 보면 기능충돌/정합성 오류 대부분 포착)

패치(implicit/explicit 분리, triptych 확장, sanity check 등)까지 끝난 뒤 **최종 정합성 점검**은 아래 6개 산출물/체크로 종결.

| # | 체크/산출물 | 내용 |
|---|-------------|------|
| 1 | B1 sanity check | gold→gold F1=1, final→final F1=1 (실패 시 중단) |
| 2 | tuple_source_coverage.csv | final/stage1/gold fallback 비율 |
| 3 | inconsistency_flags.tsv | changed/guided 모순 행 |
| 4 | memory_usage_summary.csv | C2 retrieved/used/변화 비율 |
| 5 | gold_profile.csv | gold empty/long/brand/taxonomy 비율 (A1) |
| 6 | definition_mismatch_samples.tsv | matches=0 & gold>0 & final>0 샘플 + 태그 (A2) |

- **1–3**: aggregator `--diagnostics_dir` 한 번으로 생성.
- **4**: 동일 `--diagnostics_dir`로 생성.
- **5–6**: `scripts/gold_diagnostics.py --input <scorecards> --run_dir <run_dir>` 로 생성.
