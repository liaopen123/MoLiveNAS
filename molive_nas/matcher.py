from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .commands import exif_json
from .config import Config
from .database import Database

log = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {".heic", ".heif", ".jpg", ".jpeg"}
VIDEO_EXTENSIONS = {".mov", ".mp4"}


def _fingerprint(image: Path, video: Path) -> str:
    values = []
    for path in (image, video):
        stat = path.stat()
        values.append(f"{path}:{stat.st_size}:{stat.st_mtime_ns}")
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def _safe_output(config: Config, image: Path) -> Path:
    relative = image.relative_to(config.input_dir)
    parent = config.output_dir / relative.parent
    parent.mkdir(parents=True, exist_ok=True)
    return parent / f"{image.stem}_MP.jpg"


def scan(config: Config, db: Database) -> int:
    images: list[Path] = []
    videos_by_dir_stem: dict[tuple[Path, str], Path] = {}

    for path in config.input_dir.rglob("*"):
        if not path.is_file() or config.output_dir in path.parents:
            continue
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            images.append(path)
        elif suffix in VIDEO_EXTENSIONS:
            videos_by_dir_stem[(path.parent, path.stem.casefold())] = path

    enqueued = 0
    unmatched: list[Path] = []
    for image in images:
        video = videos_by_dir_stem.get((image.parent, image.stem.casefold()))
        if video is None:
            unmatched.append(image)
            continue
        if min(db.observe_file(image, "image"), db.observe_file(video, "video")) < config.stable_seconds:
            continue
        db.enqueue(image, video, _safe_output(config, image), _fingerprint(image, video))
        enqueued += 1

    # 只对同名失败项做 Content Identifier 匹配，避免全库都调用 exiftool。
    if unmatched:
        video_ids: dict[str, Path] = {}
        for video in videos_by_dir_stem.values():
            metadata = exif_json(video, "-ContentIdentifier")
            cid = str(metadata.get("ContentIdentifier", "")).strip()
            if cid:
                video_ids[cid] = video
        for image in unmatched:
            metadata = exif_json(image, "-ContentIdentifier")
            cid = str(metadata.get("ContentIdentifier", "")).strip()
            video = video_ids.get(cid)
            if not video:
                continue
            if min(db.observe_file(image, "image"), db.observe_file(video, "video")) < config.stable_seconds:
                continue
            db.enqueue(image, video, _safe_output(config, image), _fingerprint(image, video))
            enqueued += 1

    log.info("scan complete: images=%d enqueued_candidates=%d", len(images), enqueued)
    return enqueued
