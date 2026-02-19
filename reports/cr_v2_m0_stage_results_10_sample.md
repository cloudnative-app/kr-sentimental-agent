# CR v2 M0 스테이지별 결과 샘플 (10건)

튜플 = (aspect_ref, aspect_term, polarity). pairs = (aspect_term, polarity) — P0 평가 키.

## 1. nikluge-sa-2022-train-00987

**input_text**: 엄마따라하기를 좋아하는 아이들에게 안성맞춤 #아이립밤

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('제품 전체#일반','아이립밤','positive') |
| **s1_tuples** (ref, term, pol) | ('','아이립밤','positive') |
| **s1_pairs** (term, pol) | ('아이립밤','positive') |
| **final_tuples** (ref, term, pol) | ('아이립밤','아이립밤','positive') |
| **final_pairs** (term, pol) | ('아이립밤','positive') |
| **stage_delta.changed** | False |

## 2. nikluge-sa-2022-train-00922

**input_text**: 130cm/24kg 딸 13호 입었는데 사이즈는 좀 넉넉하게 나온거 같아요~

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('패키지/구성품#편의성','사이즈','positive') |
| **s1_tuples** (ref, term, pol) | ('','사이즈','positive') |
| **s1_pairs** (term, pol) | ('사이즈','positive') |
| **final_tuples** (ref, term, pol) | ('사이즈','사이즈','positive') |
| **final_pairs** (term, pol) | ('사이즈','positive') |
| **stage_delta.changed** | False |

## 3. nikluge-sa-2022-train-00077

**input_text**: 왜 일류 기업이라는 게 아이리버나 다른 중소업체보다 못하지?

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('브랜드#품질','','negative') |
| **s1_tuples** (ref, term, pol) | ('','quality or performance','negative'); ('','일류 기업','negative') |
| **s1_pairs** (term, pol) | ('quality or performance','negative'); ('일류 기업','negative') |
| **final_tuples** (ref, term, pol) | ('quality or performance','quality or performance','negative'); ('일류 기업','일류 기업','negative') |
| **final_pairs** (term, pol) | ('quality or performance','negative'); ('일류 기업','negative') |
| **stage_delta.changed** | False |

## 4. nikluge-sa-2022-train-00536

**input_text**: 피부 단백질 구조와 가장 흡사한 고가의 캐비아를 저렴한 가격에 마스크팩으로 피부관리를 할 수 있으니 #대박템 !!💜

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('제품 전체#가격','마스크팩','positive') |
| **s1_tuples** (ref, term, pol) | ('','가격','positive'); ('','마스크팩','positive'); ('','성분 품질','positive'); ('','캐비아','positive'); ('','피부 단백질 구조','positive'); ('','피부관리','positive'); ('','피부관리 효과','positive') |
| **s1_pairs** (term, pol) | ('가격','positive'); ('마스크팩','positive'); ('성분 품질','positive'); ('캐비아','positive'); ('피부 단백질 구조','positive'); ('피부관리','positive'); ('피부관리 효과','positive') |
| **final_tuples** (ref, term, pol) | ('가격','가격','positive'); ('마스크팩','마스크팩','positive'); ('성분 품질','성분 품질','positive'); ('캐비아','캐비아','positive'); ('피부 단백질 구조','피부 단백질 구조','positive'); ('피부관리','피부관리','positive'); ('피부관리 효과','피부관리 효과','positive') |
| **final_pairs** (term, pol) | ('가격','positive'); ('마스크팩','positive'); ('성분 품질','positive'); ('캐비아','positive'); ('피부 단백질 구조','positive'); ('피부관리','positive'); ('피부관리 효과','positive') |
| **stage_delta.changed** | False |

## 5. nikluge-sa-2022-train-00969

