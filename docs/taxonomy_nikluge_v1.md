# NIKLuge ABSA Taxonomy v1 (SSOT)

**SSOT**: `schemas/taxonomy.py` — 이 문서는 py를 기준으로 동기화됨.

목적: aspect_ref 추출 타당도(construct validity) 보강. 허용 집합 제한(제약) 수준까지만 적용. 정답 강요/룰 기반 매핑 금지.

---

## 1. Entity (개체) 정의 — 표53 요약

| Entity | 정의 |
|--------|------|
| **제품 전체** | 전체/총평/전반/전반적인 제품 |
| **본품** | 특정 장치/부품/본체/내용물(본품 하위 구성요소) |
| **패키지·구성품** | 패키지/구성품(브러쉬, 펌프 등) |
| **브랜드** | 브랜드 이미지/유명도/인지도/기업 |

---

## 2. Attribute (속성) 정의 — 표54 요약

| Attribute | 의미 |
|-----------|------|
| **일반** | 일반적 평가·총평 |
| **가격** | 가격·가성비 |
| **디자인** | 디자인·외형·스타일 |
| **품질** | 품질·성능·효과 |
| **편의성** | 편의성·사용성 |
| **다양성** | 다양성·라인업 |
| **인지도** | 인지도·유명도 |

---

## 3. 허용 조합 (Allowed Matrix)

행렬에서 O인 조합만 허용. aspect_ref는 `entity#attribute` 형식.

| Entity \ Attribute | 일반 | 가격 | 디자인 | 품질 | 편의성 | 다양성 | 인지도 |
|--------------------|------|------|--------|------|--------|--------|--------|
| 제품 전체 | O | O | O | O | O | O | O |
| 본품 | O | O | O | O | O | O | O |
| 패키지·구성품 | O | O | O | O | O | O | — |
| 브랜드 | O | O | O | O | — | — | O |

---

## 4. 허용 aspect_ref 목록 (ALLOWED_REFS)

`ALLOWED_REF_PAIRS`에서 `entity#attribute`로 생성. canonical 형식은 `·`(middle dot) 사용.

```
제품 전체#일반, 제품 전체#가격, 제품 전체#디자인, 제품 전체#품질, 제품 전체#편의성, 제품 전체#다양성, 제품 전체#인지도
본품#일반, 본품#가격, 본품#디자인, 본품#품질, 본품#편의성, 본품#다양성, 본품#인지도
패키지·구성품#일반, 패키지·구성품#가격, 패키지·구성품#디자인, 패키지·구성품#품질, 패키지·구성품#편의성, 패키지·구성품#다양성
브랜드#일반, 브랜드#가격, 브랜드#디자인, 브랜드#품질, 브랜드#인지도
```

**Gold 호환**: gold에 `패키지/구성품` 등 `/` 표기가 있어도 평가 시 `normalize_ref_canonical`로 `·`로 정규화하여 매칭. → [정규화 규칙](normalization_rules_and_locations.md#21b-normalize_ref_canonical-aspect_ref-canonical)

---

## 5. 코드 SSOT — `schemas/taxonomy.py`

| 항목 | 설명 |
|------|------|
| `ALLOWED_ENTITIES` | 허용 개체 집합 |
| `ALLOWED_ATTRIBUTES` | 허용 속성 집합 |
| `ALLOWED_REF_PAIRS` | 허용 (entity, attribute) 조합 |
| `ALLOWED_REFS` | 허용 aspect_ref 문자열 (`entity#attribute`) |
| `parse_ref(ref)` | `entity#attribute` → `(entity, attribute)` 파싱 |
| `is_valid_ref(ref)` | `ref.strip() in ALLOWED_REFS` |
| `get_entity(ref)` | entity 추출 |
| `get_attribute(ref)` | attribute 추출 |
| `normalize_entity(s)` | strip, `/`→`·`, 공백 축소 (eval 전용) |
| `normalize_ref_canonical(ref)` | aspect_ref canonical 정규화 (eval 전용) |

**정규화 관련**: aspect_ref 평가 시 적용 규칙 → [normalization_rules_and_locations.md](normalization_rules_and_locations.md) §2.1b `normalize_ref_canonical`

---

## 6. 예시

| 텍스트 | entity | attribute | aspect_ref |
|--------|--------|-----------|------------|
| "전반적으로 만족해요" | 제품 전체 | 일반 | 제품 전체#일반 |
| "가격 대비 좋아요" | 제품 전체 | 가격 | 제품 전체#가격 |
| "크림이 촉촉해요" | 본품 | 품질 | 본품#품질 |
| "브러쉬가 부드러워요" | 패키지·구성품 | 품질 | 패키지·구성품#품질 |
| "브랜드 유명도가 높아요" | 브랜드 | 인지도 | 브랜드#인지도 |
