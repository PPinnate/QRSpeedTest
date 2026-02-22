from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import Quartz

try:
    import Vision
except Exception:  # pragma: no cover
    Vision = None

try:
    import zxingcpp
except Exception:  # pragma: no cover
    zxingcpp = None


@dataclass
class DecodeResult:
    payload: str | None
    conversion_ms: float | None
    decode_ms: float


class VisionDecoder:
    name = "VISION"

    def __init__(self) -> None:
        if Vision is None:
            raise RuntimeError("Vision framework is not available")

    def decode_cgimage(self, cg_image: Any) -> DecodeResult:
        start_ns = time.perf_counter_ns()
        request = Vision.VNDetectBarcodesRequest.alloc().init()
        request.setSymbologies_([Vision.VNBarcodeSymbologyQR])
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        error = handler.performRequests_error_([request], None)[1]
        if error is not None:
            raise RuntimeError(f"Vision error: {error}")
        observations = request.results() or []
        payload = None
        if observations:
            payload = observations[0].payloadStringValue()
        end_ns = time.perf_counter_ns()
        return DecodeResult(payload=payload, conversion_ms=None, decode_ms=(end_ns - start_ns) / 1e6)


class ZXingDecoder:
    name = "ZXING"

    def __init__(self) -> None:
        if zxingcpp is None:
            raise RuntimeError("zxing-cpp Python bindings are not installed")

    def _cgimage_to_luma_bytes(self, cg_image: Any) -> tuple[bytes, int, int, float]:
        width = Quartz.CGImageGetWidth(cg_image)
        height = Quartz.CGImageGetHeight(cg_image)
        bytes_per_row = width
        t0 = time.perf_counter_ns()
        color_space = Quartz.CGColorSpaceCreateDeviceGray()
        buf = bytearray(height * bytes_per_row)
        context = Quartz.CGBitmapContextCreate(
            buf,
            width,
            height,
            8,
            bytes_per_row,
            color_space,
            Quartz.kCGImageAlphaNone,
        )
        Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), cg_image)
        t1 = time.perf_counter_ns()
        return bytes(buf), width, height, (t1 - t0) / 1e6

    def decode_cgimage(self, cg_image: Any) -> DecodeResult:
        gray, width, height, conversion_ms = self._cgimage_to_luma_bytes(cg_image)
        t0 = time.perf_counter_ns()
        result = zxingcpp.read_barcode(gray, width=width, height=height)
        t1 = time.perf_counter_ns()
        payload = result.text if result else None
        return DecodeResult(payload=payload, conversion_ms=conversion_ms, decode_ms=(t1 - t0) / 1e6)
