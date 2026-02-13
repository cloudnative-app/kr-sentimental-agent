# 라운드별 극성 통계 (시드별, 병합 없음)

**Runs**: beta_n50_c1__seed42_proposed, beta_n50_c1__seed123_proposed, beta_n50_c1__seed456_proposed

---

## 1. 라운드별 극성 집계 (시드별)

| Metric | seed42 | seed123 | seed456 |
|-------|--------|--------|--------|
| stage1_positive | 40 | 42 | 44 |
| stage1_negative | 5 | 5 | 6 |
| stage1_neutral | 71 | 67 | 69 |
| stage1_total | 116 | 114 | 119 |
| final_positive | 78 | 81 | 82 |
| final_negative | 13 | 11 | 16 |
| final_neutral | 28 | 25 | 24 |
| final_total | 119 | 117 | 122 |
| gold_positive | 51 | 51 | 51 |
| gold_negative | 2 | 2 | 2 |
| gold_neutral | 1 | 1 | 1 |
| gold_total | 54 | 54 | 54 |
| changed_rows | 51 | 48 | 51 |
| final_vs_gold_match | 17/54 | 15/54 | 18/54 |

---

## 2. 변경 유형별 요약 (시드별)

| stage1→final | seed42 | seed123 | seed456 |
|--------------|--------|--------|--------|
| neutral→negative | 8 | 6 | 10 |
| neutral→positive | 39 | 39 | 38 |
| positive→neutral | 1 | 0 | 0 |
| —→neutral | 3 | 3 | 3 |
