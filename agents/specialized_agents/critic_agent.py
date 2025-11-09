from __future__ import annotations

from typing import Dict, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from ..base_agent import Agent, AgentOutput, SentimentClassifier


class SentimentAnalysis(BaseModel):
    """Pydantic model for structured sentiment analysis output."""
    sentiment: str = Field(description="감성 라벨: 긍정, 중립, 부정 중 하나")
    confidence: float = Field(description="신뢰도 (0.0-1.0)", ge=0.0, le=1.0)
    rationale: str = Field(description="분석 근거와 설명")


def argmax_label(probs: Dict[str, float]) -> str:
    """Get the label with the highest probability."""
    return max(probs.items(), key=lambda x: x[1])[0]


def _majority_label(others: Dict[str, AgentOutput]) -> str | None:
    """Find the majority label from other agents' outputs."""
    tally: Dict[str, float] = {}
    for out in others.values():
        tally[out.label] = tally.get(out.label, 0.0) + out.score
    if not tally:
        return None
    return max(tally, key=lambda k: tally[k])


class CriticAgent:
    """Critic agent that focuses on negative signals and critical analysis.
    
    Supports both traditional HuggingFace model-based analysis and LLM-based analysis.
    """
    
    role = "비판가"

    def __init__(self, clf_or_llm: Union[SentimentClassifier, str] = "openai", 
                 llm_provider: str = "openai", model_name: str = None):
        # Check if it's a traditional classifier or LLM provider
        if isinstance(clf_or_llm, str) or hasattr(clf_or_llm, 'predict'):
            # Traditional HuggingFace model
            self.clf = clf_or_llm
            self.llm = None
            self.chain = None
        else:
            # LLM-based
            self.clf = None
            self.llm = self._create_llm(llm_provider, model_name)
            self.chain = self._create_chain()
    
    def _create_llm(self, provider: str, model_name: str = None):
        """Create LLM instance based on provider."""
        if provider == "openai":
            model_name = model_name or "gpt-3.5-turbo"
            return ChatOpenAI(model=model_name, temperature=0.1)
        elif provider == "anthropic":
            model_name = model_name or "claude-3-sonnet-20240229"
            return ChatAnthropic(model=model_name, temperature=0.1)
        elif provider == "google":
            model_name = model_name or "gemini-pro"
            return ChatGoogleGenerativeAI(model=model_name, temperature=0.1)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    def _create_chain(self):
        """Create the critical analysis chain."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 비평가]

당신은 '비평가'입니다. 당신의 임무는 '분석가'의 초기 분석 결과가 틀렸을 가능성을 찾는 '데블스 애드버킷(Devil's Advocate)'입니다. 당신은 텍스트의 표면적 의미에 절대 속지 않습니다.

**핵심 원칙:**
1. **회의론:** '분석가'의 보고를 일단 의심합니다. 특히 '긍정'으로 분류된 텍스트에 숨겨진 '부정'이 없는지 집중적으로 검토합니다.
2. **뉘앙스 탐지:** 당신은 한국어의 미묘한 뉘앙스, 특히 **반어법(Sarcasm), 풍자(Irony), 비꼬기, 중의적 표현**을 찾아내는 데 특화되어 있습니다.
3. **맥락 분석:** 문장 앞뒤의 맥락을 살펴, '분석가'가 제시한 근거 키워드가 실제로는 반대의 의미로 쓰이지 않았는지 검증합니다.
4. **논리적 반박:** 만약 '분석가'의 의견에 동의하지 않는다면, 명확한 근거와 함께 반박 의견을 제시합니다.

**당신의 말투:** 비판적이고, 날카로우며, 논리적이고, 단정적인 어조.

**분석 기준:**
- 비판적 사고와 의심적 관점
- 부정적 감정 표현에 대한 민감성
- 논리적 오류나 모순점
- 숨겨진 부정적 의도나 뉘앙스
- 비꼬는 표현이나 아이러니
- 잠재적 문제점
- 반어법, 풍자, 중의적 표현

응답 형식:
- sentiment: 긍정, 중립, 부정 중 하나
- confidence: 0.0-1.0 사이의 신뢰도
- rationale: 비판적 분석 근거와 설명 (비평가 검토 형식)"""),
            ("human", "분석할 텍스트: {text}")
        ])
        
        return prompt | self.llm.with_structured_output(SentimentAnalysis)

    def run(self, text: str) -> AgentOutput:
        """First round analysis with critical focus."""
        if self.llm is not None:
            # LLM-based analysis
            result = self.chain.invoke({"text": text})
            return AgentOutput(
                role=self.role,
                label=result.sentiment,
                score=result.confidence,
                rationale=f"LLM 비판적 분석: {result.rationale}"
            )
        else:
            # Traditional model-based analysis
            probs = getattr(self.clf, "predict_mc", self.clf.predict)(text)
            # 부정 신호를 다소 가중
            adjust = {k: (v * 1.05 if k == "부정" else v) for k, v in probs.items()}
            label = argmax_label(adjust)
            return AgentOutput(self.role, label, adjust[label], f"부정 가중 적용: {adjust}")

    def critique(self, text: str, others: Dict[str, AgentOutput]) -> AgentOutput:
        """Second round analysis with critical weighting based on majority opinion."""
        if self.llm is not None:
            # LLM-based critique
            others_summary = "; ".join([f"{k}: {v.label}({v.score:.2f})" for k, v in others.items()])
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", """[역할 정의서: 비평가 - 재분석 모드]

