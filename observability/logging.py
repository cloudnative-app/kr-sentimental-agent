import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


def setup_logger(
    name: str = "kr_sentiment",
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """Setup logger with console and optional file output."""
    
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_formatter = logging.Formatter(format_string)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, level.upper()))
        file_formatter = logging.Formatter(format_string)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "kr_sentiment") -> logging.Logger:
    """Get existing logger or create a new one."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        # If no handlers exist, setup default logger
        return setup_logger(name)
    return logger


class SentimentLogger:
    """Specialized logger for sentiment analysis operations."""
    
    def __init__(self, name: str = "sentiment_analysis"):
        self.logger = get_logger(name)
    
    def log_prediction(self, text: str, prediction: str, confidence: float, agent_role: str = ""):
        """Log prediction results."""
        self.logger.info(
            f"Prediction - Text: {text[:50]}... | "
            f"Label: {prediction} | "
            f"Confidence: {confidence:.3f} | "
            f"Agent: {agent_role}"
        )
    
    def log_experiment(self, experiment_name: str, condition: str, results: dict):
        """Log experiment results."""
        self.logger.info(
            f"Experiment - {experiment_name} | "
            f"Condition: {condition} | "
            f"Results: {results}"
        )
    
    def log_error(self, error: Exception, context: str = ""):
        """Log errors with context."""
        self.logger.error(f"Error in {context}: {str(error)}", exc_info=True)
    
    def log_performance(self, operation: str, duration: float, details: dict = None):
        """Log performance metrics."""
        details_str = f" | Details: {details}" if details else ""
        self.logger.info(f"Performance - {operation} took {duration:.3f}s{details_str}")

