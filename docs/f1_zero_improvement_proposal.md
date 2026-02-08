# F1 제로 현상 개선 방안 제안

`f1_zero_diagnosis.md`와 사용자 기준을 바탕으로 한 개선 방안입니다. **아직 수정 작업은 진행하지 않으며**, 제안만 정리합니다.

---

## 1. 평가 정의 명확화

### 1.1 현재 상태
- 채점은 **(aspect_term, polarity)** 쌍으로만 수행하고, aspect_ref는 F1에서 무시됨.
- 다만 골드/예측 모두 **튜플 구조**는 `(aspect_ref, aspect_term, polarity)` 3항으로 유지되고, 골드 정규화 시 `aspect_term`이 비어 있으면 **aspect_ref로 채우는** 동작 때문에, 골드가 택소노미 문자열로 바뀌어 예측(span)과 불일치함.

### 1.2 제안
- **평가 정의를 문서·코드에 명시**: tuple set 채점에 사용하는 평가 기준은 **aspect_term**(문장 내 표면형)과 polarity뿐이며, **aspect_ref는 채점에 사용하지 않음**.
- **답지 및 출력물의 튜플 구성**:
  - 채점에 필요한 최소 필드: **aspect_term**, **polarity**.
  - aspect_ref는 (택소노미/참조용으로) 선택적으로 유지할 수 있으나, **채점 로직에서는 사용하지 않음**.
- 수정 포인트:
  - `docs/absa_tuple_eval.md`, `docs/f1_zero_diagnosis.md`: “채점 기준 = (aspect_term, polarity), aspect_ref 미사용” 명시.
  - `metrics/eval_tuple.py` docstring 및 주석: 동일 정의 반영.
  - 골드/예측에서 aspect_term이 비어 있을 때 **aspect_ref로 채우지 않도록** 정규화 로직 변경(아래 3번과 연동).

---

## 2. 매칭 기준: 골드에 span과 텍스트 모두 포함

### 2.1 현재 상태
- 골드 `valid.gold.jsonl`은 `aspect_ref`, `aspect_term`, `polarity`만 있음. **span(start, end)** 는 없음.
- 매칭은 현재 **텍스트(aspect_term)** 기준만 사용.

### 2.2 제안
- **골드 포맷**: 골드가 **span과 텍스트를 모두 포함**하도록 정의.
  - 예: `aspect_term`(텍스트), 선택적으로 `span: { start, end }` (문장 내 문자 구간).
  - 원본 데이터에 span이 있으면 골드 생성 스크립트(`make_mini*.py` 등)에서 `span`을 넣어 저장.
- **매칭 기준**:
  - **1차**: (normalize(aspect_term), normalize(polarity))로 매칭 (현행 유지).
  - **선택/검증용**: 동일 uid에서 골드에 span이 있으면, 예측 측에도 span 또는 동일 텍스트가 있을 때 보조 검증에 활용 가능. (F1 수치는 텍스트 기준만 사용해도 됨.)
- 수정 포인트:
  - 골드 스키마/문서: `gold_tuples` 항목에 `span` 선택 필드 명시.
  - `scripts/make_mini*.py`, `make_mini2_dataset.py`, `make_mini3_dataset.py`: 원본에 span 정보가 있으면 `span` 필드로 저장.

---

## 3. aspect_term이 없는 경우: 골드 "" → 모델도 "" 출력

### 3.1 현재 상태
- 골드에서 `aspect_term: ""`인 경우(암시적 표현, 속성 생략 등), `gold_row_to_tuples`에서 **aspect_ref로 채움** → 골드 페어가 `(본품#품질, positive)` 등이 됨.
- 예측은 문장 span을 넣어 `(주머니, positive)` 등이 되어 **(aspect_term, polarity)** 만 봐도 일치하지 않음.
- `tuple_from_sent`에서도 `aspect_term`이 없으면 **aspect_ref로 채움** (`aspect_term = ... or aspect_ref`).

