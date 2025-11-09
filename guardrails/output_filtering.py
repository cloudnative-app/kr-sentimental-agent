from typing import Dict, Any, List
import re


class OutputFilter:
    """Output filtering for sentiment analysis results."""
    
    def __init__(self):
        self.confidence_threshold = 0.3
        self.blocked_labels = set()  # Can be configured to block certain labels
    
    def filter_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """Filter and validate output from sentiment analysis."""
        filtered = output.copy()
        
        # Check confidence threshold
        if "score" in output and output["score"] < self.confidence_threshold:
            filtered["warning"] = f"Low confidence prediction: {output['score']:.3f}"
        
        # Check for blocked labels
        if "label" in output and output["label"] in self.blocked_labels:
            filtered["label"] = "중립"  # Default to neutral
            filtered["warning"] = f"Blocked label replaced with neutral"
        
        # Validate rationale
        if "rationale" in output:
            filtered["rationale"] = self._sanitize_rationale(output["rationale"])
        
        return filtered
    
    def _sanitize_rationale(self, rationale: str) -> str:
        """Sanitize rationale text."""
        # Remove potentially sensitive information
        rationale = re.sub(r'\b\d{3,}\b', '[숫자]', rationale)  # Replace long numbers
        rationale = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[이메일]', rationale)  # Replace emails
        
        # Limit length
        if len(rationale) > 500:
            rationale = rationale[:500] + "..."
        
        return rationale
    
    def validate_agent_output(self, agent_output) -> bool:
        """Validate agent output structure."""
        required_fields = ["role", "label", "score", "rationale"]
        
        for field in required_fields:
            if not hasattr(agent_output, field):
                return False
        
        # Validate score range
        if not (0 <= agent_output.score <= 1):
            return False
        
        # Validate label
        valid_labels = {"긍정", "중립", "부정"}
        if agent_output.label not in valid_labels:
            return False
        
        return True

