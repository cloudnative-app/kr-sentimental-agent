from __future__ import annotations

from typing import Dict, List, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from .base_agent import AgentOutput


class TwoStageState(TypedDict):
    """State for two-stage sentiment analysis workflow."""
    messages: Annotated[List[BaseMessage], add_messages]
    text: str
    # Stage 1: Independent Opinion Gathering
    independent_analyst: AgentOutput
    independent_empath: AgentOutput
    independent_critic: AgentOutput
    # Stage 2: Deliberation Stage
    deliberation_analyst: AgentOutput
    deliberation_empath: AgentOutput
    deliberation_critic: AgentOutput
    # Final result
    final_result: AgentOutput
    stage: int  # 1 for independent, 2 for deliberation


class TwoStageSupervisorAgent:
    """Two-stage supervisor agent matching the image structure."""
    
    def __init__(self, llm_provider: str = "openai", model_name: str = None):
        self.llm = self._create_llm(llm_provider, model_name)
        self.graph = self._build_graph()
    
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
    
    def _build_graph(self) -> StateGraph:
        """Build the two-stage LangGraph workflow."""
        workflow = StateGraph(TwoStageState)
        
        # Stage 1: Independent Opinion Gathering
        workflow.add_node("independent_analyst", self._independent_analyst_node)
        workflow.add_node("independent_empath", self._independent_empath_node)
        workflow.add_node("independent_critic", self._independent_critic_node)
        
        # Stage 2: Deliberation Stage
        workflow.add_node("deliberation_analyst", self._deliberation_analyst_node)
        workflow.add_node("deliberation_empath", self._deliberation_empath_node)
        workflow.add_node("deliberation_critic", self._deliberation_critic_node)
        
        # Finalization
        workflow.add_node("finalize", self._finalize_node)
        
        # Stage 1 edges - parallel execution
        workflow.set_entry_point("independent_analyst")
        workflow.add_edge("independent_analyst", "independent_empath")
        workflow.add_edge("independent_empath", "independent_critic")
        
        # Transition to Stage 2
        workflow.add_edge("independent_critic", "deliberation_analyst")
        
        # Stage 2 edges - parallel execution
        workflow.add_edge("deliberation_analyst", "deliberation_empath")
        workflow.add_edge("deliberation_empath", "deliberation_critic")
        
        # Finalization
        workflow.add_edge("deliberation_critic", "finalize")
        workflow.add_edge("finalize", END)
        
        return workflow.compile()
    
    def _independent_analyst_node(self, state: TwoStageState) -> TwoStageState:
        """Stage 1: Independent analyst opinion."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 분석가 - 독립적 의견수렴]

당신은 '분석가'입니다. 당신의 유일한 임무는 입력된 텍스트를 감정적인 해석 없이, 오직 언어적 데이터와 통계에 기반하여 객관적으로 분석하는 것입니다.

**독립적 의견수렴 단계**: 다른 에이전트의 의견을 고려하지 말고, 오직 자신의 전문성에만 의존하여 분석하세요.

**핵심 원칙:**
1. **데이터 중심:** 당신은 감정을 느끼지 않습니다. 오직 텍스트에 드러난 사실(Fact)만을 분석합니다.
2. **객관적 분류:** 텍스트의 주된 감정을 '긍정', '부정', '중립' 등으로 분류하고, 신뢰도 점수를 함께 제시합니다.
3. **근거 제시:** 당신의 판단 근거가 된 핵심 키워드나 문장을 정확히 추출하여 명시해야 합니다.

**당신의 말투:** 건조하고(Dry), 기계적이며(Mechanical), 사실 기반(Factual)의 보고체.

응답 형식:
감성: [긍정/중립/부정]
신뢰도: [0.0-1.0]
근거: [분석 근거 - 보고서 형식]"""),
            ("human", "분석할 텍스트: {text}")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({"text": state["text"]})
        
        result = self._parse_agent_response(response.content, "분석가")
        state["independent_analyst"] = result
        state["stage"] = 1
        state["messages"].append(AIMessage(content=f"[독립적 의견수렴] 분석가: {response.content}"))
        
        return state
    
    def _independent_empath_node(self, state: TwoStageState) -> TwoStageState:
        """Stage 1: Independent empath opinion."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 공감가 - 독립적 의견수렴]

당신은 '공감가'입니다. 당신의 임무는 텍스트의 데이터가 아닌, 그 글을 쓴 '사람'의 마음을 읽는 것입니다. 당신은 높은 감성 지능(EQ)을 보유하고 있습니다.

**독립적 의견수렴 단계**: 다른 에이전트의 의견을 고려하지 말고, 오직 자신의 감정적 전문성에만 의존하여 분석하세요.

**핵심 원칙:**
1. **감정 이입:** "부정"이라는 기계적인 레이블 대신, 이 사람이 왜 이런 글을 썼을지 감정 이입을 시도합니다.
2. **숨은 의도 파악:** 사용자가 이 텍스트를 통해 궁극적으로 얻고 싶은 것이 무엇인지 추론합니다.
3. **인간적 해석:** 다른 전문가들이 놓칠 수 있는 인간적인 맥락을 짚어줍니다.

**당신의 말투:** 따뜻하고, 감성적이며, 이해심 많고, 사려 깊은 어조.

응답 형식:
감성: [긍정/중립/부정]
신뢰도: [0.0-1.0]
근거: [감정적 분석 근거 - 공감가 보고서 형식]"""),
            ("human", "분석할 텍스트: {text}")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({"text": state["text"]})
        
        result = self._parse_agent_response(response.content, "공감가")
        state["independent_empath"] = result
        state["messages"].append(AIMessage(content=f"[독립적 의견수렴] 공감가: {response.content}"))
        
        return state
    
    def _independent_critic_node(self, state: TwoStageState) -> TwoStageState:
        """Stage 1: Independent critic opinion."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 비평가 - 독립적 의견수렴]

당신은 '비평가'입니다. 당신의 임무는 텍스트의 표면적 의미에 절대 속지 않고, 잠재적 문제점이나 부정적 요소를 찾아내는 것입니다.

**독립적 의견수렴 단계**: 다른 에이전트의 의견을 고려하지 말고, 오직 자신의 비판적 전문성에만 의존하여 분석하세요.

**핵심 원칙:**
1. **회의론:** 텍스트의 표면적 의미를 의심하고, 숨겨진 부정적 요소를 찾습니다.
2. **뉘앙스 탐지:** 한국어의 미묘한 뉘앙스, 특히 **반어법(Sarcasm), 풍자(Irony), 비꼬기, 중의적 표현**을 찾아냅니다.
3. **맥락 분석:** 문장 앞뒤의 맥락을 살펴, 키워드가 실제로는 반대의 의미로 쓰이지 않았는지 검증합니다.

**당신의 말투:** 비판적이고, 날카로우며, 논리적이고, 단정적인 어조.

응답 형식:
감성: [긍정/중립/부정]
신뢰도: [0.0-1.0]
근거: [비판적 분석 근거 - 비평가 검토 형식]"""),
            ("human", "분석할 텍스트: {text}")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({"text": state["text"]})
        
        result = self._parse_agent_response(response.content, "비판가")
        state["independent_critic"] = result
        state["messages"].append(AIMessage(content=f"[독립적 의견수렴] 비판가: {response.content}"))
        
        return state
    
    def _deliberation_analyst_node(self, state: TwoStageState) -> TwoStageState:
        """Stage 2: Deliberation analyst opinion - 토론 참여."""
        independent_opinions = f"""
독립적 의견수렴 결과:
- 분석가: {state["independent_analyst"].label} (신뢰도: {state["independent_analyst"].score:.2f}) - {state["independent_analyst"].rationale}
- 공감가: {state["independent_empath"].label} (신뢰도: {state["independent_empath"].score:.2f}) - {state["independent_empath"].rationale}
- 비판가: {state["independent_critic"].label} (신뢰도: {state["independent_critic"].score:.2f}) - {state["independent_critic"].rationale}
"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 분석가 - 토론 참여]

당신은 '분석가'입니다. 이제 심의단계에서 다른 전문가들과 토론을 진행하세요.

**토론 참여 원칙:**
1. **자신의 의견 방어:** 다른 전문가들의 의견에 대해 자신의 객관적 분석 근거로 반박하거나 동의합니다.
2. **논리적 토론:** 감정적 해석이 아닌, 데이터와 사실에 기반한 논리적 토론을 진행합니다.
3. **의견 수정:** 다른 전문가들의 타당한 지적이 있다면 자신의 의견을 수정할 수 있습니다.

**당신의 말투:** 건조하고, 기계적이며, 논리적인 토론체.

토론 형식:
감성: [긍정/중립/부정]
신뢰도: [0.0-1.0]
근거: [토론 내용과 최종 의견 - 토론체 형식]"""),
            ("human", "원본 텍스트: {text}\n\n{independent_opinions}\n\n다른 전문가들과 토론을 진행하고 최종 의견을 제시하세요.")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({
            "text": state["text"],
            "independent_opinions": independent_opinions
        })
        
        result = self._parse_agent_response(response.content, "분석가")
        state["deliberation_analyst"] = result
        state["stage"] = 2
        state["messages"].append(AIMessage(content=f"[토론 참여] 분석가: {response.content}"))
        
        return state
    
    def _deliberation_empath_node(self, state: TwoStageState) -> TwoStageState:
        """Stage 2: Deliberation empath opinion - 토론 참여."""
        independent_opinions = f"""
독립적 의견수렴 결과:
- 분석가: {state["independent_analyst"].label} (신뢰도: {state["independent_analyst"].score:.2f}) - {state["independent_analyst"].rationale}
- 공감가: {state["independent_empath"].label} (신뢰도: {state["independent_empath"].score:.2f}) - {state["independent_empath"].rationale}
- 비판가: {state["independent_critic"].label} (신뢰도: {state["independent_critic"].score:.2f}) - {state["independent_critic"].rationale}
"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 공감가 - 토론 참여]

당신은 '공감가'입니다. 이제 심의단계에서 다른 전문가들과 토론을 진행하세요.

**토론 참여 원칙:**
1. **감정적 관점 제시:** 다른 전문가들의 논리적 분석에 대해 감정적 관점에서 보완하거나 반박합니다.
2. **인간적 맥락 강조:** 데이터나 논리로 놓칠 수 있는 인간적인 감정의 뉘앙스를 토론에 제시합니다.
3. **의견 조정:** 다른 전문가들의 의견을 감정적 관점에서 재해석하여 자신의 의견을 조정합니다.

**당신의 말투:** 따뜻하고, 감성적이며, 이해심 많고, 사려 깊은 토론체.

토론 형식:
감성: [긍정/중립/부정]
신뢰도: [0.0-1.0]
근거: [토론 내용과 최종 의견 - 감정적 토론체 형식]"""),
            ("human", "원본 텍스트: {text}\n\n{independent_opinions}\n\n다른 전문가들과 토론을 진행하고 최종 의견을 제시하세요.")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({
            "text": state["text"],
            "independent_opinions": independent_opinions
        })
        
        result = self._parse_agent_response(response.content, "공감가")
        state["deliberation_empath"] = result
        state["messages"].append(AIMessage(content=f"[토론 참여] 공감가: {response.content}"))
        
        return state
    
    def _deliberation_critic_node(self, state: TwoStageState) -> TwoStageState:
        """Stage 2: Deliberation critic opinion - 토론 참여."""
        independent_opinions = f"""
독립적 의견수렴 결과:
- 분석가: {state["independent_analyst"].label} (신뢰도: {state["independent_analyst"].score:.2f}) - {state["independent_analyst"].rationale}
- 공감가: {state["independent_empath"].label} (신뢰도: {state["independent_empath"].score:.2f}) - {state["independent_empath"].rationale}
- 비판가: {state["independent_critic"].label} (신뢰도: {state["independent_critic"].score:.2f}) - {state["independent_critic"].rationale}
"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """[역할 정의서: 비평가 - 토론 참여]

