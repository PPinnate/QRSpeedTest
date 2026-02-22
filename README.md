# QRSpeedTest (macOS, PyObjC)

A native macOS Python app to benchmark QR decoding speed/stability across:

- **AVFoundation metadata** (`AVCaptureMetadataOutput`, QR only) for live stream
- **Vision** (`VNDetectBarcodesRequest`) for live + still image
- **zxing-cpp Python bindings** for live + still image

All timing uses `time.perf_counter_ns()` and logs nanosecond timestamps.

## 1) Exact install commands

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Project file tree

```text
QRSpeedTest/
├── main.py
├── qrspeedtest/
│   ├── __init__.py
│   ├── app.py
│   ├── camera.py
│   ├── config.py
│   ├── decoders.py
│   ├── live_benchmark.py
│   ├── logger.py
│   ├── stats.py
│   ├── still_benchmark.py
│   └── stimulus.py
├── requirements.txt
├── setup.py
└── README.md
```

## 3) One-click GUI

Run:

```bash
python main.py
```

The app opens a Cocoa window with 3 tabs:

### Tab 1 — Live Benchmark
- **Start Camera**, **Stop Camera**, **Run 10-Trial Benchmark**, **Export Logs**
- One camera session shared across all decoders.
- AVFoundation metadata decoder runs from metadata output callback.
- Vision and ZXing run from video output frames on background threads.
- Video output sets `alwaysDiscardsLateVideoFrames=True`.
- Trial metrics include success rate, first/confirm latencies, jitter, and delta-vs-fastest.

### Tab 2 — Still Image Benchmark
- **Choose Image…** then **Run Benchmark (10x)**
- **Choose Folder (Batch)** for per-image repeated benchmarking
- Reports payload, payload match, per-run times, and summary stats.

### Tab 3 — Stimulus Generator
- **Open Stimulus Window** opens a separate QR display window.
- **Start Fade Script** runs controlled fade-in trials:
  - fade alpha 0→1
  - hold visible
  - gap blank
- Emits exact trial `t0_ns` and unique `trial_id` values for live benchmarking.

## 4) Controlled live workflow (recommended)

1. Launch app: `python main.py`
2. Open **Stimulus Generator** tab, click **Open Stimulus Window**.
3. Position stimulus window so camera sees it.
4. Go to **Live Benchmark** tab, click **Run 10-Trial Benchmark**.
5. Wait for script completion and summary output.
6. Click **Export Logs**.

Generated exports in `exports/`:
- `raw_events.csv`
- `trials_summary.csv`
- `still_image_summary.csv`
- `summary.json`

## 5) Still-image workflow

1. Go to **Still Image Benchmark** tab.
2. Click **Choose Image…** and select a test QR image.
3. Click **Run Benchmark (10x)**.
4. Optionally choose a folder for batch mode.
5. Export logs from Live tab (same export directory).

## 6) Statistics implemented

For live and still modes:
- success_rate
- mean_ms
- std_ms
- median_ms
- p95_ms
- min_ms
- max_ms
- coefficient_of_variation = std/mean (if mean > 0)

Live mode also computes **delta vs fastest** per trial and aggregate mean/median delta.

## 7) Fairness + timing details

- Same camera feed for all live decoders.
- AVFoundation metadata callback and VideoData callback run concurrently.
- Vision/ZXing decode offloaded to thread pool to avoid blocking capture callback.
- All logs use `perf_counter_ns` nanosecond timestamps; durations reported in ms.
- ZXing conversion overhead (`CGImage -> grayscale bytes`) is timed separately from decode.

## 8) Camera permissions (macOS)

Camera access prompt appears for the app host process (Terminal or packaged app).
If running from Terminal, grant Terminal camera access in:

**System Settings → Privacy & Security → Camera**

## 9) Optional: build clickable .app (py2app)

```bash
source .venv/bin/activate
pip install py2app
python setup.py py2app
open dist/QRSpeedTest.app
```

`setup.py` includes `NSCameraUsageDescription` in `Info.plist`.

## 10) Interpreting results

- If decoder latency differences are within ~1 frame interval, they may be practically tied.
  - ~33.3ms at 30fps
  - ~16.7ms at 60fps
- Prefer decoder(s) with:
  1) lower mean first-detect latency,
  2) lower std (jitter) and lower coefficient of variation,
  3) higher success rate,
  4) consistently low delta-vs-fastest.
- A decoder that is slightly faster on mean but with high jitter/failures may be less reliable in production.
