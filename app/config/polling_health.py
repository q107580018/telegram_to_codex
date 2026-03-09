from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecoveryDecision:
    should_restart_polling: bool = False
    should_escalate_process: bool = False
    next_retry_sec: float = 0.0
    reason: str = ""


class PollingHealthManager:
    def __init__(
        self,
        restart_threshold: int,
        restart_cooldown_sec: float,
        max_restarts_per_window: int,
        restart_window_sec: float,
    ):
        self.restart_threshold = max(1, int(restart_threshold))
        self.restart_cooldown_sec = max(0.0, float(restart_cooldown_sec))
        self.max_restarts_per_window = max(1, int(max_restarts_per_window))
        self.restart_window_sec = max(1.0, float(restart_window_sec))

        self.state = "healthy"
        self.consecutive_network_errors = 0
        self.last_restart_monotonic = 0.0
        self.last_healthy_monotonic = 0.0
        self.last_event = ""
        self.last_restart_reason = ""
        self.restart_timestamps: list[float] = []

    def _prune_window(self, now: float) -> None:
        cutoff = now - self.restart_window_sec
        self.restart_timestamps = [ts for ts in self.restart_timestamps if ts >= cutoff]

    def mark_healthy(self, now: float) -> None:
        self.state = "healthy"
        self.consecutive_network_errors = 0
        self.last_healthy_monotonic = now
        self.last_event = "healthy"

    def _evaluate_restart(self, now: float, reason: str, force: bool) -> RecoveryDecision:
        self._prune_window(now)

        if not force and self.consecutive_network_errors < self.restart_threshold:
            return RecoveryDecision(reason=reason)

        if self.last_restart_monotonic:
            since_last = now - self.last_restart_monotonic
            if since_last < self.restart_cooldown_sec:
                self.state = "degraded"
                return RecoveryDecision(
                    next_retry_sec=self.restart_cooldown_sec - since_last,
                    reason=reason,
                )

        self.last_restart_monotonic = now
        self.last_restart_reason = reason
        self.restart_timestamps.append(now)
        self._prune_window(now)

        if len(self.restart_timestamps) > self.max_restarts_per_window:
            self.state = "escalated"
            return RecoveryDecision(should_escalate_process=True, reason=reason)

        self.state = "recovering"
        return RecoveryDecision(should_restart_polling=True, reason=reason)

    def record_network_error(self, now: float) -> RecoveryDecision:
        self.consecutive_network_errors += 1
        self.state = "degraded"
        self.last_event = "network_error"
        return self._evaluate_restart(now=now, reason="network_error", force=False)

    def record_watchdog_gap(self, now: float, gap_sec: float) -> RecoveryDecision:
        self.state = "degraded"
        self.last_event = "watchdog_gap"
        return self._evaluate_restart(now=now, reason=f"watchdog_gap:{gap_sec:.1f}", force=True)

    def record_restart_result(self, now: float, success: bool) -> None:
        if success:
            self.mark_healthy(now)
        else:
            self.state = "degraded"
            self.last_event = "restart_failed"

    def snapshot(self, now: float) -> dict:
        self._prune_window(now)
        return {
            "state": self.state,
            "consecutive_network_errors": self.consecutive_network_errors,
            "restarts_in_window": len(self.restart_timestamps),
            "last_restart_monotonic": self.last_restart_monotonic,
            "last_healthy_monotonic": self.last_healthy_monotonic,
            "last_event": self.last_event,
            "last_restart_reason": self.last_restart_reason,
        }