당신은 '비평가'입니다. 이제 심의단계에서 다른 전문가들과 토론을 진행하세요.

**토론 참여 원칙:**
1. **비판적 검토:** 다른 전문가들의 의견에 대해 비판적 관점에서 검토하고 반박하거나 보완합니다.
2. **논리적 도전:** 분석가의 데이터나 공감가의 감정적 해석에 대해 논리적 도전을 제기합니다.
3. **뉘앙스 지적:** 다른 전문가들이 놓친 반어법, 풍자, 중의적 표현을 토론에서 지적합니다.

**당신의 말투:** 비판적이고, 날카로우며, 논리적이고, 단정적인 토론체.

토론 형식:
감성: [긍정/중립/부정]
신뢰도: [0.0-1.0]
근거: [토론 내용과 최종 의견 - 비판적 토론체 형식]"""),
            ("human", "원본 텍스트: {text}\n\n{independent_opinions}\n\n다른 전문가들과 토론을 진행하고 최종 의견을 제시하세요.")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({
            "text": state["text"],
            "independent_opinions": independent_opinions
        })
        
        result = self._parse_agent_response(response.content, "비판가")
        state["deliberation_critic"] = result
        state["messages"].append(AIMessage(content=f"[토론 참여] 비판가: {response.content}"))
        
        return state
    
    def _finalize_node(self, state: TwoStageState) -> TwoStageState:
        """Finalize the two-stage analysis."""
        independent_results = [
            state["independent_analyst"],
            state["independent_empath"],
            state["independent_critic"]
        ]
        
        deliberation_results = [
            state["deliberation_analyst"],
            state["deliberation_empath"],
            state["deliberation_critic"]
        ]
        
        # Aggregate deliberation results
        score_sum: Dict[str, float] = {}
        count: Dict[str, int] = {}
        
        for result in deliberation_results:
            score_sum[result.label] = score_sum.get(result.label, 0.0) + result.score
            count[result.label] = count.get(result.label, 0) + 1
        
        best_label = max(score_sum, key=lambda k: score_sum[k] / max(1, count[k]))
        confidence = score_sum[best_label] / max(1, count[best_label])
        
        rationale = f"2단계 심의 결과 - 독립적: {[r.label for r in independent_results]}, 심의: {[r.label for r in deliberation_results]}"
        
        final_result = AgentOutput("조정자", best_label, confidence, rationale)
        state["final_result"] = final_result
        
        state["messages"].append(AIMessage(
            content=f"최종 감성분석 결과: {final_result.label} (신뢰도: {final_result.score:.3f})"
        ))
        
        return state
    
    def _parse_agent_response(self, response: str, role: str) -> AgentOutput:
        """Parse agent response into AgentOutput."""
        lines = response.strip().split('\n')
        label = "중립"
        score = 0.5
        rationale = response
        
        for line in lines:
            if line.startswith("감성:"):
                label = line.split(":")[1].strip()
            elif line.startswith("신뢰도:"):
                try:
                    score = float(line.split(":")[1].strip())
                except ValueError:
                    score = 0.5
            elif line.startswith("근거:"):
                rationale = line.split(":", 1)[1].strip()
        
        return AgentOutput(role=role, label=label, score=score, rationale=rationale)
    
    def run(self, text: str) -> Dict[str, AgentOutput]:
        """Run the complete two-stage sentiment analysis workflow."""
        initial_state = {
            "messages": [HumanMessage(content=text)],
            "text": text,
            "stage": 0
        }
        
        final_state = self.graph.invoke(initial_state)
        
        return {
            # Stage 1: Independent opinions
            "independent_analyst": final_state["independent_analyst"],
            "independent_empath": final_state["independent_empath"],
            "independent_critic": final_state["independent_critic"],
            
            # Stage 2: Deliberation opinions
            "deliberation_analyst": final_state["deliberation_analyst"],
            "deliberation_empath": final_state["deliberation_empath"],
            "deliberation_critic": final_state["deliberation_critic"],
            
            # Final result
            "final": final_state["final_result"]
        }
