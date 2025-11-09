import re
from typing import List, Dict, Any, Optional


class InputValidator:
    """Input validation for sentiment analysis."""
    
    def __init__(self, max_length: int = 1000, min_length: int = 1):
        self.max_length = max_length
        self.min_length = min_length
        self.blocked_patterns = [
            r'<script.*?>.*?</script>',  # Script tags
            r'javascript:',  # JavaScript URLs
            r'data:.*?base64',  # Data URLs
        ]
    
    def validate(self, text: str) -> Dict[str, Any]:
        """Validate input text and return validation results."""
        result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Length validation
        if len(text) < self.min_length:
            result["valid"] = False
            result["errors"].append(f"Text too short (minimum {self.min_length} characters)")
        
        if len(text) > self.max_length:
            result["valid"] = False
            result["errors"].append(f"Text too long (maximum {self.max_length} characters)")
        
        # Security validation
        for pattern in self.blocked_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                result["valid"] = False
                result["errors"].append(f"Potentially malicious content detected: {pattern}")
        
        # Content validation
        if not text.strip():
            result["valid"] = False
            result["errors"].append("Empty or whitespace-only text")
        
        # Language validation (basic Korean text check)
        korean_chars = len(re.findall(r'[가-힣]', text))
        total_chars = len(re.sub(r'\s', '', text))
        
        if total_chars > 0 and korean_chars / total_chars < 0.1:
            result["warnings"].append("Text may not be primarily in Korean")
        
        return result
    
    def sanitize(self, text: str) -> str:
        """Sanitize input text by removing potentially harmful content."""
        # Remove script tags
        text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