**input_text**: 아담한사이즈 그리고 #프릴장식 까지 넘 사랑스런 #토끼인형

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('제품 전체#디자인','프릴장식','positive') |
| **s1_tuples** (ref, term, pol) | ('','frill decoration','positive'); ('','overall appearance','positive'); ('','size','positive'); ('','아담한사이즈','positive'); ('','토끼인형','positive'); ('','프릴장식','positive') |
| **s1_pairs** (term, pol) | ('frill decoration','positive'); ('overall appearance','positive'); ('size','positive'); ('아담한사이즈','positive'); ('토끼인형','positive'); ('프릴장식','positive') |
| **final_tuples** (ref, term, pol) | ('frill decoration','frill decoration','positive'); ('overall appearance','overall appearance','positive'); ('size','size','positive'); ('아담한사이즈','아담한사이즈','positive'); ('토끼인형','토끼인형','positive'); ('프릴장식','프릴장식','positive') |
| **final_pairs** (term, pol) | ('frill decoration','positive'); ('overall appearance','positive'); ('size','positive'); ('아담한사이즈','positive'); ('토끼인형','positive'); ('프릴장식','positive') |
| **stage_delta.changed** | False |

## 6. nikluge-sa-2022-train-01877

**input_text**: 간편하게 #올인원크림 으로 관리하는 여자

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('본품#편의성','올인원크림','positive') |
| **s1_tuples** (ref, term, pol) | ('','skincare convenience','positive'); ('','올인원크림','positive') |
| **s1_pairs** (term, pol) | ('skincare convenience','positive'); ('올인원크림','positive') |
| **final_tuples** (ref, term, pol) | ('skincare convenience','skincare convenience','positive'); ('올인원크림','올인원크림','positive') |
| **final_pairs** (term, pol) | ('skincare convenience','positive'); ('올인원크림','positive') |
| **stage_delta.changed** | False |

## 7. nikluge-sa-2022-train-02944

**input_text**: 역시 바르고 난 직후에는 이렇게 맨들거리지만 금방 바로 흡수되어 버린답니다.

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('본품#품질','','positive') |
| **s1_tuples** (ref, term, pol) | ('','absorption','positive'); ('','texture immediately after application','neutral'); ('','바르고 난 직후','neutral'); ('','흡수','positive') |
| **s1_pairs** (term, pol) | ('absorption','positive'); ('texture immediately after application','neutral'); ('바르고 난 직후','neutral'); ('흡수','positive') |
| **final_tuples** (ref, term, pol) | ('absorption','absorption','positive'); ('texture immediately after application','texture immediately after application','neutral'); ('바르고 난 직후','바르고 난 직후','neutral'); ('흡수','흡수','positive') |
| **final_pairs** (term, pol) | ('absorption','positive'); ('texture immediately after application','neutral'); ('바르고 난 직후','neutral'); ('흡수','positive') |
| **stage_delta.changed** | False |

## 8. nikluge-sa-2022-train-01305