### 3.2 제안
- **골드**: `aspect_term`이 원 데이터에서 빈 문자열이면, 정규화 후에도 **""로 유지**. aspect_ref로 채우지 않음.
- **예측**: 문장 내에 속성이 암시된 경우(암시적 표현), **최종 결과를 취합하는 파트**에서 “암시된 표현”을 추측하더라도, **최종 출력의 aspect_term은 ""로 내보내도록** 규칙 적용.
- 수정 포인트:
  - **`metrics/eval_tuple.py`**
    - `gold_row_to_tuples`: `aspect_term`이 원본에서 명시적으로 `""`이면 `""` 유지. `t.get("aspect_term")`이 빈 문자열이면 `aspect_ref`로 대체하지 않음 (현재 `or t.get("aspect_ref") or ""` 제거 또는 조건 분기).
    - `tuple_from_sent`: 예측 쪽에서도, **명시적으로 aspect_term이 없음(암시적)**으로 올 경우 aspect_ref로 채우지 않고 `aspect_term=""` 유지. (예: `aspect_term` 필드가 존재하고 빈 문자열이면 `""` 사용.)
  - **파이프라인(Moderator/Supervisor)**  
    - 최종 `final_aspects`/`final_tuples`를 만들 때, “암시적 관점”에 대해서는 **aspect_term을 ""로 설정**하는 로직 추가.  
    - ATSA/Stage2 출력에 `is_implicit` 등 플래그가 있으면, 해당 항목은 `aspect_term=""`으로 통일.
  - **`tuples_from_list`**: `aspect_term`만 있고 aspect_ref가 비어 있어도, **aspect_term이 ""인 튜플은 제외하지 않고** 포함하도록 변경 검토. 즉 `("", "", positive)` 같은 튜플도 (aspect_term, polarity) 쌍에서는 `("", positive)`로 매칭에 참여하도록.

---

## 4. 파이프라인: span → aspect_term으로 전달 (aspect_ref로 보내지 않기)

### 4.1 현재 상태
- 문장에서 추출한 **구체 표현(span 텍스트)**가 ATSA/Moderator에서 **aspect_ref**로 전달됨.
- 골드는 택소노미(aspect_ref) + 표면형(aspect_term) 체계인데, 예측은 span을 aspect_ref에 넣어 체계가 어긋남.

### 4.2 제안
- **문장에서 추출한 span(텍스트)**는 **aspect_term**으로만 전달.
  - **aspect_ref**: 택소노미/카테고리 참조용. 비어 있거나, 매핑이 있으면 택소노미 라벨을 넣고, 없으면 `""` 또는 `null` 처리.
  - **aspect_term**: 문장 내 표면형(span 텍스트). ATSA/ATE가 뽑은 “구체 표현”은 여기에만 넣기.
- 수정 포인트:
  - **스키마**: `AspectSentimentItem` 등에서 `aspect_ref` / `aspect_term` 의미를 문서로 명확히 (aspect_ref=참조/택소노미, aspect_term=표면형/span 텍스트).
  - **ATE → ATSA**: ATSA 입력 시 span 텍스트는 **aspect_term** (또는 opinion_term.term을 이 데이터셋에서는 aspect 표면형으로 해석)으로 전달; **aspect_ref**에는 택소노미가 있으면 넣고 없으면 빈 문자열.
  - **ATSA 에이전트/프롬프트**: “aspect_ref에는 ATE term을 그대로 써라”가 아니라 “문장 내 추출한 표현(span)은 aspect_term에, 참조/카테고리는 aspect_ref에”라고 지시.
  - **Moderator `build_final_aspects`**: `AspectSentimentItem`을 dict로 넘길 때, **aspect_term** 필드를 span 텍스트로 명시적으로 채우고, aspect_ref는 참조용으로만 유지.
  - **backbone_client / provider mock**: mock에서도 `aspect_ref`에 term(span)을 넣지 않고, span 텍스트는 `aspect_term` 또는 `opinion_term.term`으로 넣도록 수정.

---

## 5. 튜플 양식 및 null/극성 정규화

### 5.1 튜플 양식 [null, 0, 0], positive
- **의도**: 원 데이터에서 aspect가 없는 경우 **null**로 표현하고, 처리 시 `""`, `null` 등 **오류가 가장 적은 표기 하나로 정규화**해 통일.

### 5.2 제안
- **저장/직렬화**:
  - 튜플 형태를 `[aspect_ref_or_null, span_start, span_end], polarity` 형태로 둘 수 있도록 스키마/문서에 정의.
  - aspect가 없을 때: `null`(JSON) / `None`(Python)을 사용하고, **평가/집계 시점**에서는 `""` 또는 하나의 규약(예: 항상 `""`)으로 정규화해 비교. (JSON에서 `null`과 `""` 혼용 시 오류 가능성을 줄이기 위해, 코드 내부에서는 `""`로 통일하는 것을 권장.)
