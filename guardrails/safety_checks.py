from typing import Dict, Any, List
import re


class SafetyChecker:
    """Safety checks for sentiment analysis system."""
    
    def __init__(self):
        self.toxic_patterns = [
            r'욕설|비속어|욕|씨발|개새끼|지랄|병신|미친|바보|멍청이',
            r'혐오|차별|편견|인종차별|성차별',
            r'자살|자해|목숨|죽고|죽어',
        ]
        self.sensitive_topics = [
            r'정치|선거|정부|대통령|국회의원',
            r'종교|기독교|불교|이슬람|힌두교',
            r'성|섹스|성관계|임신|낙태',
        ]
    
    def check_safety(self, text: str) -> Dict[str, Any]:
        """Perform safety checks on input text."""
        result = {
            "safe": True,
            "warnings": [],
            "blocked": False,
            "risk_level": "low"
        }
        
        # Check for toxic content
        toxic_found = []
        for pattern in self.toxic_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                toxic_found.append(pattern)
        
        if toxic_found:
            result["safe"] = False
            result["blocked"] = True
            result["risk_level"] = "high"
            result["warnings"].append(f"Toxic content detected: {toxic_found}")
        
        # Check for sensitive topics
        sensitive_found = []
        for pattern in self.sensitive_topics:
            if re.search(pattern, text, re.IGNORECASE):
                sensitive_found.append(pattern)
        
        if sensitive_found:
            result["warnings"].append(f"Sensitive topics detected: {sensitive_found}")
            if result["risk_level"] == "low":
                result["risk_level"] = "medium"
        
        # Check for personal information
        personal_info = self._check_personal_info(text)
        if personal_info:
            result["warnings"].append(f"Potential personal information: {personal_info}")
            if result["risk_level"] == "low":
                result["risk_level"] = "medium"
        
        return result
    
    def _check_personal_info(self, text: str) -> List[str]:
        """Check for potential personal information."""
        found = []
        
        # Korean phone number pattern
        if re.search(r'\d{2,3}-\d{3,4}-\d{4}', text):
            found.append("phone_number")
        
        # Korean address pattern
        if re.search(r'[가-힣]+시\s+[가-힣]+구\s+[가-힣]+동', text):
            found.append("address")
        
        # Korean name pattern (simple heuristic)
        if re.search(r'[가-힣]{2,4}씨|[가-힣]{2,4}님', text):
            found.append("name")
        
        return found
    
    def should_block(self, text: str) -> bool:
        """Determine if text should be blocked from processing."""
        safety_result = self.check_safety(text)
        return safety_result["blocked"] or safety_result["risk_level"] == "high"