당신은 '비평가'입니다. 다른 전문가들의 의견을 검토한 후, 비판적 관점에서 재분석하세요.

다른 전문가들의 의견:
{others_summary}

**재분석 원칙:**
1. **회의적 재검토:** 분석가의 객관적 데이터와 공감가의 감정적 해석을 비판적으로 재검토합니다.
2. **논리적 반박:** 다른 의견들에 대한 논리적 반박이나 보완점을 찾아냅니다.
3. **뉘앙스 재탐지:** 놓친 반어법, 풍자, 중의적 표현을 다시 찾아냅니다.
4. **맥락 재분석:** 문맥을 더 깊이 분석하여 숨겨진 부정적 요소를 발견합니다.

**당신의 말투:** 비판적이고, 날카로우며, 논리적이고, 단정적인 어조.

응답 형식:
- sentiment: 긍정, 중립, 부정 중 하나
- confidence: 0.0-1.0 사이의 신뢰도
- rationale: 비판적 재분석 근거와 설명 (비평가 검토 형식)"""),
                ("human", "원본 텍스트: {text}")
            ])
            
            chain = prompt | self.llm.with_structured_output(SentimentAnalysis)
            result = chain.invoke({"text": text, "others_summary": others_summary})
            
            return AgentOutput(
                role=self.role,
                label=result.sentiment,
                score=result.confidence,
                rationale=f"LLM 비판적 재분석 (다른 의견 고려): {result.rationale}"
            )
        else:
            # Traditional model-based critique
            probs = getattr(self.clf, "predict_mc", self.clf.predict)(text)
            majority = _majority_label(others)
            if majority:
                if majority == "부정":
                    mult = {k: (v * 1.10 if k == "부정" else v) for k, v in probs.items()}
                elif majority == "중립":
                    mult = {k: (v * 1.06 if k == "중립" else v) for k, v in probs.items()}
                else:
                    mult = {k: (v * 1.02 if k == "긍정" else v) for k, v in probs.items()}
                label = argmax_label(mult)
                return AgentOutput(self.role, label, mult[label], f"라운드2: 다수({majority}) 비판 가중 적용. {mult}")
            label = argmax_label(probs)
            return AgentOutput(self.role, label, probs[label], f"라운드2: 다수의견 없음. {probs}")