- **정규화 규칙**:
  - **aspect 부재**: `null`, `None`, `""` → 평가 시 **`""`로 통일**.
  - **극성**: `pos` / `positive` → **`positive`**, `neg` / `negative` → **`negative`**, `neu` / `neutral` → **`neutral`**.  
    `normalize_for_eval` 또는 전용 `normalize_polarity(s)` 도입해 파이프라인 전체에서 동일 적용.
  - **aspect_term 텍스트**: 공백/띄어쓰기 정규화 (예: 연속 공백을 하나로, 앞뒤 공백 제거).  
    “뿌리는 마스크팩” vs “뿌리는마스크팩” 차이를 줄이기 위해, **비교 시에만** 적용할지, 저장 시점에 적용할지 정책 결정 후 일관 적용 (예: 매칭 시 내부적으로 공백 제거 비교 옵션 추가).

### 5.3 수정 포인트
- **`metrics/eval_tuple.py`**
  - `normalize_for_eval`:  
    - polarity 전용: `pos`→`positive`, `neg`→`negative`, `neu`→`neutral` 매핑 추가.  
    - aspect_term: `null`/`None` → `""` 통일.
  - `tuple_from_sent` / 골드 읽기: `aspect_ref`/`aspect_term`이 `null`이면 `""`로 정규화.
- **파이프라인 내부**
  - Supervisor/Moderator에서 최종 튜플 리스트를 만들 때, polarity를 위 정규화 규칙으로 한 번 더 통일.
  - JSON 출력 시 aspect 부재는 `""` 또는 팀 규약에 따라 `null` 중 하나로 통일 (문서화 필수).
- **텍스트 정규화(선택)**
  - aspect_term 비교 시: 공백 제거 후 비교 옵션 추가 (골드 "뿌리는 마스크팩" vs 예측 "뿌리는마스크팩" 매칭 가능).  
  - 또는 골드 생성 시점에 “공백 제거” 정책을 적용해 저장하고, 예측도 동일 규칙으로 정규화.

---

## 6. 추가로 제안하는 수정 사항

### 6.1 골드 gold_tuples 포맷 문서화
- `gold_tuples` 항목별 필드: `aspect_ref`(선택), `aspect_term`(필수, 빈 문자열 가능), `polarity`, `span`(선택) 등을 한곳에 정의.
- `docs/absa_tuple_eval.md` 또는 `docs/pipeline_output_formats.md`에 “평가용 골드 포맷” 섹션 추가.

### 6.2 F1 집계 시 빈 aspect_term 포함
- 현재 `tuples_from_list`에서 `if t[0] or t[1]`로 (aspect_ref 또는 aspect_term이 있을 때만) 추가하므로, `("", "", positive)`는 제외됨.
- 골드/예측 모두 **aspect_term이 ""인 튜플**을 허용하려면, `(aspect_term, polarity)` 쌍으로는 `("", positive)`가 유효하므로, **튜플을 버리지 않고** 넣은 뒤, `tuples_to_pairs`에서 `("", positive)`처럼 쌍이 나오도록 하고, F1 계산 시 이 쌍도 정상적으로 매칭되도록 함.

### 6.3 테스트 보강
- `tests/test_tuple_eval.py`:  
  - 골드 `aspect_term: ""`인 경우 aspect_ref로 채우지 않고 `""` 유지하는지,  
  - (aspect_term, polarity) 매칭에서 `("", positive)` vs `("", positive)` 일치하는지,  
  - polarity 정규화 (pos→positive 등) 단위 테스트 추가.

### 6.4 스키마 필드 명시 (AspectSentimentItem)
- `aspect_term` 필드를 스키마에 추가하거나, 기존 `opinion_term.term`을 “이 데이터셋에서는 aspect 표면형”으로 고정해 사용할 경우, **최종 출력(dict)**에 `aspect_term`이 항상 포함되도록 하면, 평가 쪽에서 일관되게 aspect_term만 읽을 수 있음.

---

## 7. 수정 작업 순서 제안 (참고)

