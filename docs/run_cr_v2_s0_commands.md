# CR v2 S0 (Single-pass baseline) 실행 명령어

S0: Single-pass baseline for Δ_refinement = M0 − S0 (multi-agent refinement effect).

- **stage1_mode**: single_integrated (one agent, internal NEG/IMP/LIT lenses)
- **enable_review**: false (no Review A/B/C, no Arbiter)
- **enable_memory**: false (no retrieval)
- **conflict_flags_mode**: intra_output_only (structural conflict within single output)

---

## 1. S0 파이프라인 실행

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_MODEL="gpt-4.1-mini"

python scripts/run_pipeline.py --config experiments/configs/cr_v2_n601_s0_v1.yaml --run-id cr_v2_n601_s0_v1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3
```

---

## 2. S0 시드별 메트릭 머지 및 집계

```powershell
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n601_s0_v1__seed42_proposed,results/cr_v2_n601_s0_v1__seed123_proposed,results/cr_v2_n601_s0_v1__seed456_proposed --outdir results/cr_v2_n601_s0_v1_aggregated --metrics_profile paper_main
```

---

## 3. Δ_refinement 비교 (M0 vs S0)

S0와 M0 결과를 비교하여 multi-agent refinement 효과를 산출:

- **Δ_refinement** = M0 tuple_f1_s2 - S0 tuple_f1_s2 (또는 해당 메트릭)
- S0의 process metrics (fix/break/net_gain)는 stage2 미실행으로 NA/0 처리

---

## 체크리스트 (실행 전/후)

### A. 구조 정합성
- [ ] S0에서 review 단계 호출 0회
- [ ] S0에서 arbiter 호출 0회
- [ ] S0에서 final_tuples == final_tuples_pre_review
- [ ] S0에서 enable_memory=False이며 retrieval 호출 0회
- [ ] S0 outputs.jsonl에 필요한 키가 모두 존재

### B. conflict_flags 의미
- [ ] S0의 conflict_flags는 "intra-output structural conflict"로만 해석
- [ ] conflict_flags_mode="intra_output_only" 기록 확인

### C. 평가/집계
- [ ] aggregator 수정 없이 S0 포함 집계 성공
- [ ] paper_tables 생성 시 S0 포함 가능 여부 확인
