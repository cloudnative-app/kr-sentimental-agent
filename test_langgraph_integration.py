#!/usr/bin/env python3
"""
LangGraph 통합 테스트 스크립트
"""

import os
import sys
sys.path.append(os.path.dirname(__file__))

from agents.supervisor_agent import SupervisorAgent
from agents.two_stage_supervisor import TwoStageSupervisorAgent


def test_llm_specialized_agents():
    """Test LLM-based specialized agents."""
    print("🧪 Testing LLM-based specialized agents...")
    
    try:
        # Create LLM-based agents
        from agents.specialized_agents import AnalystAgent, EmpathAgent, CriticAgent
        
        analyst = AnalystAgent("openai", "openai", "gpt-3.5-turbo")
        empath = EmpathAgent("openai", "openai", "gpt-3.5-turbo")
        critic = CriticAgent("openai", "openai", "gpt-3.5-turbo")
        
        test_text = "오늘 날씨가 정말 좋아서 기분이 상쾌해!"
        
        # Test individual agents
        analyst_result = analyst.run(test_text)
        empath_result = empath.run(test_text)
        critic_result = critic.run(test_text)
        
        print(f"✅ LLM Analyst: {analyst_result.label} ({analyst_result.score:.3f})")
        print(f"✅ LLM Empath: {empath_result.label} ({empath_result.score:.3f})")
        print(f"✅ LLM Critic: {critic_result.label} ({critic_result.score:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM specialized agents test failed: {e}")
        return False


def test_langchain_agents():
    """Test LangChain-based individual agents."""
    print("\n🧪 Testing LangChain-based individual agents...")
    
    try:
        # Create agents
        analyst = LangChainAnalystAgent("openai", "gpt-3.5-turbo")
        empath = LangChainEmpathAgent("openai", "gpt-3.5-turbo")
        critic = LangChainCriticAgent("openai", "gpt-3.5-turbo")
        
        test_text = "오늘 날씨가 정말 좋아서 기분이 상쾌해!"
        
        # Test individual agents
        analyst_result = analyst.run(test_text)
        empath_result = empath.run(test_text)
        critic_result = critic.run(test_text)
        
        print(f"✅ LangChain Analyst: {analyst_result.label} ({analyst_result.score:.3f})")
        print(f"✅ LangChain Empath: {empath_result.label} ({empath_result.score:.3f})")
        print(f"✅ LangChain Critic: {critic_result.label} ({critic_result.score:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ LangChain agents test failed: {e}")
        return False


def test_langgraph_supervisor():
    """Test LangGraph-based supervisor."""
    print("\n🧪 Testing LangGraph-based supervisor...")
    
    try:
        # Create LangGraph supervisor
        supervisor = LangGraphSupervisorAgent("openai", "gpt-3.5-turbo")
        
        test_text = "이 영화는 정말 재미없었어. 시간 낭비였어."
        
        # Test supervisor
        results = supervisor.run(test_text)
        
        print(f"✅ Analyst: {results['analyst'].label} ({results['analyst'].score:.3f})")
        print(f"✅ Empath: {results['empath'].label} ({results['empath'].score:.3f})")
        print(f"✅ Critic: {results['critic'].label} ({results['critic'].score:.3f})")
        print(f"✅ Final: {results['final'].label} ({results['final'].score:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ LangGraph supervisor test failed: {e}")
        return False


def test_two_stage_supervisor():
    """Test two-stage supervisor (matches image structure)."""
    print("\n🧪 Testing two-stage supervisor...")
    
    try:
        # Create two-stage supervisor
        supervisor = TwoStageSupervisorAgent("openai", "gpt-3.5-turbo")
        
        test_text = "참 잘하는 짓이다... 정말 대단해!"
        
        # Test two-stage workflow
        results = supervisor.run(test_text)
        
        print(f"✅ Independent Analyst: {results['independent_analyst'].label} ({results['independent_analyst'].score:.3f})")
        print(f"✅ Independent Empath: {results['independent_empath'].label} ({results['independent_empath'].score:.3f})")
        print(f"✅ Independent Critic: {results['independent_critic'].label} ({results['independent_critic'].score:.3f})")
        print(f"✅ Deliberation Analyst: {results['deliberation_analyst'].label} ({results['deliberation_analyst'].score:.3f})")
        print(f"✅ Deliberation Empath: {results['deliberation_empath'].label} ({results['deliberation_empath'].score:.3f})")
        print(f"✅ Deliberation Critic: {results['deliberation_critic'].label} ({results['deliberation_critic'].score:.3f})")
        print(f"✅ Final: {results['final'].label} ({results['final'].score:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ Two-stage supervisor test failed: {e}")
        return False


def test_unified_supervisor():
    """Test unified supervisor with different modes."""
    print("\n🧪 Testing unified supervisor...")
    
    try:
        test_text = "참 잘하는 짓이다... 정말 대단해!"
        
        # Test Two-Stage mode (matches image)
        print("Testing Two-Stage mode...")
        supervisor_ts = SupervisorAgent(llm_provider="openai", model_name="gpt-3.5-turbo")
        results_ts = supervisor_ts.run(test_text)
        print(f"✅ Two-Stage Final: {results_ts['final'].label} ({results_ts['final'].score:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ Unified supervisor test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Starting LangGraph/LangChain integration tests...\n")
    
    # Check environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Some tests may fail.")
    
    tests = [
        test_llm_specialized_agents,
        test_langchain_agents,
        test_langgraph_supervisor,
        test_two_stage_supervisor,
        test_unified_supervisor
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! LangGraph/LangChain integration is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the error messages above.")
        return 1


if __name__ == "__main__":
    exit(main())
