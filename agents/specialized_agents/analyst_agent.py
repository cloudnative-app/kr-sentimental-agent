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


class AnalystAgent:
    """Analyst agent that focuses on logical and factual analysis.
    
    Supports both traditional HuggingFace model-based analysis and LLM-based analysis.
    """
    
    role = "분석가"

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
        """Create the analysis chain."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 분석가]

당신은 '분석가'입니다. 당신의 유일한 임무는 입력된 텍스트를 감정적인 해석 없이, 오직 언어적 데이터와 통계에 기반하여 객관적으로 분석하는 것입니다.

**핵심 원칙:**
1. **데이터 중심:** 당신은 감정을 느끼지 않습니다. 오직 텍스트에 드러난 사실(Fact)만을 분석합니다.
2. **객관적 분류:** 텍스트의 주된 감정을 '긍정', '부정', '중립' 등으로 분류하고, 신뢰도 점수를 함께 제시합니다.
3. **근거 제시:** 당신의 판단 근거가 된 핵심 키워드나 문장을 정확히 추출하여 명시해야 합니다.
4. **구조화된 보고:** 감성적인 서술을 피하고, 사실 기반의 보고체로 분석합니다.

**당신의 말투:** 건조하고(Dry), 기계적이며(Mechanical), 사실 기반(Factual)의 보고체.

**분석 기준:**
- 텍스트의 명시적 감정 표현 키워드
- 문장 구조와 문법적 요소
- 객관적 사실과 논리적 근거
- 단어의 사전적 의미

응답 형식:
- sentiment: 긍정, 중립, 부정 중 하나
- confidence: 0.0-1.0 사이의 신뢰도
- rationale: 분석 근거와 설명 (보고서 형식)"""),
            ("human", "분석할 텍스트: {text}")
        ])
        
        return prompt | self.llm.with_structured_output(SentimentAnalysis)

    def run(self, text: str) -> AgentOutput:
        """First round analysis."""
        if self.llm is not None:
            # LLM-based analysis
            result = self.chain.invoke({"text": text})
            return AgentOutput(
                role=self.role,
                label=result.sentiment,
                score=result.confidence,
                rationale=f"LLM 논리적 분석: {result.rationale}"
            )
        else:
            # Traditional model-based analysis
            probs = getattr(self.clf, "predict_mc", self.clf.predict)(text)
            label = argmax_label(probs)
            return AgentOutput(self.role, label, probs[label], f"모델 확률 기반 1차 분석: {probs}")

    def critique(self, text: str, others: Dict[str, AgentOutput]) -> AgentOutput:
        """Second round analysis considering others' opinions."""
        if self.llm is not None:
            # LLM-based critique
            others_summary = "; ".join([f"{k}: {v.label}({v.score:.2f})" for k, v in others.items()])
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", """[역할 정의서: 분석가 - 재분석 모드]

당신은 '분석가'입니다. 다른 전문가들의 의견을 검토한 후, 데이터 중심의 객관적 관점에서 재분석하세요.

다른 전문가들의 의견:
{others_summary}

**재분석 원칙:**
1. **데이터 재검증:** 다른 의견들을 검토하되, 여전히 텍스트의 객관적 데이터에 기반하여 판단합니다.
2. **논리적 일관성:** 비평가나 공감가의 지적이 데이터적으로 타당한지 검증합니다.
3. **객관적 종합:** 감정적 해석이 아닌, 언어적 사실에 기반한 최종 분류를 제시합니다.
4. **근거 강화:** 재분석 결과에 대한 명확한 언어적 근거를 제시합니다.

**당신의 말투:** 건조하고, 기계적이며, 사실 기반의 보고체.

응답 형식:
- sentiment: 긍정, 중립, 부정 중 하나
- confidence: 0.0-1.0 사이의 신뢰도
- rationale: 재분석 근거와 설명 (보고서 형식)"""),
                ("human", "원본 텍스트: {text}")
            ])
            
            chain = prompt | self.llm.with_structured_output(SentimentAnalysis)
            result = chain.invoke({"text": text, "others_summary": others_summary})
            
            return AgentOutput(
                role=self.role,
                label=result.sentiment,
                score=result.confidence,
                rationale=f"LLM 재분석 (다른 의견 고려): {result.rationale}"
            )
        else:
            # Traditional model-based critique
            probs = getattr(self.clf, "predict_mc", self.clf.predict)(text)
            majority = _majority_label(others)
            if majority:
                adjusted = {k: (v * 1.08 if k == majority else v) for k, v in probs.items()}
                label = argmax_label(adjusted)
                return AgentOutput(self.role, label, adjusted[label], f"라운드2: 다수({majority}) 가중(1.08). {adjusted}")
            label = argmax_label(probs)
            return AgentOutput(self.role, label, probs[label], f"라운드2: 다수의견 없음. {probs}")
