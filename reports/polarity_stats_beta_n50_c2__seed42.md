# 라운드별 극성 통계 및 정답 극성 집계

**Source**: results\beta_n50_c2__seed42_proposed\derived\tables\triptych_table.tsv  |  **n_samples**: 50

---

## 1. 라운드별 극성 집계 (튜플 수)

| Round | positive | negative | neutral | mixed | total |
|-------|----------|----------|---------|-------|-------|
| stage1 | 37 | 4 | 80 | 0 | 121 |
| final | 75 | 14 | 30 | 0 | 119 |
| gold | 51 | 2 | 1 | 0 | 54 |

---

## 2. stage1→final 달라진 것

### 변경 유형별 요약

| stage1→final | count |
|--------------|-------|
| neutral→positive | 38 |
| neutral→negative | 10 |
| neutral→— | 5 |
| —→neutral | 3 |

### 상세 (stage1≠final)

| text_id | aspect | stage1 | final | gold | 변경유형 |
|---------|--------|--------|-------|------|----------|
| nikluge-sa-2022-train-00922 | 130cm | neutral | — | — | neutral→— |
| nikluge-sa-2022-train-00922 | 13호 | neutral | — | — | neutral→— |
| nikluge-sa-2022-train-00922 | 24kg | neutral | — | — | neutral→— |
| nikluge-sa-2022-train-00922 | 딸 | neutral | — | — | neutral→— |
| nikluge-sa-2022-train-00536 | 고가의 캐비아 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00536 | 마스크팩 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-00536 | 저렴한 가격 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00536 | 피부 단백질 구조 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00969 | #토끼인형 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00969 | #프릴장식 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01305 | (implicit) | — | neutral | — | —→neutral |
| nikluge-sa-2022-train-01305 | 기본적인 기능 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01305 | 냉동실full 드로어 기능들 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01305 | 장점들 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01356 | 로지사틴크림 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-01356 | 피부 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01797 | 너무 좋아 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-00643 | 99.9% 자연유래의 착한 성분들 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-00028 | 각진 인생 | neutral | positive | negative | neutral→positive |
| nikluge-sa-2022-train-00028 | 사각 | neutral | positive | negative | neutral→positive |
| nikluge-sa-2022-train-00028 | 펄 같은 거 | neutral | negative | negative | neutral→negative |
| nikluge-sa-2022-train-00028 | 폰 | neutral | positive | negative | neutral→positive |
| nikluge-sa-2022-train-01621 | 강황 발효 에너지 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01621 | 모발 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01621 | 암라성분 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-01621 | 인삼 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01621 | 헤어 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00189 | 손씻고 땡기지 않아서 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00189 | 아이들 손씻길때 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00189 | 작은사이즈의 #스틱비누 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-00237 | 프라젠트라 벨리크림 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-00192 | 대용량 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-01875 | (implicit) | — | neutral | — | —→neutral |
| nikluge-sa-2022-train-01128 | 선케어 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-01804 | 피부 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-00986 | 엄마 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-01751 | 로하셀글로시립스탬프 | neutral | — | positive | neutral→— |
| nikluge-sa-2022-train-01235 | 냄새 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-01235 | 위생적 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00107 | 리시버 | neutral | negative | neutral | neutral→negative |
| nikluge-sa-2022-train-00107 | 불만사항 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-02608 | 피부 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-01800 | 일하다 보면 덥고 답답했는데 | neutral | negative | — | neutral→negative |
| nikluge-sa-2022-train-01800 | 컴퓨터 하는곳 | neutral | negative | — | neutral→negative |
| nikluge-sa-2022-train-02562 | (implicit) | — | neutral | positive | —→neutral |
| nikluge-sa-2022-train-02562 | 스킨케어 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-02562 | 피부뿌리부터힘있게 | neutral | positive | positive | neutral→positive |
| nikluge-sa-2022-train-02562 | 화장품 | neutral | negative | positive | neutral→negative |
| nikluge-sa-2022-train-02162 | #아베다 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00336 | 기분 | neutral | negative | — | neutral→negative |
| nikluge-sa-2022-train-00336 | 몸 | neutral | negative | — | neutral→negative |
| nikluge-sa-2022-train-00336 | 온가족 | neutral | positive | — | neutral→positive |
| nikluge-sa-2022-train-00336 | 입 | neutral | negative | — | neutral→negative |
| nikluge-sa-2022-train-00336 | 치약들 | neutral | negative | — | neutral→negative |
| nikluge-sa-2022-train-00336 | 코 | neutral | negative | — | neutral→negative |
| nikluge-sa-2022-train-01121 | 그것 | neutral | positive | positive | neutral→positive |

---

## 3. final vs gold (정답 일치)

*gold와 match 가능한 aspect 수: 54, 일치: 15*

| text_id | aspect | final_polarity | gold_polarity | match |
|---------|--------|----------------|---------------|-------|
| nikluge-sa-2022-train-00987 | 아이립밤 | positive | positive | Y |
| nikluge-sa-2022-train-00922 | 사이즈 | positive | positive | Y |
| nikluge-sa-2022-train-00077 | (implicit) | — | negative | N |
| nikluge-sa-2022-train-00536 | 마스크팩 | positive | positive | Y |
| nikluge-sa-2022-train-00969 | 프릴장식 | — | positive | N |
| nikluge-sa-2022-train-01877 | 올인원크림 | — | positive | N |
| nikluge-sa-2022-train-02944 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01305 | 24시간 자동정온, 도어쿨링, 신선야채실, 멀티수납함, 냉동실full 드로어 기능 | — | positive | N |
| nikluge-sa-2022-train-01305 | 냉장고가 갖고 있어야 할 기본적인 기능 | — | positive | N |
| nikluge-sa-2022-train-01356 | 로지사틴크림 | positive | positive | Y |
| nikluge-sa-2022-train-00433 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01287 | 에센스 | neutral | positive | N |
| nikluge-sa-2022-train-02175 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01797 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00644 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00644 | 패키지 | positive | positive | Y |
| nikluge-sa-2022-train-00643 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00028 | (implicit) | — | negative | N |
| nikluge-sa-2022-train-01621 | 암라성분 | positive | positive | Y |
| nikluge-sa-2022-train-01621 | 인삼과 강황 발효 에너지 | — | positive | N |
| nikluge-sa-2022-train-00189 | 작은사이즈의 #스틱비누 | positive | positive | Y |
| nikluge-sa-2022-train-00237 | 프라젠트라 벨리크림 | positive | positive | Y |
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
| nikluge-sa-2022-train-01748 | 리파캐럿 | — | positive | N |
| nikluge-sa-2022-train-00472 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-02941 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-00986 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01751 | 로하셀글로시립스탬프 | — | positive | N |
| nikluge-sa-2022-train-01235 | 마이스 음식물쓰레기봉투 | neutral | positive | N |
| nikluge-sa-2022-train-00107 | 리시버 | negative | neutral | N |
| nikluge-sa-2022-train-02608 | (implicit) | — | positive | N |
| nikluge-sa-2022-train-01800 | 탁상용선풍기 | positive | positive | Y |
| nikluge-sa-2022-train-02562 | (implicit) | neutral | positive | N |
| nikluge-sa-2022-train-02162 | 아베다 | — | positive | N |
| nikluge-sa-2022-train-00320 | 아토클리닉 #유아세안제 | — | positive | N |
| ... | (54 rows total) | | | |
