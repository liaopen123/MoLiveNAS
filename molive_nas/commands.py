from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def require_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe", "exiftool") if shutil.which(name) is None]
    if shutil.which("magick") is None and shutil.which("convert") is None:
        missing.append("magick/convert")
    if missing:
        raise RuntimeError(f"Missing required tools: {', '.join(missing)}")


def run(args: list[str], *, binary: bool = False, check: bool = True):
    log.debug("run: %s", " ".join(map(str, args)))
    result = subprocess.run(args, capture_output=True, text=not binary)
    if check and result.returncode:
        stderr = result.stderr.decode(errors="replace") if binary else result.stderr
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{stderr[-2000:]}")
    return result


def ffprobe(path: Path) -> dict:
    result = run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ])
    return json.loads(result.stdout or "{}")


def exif_json(path: Path, *tags: str) -> dict:
    result = run(["exiftool", "-j", "-n", *tags, str(path)], check=False)
    if result.returncode:
        return {}
    values = json.loads(result.stdout or "[]")
    return values[0] if values else {}
