"""
metrics.py — Lightweight in-memory metrics system for SmartRack.
Thread-safe using threading.Lock.
Designed to run completely inside the .exe without external dependencies.
"""
import threading

class MetricsState:
    def __init__(self):
        self._lock = threading.Lock()
        self.requests_total = 0
        self.errors_total = 0
        self.total_response_time_ms = 0.0
        self.extractions_total = 0
        self.poller_runs = 0
        self.poller_errors = 0

    def inc_requests(self, response_time_ms: float, is_error: bool):
        with self._lock:
            self.requests_total += 1
            self.total_response_time_ms += response_time_ms
            if is_error:
                self.errors_total += 1

    def inc_extractions(self, count: int = 1):
        with self._lock:
            self.extractions_total += count

    def inc_poller_runs(self):
        with self._lock:
            self.poller_runs += 1

    def inc_poller_errors(self):
        with self._lock:
            self.poller_errors += 1

    def get_metrics_snapshot(self) -> dict:
        with self._lock:
            avg_response = (
                self.total_response_time_ms / self.requests_total
                if self.requests_total > 0 else 0.0
            )
            return {
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "avg_response_time_ms": round(avg_response, 2),
                "extractions_total": self.extractions_total,
                "poller_runs": self.poller_runs,
                "poller_errors": self.poller_errors,
            }

# Global singleton
metrics = MetricsState()
