from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4


@dataclass
class TraceTimer:
    trace_id: str = field(default_factory=lambda: f"trace_{uuid4().hex}")
    started_at: float = field(default_factory=perf_counter)

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self.started_at) * 1000, 2)
