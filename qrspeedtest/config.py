from dataclasses import dataclass


@dataclass
class LiveBenchmarkConfig:
    trials: int = 10
    timeout_s: float = 3.0
    warmup_s: float = 2.0
    resolution_preset: str = "1280x720"
    throttle_n_frames: int = 1
    parallel_decode: bool = True
    confirmations_required: int = 2
    confirmation_window_ms: float = 500.0


@dataclass
class StillBenchmarkConfig:
    repeats: int = 10


@dataclass
class StimulusConfig:
    fade_duration_ms: int = 1500
    hold_duration_ms: int = 1000
    gap_duration_ms: int = 1000
    trials: int = 10
    payload_base: str = "QRSpeedTest"

