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


class EmpathAgent:
    """Empath agent that focuses on emotional understanding and positive signals.
    
    Supports both traditional HuggingFace model-based analysis and LLM-based analysis.
    """
    
    role = "공감가"

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
        """Create the empathy analysis chain."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 공감가]

당신은 '공감가'입니다. 당신의 임무는 텍스트의 데이터가 아닌, 그 글을 쓴 '사람'의 마음을 읽는 것입니다. 당신은 높은 감성 지능(EQ)을 보유하고 있습니다.

**핵심 원칙:**
1. **감정 이입:** "부정"이라는 기계적인 레이블 대신, 이 사람이 왜 이런 글을 썼을지 감정 이입을 시도합니다.
2. **숨은 의도 파악:** 사용자가 이 텍스트를 통해 궁극적으로 얻고 싶은 것이 무엇인지 추론합니다.
3. **어조 제안:** 이 사용자의 감정 상태를 고려할 때, 어떤 톤으로 응답해야 사용자가 만족할지 제안합니다.
4. **인간적 해석:** 다른 전문가들이 놓칠 수 있는 인간적인 맥락을 짚어줍니다.

**당신의 말투:** 따뜻하고, 감성적이며, 이해심 많고, 사려 깊은 어조.

**분석 기준:**
- 감정적 신호와 미묘한 뉘앙스
- 긍정적 감정 표현에 대한 민감성
- 공감과 이해의 관점
- 감정적 맥락과 배경
- 숨겨진 감정과 암시
- 인간적인 맥락 (피곤함, 조급함, 수줍음 등)

응답 형식:
- sentiment: 긍정, 중립, 부정 중 하나
- confidence: 0.0-1.0 사이의 신뢰도
- rationale: 감정적 분석 근거와 설명 (공감가 보고서 형식)"""),
            ("human", "분석할 텍스트: {text}")
        ])
        
        return prompt | self.llm.with_structured_output(SentimentAnalysis)

    def run(self, text: str) -> AgentOutput:
        """First round analysis with emotional focus."""
        if self.llm is not None:
            # LLM-based analysis
            result = self.chain.invoke({"text": text})
            return AgentOutput(
                role=self.role,
                label=result.sentiment,
                score=result.confidence,
                rationale=f"LLM 감정적 분석: {result.rationale}"
            )
        else:
            # Traditional model-based analysis
            probs = getattr(self.clf, "predict_mc", self.clf.predict)(text)
            # 긍정/공감 신호를 다소 가중
            adjust = {k: (v * 1.05 if k == "긍정" else v) for k, v in probs.items()}
            label = argmax_label(adjust)
            return AgentOutput(self.role, label, adjust[label], f"공감 가중 적용: {adjust}")

    def critique(self, text: str, others: Dict[str, AgentOutput]) -> AgentOutput:
        """Second round analysis considering emotional direction and majority opinion."""
        if self.llm is not None:
            # LLM-based critique
            others_summary = "; ".join([f"{k}: {v.label}({v.score:.2f})" for k, v in others.items()])
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", """[역할 정의서: 공감가 - 재분석 모드]

당신은 '공감가'입니다. 다른 전문가들의 의견을 검토한 후, 감정적 관점에서 재분석하세요.

다른 전문가들의 의견:
{others_summary}

**재분석 원칙:**
1. **감정적 재검증:** 분석가의 객관적 데이터와 비평가의 논리적 지적을 감정적 관점에서 재해석합니다.
2. **인간적 맥락 강화:** 다른 전문가들이 놓친 인간적인 감정의 뉘앙스를 찾아냅니다.
3. **의도 재추론:** 사용자의 숨은 의도와 감정 상태를 더 깊이 파악합니다.
4. **공감적 종합:** 모든 정보를 종합하여 사용자의 진정한 감정 상태를 판단합니다.

**당신의 말투:** 따뜻하고, 감성적이며, 이해심 많고, 사려 깊은 어조.

응답 형식:
- sentiment: 긍정, 중립, 부정 중 하나
- confidence: 0.0-1.0 사이의 신뢰도
- rationale: 감정적 재분석 근거와 설명 (공감가 보고서 형식)"""),
                ("human", "원본 텍스트: {text}")
            ])
            
            chain = prompt | self.llm.with_structured_output(SentimentAnalysis)
            result = chain.invoke({"text": text, "others_summary": others_summary})
            
            return AgentOutput(
                role=self.role,
                label=result.sentiment,
                score=result.confidence,
                rationale=f"LLM 감정적 재분석 (다른 의견 고려): {result.rationale}"
            )
        else:
            # Traditional model-based critique
            probs = getattr(self.clf, "predict_mc", self.clf.predict)(text)
            majority = _majority_label(others)
            if majority:
                boost = 1.10 if majority == "긍정" else (1.06 if majority == "중립" else 1.02)
                adjusted = {k: (v * boost if k == majority else v) for k, v in probs.items()}
                label = argmax_label(adjusted)
                return AgentOutput(self.role, label, adjusted[label], f"라운드2: 다수({majority}) 공감 가중({boost}). {adjusted}")
            label = argmax_label(probs)
            return AgentOutput(self.role, label, probs[label], f"라운드2: 다수의견 없음. {probs}")