1. **평가 정의 문서화** (absa_tuple_eval.md, f1_zero_diagnosis.md)
2. **정규화 통일** (eval_tuple.py: aspect_term "" 유지, polarity 정규화, null→"")
3. **골드 정규화** (gold_row_to_tuples에서 aspect_term="" 유지)
4. **tuples_from_list** (aspect_term=""인 튜플도 F1 쌍에 포함)
5. **파이프라인** (span → aspect_term, aspect_ref 분리; Moderator/ATSA/backbone_client)
6. **암시적 관점** (final_aspects에서 is_implicit → aspect_term="")
7. **골드 span** (gold 포맷 + make_mini* 스크립트)
8. **테스트 및 리포트** (test_tuple_eval, build_metric_report 등)

**※ 위 8단계 반영 완료** (평가 정의·정규화·골드·tuples_from_list·암시적 관점·골드 span·테스트 추가 적용).

---

## 8. 함께 고려할 사항 (검토 결과)

아래 두 가지는 개선안과 함께 검토·결정이 필요한 사항입니다. **시스템 수정은 아직 진행하지 않음.**

---

### 8.1 ATSA 단계별 출력물 정의: opinion_term vs aspect_term

#### 현재 상태
- **스키마**: `AspectSentimentItem`은 `aspect_ref`, `polarity`, **`opinion_term`**(term, span), evidence, confidence 등을 가짐.
- **문서**: `docs/pipeline_output_formats.md`에서는 “ATSA: aspect_ref, polarity, **opinion_term(term, span)**”으로 기술.
- **평가 쪽**: `metrics/eval_tuple.py`와 `docs/absa_tuple_eval.md`에서 **“이 데이터셋에서는 opinion_term.term을 aspect 표면형(aspect_term)으로 재해석”**한다고 명시.

#### 검토 결과
- 이 태스크에서 **문장 내 관점의 표면형**은 “의견 표현(opinion)”이 아니라 **관점 표현(aspect)**에 해당함.
- 따라서 **opinion_term(term, span)**은 의미적으로 **aspect_term(문장 내 표면형 + span)**에 가깝고, 이름/정의가 태스크와 어긋남.
- 파이프라인 전반에서 `opinion_term.term`을 aspect 표면형으로 쓰고, F1은 (aspect_term, polarity)로 매칭하는데, 스키마·문서는 여전히 “opinion”으로 되어 있어 혼선 가능.

#### 제안 (검토용)
- **정의 정리**: ATSA 출력에서 “문장 내 관점 표면형(term + span)”을 **aspect_term** 개념으로 문서·스키마에 명확히 정의.
- **선택지**  
  - **(A)** 스키마에 **`aspect_term`** 필드(및 필요 시 span)를 추가하고, ATSA는 관점 표면형을 `aspect_term`(또는 term+span)으로 내보내며, `opinion_term`은 점진적 deprecated 또는 “의견 표현용”으로만 한정 문서화.  
  - **(B)** 스키마는 유지하되, **문서·주석**에서 “이 파이프라인/데이터셋에서는 opinion_term = aspect 표면형(term, span)”이라고 명시하고, 평가·다운스트림에서 사용하는 필드 매핑(opinion_term.term → aspect_term)을 한곳에 정리.
- **문서 수정**: `docs/pipeline_output_formats.md`의 ATSA 설명에 “관점 표면형(aspect_term에 해당하는 term, span)”임을 명시하고, 필요 시 “opinion_term은 본 태스크에서 aspect 표면형으로 사용”이라는 주를 추가.

---

### 8.2 ATSA의 aspect_ref: 파이프라인 내 사용처 및 분류 기능 여부

#### 파이프라인 내 aspect_ref 사용처 (코드 기준)

