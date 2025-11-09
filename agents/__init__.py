"""
Agents module for KR Sentiment Agent.

This module contains the multi-agent system for sentiment analysis,
including base agent interfaces, supervisor agent, and specialized agents.
Supports both traditional and LangChain/LangGraph-based implementations.
"""

from .base_agent import Agent, AgentOutput, SentimentClassifier
from .supervisor_agent import SupervisorAgent
from .specialized_agents import AnalystAgent, EmpathAgent, CriticAgent
from .two_stage_supervisor import TwoStageSupervisorAgent

__all__ = [
    # Base classes
    "Agent",
    "AgentOutput", 
    "SentimentClassifier",
    
    # Traditional agents
    "SupervisorAgent",
    "AnalystAgent",
    "EmpathAgent",
    "CriticAgent",
    
    
    # Two-stage supervisor (matches image structure)
    "TwoStageSupervisorAgent",
]

