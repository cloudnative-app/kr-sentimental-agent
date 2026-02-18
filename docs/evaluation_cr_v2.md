# CR v2 평가 정의 (Evaluation)

## 공식 평가 단위 (PART 0)

| 용어 | 공식 정의 |
|------|-----------|
| **GoldUnit** | (aspect_ref, polarity) — 주평가 키 |
| **SurfaceUnit** | (aspect_term, polarity) — 보조평가 (explicit-only) |
| **EvalTuple** | (aspect_ref, aspect_term, polarity) |
| **Triplet** | ASTETripletItem (raw agent output) |

### 선언문

> In CR v2, the primary evaluation unit is the entity–attribute pair **(aspect_ref, polarity)**, aligning with the original annotation scheme.
> Surface-level aspect terms (OTE) are used only for auxiliary grounding analysis.

### 결과표 구조

**본문 표**

| Condition | Ref_F1_S1 | Ref_F1_S2 | Delta | Break | Fix |

**Appendix**

| Explicit_Surface_F1 | Invalid_Ref_Rate | Invalid_Language_Rate | Invalid_Target_Rate | OTE_Null_Rate |

---

## ΔF1 (delta_f1) 해석 프레이밍

**정의**

```
ΔF1_ref = F1_final(ref, pol) − F1_stage1(ref, pol)
```

**의미**

- **차원(구성개념) 수준 판단 안정성 변화**: taxonomy 기반 (aspect_ref, polarity) 쌍의 Stage1→Final 변화
- **surface 언어 변동과 무관**: aspect_term 표면형 변동은 주평가에 반영되지 않음
- **taxonomy 기반 측정 정합성 변화**: closed-set aspect_ref 기준으로 일관된 평가

---

## IRR (Inter-Rater Reliability)

### A. Process Reliability (Action IRR)

- **unit**: stage1 tuple_id (candidate)
- **label**: reviewer action (KEEP/DROP/FLIP_POS/FLIP_NEG/MERGE/OTHER)
- **raters**: Review A/B/C
- **의미**: 교정행위 전략의 합의도 (= 프로세스 신뢰도)

### B. Measurement Reliability (Final decision IRR)

- **unit**: stage1 tuple_id (동일)
- **label**: final measurement label ∈ {POS, NEG, NEU, DROP}
- **raters**: Review A/B/C
- **의미**: 교정 이후 측정값(polarity)의 합의도 (= 측정 신뢰도)

**Action → final_label 매핑**:
- KEEP → 원 polarity (POS/NEG/NEU)
- FLIP_POS → POS, FLIP_NEG → NEG
- DROP → DROP
- **MERGE/OTHER → DROP** (측정에서 제외, 해석 용이성)
