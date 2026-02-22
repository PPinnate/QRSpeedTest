from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class EventRow:
    timestamp_ns: int
    mode: str
    decoder: str
    event_type: str
    trial_id: int | None = None
    frame_index: int | None = None
    conversion_ms: float | None = None
    decode_duration_ms: float | None = None
    payload_string: str | None = None
    payload_changed: bool | None = None


class StructuredLogger:
    def __init__(self) -> None:
        self._events: list[EventRow] = []
        self._lock = Lock()

    def log(self, **kwargs: Any) -> None:
        row = EventRow(**kwargs)
        with self._lock:
            self._events.append(row)

    def snapshot(self) -> list[EventRow]:
        with self._lock:
            return list(self._events)

    def export_raw_events_csv(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "raw_events.csv"
        rows = self.snapshot()
        with out_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()) if rows else list(EventRow.__dataclass_fields__.keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
        return out_file

    @staticmethod
    def export_csv(out_file: Path, rows: list[dict[str, Any]]) -> Path:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        keys: list[str] = []
        if rows:
            seen: set[str] = set()
            for row in rows:
                for key in row.keys():
                    if key not in seen:
                        keys.append(key)
                        seen.add(key)
        with out_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return out_file

    @staticmethod
    def export_json(out_file: Path, payload: dict[str, Any]) -> Path:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return out_file
