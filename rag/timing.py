import time
from dataclasses import dataclass, field


@dataclass
class IngestionTimings:
    total_start_time: float = 0.0
    stages: dict[str, float] = field(default_factory=dict)

    def start_total(self):
        self.total_start_time = time.time()

    def record_stage(self, stage_name: str, duration: float):
        self.stages[stage_name] = round(duration, 4)

    def get_summary(self) -> dict[str, float]:
        summary = self.stages.copy()
        if self.total_start_time > 0:
            summary["total"] = round(time.time() - self.total_start_time, 4)
        return summary


class StageTimer:
    def __init__(self, timings: IngestionTimings, stage_name: str):
        self.timings = timings
        self.stage_name = stage_name
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        duration = time.time() - self.start_time
        self.timings.record_stage(self.stage_name, duration)
