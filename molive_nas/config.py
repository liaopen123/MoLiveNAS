from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    input_dir: Path = Path(os.getenv("MOLIVE_INPUT", "/input"))
    output_dir: Path = Path(os.getenv("MOLIVE_OUTPUT", "/output"))
    data_dir: Path = Path(os.getenv("MOLIVE_DATA", "/data"))
    scan_interval: int = _int("MOLIVE_SCAN_INTERVAL", 300)
    stable_seconds: int = _int("MOLIVE_STABLE_SECONDS", 120)
    workers: int = max(1, _int("MOLIVE_WORKERS", 2))
    transcode_workers: int = max(1, _int("MOLIVE_TRANSCODE_WORKERS", 1))
    jpeg_quality: int = min(100, max(80, _int("MOLIVE_JPEG_QUALITY", 96)))
    video_crf: int = min(28, max(12, _int("MOLIVE_VIDEO_CRF", 17)))
    web_port: int = _int("MOLIVE_WEB_PORT", 8787)
    use_qsv: str = os.getenv("MOLIVE_USE_QSV", "auto").lower()
    allow_hdr_sdr_fallback: bool = _bool("MOLIVE_ALLOW_HDR_SDR_FALLBACK", False)
    baseline_on_first_run: bool = _bool("MOLIVE_BASELINE_ON_FIRST_RUN", False)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "molive.sqlite3"

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
