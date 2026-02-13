# Stage1 ATSA raw output (3~5 samples, as-is)

Raw = LLM raw response string. Parsed = schema-parsed output (aspect_sentiments).

## Sample 1 (nikluge-sa-2022-train-02669)

### Raw output (as-is)
```
{
  "aspect_sentiments": [
    {
      "aspect_ref": "컨실러",
      "polarity": "positive",
      "opinion_term": {
        "term": "0번",
        "span": {
          "start": 21,
          "end": 23
        }
      },
      "evidence": "#컨실러순위 0번 😙😙",
      "confidence": 0.9,
      "polarity_distribution": {
        "pos": 0.9,
        "neg": 0.05,
        "neu": 0.05
      },
      "is_implicit": false
    }
  ]
}
```

### Parsed JSON
```json
{
  "aspect_sentiments": [
    {
      "aspect_term": {
        "term": "컨실러",
        "span": {
          "start": 26,
          "end": 29
        }
      },
      "polarity": "neutral",
      "evidence": "#쉬드엘아티스트웨어스킨핏듀얼컨실러 내마음 #컨실러순위 0번 😙😙",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    }
  ]
}
```

## Sample 2 (nikluge-sa-2022-train-02211)

### Raw output (as-is)
```
{
  "aspect_sentiments": [
    {
      "aspect_ref": "라임리치향",
      "polarity": "positive",
      "opinion_term": { "term": "상큼한", "span": { "start": 9, "end": 12 } },
      "evidence": "라임리치향 넘나 상큼한 것",
      "confidence": 0.95,
      "polarity_distribution": { "pos": 0.95, "neg": 0.03, "neu": 0.02 },
      "is_implicit": false
    }
  ]
}
```

### Parsed JSON
```json
{
  "aspect_sentiments": [
    {
      "aspect_term": {
        "term": "라임리치향",
        "span": {
          "start": 0,
          "end": 5
        }
      },
      "polarity": "neutral",
      "evidence": "라임리치향 넘나 상큼한 것",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    }
  ]
}
```

## Sample 3 (nikluge-sa-2022-train-01786)

### Raw output (as-is)
```
{
  "aspect_sentiments": [
    {
      "aspect_ref": "파우치에 쏙 넣는 것",
      "polarity": "positive",
      "opinion_term": { "term": "쏙 넣고", "span": { "start": 3, "end": 7 } },
      "evidence": "파우치에 쏙 넣고 자주 자주 발라줘야겠어요",
      "confidence": 0.9,
      "polarity_distribution": { "pos": 0.9, "neg": 0.05, "neu": 0.05 },
      "is_implicit": false
    },
    {
      "aspect_ref": "자주 바르는 것",
      "polarity": "positive",
      "opinion_term": { "term": "자주 자주 발라줘야겠어요", "span": { "start": 8, "end": 20 
```

### Parsed JSON
```json
{
  "aspect_sentiments": [
    {
      "aspect_term": {
        "term": "파우치",
        "span": {
          "start": 0,
          "end": 3
        }
      },
      "polarity": "neutral",
      "evidence": "파우치에 쏙 넣고 자주 자주 발라줘야겠어요",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    }
  ]
}
```

## Sample 4 (nikluge-sa-2022-train-02482)

### Raw output (as-is)
```
{
  "aspect_sentiments": [
    {
      "aspect_ref": "젤제형",
      "polarity": "positive",
      "opinion_term": { "term": "좋은", "span": { "start": 9, "end": 11 } },
      "evidence": "여름에 사용하기 좋은 젤제형으로",
      "confidence": 0.95,
      "polarity_distribution": { "pos": 0.95, "neg": 0.02, "neu": 0.03 },
      "is_implicit": false
    },
    {
      "aspect_ref": "발림성",
      "polarity": "positive",
      "opinion_term": { "term": "부드럽고 촉촉한", "span": { "start": 14, "end": 22 } },
      "evidence":
```

### Parsed JSON
```json
{
  "aspect_sentiments": [
    {
      "aspect_term": {
        "term": "젤제형",
        "span": {
          "start": 11,
          "end": 14
        }
      },
      "polarity": "neutral",
      "evidence": "여름에 사용하기 좋은 젤제형으로 부드럽고 촉촉한 발림성 피부에 빠르게 밀착되어 겉돌지않고 끈적이지 않아 산뜻한느낌!!",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    },
    {
      "aspect_term": {
        "term": "발림성",
        "span": {
          "start": 22,
          "end": 25
        }
      },
      "polarity": "neutral",
      "evidence": "여름에 사용하기 좋은 젤제형으로 부드럽고 촉촉한 발림성 피부에 빠르게 밀착되어 겉돌지않고 끈적이지 않아 산뜻한느낌!!",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    },
    {
      "aspect_term": {
        "term": "피부",
        "span": {
          "start": 26,
          "end": 28
        }
      },
      "polarity": "neutral",
      "evidence": "여름에 사용하기 좋은 젤제형으로 부드럽고 촉촉한 발림성 피부에 빠르게 밀착되어 겉돌지않고 끈적이지 않아 산뜻한느낌!!",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    },
    {
      "aspect_term": {
        "term": "산뜻한느낌",
        "span": {
          "start": 56,
          "end": 61
        }
      },
      "polarity": "neutral",
      "evidence": "여름에 사용하기 좋은 젤제형으로 부드럽고 촉촉한 발림성 피부에 빠르게 밀착되어 겉돌지않고 끈적이지 않아 산뜻한느낌!!",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    }
  ]
}
```

## Sample 5 (nikluge-sa-2022-train-01939)

### Raw output (as-is)
```
{
  "aspect_sentiments": [
    {
      "aspect_ref": "잔향",
      "polarity": "positive",
      "opinion_term": { "term": "오래가", "span": { "start": 11, "end": 14 } },
      "evidence": "샤워후 가볍게 뿌려주면 잔향도 오래가",
      "confidence": 0.95,
      "polarity_distribution": { "pos": 0.95, "neg": 0.03, "neu": 0.02 },
      "is_implicit": false
    },
    {
      "aspect_ref": "향기",
      "polarity": "positive",
      "opinion_term": { "term": "향기로운", "span": { "start": 23, "end": 27 } },
      "evidence": 
```

### Parsed JSON
```json
{
  "aspect_sentiments": [
    {
      "aspect_term": {
        "term": "잔향",
        "span": {
          "start": 11,
          "end": 13
        }
      },
      "polarity": "neutral",
      "evidence": "샤워후 가볍게 뿌려주면 잔향도 오래가 머리부터 발끝까지 향기로운 여자~",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    },
    {
      "aspect_term": {
        "term": "머리부터 발끝까지 향기로운 여자",
        "span": {
          "start": 14,
          "end": 27
        }
      },
      "polarity": "neutral",
      "evidence": "샤워후 가볍게 뿌려주면 잔향도 오래가 머리부터 발끝까지 향기로운 여자~",
      "confidence": 0.5,
      "polarity_distribution": {
        "neutral": 1.0
      },
      "is_implicit": false
    }
  ]
}
```
