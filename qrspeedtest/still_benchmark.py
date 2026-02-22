from __future__ import annotations

import time
from pathlib import Path

import AppKit

from .config import StillBenchmarkConfig
from .decoders import VisionDecoder, ZXingDecoder
from .logger import StructuredLogger
from .stats import compute_stats_ms, success_rate


class StillImageBenchmarker:
    def __init__(self, logger: StructuredLogger, config: StillBenchmarkConfig) -> None:
        self.logger = logger
        self.config = config
        self.vision = VisionDecoder()
        self.zxing = ZXingDecoder()

    def _load_cgimage(self, image_path: Path):
        ns_image = AppKit.NSImage.alloc().initByReferencingFile_(str(image_path))
        rep = ns_image.representations()[0]
        return rep.CGImage()

    def run_single(self, image_path: Path) -> dict:
        cg = self._load_cgimage(image_path)
        out: dict[str, dict] = {}
        payloads: dict[str, str | None] = {}
        for name, decoder in (("VISION", self.vision), ("ZXING", self.zxing)):
            times = []
            successes = 0
            last_payload = None
            for i in range(self.config.repeats):
                t_ns = time.perf_counter_ns()
                self.logger.log(timestamp_ns=t_ns, mode="image", trial_id=i + 1, decoder=name, event_type="DECODE_START")
                result = decoder.decode_cgimage(cg)
                t2_ns = time.perf_counter_ns()
                self.logger.log(
                    timestamp_ns=t2_ns,
                    mode="image",
                    trial_id=i + 1,
                    decoder=name,
                    event_type="DECODE_END",
                    decode_duration_ms=result.decode_ms,
                    conversion_ms=result.conversion_ms,
                    payload_string=result.payload,
                )
                times.append(result.decode_ms)
                if result.payload:
                    successes += 1
                    last_payload = result.payload
            payloads[name] = last_payload
            out[name] = {
                "payload": last_payload,
                "success_rate": success_rate(successes, self.config.repeats),
                "per_run_decode_ms": times,
                "stats": compute_stats_ms(times),
            }
        out["payload_match"] = payloads["VISION"] == payloads["ZXING"] and payloads["VISION"] is not None
        return out

    def run_batch(self, folder: Path) -> dict:
        image_files = [p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}]
        per_image = {str(p): self.run_single(p) for p in sorted(image_files)}
        return {"per_image": per_image}
