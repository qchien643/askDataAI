"""
Pipeline Tracer — Debug system cho pipeline.

Ghi lại input/output/timing của từng stage để debug.

Usage:
  # Trong pipeline:
  tracer = PipelineTracer(enabled=True)
  tracer.start("Stage 1: PreFilter")
  tracer.log_input({"question": "..."})
  result = pre_filter.filter(question)
  tracer.log_output({"result": "GREETING", "response": "Xin chào!"})
  tracer.end()

  # Lấy trace:
  trace = tracer.to_dict()  # → list of stage traces
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StageTrace:
    """Trace 1 stage trong pipeline."""
    stage: str
    status: str = "pending"    # pending → running → done / error
    duration_ms: float = 0.0
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    error: str = ""
    _start_time: float = 0.0


class PipelineTracer:
    """
    Ghi lại execution trace cho toàn bộ pipeline.

    Mỗi stage được track với:
    - Stage name
    - Input summary (truncated)
    - Output summary (truncated)
    - Duration (ms)
    - Status (done/error/skipped)
    """

    MAX_VALUE_LENGTH = 200   # Truncate values dài
    MAX_LIST_ITEMS = 5       # Max items hiển thị cho list
    MAX_ROWS_PREVIEW = 3     # Max rows preview cho data results

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.stages: list[StageTrace] = []
        self._current: StageTrace | None = None
        self._pipeline_start: float = 0.0

    def start(self, stage_name: str) -> None:
        """Bắt đầu trace 1 stage."""
        if not self.enabled:
            return
        if self._pipeline_start == 0.0:
            self._pipeline_start = time.time()

        trace = StageTrace(
            stage=stage_name,
            status="running",
            _start_time=time.time(),
        )
        self._current = trace
        self.stages.append(trace)

    def log_input(self, data: dict[str, Any]) -> None:
        """Ghi input của stage hiện tại."""
        if not self.enabled or not self._current:
            return
        self._current.input_data = self._sanitize(data)

    def log_output(self, data: dict[str, Any]) -> None:
        """Ghi output của stage hiện tại."""
        if not self.enabled or not self._current:
            return
        self._current.output_data = self._sanitize(data)

    def end(self, status: str = "done") -> None:
        """Kết thúc stage hiện tại."""
        if not self.enabled or not self._current:
            return
        self._current.duration_ms = round(
            (time.time() - self._current._start_time) * 1000, 1
        )
        self._current.status = status
        self._current = None

    def error(self, error_msg: str) -> None:
        """Ghi lỗi và kết thúc stage."""
        if not self.enabled or not self._current:
            return
        self._current.error = str(error_msg)[:500]
        self.end(status="error")

    def skip(self, stage_name: str, reason: str = "") -> None:
        """Đánh dấu 1 stage bị skip."""
        if not self.enabled:
            return
        trace = StageTrace(
            stage=stage_name,
            status="skipped",
            output_data={"reason": reason} if reason else {},
        )
        self.stages.append(trace)

    def to_dict(self) -> dict:
        """Export trace thành dict cho API response."""
        if not self.enabled:
            return {}

        # Auto-close any stage left in 'running' state
        if self._current and self._current.status == "running":
            self._current.duration_ms = round(
                (time.time() - self._current._start_time) * 1000, 1
            )
            self._current.status = "interrupted"
            self._current = None

        total_ms = round((time.time() - self._pipeline_start) * 1000, 1) if self._pipeline_start else 0

        return {
            "total_duration_ms": total_ms,
            "total_stages": len(self.stages),
            "stages": [
                {
                    "stage": s.stage,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "input": s.input_data,
                    "output": s.output_data,
                    **({"error": s.error} if s.error else {}),
                }
                for s in self.stages
            ],
        }

    def trace_stage(self, stage_name: str):
        """Context manager cho stage tracing.

        Usage:
            with tracer.trace_stage("Stage 1: PreFilter") as t:
                t.log_input({"question": "..."})
                result = do_something()
                t.log_output({"result": result})
        """
        return _StageContext(self, stage_name)

    def _sanitize(self, data: dict[str, Any]) -> dict:
        """Truncate values dài, giữ debug output vừa phải."""
        result = {}
        for key, value in data.items():
            result[key] = self._truncate_value(value)
        return result

    def _truncate_value(self, value: Any) -> Any:
        """Truncate 1 value."""
        if value is None:
            return None

        if isinstance(value, (bool, int, float)):
            return value

        if isinstance(value, str):
            if len(value) > self.MAX_VALUE_LENGTH:
                return value[:self.MAX_VALUE_LENGTH] + f"... ({len(value)} chars)"
            return value

        if isinstance(value, list):
            if not value:
                return []
            # Show count + first N items
            items = [self._truncate_value(v) for v in value[:self.MAX_LIST_ITEMS]]
            if len(value) > self.MAX_LIST_ITEMS:
                items.append(f"... (+{len(value) - self.MAX_LIST_ITEMS} more)")
            return items

        if isinstance(value, dict):
            # Nếu là row data (nhiều keys), chỉ show vài fields
            if len(value) > 8:
                keys = list(value.keys())[:5]
                result = {k: self._truncate_value(value[k]) for k in keys}
                result["__truncated__"] = f"{len(value)} total keys"
                return result
            return {k: self._truncate_value(v) for k, v in value.items()}

        # Fallback: convert to string
        s = str(value)
        if len(s) > self.MAX_VALUE_LENGTH:
            return s[:self.MAX_VALUE_LENGTH] + "..."
        return s


class _StageContext:
    """Context manager cho PipelineTracer.trace_stage().

    Tự động start/end stage + catch error nếu có exception.
    """

    def __init__(self, tracer: PipelineTracer, stage_name: str):
        self._tracer = tracer
        self._stage_name = stage_name

    def __enter__(self):
        self._tracer.start(self._stage_name)
        return self._tracer

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._tracer.error(str(exc_val))
        elif self._tracer._current and self._tracer._current.status == "running":
            self._tracer.end()
        return False  # Don't suppress exceptions
