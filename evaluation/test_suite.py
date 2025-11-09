from typing import List, Dict, Any
import pandas as pd
from pathlib import Path


class TestSuite:
    """Test suite for sentiment analysis evaluation."""
    
    def __init__(self):
        self.test_cases = []
    
    def add_test_case(self, text: str, expected_label: str, description: str = ""):
        """Add a test case to the suite."""
        self.test_cases.append({
            "text": text,
            "expected_label": expected_label,
            "description": description
        })
    
    def load_from_csv(self, csv_path: str, text_column: str = "text", label_column: str = "label"):
        """Load test cases from a CSV file."""
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            self.add_test_case(
                text=row[text_column],
                expected_label=row[label_column],
                description=f"CSV row {row.name}"
            )
    
    def run_tests(self, predictor_func) -> Dict[str, Any]:
        """Run all test cases and return results."""
        results = {
            "total": len(self.test_cases),
            "correct": 0,
            "incorrect": 0,
            "details": []
        }
        
        for i, test_case in enumerate(self.test_cases):
            try:
                prediction = predictor_func(test_case["text"])
                is_correct = prediction == test_case["expected_label"]
                
                if is_correct:
                    results["correct"] += 1
                else:
                    results["incorrect"] += 1
                
                results["details"].append({
                    "test_id": i,
                    "text": test_case["text"],
                    "expected": test_case["expected_label"],
                    "predicted": prediction,
                    "correct": is_correct,
                    "description": test_case["description"]
                })
            except Exception as e:
                results["incorrect"] += 1
                results["details"].append({
                    "test_id": i,
                    "text": test_case["text"],
                    "expected": test_case["expected_label"],
                    "predicted": f"ERROR: {str(e)}",
                    "correct": False,
                    "description": test_case["description"]
                })
        
        results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
        return results
    
    def save_results(self, results: Dict[str, Any], output_path: str):
        """Save test results to a JSON file."""
        import json
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

