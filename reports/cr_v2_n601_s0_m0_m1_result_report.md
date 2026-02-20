# CR v2 n601 S0 | M0 | M1 결과 보고서

**실험 구성**: S0 (single-pass baseline), M0 (multi-agent, no memory), M1 (multi-agent, memory)  
**데이터**: beta_n601 valid (601 samples)  
**시드**: 42, 123, 456  
**생성일**: 2026-02-20

---

## 1. 실행 요약

| 단계 | 명령 | 결과 |
|------|------|------|
| S0 메트릭 집계 | `aggregate_seed_metrics.py --run_dirs results/cr_v2_n601_s0_v1__seed* --outdir results/cr_v2_n601_s0_v1_aggregated` | ✅ |
| Paper Table v2 생성 | `build_cr_v2_paper_table_v2.py --agg-s0 ... --agg-m0 ... --agg-m1 ...` | ✅ |

**산출물 경로**:
- S0 aggregated: `results/cr_v2_n601_s0_v1_aggregated/aggregated_mean_std.csv`
- Paper Table v2: `reports/cr_v2_n601_v1_paper_table_v2.md`

---

## 2. 핵심 결과: Δ_refinement (M0 − S0)

**Δ_refinement** = multi-agent refinement 효과 (Review + Arbiter 적용 시 S0 대비 개선)

| 메트릭 | S0 | M0 | Δ_refinement | 해석 |
|--------|-----|-----|--------------|------|
| **ATSA-F1** | 0.5824 ± 0.0022 | 0.6717 ± 0.0037 | **+0.0893** | Review+Arbiter로 표면 추출 F1 약 9%p 상승 |
| **ACSA-F1** | 0.4015 ± 0.0028 | 0.4932 ± 0.0057 | **+0.0917** | 스키마 정합 F1 약 9%p 상승 |
| **#attribute f1** | 0.5437 ± 0.0030 | 0.6417 ± 0.0083 | **+0.0980** | 속성 수준 F1 약 10%p 상승 |
| **Implicit Error Rate** | 0.2018 ± 0.0042 | 0.0078 ± 0.0016 | **-0.1940** | 암시적 오류율 대폭 감소 |
| **Fix Rate** | 0.0000 | 0.0694 ± 0.0059 | **+0.0694** | S0는 Stage2 미실행 → fix=0 |
| **Net Gain** | 0.0000 | 0.0444 ± 0.0039 | **+0.0444** | 순수 정제 이득 |

---

## 3. S0 vs M0 vs M1 3-way 비교

### 3.1 Surface Layer (ATSA-F1)
- **S0**: 0.5824 — 단일 통합 에이전트
- **M0**: 0.6717 — 3-facet merge + Review + Arbiter
- **M1**: 0.6719 — M0 + episodic memory
- **Δ_refinement (M0−S0)**: +0.0893
- **Δ (M1−M0)**: +0.0002 (거의 동일)

### 3.2 Schema Layer
- **Polarity Conflict Rate**: S0(0.0155) < M0(0.0471) — S0는 intra-output만, M0는 inter-facet conflict 포함
- **Ref Fill Rate**: S0(0.9250) > M0(0.7441) — S0 단일 에이전트가 ref 채움에 더 적극적

### 3.3 Process Layer (S0 = 0)
- S0는 Stage2 미실행 → fix_rate, break_rate, net_gain 모두 0
- M0/M1만 Correction Stability 메트릭 의미 있음

### 3.4 Stochastic Stability
- **Seed variance**: S0(0.0028) < M0(0.0057) < M1(0.0138)
- **aar_majority_rate**: S0(1.0) — 단일 출력이라 항상 일치

---

## 4. 결론

1. **Δ_refinement 유의**: M0 − S0 = +0.0893 (ATSA-F1), +0.0917 (ACSA-F1) — multi-agent refinement 효과가 뚜렷함.
2. **S0 한계**: 단일 에이전트는 implicit error rate가 높고(20.2%), 3-facet merge+review로 0.78%까지 감소.
3. **M1 vs M0**: n601 기준 Δ (M1−M0)는 미미 (+0.0002 ATSA-F1). 메모리 효과는 본 실험 규모에서 제한적.

---

## 5. 산출물 체크리스트

- [x] S0 페이퍼 메트릭 계산 (structural_error_aggregator → aggregate_seed_metrics)
- [x] CR v2 Paper Table v2 생성 (S0 | M0 | M1 | Δ_refinement | Δ)
- [x] 결과 보고서 작성
