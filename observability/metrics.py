import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
import json


@dataclass
class PerformanceMetrics:
    """Performance metrics for sentiment analysis."""
    total_predictions: int = 0
    total_errors: int = 0
    avg_prediction_time: float = 0.0
    avg_confidence: float = 0.0
    label_distribution: Dict[str, int] = field(default_factory=dict)
    agent_performance: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recent_predictions: deque = field(default_factory=lambda: deque(maxlen=100))


class MetricsCollector:
    """Collect and manage metrics for sentiment analysis system."""
    
    def __init__(self):
        self.metrics = PerformanceMetrics()
        self.prediction_times = deque(maxlen=1000)
        self.confidence_scores = deque(maxlen=1000)
        self.start_time = time.time()
    
    def record_prediction(
        self,
        text: str,
        prediction: str,
        confidence: float,
        agent_role: str = "",
        prediction_time: Optional[float] = None
    ):
        """Record a prediction with its metrics."""
        if prediction_time is None:
            prediction_time = 0.0
        
        # Update counters
        self.metrics.total_predictions += 1
        self.metrics.label_distribution[prediction] = self.metrics.label_distribution.get(prediction, 0) + 1
        
        # Update time metrics
        self.prediction_times.append(prediction_time)
        self.metrics.avg_prediction_time = sum(self.prediction_times) / len(self.prediction_times)
        
        # Update confidence metrics
        self.confidence_scores.append(confidence)
        self.metrics.avg_confidence = sum(self.confidence_scores) / len(self.confidence_scores)
        
        # Update agent performance
        if agent_role:
            if agent_role not in self.metrics.agent_performance:
                self.metrics.agent_performance[agent_role] = {
                    "total_predictions": 0,
                    "avg_confidence": 0.0,
                    "avg_time": 0.0,
                    "label_distribution": defaultdict(int)
                }
            
            agent_metrics = self.metrics.agent_performance[agent_role]
            agent_metrics["total_predictions"] += 1
            agent_metrics["label_distribution"][prediction] += 1
            
            # Update agent averages
            agent_confidences = [c for _, _, c, role, _ in self.metrics.recent_predictions if role == agent_role]
            if agent_confidences:
                agent_metrics["avg_confidence"] = sum(agent_confidences) / len(agent_confidences)
        
        # Store recent prediction
        self.metrics.recent_predictions.append((text, prediction, confidence, agent_role, prediction_time))
    
    def record_error(self, error: Exception, context: str = ""):
        """Record an error occurrence."""
        self.metrics.total_errors += 1
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of current metrics."""
        uptime = time.time() - self.start_time
        
        return {
            "uptime_seconds": uptime,
            "total_predictions": self.metrics.total_predictions,
            "total_errors": self.metrics.total_errors,
            "error_rate": self.metrics.total_errors / max(1, self.metrics.total_predictions),
            "avg_prediction_time": self.metrics.avg_prediction_time,
            "avg_confidence": self.metrics.avg_confidence,
            "label_distribution": dict(self.metrics.label_distribution),
            "agent_performance": {
                agent: {
                    "total_predictions": metrics["total_predictions"],
                    "avg_confidence": metrics["avg_confidence"],
                    "label_distribution": dict(metrics["label_distribution"])
                }
                for agent, metrics in self.metrics.agent_performance.items()
            },
            "recent_predictions_count": len(self.metrics.recent_predictions)
        }
    
    def export_metrics(self, filepath: str):
        """Export metrics to a JSON file."""
        metrics_data = self.get_metrics_summary()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metrics_data, f, ensure_ascii=False, indent=2)
    
    def reset_metrics(self):
        """Reset all metrics."""
        self.metrics = PerformanceMetrics()
        self.prediction_times.clear()
        self.confidence_scores.clear()
        self.start_time = time.time()

