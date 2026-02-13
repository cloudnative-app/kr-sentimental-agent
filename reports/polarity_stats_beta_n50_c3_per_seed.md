# 라운드별 극성 통계 (시드별, 병합 없음)

**Runs**: beta_n50_c3__seed42_proposed, beta_n50_c3__seed123_proposed, beta_n50_c3__seed456_proposed

---

## 1. 라운드별 극성 집계 (시드별)

| Metric | seed42 | seed123 | seed456 |
|-------|--------|--------|--------|
| stage1_positive | 40 | 41 | 39 |
| stage1_negative | 6 | 6 | 4 |
| stage1_neutral | 67 | 70 | 75 |
| stage1_total | 113 | 117 | 118 |
| final_positive | 75 | 70 | 77 |
| final_negative | 12 | 15 | 17 |
| final_neutral | 26 | 30 | 25 |
| final_total | 113 | 115 | 119 |
| gold_positive | 51 | 51 | 51 |
| gold_negative | 2 | 2 | 2 |
| gold_neutral | 1 | 1 | 1 |
| gold_total | 54 | 54 | 54 |
| changed_rows | 47 | 46 | 53 |
| final_vs_gold_match | 19/54 | 13/54 | 15/54 |

---

## 2. 변경 유형별 요약 (시드별)

| stage1→final | seed42 | seed123 | seed456 |
|--------------|--------|--------|--------|
| neutral→negative | 6 | 9 | 12 |
| neutral→positive | 35 | 29 | 38 |
| neutral→— | 3 | 5 | 1 |
| —→negative | 0 | 0 | 1 |
| —→neutral | 3 | 3 | 1 |
