import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import contextmanager
import json


@dataclass
class TraceSpan:
    """A single span in a trace."""
    span_id: str
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    parent_span_id: Optional[str] = None
    child_span_ids: List[str] = field(default_factory=list)


@dataclass
class Trace:
    """A complete trace containing multiple spans."""
    trace_id: str
    start_time: float
    end_time: Optional[float] = None
    spans: Dict[str, TraceSpan] = field(default_factory=dict)
    root_span_id: Optional[str] = None


class TraceCollector:
    """Collect and manage distributed traces for sentiment analysis."""
    
    def __init__(self):
        self.active_traces: Dict[str, Trace] = {}
        self.completed_traces: List[Trace] = []
        self.max_traces = 1000
    
    def start_trace(self, operation_name: str, trace_id: Optional[str] = None) -> str:
        """Start a new trace."""
        if trace_id is None:
            trace_id = str(uuid.uuid4())
        
        span_id = str(uuid.uuid4())
        span = TraceSpan(
            span_id=span_id,
            operation_name=operation_name,
            start_time=time.time()
        )
        
        trace = Trace(
            trace_id=trace_id,
            start_time=time.time(),
            root_span_id=span_id
        )
        trace.spans[span_id] = span
        
        self.active_traces[trace_id] = trace
        return trace_id
    
    def start_span(
        self,
        trace_id: str,
        operation_name: str,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None
    ) -> str:
        """Start a new span within a trace."""
        if trace_id not in self.active_traces:
            raise ValueError(f"Trace {trace_id} not found")
        
        trace = self.active_traces[trace_id]
        span_id = str(uuid.uuid4())
        
        span = TraceSpan(
            span_id=span_id,
            operation_name=operation_name,
            start_time=time.time(),
            parent_span_id=parent_span_id,
            tags=tags or {}
        )
        
        trace.spans[span_id] = span
        
        # Update parent-child relationships
        if parent_span_id and parent_span_id in trace.spans:
            trace.spans[parent_span_id].child_span_ids.append(span_id)
        
        return span_id
    
    def finish_span(self, trace_id: str, span_id: str):
        """Finish a span and calculate its duration."""
        if trace_id not in self.active_traces:
            return
        
        trace = self.active_traces[trace_id]
        if span_id not in trace.spans:
            return
        
        span = trace.spans[span_id]
        span.end_time = time.time()
        span.duration = span.end_time - span.start_time
    
    def add_span_tag(self, trace_id: str, span_id: str, key: str, value: Any):
        """Add a tag to a span."""
        if trace_id in self.active_traces and span_id in self.active_traces[trace_id].spans:
            self.active_traces[trace_id].spans[span_id].tags[key] = value
    
    def add_span_log(self, trace_id: str, span_id: str, message: str, level: str = "INFO"):
        """Add a log entry to a span."""
        if trace_id in self.active_traces and span_id in self.active_traces[trace_id].spans:
            log_entry = {
                "timestamp": time.time(),
                "level": level,
                "message": message
            }
            self.active_traces[trace_id].spans[span_id].logs.append(log_entry)
    
    def finish_trace(self, trace_id: str):
        """Finish a trace and move it to completed traces."""
        if trace_id not in self.active_traces:
            return
        
        trace = self.active_traces[trace_id]
        trace.end_time = time.time()
        
        # Move to completed traces
        self.completed_traces.append(trace)
        del self.active_traces[trace_id]
        
        # Limit number of stored traces
        if len(self.completed_traces) > self.max_traces:
            self.completed_traces = self.completed_traces[-self.max_traces:]
    
    @contextmanager
    def trace_span(self, trace_id: str, operation_name: str, parent_span_id: Optional[str] = None):
        """Context manager for automatic span management."""
        span_id = self.start_span(trace_id, operation_name, parent_span_id)
        try:
            yield span_id
        finally:
            self.finish_span(trace_id, span_id)
    
    def get_trace_summary(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get a summary of a specific trace."""
        # Check active traces first
        if trace_id in self.active_traces:
            trace = self.active_traces[trace_id]
        else:
            # Check completed traces
            trace = next((t for t in self.completed_traces if t.trace_id == trace_id), None)
        
        if not trace:
            return None
        
        total_duration = (trace.end_time or time.time()) - trace.start_time
        
        return {
            "trace_id": trace_id,
            "start_time": trace.start_time,
            "end_time": trace.end_time,
            "total_duration": total_duration,
            "span_count": len(trace.spans),
            "root_operation": trace.spans[trace.root_span_id].operation_name if trace.root_span_id else None
        }
    
    def export_traces(self, filepath: str, limit: int = 100):
        """Export recent traces to a JSON file."""
        recent_traces = self.completed_traces[-limit:] if self.completed_traces else []
        
        traces_data = []
        for trace in recent_traces:
            trace_data = {
                "trace_id": trace.trace_id,
                "start_time": trace.start_time,
                "end_time": trace.end_time,
                "spans": []
            }
            
            for span in trace.spans.values():
                span_data = {
                    "span_id": span.span_id,
                    "operation_name": span.operation_name,
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "duration": span.duration,
                    "tags": span.tags,
                    "logs": span.logs,
                    "parent_span_id": span.parent_span_id,
                    "child_span_ids": span.child_span_ids
                }
                trace_data["spans"].append(span_data)
            
            traces_data.append(trace_data)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(traces_data, f, ensure_ascii=False, indent=2)

