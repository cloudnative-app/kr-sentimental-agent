# KR Sentiment Agent Flow Diagram

## 1. 2단계 멀티 에이전트 시스템 (이미지 구조와 일치, 권장)

```mermaid
graph TD
    A[입력 텍스트] --> B[모더레이터 에이전트]
    
    subgraph "1단계: 독립적 의견수렴"
        B --> C[분석가 에이전트]
        B --> D[공감가 에이전트]
        B --> E[비판가 에이전트]
        
        C --> C1[논리적/사실적 분석]
        C1 --> C2[LLM: 독립적 의견]
        C2 --> C3[AgentOutput: 독립적 분석가]
        
        D --> D1[감정적 이해]
        D1 --> D2[LLM: 독립적 감정 분석]
        D2 --> D3[AgentOutput: 독립적 공감가]
        
        E --> E1[비판적 분석]
        E1 --> E2[LLM: 독립적 비판]
        E2 --> E3[AgentOutput: 독립적 비판가]
    end
    
    subgraph "2단계: 심의단계"
        C3 --> F[분석가 에이전트]
        D3 --> G[공감가 에이전트]
        E3 --> H[비판가 에이전트]
        
        F --> F1[다른 의견 고려]
        F1 --> F2[LLM: 심의 분석]
        F2 --> F3[AgentOutput: 심의 분석가]
        
        G --> G1[다른 의견 고려]
        G1 --> G2[LLM: 심의 감정 분석]
        G2 --> G3[AgentOutput: 심의 공감가]
        
        H --> H1[다른 의견 고려]
        H1 --> H2[LLM: 심의 비판]
        H2 --> H3[AgentOutput: 심의 비판가]
    end
    
    F3 --> I[최종화]
    G3 --> I
    H3 --> I
    
    I --> J[최종 감성분석 결과]
    
    style A fill:#e1f5fe
    style J fill:#c8e6c9
    style B fill:#fff3e0
    style C fill:#f3e5f5
    style D fill:#e8f5e8
    style E fill:#ffebee
    style F fill:#f3e5f5
    style G fill:#e8f5e8
    style H fill:#ffebee
    style I fill:#e0f2f1
```

## 2. LangGraph 기반 워크플로우

```mermaid
graph TD
    A[입력 텍스트] --> B[LangGraph Supervisor]
    B --> C[Analyst Node]
    B --> D[Empath Node] 
    B --> E[Critic Node]
    B --> F[Supervisor Node]
    B --> G[Finalize Node]
    
    C --> C1[논리적/사실적 분석]
    C1 --> C2[LLM: GPT-3.5/Claude/Gemini]
    C2 --> C3[AgentOutput: 분석가]
    
    D --> D1[감정적 이해]
    D1 --> D2[LLM: 감정 공감 분석]
    D2 --> D3[AgentOutput: 공감가]
    
    E --> E1[비판적 분석]
    E1 --> E2[LLM: 비판적 관점]
    E2 --> E3[AgentOutput: 비판가]
    
    F --> F1[종합 분석]
    F1 --> F2[전문가 의견 통합]
    F2 --> F3[AgentOutput: 조정자]
    
    G --> G1[최종 결과 생성]
    G1 --> H[최종 감성분석 결과]
    
    C3 --> F
    D3 --> F
    E3 --> F
    F3 --> G
    
    style A fill:#e1f5fe
    style H fill:#c8e6c9
    style B fill:#fff3e0
    style C fill:#f3e5f5
    style D fill:#e8f5e8
    style E fill:#ffebee
    style F fill:#fff8e1
    style G fill:#e0f2f1
```

## 3. LangChain 기반 개별 에이전트

```mermaid
graph TD
    A[입력 텍스트] --> B[SupervisorAgent]
    B --> C[LangChain Analyst]
    B --> D[LangChain Empath]
    B --> E[LangChain Critic]
    
    C --> C1[Pydantic 파싱]
    C1 --> C2[LLM 호출]
    C2 --> C3[구조화된 응답]
    C3 --> C4[AgentOutput: 분석가]
    
    D --> D1[Pydantic 파싱]
    D1 --> D2[LLM 호출]
    D2 --> D3[구조화된 응답]
    D3 --> D4[AgentOutput: 공감가]
    
    E --> E1[Pydantic 파싱]
    E1 --> E2[LLM 호출]
    E2 --> E3[구조화된 응답]
    E3 --> E4[AgentOutput: 비판가]
    
    C4 --> F[Round 1 결과]
    D4 --> F
    E4 --> F
    
    F --> G[Critique Phase]
    G --> C5[재분석: 분석가]
    G --> D5[재분석: 공감가]
    G --> E5[재분석: 비판가]
    
    C5 --> H[Round 2 결과]
    D5 --> H
    E5 --> H
    
    H --> I[Finalize]
    I --> J[집계 방법 선택]
    J --> K[최종 결과]
    
    style A fill:#e1f5fe
    style K fill:#c8e6c9
    style B fill:#fff3e0
    style C fill:#f3e5f5
    style D fill:#e8f5e8
    style E fill:#ffebee
    style F fill:#fff8e1
    style G fill:#e0f2f1
    style H fill:#f1f8e9
    style I fill:#fce4ec
```

## 4. 전통적 멀티 에이전트 시스템

