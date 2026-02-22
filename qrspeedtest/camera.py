from __future__ import annotations

import queue
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

import AVFoundation
import CoreMedia
import Foundation
import Quartz

from .decoders import VisionDecoder, ZXingDecoder
from .logger import StructuredLogger

DecoderCallback = Callable[[str, int, str, int | None, float | None, float | None], None]


class MetadataDelegate(Foundation.NSObject):
    def initWithOwner_(self, owner):
        self = Foundation.NSObject.init(self)
        if self is None:
            return None
        self.owner = owner
        return self

    def captureOutput_didOutputMetadataObjects_fromConnection_(self, output, metadata_objects, connection):
        ts_ns = time.perf_counter_ns()
        for item in metadata_objects:
            payload = item.stringValue() if hasattr(item, "stringValue") else None
            if payload:
                self.owner.on_metadata_detected(payload, ts_ns)


class VideoDelegate(Foundation.NSObject):
    def initWithOwner_(self, owner):
        self = Foundation.NSObject.init(self)
        if self is None:
            return None
        self.owner = owner
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sample_buffer, connection):
        self.owner.on_video_sample(sample_buffer)

    def captureOutput_didDropSampleBuffer_fromConnection_(self, output, sample_buffer, connection):
        self.owner.dropped_frames += 1


@dataclass
class CameraMetrics:
    frames_received: int = 0
    frames_processed: int = 0
    dropped_frames: int = 0


class SharedCameraSession:
    def __init__(
        self,
        logger: StructuredLogger,
        decoder_callback: DecoderCallback,
        throttle_n_frames: int = 1,
        parallel_decode: bool = True,
    ) -> None:
        self.logger = logger
        self.decoder_callback = decoder_callback
        self.throttle_n_frames = max(1, throttle_n_frames)
        self.parallel_decode = parallel_decode

        self.capture_session = AVFoundation.AVCaptureSession.alloc().init()
        self.metadata_delegate = MetadataDelegate.alloc().initWithOwner_(self)
        self.video_delegate = VideoDelegate.alloc().initWithOwner_(self)
        self.metadata_output = AVFoundation.AVCaptureMetadataOutput.alloc().init()
        self.video_output = AVFoundation.AVCaptureVideoDataOutput.alloc().init()
        self.video_output.setAlwaysDiscardsLateVideoFrames_(True)
        self.video_output.setSampleBufferDelegate_queue_(
            self.video_delegate,
            Foundation.dispatch_queue_create("qrspeed.video", None),
        )
        self.metadata_output.setMetadataObjectsDelegate_queue_(
            self.metadata_delegate,
            Foundation.dispatch_queue_create("qrspeed.metadata", None),
        )

        self.metrics = CameraMetrics()
        self.dropped_frames = 0
        self._frame_index = 0
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._decode_queue: queue.Queue[tuple[int, object]] = queue.Queue(maxsize=2)
        self._vision = VisionDecoder()
        self._zxing = ZXingDecoder()

    def configure(self, preset: str) -> None:
        device = AVFoundation.AVCaptureDevice.defaultDeviceWithMediaType_(AVFoundation.AVMediaTypeVideo)
        input_device = AVFoundation.AVCaptureDeviceInput.deviceInputWithDevice_error_(device, None)[0]
        if self.capture_session.canAddInput_(input_device):
            self.capture_session.addInput_(input_device)

        if self.capture_session.canSetSessionPreset_(preset):
            self.capture_session.setSessionPreset_(preset)

        if self.capture_session.canAddOutput_(self.metadata_output):
            self.capture_session.addOutput_(self.metadata_output)
            self.metadata_output.setMetadataObjectTypes_([AVFoundation.AVMetadataObjectTypeQRCode])

        pixel_key = Quartz.kCVPixelBufferPixelFormatTypeKey
        self.video_output.setVideoSettings_({pixel_key: 1111970369})
        if self.capture_session.canAddOutput_(self.video_output):
            self.capture_session.addOutput_(self.video_output)

    def start(self) -> None:
        self.capture_session.startRunning()

    def stop(self) -> None:
        self.capture_session.stopRunning()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def on_metadata_detected(self, payload: str, ts_ns: int) -> None:
        self.logger.log(
            timestamp_ns=ts_ns,
            mode="live",
            trial_id=None,
            decoder="AVFOUNDATION",
            event_type="METADATA_DETECTED",
            payload_string=payload,
        )
        self.decoder_callback("AVFOUNDATION", ts_ns, payload, None, None, None)

    def on_video_sample(self, sample_buffer) -> None:
        ts_ns = time.perf_counter_ns()
        self.metrics.frames_received += 1
        self._frame_index += 1
        frame_idx = self._frame_index
        self.logger.log(
            timestamp_ns=ts_ns,
            mode="live",
            trial_id=None,
            decoder="PIPELINE",
            event_type="FRAME_RECEIVED",
            frame_index=frame_idx,
        )
        if frame_idx % self.throttle_n_frames != 0:
            return

        image_buf = CoreMedia.CMSampleBufferGetImageBuffer(sample_buffer)
        ci = Quartz.CIImage.imageWithCVPixelBuffer_(image_buf)
        context = Quartz.CIContext.context()
        cg = context.createCGImage_fromRect_(ci, ci.extent())

        def run_decode(decoder, name: str):
            start_ns = time.perf_counter_ns()
            self.logger.log(timestamp_ns=start_ns, mode="live", trial_id=None, decoder=name, event_type="DECODE_START", frame_index=frame_idx)
            result = decoder.decode_cgimage(cg)
            end_ns = time.perf_counter_ns()
            self.logger.log(
                timestamp_ns=end_ns,
                mode="live",
                trial_id=None,
                decoder=name,
                event_type="DECODE_END",
                frame_index=frame_idx,
                conversion_ms=result.conversion_ms,
                decode_duration_ms=result.decode_ms,
                payload_string=result.payload,
            )
            self.metrics.frames_processed += 1
            if result.payload:
                self.decoder_callback(name, end_ns, result.payload, frame_idx, result.conversion_ms, result.decode_ms)

        if self.parallel_decode:
            self._executor.submit(run_decode, self._vision, "VISION")
            self._executor.submit(run_decode, self._zxing, "ZXING")
        else:
            self._executor.submit(lambda: (run_decode(self._vision, "VISION"), run_decode(self._zxing, "ZXING")))
