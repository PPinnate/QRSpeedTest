from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import AppKit
import Foundation
import Quartz

from .config import StimulusConfig


@dataclass
class StimulusEvent:
    trial_id: int
    t0_ns: int
    payload: str


class StimulusView(AppKit.NSView):
    alpha_value = 0.0
    ci_image = None

    def set_ciimage_alpha_(self, ci_img, alpha: float):
        self.ci_image = ci_img
        self.alpha_value = alpha
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        AppKit.NSColor.blackColor().setFill()
        AppKit.NSRectFill(rect)
        if self.ci_image is None:
            return
        context = AppKit.NSGraphicsContext.currentContext().CGContext()
        cg_ctx = Quartz.CIContext.contextWithCGContext_options_(context, None)
        transformed = self.ci_image.imageByApplyingTransform_(Quartz.CGAffineTransformMakeScale(8.0, 8.0))
        extent = transformed.extent()
        Quartz.CGContextSetAlpha(context, self.alpha_value)
        cg_ctx.drawImage_inRect_fromRect_(transformed, rect, extent)
        Quartz.CGContextSetAlpha(context, 1.0)


class StimulusController(Foundation.NSObject):
    def initWithConfig_callback_(self, config: StimulusConfig, trial_callback: Callable[[StimulusEvent], None]):
        self = Foundation.NSObject.init(self)
        if self is None:
            return None
        self.config = config
        self.trial_callback = trial_callback
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(200, 200, 600, 600),
            AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable | AppKit.NSWindowStyleMaskResizable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Stimulus Generator")
        self.view = StimulusView.alloc().initWithFrame_(self.window.contentView().bounds())
        self.window.setContentView_(self.view)
        self.current_trial = 0
        return self

    def show(self):
        self.window.makeKeyAndOrderFront_(None)

    def _qr_ciimage(self, payload: str):
        data = payload.encode("utf-8")
        ns_data = Foundation.NSData.dataWithBytes_length_(data, len(data))
        filt = Quartz.CIFilter.filterWithName_("CIQRCodeGenerator")
        filt.setValue_forKey_(ns_data, "inputMessage")
        filt.setValue_forKey_("M", "inputCorrectionLevel")
        return filt.valueForKey_("outputImage")

    def run_fade_trials(self):
        self.current_trial = 0
        self._run_next_trial()

    def _run_next_trial(self):
        if self.current_trial >= self.config.trials:
            self.view.set_ciimage_alpha_(None, 0.0)
            return
        self.current_trial += 1
        payload = f"{self.config.payload_base}-trial-{self.current_trial}"
        ci = self._qr_ciimage(payload)
        t0_ns = time.perf_counter_ns()
        self.trial_callback(StimulusEvent(trial_id=self.current_trial, t0_ns=t0_ns, payload=payload))

        steps = 30
        interval_s = (self.config.fade_duration_ms / 1000.0) / steps

        def step(idx=0):
            alpha = min(1.0, idx / steps)
            self.view.set_ciimage_alpha_(ci, alpha)
            if idx < steps:
                Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(interval_s, self, "_fadeStep:", {"idx": idx + 1, "ci": ci}, False)
            else:
                hold_s = self.config.hold_duration_ms / 1000.0
                Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(hold_s, self, "_holdDone:", None, False)

        step(0)

    def _fadeStep_(self, timer):
        info = timer.userInfo()
        idx = info["idx"]
        ci = info["ci"]
        steps = 30
        interval_s = (self.config.fade_duration_ms / 1000.0) / steps
        alpha = min(1.0, idx / steps)
        self.view.set_ciimage_alpha_(ci, alpha)
        if idx < steps:
            Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(interval_s, self, "_fadeStep:", {"idx": idx + 1, "ci": ci}, False)
        else:
            hold_s = self.config.hold_duration_ms / 1000.0
            Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(hold_s, self, "_holdDone:", None, False)

    def _holdDone_(self, timer):
        self.view.set_ciimage_alpha_(None, 0.0)
        gap_s = self.config.gap_duration_ms / 1000.0
        Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(gap_s, self, "_gapDone:", None, False)

    def _gapDone_(self, timer):
        self._run_next_trial()
