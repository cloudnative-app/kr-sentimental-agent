from __future__ import annotations

from typing import Dict
from .two_stage_supervisor import TwoStageSupervisorAgent


class SupervisorAgent:
    """Two-stage supervisor agent that coordinates multiple specialized agents.
    
    This class provides a unified interface for the two-stage sentiment analysis system
    that matches the image structure with independent opinion gathering and deliberation stages.
    """
    
    def __init__(self, llm_provider: str = "openai", model_name: str = None):
        """Initialize the two-stage supervisor agent.
        
        Args:
            llm_provider: LLM provider ("openai", "anthropic", "google")
            model_name: Specific model name (optional)
        """
        self.two_stage_supervisor = TwoStageSupervisorAgent(llm_provider, model_name)

    def run(self, text: str) -> Dict[str, any]:
        """Run the complete two-stage sentiment analysis process.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary containing:
            - independent_analyst: Independent analyst opinion
            - independent_empath: Independent empath opinion  
            - independent_critic: Independent critic opinion
            - deliberation_analyst: Deliberation analyst opinion
            - deliberation_empath: Deliberation empath opinion
            - deliberation_critic: Deliberation critic opinion
            - final: Final aggregated result
        """
        return self.two_stage_supervisor.run(text)