**input_text**: 얼음정수기 기능 이외에도 냉장고가 갖고 있어야 할 기본적인 기능은 물론이고, 24시간 자동정온, 도어쿨링, 신선야채실, 멀티수납함, 냉동실Full 드로어 기능들은 #냉장고추천 하기에 충분한 매력덩어리들이라서, 사용하면서도 늘 감사했던 장점들이랍니다.

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('본품#일반','24시간 자동정온, 도어쿨링, 신선야채실, 멀티수납함, 냉동실full 드로어 기능','positive'); ('본품#일반','냉장고가 갖고 있어야 할 기본적인 기능','positive') |
| **s1_tuples** (ref, term, pol) | ('','24시간 자동정온','positive'); ('','냉동실full 드로어 기능','positive'); ('','냉장고 기능','positive'); ('','냉장고 기본 기능','positive'); ('','도어쿨링','positive'); ('','멀티수납함','positive'); ('','사용 경험','positive'); ('','사용 만족도','positive'); ('','신선야채실','positive'); ('','얼음정수기 기능','positive'); ('24시간 자동정온','온도 유지 기능','positive'); ('냉동실full 드로어 기능','냉동실 수납 방식','positive'); ('도어쿨링','도어 쿨링 기능','positive'); ('멀티수납함','수납 공간','positive'); ('신선야채실','야채 보관 공간','positive') |
| **s1_pairs** (term, pol) | ('24시간 자동정온','positive'); ('냉동실 수납 방식','positive'); ('냉동실full 드로어 기능','positive'); ('냉장고 기능','positive'); ('냉장고 기본 기능','positive'); ('도어 쿨링 기능','positive'); ('도어쿨링','positive'); ('멀티수납함','positive'); ('사용 경험','positive'); ('사용 만족도','positive'); ('수납 공간','positive'); ('신선야채실','positive'); ('야채 보관 공간','positive'); ('얼음정수기 기능','positive'); ('온도 유지 기능','positive') |
| **final_tuples** (ref, term, pol) | ('24시간 자동정온','24시간 자동정온','positive'); ('냉동실 수납 방식','냉동실 수납 방식','positive'); ('냉동실full 드로어 기능','냉동실full 드로어 기능','positive'); ('냉장고 기능','냉장고 기능','positive'); ('냉장고 기본 기능','냉장고 기본 기능','positive'); ('도어 쿨링 기능','도어 쿨링 기능','positive'); ('도어쿨링','도어쿨링','positive'); ('멀티수납함','멀티수납함','positive'); ('사용 경험','사용 경험','positive'); ('사용 만족도','사용 만족도','positive'); ('수납 공간','수납 공간','positive'); ('신선야채실','신선야채실','positive'); ('야채 보관 공간','야채 보관 공간','positive'); ('얼음정수기 기능','얼음정수기 기능','positive'); ('온도 유지 기능','온도 유지 기능','positive') |
| **final_pairs** (term, pol) | ('24시간 자동정온','positive'); ('냉동실 수납 방식','positive'); ('냉동실full 드로어 기능','positive'); ('냉장고 기능','positive'); ('냉장고 기본 기능','positive'); ('도어 쿨링 기능','positive'); ('도어쿨링','positive'); ('멀티수납함','positive'); ('사용 경험','positive'); ('사용 만족도','positive'); ('수납 공간','positive'); ('신선야채실','positive'); ('야채 보관 공간','positive'); ('얼음정수기 기능','positive'); ('온도 유지 기능','positive') |
| **stage_delta.changed** | False |

## 9. nikluge-sa-2022-train-01356

**input_text**: 그만큼 피부결이 중요한데 로지사틴크림은 소량만 발라도 메이크업이 쫀쫀해지고 밤에 바르고 자면 다음날 아침 피부가 깐달걀처럼 매끈하답니다

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('본품#품질','로지사틴크림','positive') |
| **s1_tuples** (ref, term, pol) | ('','로지사틴크림','positive'); ('','피부','positive'); ('','피부 상태','positive'); ('','피부결','positive'); ('메이크업','메이크업 지속력','positive') |
| **s1_pairs** (term, pol) | ('로지사틴크림','positive'); ('메이크업 지속력','positive'); ('피부','positive'); ('피부 상태','positive'); ('피부결','positive') |
| **final_tuples** (ref, term, pol) | ('로지사틴크림','로지사틴크림','positive'); ('메이크업 지속력','메이크업 지속력','positive'); ('피부','피부','positive'); ('피부 상태','피부 상태','positive'); ('피부결','피부결','positive') |
| **final_pairs** (term, pol) | ('로지사틴크림','positive'); ('메이크업 지속력','positive'); ('피부','positive'); ('피부 상태','positive'); ('피부결','positive') |
| **stage_delta.changed** | False |

## 10. nikluge-sa-2022-train-00433

**input_text**: 사용감 좋아요

| 구분 | 내용 |
|------|------|
| **gold** (ref, term, pol) | ('본품#품질','','positive') |
| **s1_tuples** (ref, term, pol) | ('','사용감','positive') |
| **s1_pairs** (term, pol) | ('사용감','positive') |
| **final_tuples** (ref, term, pol) | ('사용감','사용감','positive') |
| **final_pairs** (term, pol) | ('사용감','positive') |
| **stage_delta.changed** | False |
