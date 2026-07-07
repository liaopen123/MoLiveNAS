from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .commands import ffprobe

LENGTH_RE = re.compile(rb'Item:Semantic="MotionPhoto"[^>]*Item:Length="(\d+)"|Item:Length="(\d+)"[^>]*Item:Semantic="MotionPhoto"')
OFFSET_RE = re.compile(rb'(?:Camera|GCamera):MicroVideoOffset="(\d+)"')


def video_length(data: bytes) -> int:
    match = LENGTH_RE.search(data) or OFFSET_RE.search(data)
    if not match:
        raise ValueError("missing Motion Photo video length")
    value = next(group for group in match.groups() if group is not None)
    return int(value)


def validate(path: Path) -> dict:
    size = path.stat().st_size
    with path.open("rb") as stream:
        head = stream.read(min(size, 256 * 1024))
    if not head.startswith(b"\xff\xd8"):
        raise ValueError("output is not JPEG")
    length = video_length(head)
    if length <= 12 or length >= size:
        raise ValueError("invalid video length")
    with path.open("rb") as stream:
        stream.seek(size - length)
        box = stream.read(12)
    if box[4:8] != b"ftyp":
        raise ValueError("embedded video does not start with ftyp")

    fd, temp_name = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    temp = Path(temp_name)
    try:
        with path.open("rb") as source, temp.open("wb") as target:
            source.seek(size - length)
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        info = ffprobe(temp)
        videos = [stream for stream in info.get("streams", []) if stream.get("codec_type") == "video"]
        if not videos:
            raise ValueError("embedded file has no video track")
        return {"size": size, "video_size": length, "codec": videos[0].get("codec_name")}
    finally:
        temp.unlink(missing_ok=True)
