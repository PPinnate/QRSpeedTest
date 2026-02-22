from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable

from .config import LiveBenchmarkConfig
from .logger import StructuredLogger
from .stats import compute_stats_ms, success_rate

DECODERS = ["AVFOUNDATION", "VISION", "ZXING"]


@dataclass
class TrialDecoderState:
    first_detect_ns: int | None = None
    confirm_detect_ns: int | None = None
    history: deque[tuple[str, int]] = field(default_factory=deque)


@dataclass
class TrialRecord:
    trial_id: int
    t0_ns: int
    timeout_ns: int
    per_decoder: dict[str, TrialDecoderState] = field(default_factory=lambda: defaultdict(TrialDecoderState))


class LiveBenchmarkController:
    def __init__(self, logger: StructuredLogger, config: LiveBenchmarkConfig) -> None:
        self.logger = logger
        self.config = config
        self._lock = threading.Lock()
        self._trials: dict[int, TrialRecord] = {}
        self._active_trial_id: int | None = None

    def start_trial(self, trial_id: int, t0_ns: int) -> None:
        with self._lock:
            timeout_ns = t0_ns + int(self.config.timeout_s * 1e9)
            self._trials[trial_id] = TrialRecord(trial_id=trial_id, t0_ns=t0_ns, timeout_ns=timeout_ns)
            self._active_trial_id = trial_id
        self.logger.log(timestamp_ns=t0_ns, mode="live", trial_id=trial_id, decoder="SYSTEM", event_type="TRIAL_START")

    def end_trial(self, trial_id: int) -> None:
        ts_ns = time.perf_counter_ns()
        self.logger.log(timestamp_ns=ts_ns, mode="live", trial_id=trial_id, decoder="SYSTEM", event_type="TRIAL_END")

    def current_trial_id(self) -> int | None:
        with self._lock:
            return self._active_trial_id

    def on_detection(self, decoder: str, ts_ns: int, payload: str) -> None:
        with self._lock:
            trial_id = self._active_trial_id
            if trial_id is None:
                return
            trial = self._trials.get(trial_id)
            if trial is None or ts_ns < trial.t0_ns or ts_ns > trial.timeout_ns:
                return
            state = trial.per_decoder[decoder]
            if state.first_detect_ns is None:
                state.first_detect_ns = ts_ns

            window_ns = int(self.config.confirmation_window_ms * 1e6)
            state.history.append((payload, ts_ns))
            while state.history and ts_ns - state.history[0][1] > window_ns:
                state.history.popleft()
            count = sum(1 for p, _ in state.history if p == payload)
            if state.confirm_detect_ns is None:
                if decoder == "AVFOUNDATION" and self.config.confirmations_required > 1 and count < self.config.confirmations_required:
                    state.confirm_detect_ns = state.first_detect_ns
                elif count >= self.config.confirmations_required:
                    state.confirm_detect_ns = ts_ns

        self.logger.log(
            timestamp_ns=ts_ns,
            mode="live",
            trial_id=trial_id,
            decoder=decoder,
            event_type="PAYLOAD_DETECTED",
            payload_string=payload,
        )

    def trials_summary_rows(self) -> list[dict]:
        rows: list[dict] = []
        for trial_id, trial in sorted(self._trials.items()):
            for decoder in DECODERS:
                state = trial.per_decoder.get(decoder, TrialDecoderState())
                first_ms = ((state.first_detect_ns - trial.t0_ns) / 1e6) if state.first_detect_ns else None
                confirm_ms = ((state.confirm_detect_ns - trial.t0_ns) / 1e6) if state.confirm_detect_ns else None
                rows.append(
                    {
                        "trial_id": trial_id,
                        "decoder": decoder,
                        "success": bool(state.first_detect_ns),
                        "first_detect_latency_ms": first_ms,
                        "confirm_detect_latency_ms": confirm_ms,
                    }
                )
        return rows

    def aggregate(self) -> dict:
        rows = self.trials_summary_rows()
        by_decoder: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_decoder[row["decoder"]].append(row)

        # delta vs fastest
        per_trial_fastest: dict[int, float] = {}
        for trial_id in {r["trial_id"] for r in rows}:
            vals = [r["first_detect_latency_ms"] for r in rows if r["trial_id"] == trial_id and r["first_detect_latency_ms"] is not None]
            if vals:
                per_trial_fastest[trial_id] = min(vals)

        out = {}
        for decoder, drows in by_decoder.items():
            first_vals = [r["first_detect_latency_ms"] for r in drows if r["first_detect_latency_ms"] is not None]
            confirm_vals = [r["confirm_detect_latency_ms"] for r in drows if r["confirm_detect_latency_ms"] is not None]
            deltas = []
            for r in drows:
                tid = r["trial_id"]
                if r["first_detect_latency_ms"] is not None and tid in per_trial_fastest:
                    deltas.append(r["first_detect_latency_ms"] - per_trial_fastest[tid])
            successes = sum(1 for r in drows if r["success"])
            out[decoder] = {
                "success_rate": success_rate(successes, len(drows)),
                "first_detect": compute_stats_ms(first_vals),
                "confirm_detect": compute_stats_ms(confirm_vals),
                "delta_vs_fastest": {
                    "mean_delta_ms": compute_stats_ms(deltas)["mean_ms"],
                    "median_delta_ms": compute_stats_ms(deltas)["median_ms"],
                },
                "per_trial_latencies_ms": first_vals,
            }
        return out

    def run_scripted_trials(self, t0_provider: Callable[[int], int]) -> None:
        for i in range(1, self.config.trials + 1):
            t0_ns = t0_provider(i)
            self.start_trial(i, t0_ns)
            time.sleep(self.config.timeout_s)
            self.end_trial(i)