```mermaid
graph TD
    A[입력 텍스트] --> B[SupervisorAgent]
    B --> C[AnalystAgent]
    B --> D[EmpathAgent]
    B --> E[CriticAgent]
    
    C --> C1[HFClassifier]
    C1 --> C2[모델 예측]
    C2 --> C3[AgentOutput: 분석가]
    
    D --> D1[HFClassifier]
    D1 --> D2[감정 가중치 적용]
    D2 --> D3[AgentOutput: 공감가]
    
    E --> E1[HFClassifier]
    E1 --> E2[비판 가중치 적용]
    E2 --> E3[AgentOutput: 비판가]
    
    C3 --> F[Round 1]
    D3 --> F
    E3 --> F
    
    F --> G[Critique Phase]
    G --> C4[다수 의견 고려]
    G --> D4[감정적 재평가]
    G --> E4[비판적 재평가]
    
    C4 --> H[Round 2]
    D4 --> H
    E4 --> H
    
    H --> I[Finalize]
    I --> J{집계 방법}
    J -->|mean| K[평균 기반]
    J -->|vote| L[다수결]
    J -->|max| M[최고 신뢰도]
    
    K --> N[최종 결과]
    L --> N
    M --> N
    
    style A fill:#e1f5fe
    style N fill:#c8e6c9
    style B fill:#fff3e0
    style C fill:#f3e5f5
    style D fill:#e8f5e8
    style E fill:#ffebee
    style F fill:#fff8e1
    style G fill:#e0f2f1
    style H fill:#f1f8e9
    style I fill:#fce4ec
```

## 5. 통합 아키텍처 개요

```mermaid
graph TB
    subgraph "입력 계층"
        A[텍스트 입력]
        B[설정 파일]
        C[API 키]
    end
    
    subgraph "에이전트 선택"
        D{Agent Mode}
    D -->|use_two_stage=True| E[Two-Stage Supervisor]
    D -->|use_langgraph=True| F[LangGraph Supervisor]
    D -->|use_langgraph=False| G[LangChain Agents]
    D -->|Traditional| H[Traditional Agents]
    end
    
    subgraph "2단계 워크플로우"
        E --> I[독립적 의견수렴]
        E --> J[심의단계]
        I --> K[최종화]
        J --> K
    end
    
    subgraph "LangGraph 워크플로우"
        F --> L[Analyst Node]
        F --> M[Empath Node]
        F --> N[Critic Node]
        F --> O[Supervisor Node]
        F --> P[Finalize Node]
    end
    
    subgraph "LangChain 에이전트"
        G --> Q[LangChainAnalystAgent]
        G --> R[LangChainEmpathAgent]
        G --> S[LangChainCriticAgent]
    end
    
    subgraph "전통적 에이전트"
        H --> T[AnalystAgent]
        H --> U[EmpathAgent]
        H --> V[CriticAgent]
    end
    
    subgraph "LLM 계층"
        S[OpenAI GPT]
        T[Anthropic Claude]
        U[Google Gemini]
        V[HuggingFace Models]
    end
    
    subgraph "출력 계층"
        W[AgentOutput]
        X[JSON 결과]
        Y[로그 파일]
    end
    
    A --> D
    B --> D
    C --> S
    C --> T
    C --> U
    
    I --> W
    J --> X
    K --> Y
    L --> Z
    M --> AA
    N --> BB
    O --> CC
    P --> DD
    Q --> EE
    R --> FF
    S --> GG
    T --> HH
    U --> II
    V --> JJ
    
    W --> KK
    X --> KK
    Y --> KK
    Z --> KK
    AA --> KK
    BB --> KK
    CC --> KK
    DD --> KK
    EE --> KK
    FF --> KK
    GG --> KK
    HH --> KK
    II --> KK
    JJ --> KK
    
    KK --> LL
    KK --> MM
    
    style A fill:#e1f5fe
    style D fill:#fff3e0
    style E fill:#f3e5f5
    style F fill:#e8f5e8
    style G fill:#ffebee
    style W fill:#c8e6c9
```

## 6. 실험 실행 플로우

```mermaid
graph TD
    A[실험 시작] --> B[설정 로드]
    B --> C[데이터 로드]
    C --> D{실험 모드}
    
    D -->|single| E[단일 에이전트]
    D -->|self| F[Self-consistency]
    D -->|persona| G[멀티 에이전트]
    D -->|persona_delib| H[심의 과정]
    D -->|two_stage| I[2단계 워크플로우]
    D -->|langgraph| J[LangGraph 워크플로우]
    D -->|langchain| K[LangChain 에이전트]
    
    E --> K[결과 수집]
    F --> K
    G --> K
    H --> K
    I --> K
    J --> K
    
    K --> L[JSON 저장]
    L --> M[실험 완료]
    
    style A fill:#e1f5fe
    style M fill:#c8e6c9
    style D fill:#fff3e0
    style I fill:#f3e5f5
    style J fill:#e8f5e8
    style K fill:#ffebee
```

## 주요 특징

### 2단계 워크플로우 (이미지 구조와 일치)
- **독립적 의견수렴**: 각 에이전트가 독립적으로 분석
- **심의단계**: 다른 에이전트들의 의견을 고려한 재분석
- **명확한 구분**: 2단계 프로세스로 구조화
- **이미지 일치**: 제공된 이미지와 동일한 구조

### LangGraph 워크플로우
- **노드 기반**: 각 에이전트가 독립적인 노드
- **자동화된 흐름**: 그래프 구조로 자동 실행
- **상태 관리**: 전체 프로세스 상태 추적
- **메시지 체인**: LangChain 메시지 시스템 활용

### LangChain 에이전트
- **구조화된 출력**: Pydantic 모델로 일관된 응답
- **프롬프트 템플릿**: 전문적인 프롬프트 엔지니어링
- **2단계 심의**: Round 1 + Critique Phase
- **다중 LLM**: OpenAI, Anthropic, Google 지원

### 전통적 에이전트
- **모델 기반**: HuggingFace 분류기 사용
- **가중치 적용**: 각 에이전트별 특화된 가중치
- **집계 방법**: mean, vote, max 선택 가능
- **하위 호환성**: 기존 시스템과 완전 호환