| 사용처 | 파일·위치 | 용도 |
|--------|-----------|------|
| **Stage2 리뷰 provenance 키** | `supervisor_agent.py` | `_inject_review_provenance(..., key_field="aspect_ref")` — sentiment_review 항목 식별 키 |
| **최종 필터** | `supervisor_agent.py` | `final_aspect_sentiments = [s for s in ... if s.aspect_ref in kept_aspect_terms]` — ATE가 유지한 term만 최종 포함 |
| **Debate 맥락** | `supervisor_agent.py` | `atsa_refs = [s.aspect_ref for s in stage1_atsa.aspect_sentiments]` → synonym_hints·norm_map·mapped의 키/값으로 사용, 토론 발언을 “어떤 관점”에 매핑할 때 사용 |
| **Fallback 매핑** | `supervisor_agent.py` | `_fallback_map_from_atsa`, `_pick_best_aspect`: sentiment 목록에서 `s.aspect_ref`로 후보 선택 후 `best.aspect_ref` 반환 |
| **Backfill** | `supervisor_agent.py` | `_backfill_sentiments`: ATE에만 있고 ATSA에 없는 관점에 대해 `AspectSentimentItem(aspect_ref=a.term, ...)` 추가 |
| **Unanchored 검사** | `supervisor_agent.py` | `_find_unanchored_aspects`: `s.aspect_ref not in ate_terms` → ATSA가 ATE term과 다른 문자열을 쓴 경우 이슈로 기록 |
| **Stage2 리뷰 적용** | `supervisor_agent.py` | `_apply_stage2_reviews`: `SentimentReviewItem.aspect_ref`로 대상 지정, `s.aspect_ref == target_aspect`로 매칭, 신규 항목 생성 시 `aspect_ref=aspect_ref` 등 |
| **Anchor 정규화** | `supervisor_agent.py` | `_map_aspect_ref_to_terms(s.aspect_ref, aspect_terms)`: ATSA의 aspect_ref를 ATE term과 substring으로 매핑, 없으면 drop, 있으면 `s.aspect_ref = mapped` |

#### ATSA 에이전트 측 지시
- `atsa_agent.py`: Stage2 프롬프트에 **“Use only ATE terms verbatim for aspect_ref.”** 라고만 있음.
- 즉, **aspect_ref에는 ATE가 추출한 term(문장 내 span 텍스트)을 그대로 쓰라**는 의미이며, **택소노미(본품#품질 등) 분류를 하라는 지시는 없음.**

#### 검토 결과
- **aspect_ref는 파이프라인 전반에서 “ATE term과의 매칭용 식별자”로만 사용됨.**  
  즉, “이 sentiment가 어떤 ATE 관점(term)에 대응하는지”를 나타내는 **내부 핸들** 역할만 함.
- **택소노미(본품#품질, 제품 전체#일반 등)로의 분류는 수행되지 않음.**  
  골드에는 aspect_ref가 택소노미인데, 예측 쪽 aspect_ref는 ATE term(span 텍스트)이라 체계가 다름.
- 따라서 **현재 aspect_ref는 “aspect 분류(택소노미)” 기능을 수행하지 않으며**, 원래 기대했을 수 있는 “참조/카테고리” 의미와 다르게 쓰이고 있음.

#### 제안 (검토용)
- **옵션 1 — 역할 명확화·이름 정리**  
  - aspect_ref를 **“ATE term 참조(파이프라인 내 매칭용)”**로만 정의하고, 문서·주석에 “택소노미가 아님”을 명시.  
  - 스키마 필드명을 유지하되, 설명을 “ATE에서 추출한 관점 term과의 매칭용 식별자”로 통일.
- **옵션 2 — 택소노미 분류 도입**  
  - 별도 단계/필드에서 **택소노미(본품#품질 등)** 를 예측하고, 그 결과를 (예: `aspect_ref` 또는 `aspect_taxonomy`)에 넣도록 설계.  
  - 이 경우 기존 aspect_ref(ATE term 참조)와 구분하기 위해 **필드 분리**(예: `ate_term_ref` vs `aspect_taxonomy`) 검토.
- **옵션 3 — 미사용 기능으로 판단 시 제거 검토**  
  - “aspect 분류(택소노미)”를 아예 하지 않을 계획이라면, **현재처럼 aspect_ref = ATE term 복사본**이면 충분한지 확인.  
  - 충분하다면 “분류”라는 이름/기대는 제거하고, **내부 매칭용 식별자**로만 정의 후, 필요 시 필드명을 `ate_term_ref` 등으로 바꿔 혼동을 줄일 수 있음.
- **삭제 시 유의점**  
  - aspect_ref 필드 자체를 제거하면, 위 표의 **모든 사용처**를 대체해야 함.  
  - 대체 방식 예: ATSA 항목을 **aspect_term(또는 opinion_term.term)**으로 ATE term과 매칭하도록 변경한 뒤, “ATE term과의 매칭용” 키는 aspect_term(또는 별도 id)으로 통일.  
  - 이 경우 4번 제안(span → aspect_term으로 보내기)과 맞춰 **aspect_term을 파이프라인 내 매칭 키**로 쓰는 설계로 정리할 수 있음.

---

이 문서는 **제안만** 담고 있으며, 실제 수정은 진행하지 않았습니다. 반영 순서와 범위는 팀 정책에 맞게 조정하면 됩니다.
