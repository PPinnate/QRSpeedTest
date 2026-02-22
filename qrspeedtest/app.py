from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import AppKit
import AVFoundation
import Foundation

from .camera import SharedCameraSession
from .config import LiveBenchmarkConfig, StillBenchmarkConfig, StimulusConfig
from .live_benchmark import LiveBenchmarkController
from .logger import StructuredLogger
from .still_benchmark import StillImageBenchmarker
from .stimulus import StimulusController


PRESETS = {
    "640x480": AVFoundation.AVCaptureSessionPreset640x480,
    "1280x720": AVFoundation.AVCaptureSessionPreset1280x720,
}


class MainWindowController(Foundation.NSObject):
    def init(self):
        self = Foundation.NSObject.init(self)
        if self is None:
            return None
        self.logger = StructuredLogger()
        self.live_config = LiveBenchmarkConfig()
        self.still_config = StillBenchmarkConfig()
        self.stimulus_config = StimulusConfig()
        self.live_controller = LiveBenchmarkController(self.logger, self.live_config)
        self.camera = None
        self.still_benchmarker = StillImageBenchmarker(self.logger, self.still_config)
        self.selected_image: Path | None = None
        self.last_live_summary = {}
        self.last_still_summary = {}
        self._build_ui()
        return self

    def _build_ui(self):
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(100, 100, 980, 700),
            AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskResizable | AppKit.NSWindowStyleMaskClosable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("QRSpeedTest")

        tab_view = AppKit.NSTabView.alloc().initWithFrame_(self.window.contentView().bounds())
        self.window.setContentView_(tab_view)

        live_tab = AppKit.NSTabViewItem.alloc().initWithIdentifier_("live")
        live_tab.setLabel_("Live Benchmark")
        live_tab.setView_(self._build_live_tab())

        still_tab = AppKit.NSTabViewItem.alloc().initWithIdentifier_("still")
        still_tab.setLabel_("Still Image Benchmark")
        still_tab.setView_(self._build_still_tab())

        stim_tab = AppKit.NSTabViewItem.alloc().initWithIdentifier_("stim")
        stim_tab.setLabel_("Stimulus Generator")
        stim_tab.setView_(self._build_stimulus_tab())

        tab_view.addTabViewItem_(live_tab)
        tab_view.addTabViewItem_(still_tab)
        tab_view.addTabViewItem_(stim_tab)

    def _button(self, title, action, frame):
        b = AppKit.NSButton.alloc().initWithFrame_(frame)
        b.setTitle_(title)
        b.setTarget_(self)
        b.setAction_(action)
        return b

    def _build_live_tab(self):
        view = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 980, 700))
        view.addSubview_(self._button("Start Camera", "startCamera:", AppKit.NSMakeRect(20, 640, 160, 32)))
        view.addSubview_(self._button("Stop Camera", "stopCamera:", AppKit.NSMakeRect(200, 640, 160, 32)))
        view.addSubview_(self._button("Run 10-Trial Benchmark", "runLiveBenchmark:", AppKit.NSMakeRect(380, 640, 220, 32)))
        view.addSubview_(self._button("Export Logs", "exportLogs:", AppKit.NSMakeRect(620, 640, 120, 32)))

        self.live_text = AppKit.NSTextView.alloc().initWithFrame_(AppKit.NSMakeRect(20, 20, 940, 600))
        self.live_text.setEditable_(False)
        view.addSubview_(self.live_text)
        return view

    def _build_still_tab(self):
        view = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 980, 700))
        view.addSubview_(self._button("Choose Image…", "chooseImage:", AppKit.NSMakeRect(20, 640, 160, 32)))
        view.addSubview_(self._button("Run Benchmark (10x)", "runStill:", AppKit.NSMakeRect(200, 640, 190, 32)))
        view.addSubview_(self._button("Choose Folder (Batch)", "chooseBatchFolder:", AppKit.NSMakeRect(410, 640, 190, 32)))
        self.still_text = AppKit.NSTextView.alloc().initWithFrame_(AppKit.NSMakeRect(20, 20, 940, 600))
        self.still_text.setEditable_(False)
        view.addSubview_(self.still_text)
        return view

    def _build_stimulus_tab(self):
        view = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 980, 700))
        view.addSubview_(self._button("Open Stimulus Window", "openStimulus:", AppKit.NSMakeRect(20, 640, 190, 32)))
        view.addSubview_(self._button("Start Fade Script", "startStimulusScript:", AppKit.NSMakeRect(230, 640, 190, 32)))
        self.stim_text = AppKit.NSTextView.alloc().initWithFrame_(AppKit.NSMakeRect(20, 20, 940, 600))
        self.stim_text.setEditable_(False)
        view.addSubview_(self.stim_text)
        return view

    def show(self):
        self.window.makeKeyAndOrderFront_(None)

    def _ensure_camera(self):
        if self.camera:
            return
        self.camera = SharedCameraSession(
            logger=self.logger,
            decoder_callback=self._decoder_event,
            throttle_n_frames=self.live_config.throttle_n_frames,
            parallel_decode=self.live_config.parallel_decode,
        )
        self.camera.configure(PRESETS[self.live_config.resolution_preset])

    def _decoder_event(self, decoder: str, ts_ns: int, payload: str, frame_idx, conversion_ms, decode_ms):
        self.live_controller.on_detection(decoder, ts_ns, payload)

    def startCamera_(self, sender):
        self._ensure_camera()
        self.camera.start()
        self.live_text.setString_("Camera started.\n")

    def stopCamera_(self, sender):
        if self.camera:
            self.camera.stop()
            self.camera = None
            self.live_text.setString_("Camera stopped.\n")

    def openStimulus_(self, sender):
        if not hasattr(self, "stimulus"):
            self.stimulus = StimulusController.alloc().initWithConfig_callback_(self.stimulus_config, self._on_stimulus_trial)
        self.stimulus.show()

    def _on_stimulus_trial(self, event):
        self.live_controller.start_trial(event.trial_id, event.t0_ns)
        self.stim_text.setString_(f"Trial {event.trial_id} T0={event.t0_ns}\n")

    def startStimulusScript_(self, sender):
        self.openStimulus_(None)
        self.stimulus.run_fade_trials()

    def runLiveBenchmark_(self, sender):
        self.startCamera_(None)
        self.startStimulusScript_(None)

        def worker():
            total_s = self.stimulus_config.trials * (
                (self.stimulus_config.fade_duration_ms + self.stimulus_config.hold_duration_ms + self.stimulus_config.gap_duration_ms)
                / 1000.0
            ) + self.live_config.timeout_s
            time.sleep(total_s)
            summary = self.live_controller.aggregate()
            self.last_live_summary = summary
            Foundation.NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self.live_text.setString_(json.dumps(summary, indent=2))
            )

        threading.Thread(target=worker, daemon=True).start()

    def chooseImage_(self, sender):
        panel = AppKit.NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        if panel.runModal() == AppKit.NSModalResponseOK:
            self.selected_image = Path(panel.URLs()[0].path())
            self.still_text.setString_(f"Selected: {self.selected_image}\n")

    def runStill_(self, sender):
        if not self.selected_image:
            self.still_text.setString_("Choose an image first.\n")
            return
        summary = self.still_benchmarker.run_single(self.selected_image)
        self.last_still_summary = summary
        self.still_text.setString_(json.dumps(summary, indent=2))

    def chooseBatchFolder_(self, sender):
        panel = AppKit.NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        if panel.runModal() == AppKit.NSModalResponseOK:
            folder = Path(panel.URLs()[0].path())
            summary = self.still_benchmarker.run_batch(folder)
            self.last_still_summary = summary
            self.still_text.setString_(json.dumps(summary, indent=2))

    def exportLogs_(self, sender):
        out = Path("exports")
        raw = self.logger.export_raw_events_csv(out)
        trials_rows = self.live_controller.trials_summary_rows()
        self.logger.export_csv(out / "trials_summary.csv", trials_rows)

        still_rows = []
        if self.last_still_summary and "per_image" not in self.last_still_summary:
            for decoder in ("VISION", "ZXING"):
                dec = self.last_still_summary[decoder]
                still_rows.append(
                    {
                        "image": str(self.selected_image) if self.selected_image else "",
                        "decoder": decoder,
                        "payload": dec["payload"],
                        "success_rate": dec["success_rate"],
                        "mean_ms": dec["stats"]["mean_ms"],
                        "std_ms": dec["stats"]["std_ms"],
                        "median_ms": dec["stats"]["median_ms"],
                        "p95_ms": dec["stats"]["p95_ms"],
                        "min_ms": dec["stats"]["min_ms"],
                        "max_ms": dec["stats"]["max_ms"],
                    }
                )
        self.logger.export_csv(out / "still_image_summary.csv", still_rows)

        self.logger.export_json(
            out / "summary.json",
            {
                "live": self.last_live_summary,
                "still": self.last_still_summary,
            },
        )
        self.live_text.setString_(f"Exported to {out.resolve()}\nRaw events: {raw}\n")


def run_app() -> None:
    app = AppKit.NSApplication.sharedApplication()
    controller = MainWindowController.alloc().init()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    controller.show()
    app.activateIgnoringOtherApps_(True)
    app.run()
