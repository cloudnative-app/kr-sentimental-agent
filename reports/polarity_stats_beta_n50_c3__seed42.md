# 라운드별 극성 통계 및 정답 극성 집계

**Source**: results\beta_n50_c3__seed42_proposed\derived\tables\triptych_table.tsv  |  **n_samples**: 50

---

## 1. 라운드별 극성 집계 (튜플 수)

| Round | positive | negative | neutral | mixed | total |
|-------|----------|----------|---------|-------|-------|
| stage1 | 40 | 6 | 67 | 0 | 113 |
| final | 75 | 12 | 26 | 0 | 113 |
| gold | 51 | 2 | 1 | 0 | 54 |

---

## 2. stage1→final 달라진 것

| text_id | aspect | stage1_polarity | final_polarity | gold_polarity | changed |
|---------|--------|-----------------|----------------|---------------|---------|
| nikluge-sa-2022-train-00536 | 고가의 캐비아 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00536 | 마스크팩 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-00536 | 저렴한 가격 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00536 | 피부 단백질 구조 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00536 | 피부관리 | neutral | positive | — | Y |
| nikluge-sa-2022-train-01305 | (implicit) | — | neutral | — | Y |
| nikluge-sa-2022-train-01305 | 기본적인 기능 | neutral | positive | — | Y |
| nikluge-sa-2022-train-01305 | 냉동실full 드로어 기능들 | neutral | positive | — | Y |
| nikluge-sa-2022-train-01305 | 장점들 | neutral | positive | — | Y |
| nikluge-sa-2022-train-01356 | 로지사틴크림 | neutral | — | positive | Y |
| nikluge-sa-2022-train-01356 | 피부 | neutral | — | — | Y |
| nikluge-sa-2022-train-01797 | 지인들 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-00643 | 99.9% 자연유래의 착한 성분들 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-00643 | 여성을 위한 제품 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-00028 | 각진 인생 | neutral | positive | negative | Y |
| nikluge-sa-2022-train-00028 | 사각 | neutral | positive | negative | Y |
| nikluge-sa-2022-train-00028 | 펄 같은 거 | neutral | negative | negative | Y |
| nikluge-sa-2022-train-00028 | 폰 | neutral | positive | negative | Y |
| nikluge-sa-2022-train-01621 | 모발 | neutral | positive | — | Y |
| nikluge-sa-2022-train-01621 | 암라성분 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-01621 | 인삼과 강황 발효 에너지 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-01621 | 헤어 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00189 | 손씻고 땡기지 않아서 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00189 | 아이들 손씻길때 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00189 | 작은사이즈의 #스틱비누 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-00258 | #예쁜치약 | neutral | positive | — | Y |
| nikluge-sa-2022-train-01875 | (implicit) | — | neutral | — | Y |
| nikluge-sa-2022-train-01128 | 선케어 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-01804 | 피부 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-00472 | 피부 관리 | neutral | — | positive | Y |
| nikluge-sa-2022-train-01751 | 로하셀글로시립스탬프 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-01235 | 냄새 | neutral | positive | — | Y |
| nikluge-sa-2022-train-01235 | 마이스 음식물쓰레기봉투 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-01235 | 음식물쓰레기통 | neutral | positive | — | Y |
| nikluge-sa-2022-train-02608 | 느낌 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-02608 | 피부 | neutral | positive | positive | Y |
| nikluge-sa-2022-train-01800 | 컴퓨터 하는곳 | neutral | negative | — | Y |
| nikluge-sa-2022-train-02562 | (implicit) | — | neutral | positive | Y |
| nikluge-sa-2022-train-02162 | #아베다 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00320 | #버블폼 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00320 | #아토클리닉 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00320 | #유아세안제 | neutral | positive | — | Y |
| nikluge-sa-2022-train-00336 | 몸 | neutral | negative | — | Y |
| nikluge-sa-2022-train-00336 | 입 | neutral | negative | — | Y |
| nikluge-sa-2022-train-00336 | 치약들 | neutral | negative | — | Y |
| nikluge-sa-2022-train-00336 | 코 | neutral | negative | — | Y |
| nikluge-sa-2022-train-01121 | 그것 | neutral | positive | positive | Y |

---

## 3. final vs gold (정답 일치)

*gold와 match 가능한 aspect 수: 54, 일치: 19*

| text_id | aspect | final_polarity | gold_polarity | match |
|---------|--------|----------------|---------------|-------|
| nikluge-sa-2022-train-00987 | 아이립밤 | positive | positive | Y |
| nikluge-sa-2022-train-00922 | 사이즈 | positive | positive | Y |
| nikluge-sa-2022-train-00077 | (implicit) | — | negative | N |
| nikluge-sa-2022-train-00536 | 마스크팩 | positive | positive | Y |
| nikluge-sa-2022-train-00969 | 프릴장식 | positive | positive | Y |
| nikluge-sa-2022-train-01877 | 올인원크림 | — | positive | N |
| nikluge-sa-2022-train-02944 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01305 | 24시간 자동정온, 도어쿨링, 신선야채실, 멀티수납함, 냉동실full 드로어 기능 | — | positive | N |
| nikluge-sa-2022-train-01305 | 냉장고가 갖고 있어야 할 기본적인 기능 | — | positive | N |
| nikluge-sa-2022-train-01356 | 로지사틴크림 | — | positive | N |
| nikluge-sa-2022-train-00433 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01287 | 에센스 | neutral | positive | N |
| nikluge-sa-2022-train-02175 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01797 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00644 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00644 | 패키지 | positive | positive | Y |
| nikluge-sa-2022-train-00643 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00028 | (implicit) | — | negative | N |
| nikluge-sa-2022-train-01621 | 암라성분 | positive | positive | Y |
| nikluge-sa-2022-train-01621 | 인삼과 강황 발효 에너지 | positive | positive | Y |
| nikluge-sa-2022-train-00189 | 작은사이즈의 #스틱비누 | positive | positive | Y |
| nikluge-sa-2022-train-00237 | 프라젠트라 벨리크림 | neutral | positive | N |
| nikluge-sa-2022-train-01689 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01241 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00817 | 2 in 1 | positive | positive | Y |
| nikluge-sa-2022-train-00192 | 대용량 | positive | positive | Y |
| nikluge-sa-2022-train-01112 | 사이즈 | positive | positive | Y |
| nikluge-sa-2022-train-02964 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00258 | 치약 | — | positive | N |
| nikluge-sa-2022-train-01801 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00726 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01961 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01875 | 리뉴본달팽이크림 | — | positive | N |
| nikluge-sa-2022-train-01638 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01128 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01128 | 선케어 | positive | positive | Y |
| nikluge-sa-2022-train-01804 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-02328 | 롱 귀걸이 | positive | positive | Y |
| nikluge-sa-2022-train-01748 | 리파캐럿 | positive | positive | Y |
| nikluge-sa-2022-train-00472 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-02941 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00986 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01751 | 로하셀글로시립스탬프 | positive | positive | Y |
| nikluge-sa-2022-train-01235 | 마이스 음식물쓰레기봉투 | positive | positive | Y |
| nikluge-sa-2022-train-00107 | 리시버 | neutral | neutral | Y |
| nikluge-sa-2022-train-02608 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01800 | 탁상용선풍기 | positive | positive | Y |
| nikluge-sa-2022-train-02562 | (implicit) | neutral | positive | N |
| nikluge-sa-2022-train-02162 | 아베다 | — | positive | N |
| nikluge-sa-2022-train-00320 | 아토클리닉 #유아세안제 | — | positive | N |
| ... | (54 rows total) | | | |
