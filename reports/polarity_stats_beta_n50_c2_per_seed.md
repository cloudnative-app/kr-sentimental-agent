# 라운드별 극성 통계 (시드별, 병합 없음)

**Runs**: beta_n50_c2__seed42_proposed, beta_n50_c2__seed123_proposed, beta_n50_c2__seed456_proposed

---

## 1. 라운드별 극성 집계 (시드별)

| Metric | seed42 | seed123 | seed456 |
|-------|--------|--------|--------|
| stage1_positive | 37 | 45 | 42 |
| stage1_negative | 4 | 4 | 5 |
| stage1_neutral | 80 | 63 | 67 |
| stage1_total | 121 | 112 | 114 |
| final_positive | 75 | 79 | 77 |
| final_negative | 14 | 13 | 14 |
| final_neutral | 30 | 21 | 25 |
| final_total | 119 | 113 | 116 |
| gold_positive | 51 | 51 | 51 |
| gold_negative | 2 | 2 | 2 |
| gold_neutral | 1 | 1 | 1 |
| gold_total | 54 | 54 | 54 |
| changed_rows | 56 | 47 | 48 |
| final_vs_gold_match | 15/54 | 17/54 | 16/54 |

---

## 2. 변경 유형별 요약 (시드별)

| stage1→final | seed42 | seed123 | seed456 |
|--------------|--------|--------|--------|
| neutral→negative | 10 | 8 | 9 |
| neutral→positive | 38 | 34 | 35 |
| neutral→— | 5 | 2 | 1 |
| —→negative | 0 | 1 | 0 |
| —→neutral | 3 | 2 | 3 |
