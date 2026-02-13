# Gold 진단 (A1/A2)

## A1) Gold 유형 분해 통계 (필수)

**inputs.gold_tuples** 기준으로 run 단위 비율을 계산해 CSV로 출력.

**산출물**: `derived/diagnostics/gold_profile.csv`

| 컬럼 | 의미 |
|------|------|
| run_id | run 디렉터리명 |
| n_gold_pairs | gold pair 총 개수 (샘플당 여러 개 가능) |
| gold_empty_aspect_rate | aspect_term=="" 비율 |
| gold_long_term_rate | aspect_term 길이 ≥ k(기본 15자) 비율 |
| gold_brand_like_rate | 해시태그/영문+숫자/모델명 패턴 비율 (정규식) |
| gold_taxonomy_like_rate | "본품#품질" 형태 패턴 비율 (정규식) |

**실행**: `python scripts/gold_diagnostics.py --input <scorecards.jsonl> --run_dir <run_dir>`

---

## A2) 정의 불일치 TOP 샘플 자동 추출 (필수)

Triptych에서 다음 조건의 샘플을 수집:

- `matches_final_vs_gold == 0` AND `gold_n_pairs > 0` AND `final_n_pairs > 0`

각 행에 gold_pairs가 **(a) empty**, **(b) 긴 문자열**, **(c) taxonomy 패턴** 중 해당하는지 태깅.

**산출물**: `derived/diagnostics/definition_mismatch_samples.tsv` (최소 50개 권장; 있는 만큼 출력)

| 태그 | 의미 |
|------|------|
| tag_empty_aspect | gold에 빈 aspect(implicit) 포함 |
| tag_long_term | gold에 길이 ≥ k인 term 포함 |
| tag_taxonomy_like | gold에 "word#word" 형태 포함 |
| tag_summary | "empty", "long", "taxonomy" 조합 (;) |

---

## 판정 기준 (바로 결론)

| 조건 | 결론 |
|------|------|
| **gold_empty_aspect_rate**가 높으면 | F1에서 implicit 분리 필수 |
| **gold_long_term_rate**가 높으면 | exact-match F1은 구조적으로 낮음 → gold 정제 또는 부분일치 보조 지표 |
| **taxonomy_like**가 높고 pred가 span이면 | 매핑 없으면 F1 무의미 / 앞선 수정과 기능적 중복이 되는 수정은 생략 가능 |
