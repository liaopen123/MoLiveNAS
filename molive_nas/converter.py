from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from .commands import exif_json, ffprobe, run
from .config import Config
from .validator import validate
from .xmp import inject_xmp

log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class UnsupportedMediaError(ValueError):
    pass


@lru_cache(maxsize=1)
def _image_tool() -> str:
    return shutil.which("magick") or shutil.which("convert") or "magick"


def _is_jpeg_file(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(2) == b"\xff\xd8"


@lru_cache(maxsize=4)
def _qsv_available(config: Config) -> bool:
    if config.use_qsv in {"0", "false", "no", "off"}:
        return False
    if not Path("/dev/dri/renderD128").exists():
        return False
    result = run(["ffmpeg", "-hide_banner", "-encoders"], check=False)
    return result.returncode == 0 and "h264_qsv" in result.stdout


def prepare_ultrahdr_jpeg(source: Path, _video: Path, output: Path, config: Config) -> str:
    bridge = shutil.which(config.ultrahdr_bridge) or config.ultrahdr_bridge
    if not bridge:
        raise UnsupportedMediaError("Ultra HDR bridge is not configured")

    with tempfile.TemporaryDirectory(prefix="molive-uhdr-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        bridge_image = temp / f"image{source.suffix.lower()}"
        bridge_video = temp / "image.mp4"
        bridge_output = temp / "image_uhdr.jpg"
        shutil.copyfile(source, bridge_image)
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=16x16:r=1:d=0.1",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-movflags", "+faststart", str(bridge_video),
        ])

        result = run([
            bridge, str(temp), "--original", "keep", "--overwrite-existing", "--output-suffix", "_uhdr",
            "-q", str(config.jpeg_quality), "-g", str(config.jpeg_quality),
        ], check=False)
        if result.returncode or not bridge_output.exists():
            raise UnsupportedMediaError(
                "Ultra HDR conversion failed; refusing unsafe SDR fallback\n"
                f"{(result.stderr or result.stdout)[-1200:]}"
            )

        metadata = exif_json(bridge_output, "-MicroVideoOffset")
        video_length = int(metadata.get("MicroVideoOffset") or 0)
        total_size = bridge_output.stat().st_size
        if video_length <= 12 or video_length >= total_size:
            raise UnsupportedMediaError("Ultra HDR bridge output has invalid embedded video offset")

        with bridge_output.open("rb") as source_stream, output.open("wb") as target:
            remaining = total_size - video_length
            while remaining:
                chunk = source_stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise UnsupportedMediaError("Ultra HDR bridge output ended unexpectedly")
                target.write(chunk)
                remaining -= len(chunk)

    # The bridge writes temporary Motion Photo XMP. Keep Ultra HDR APP2/MPF data, then let MoLiveNAS
    # inject its own Motion Photo XMP after video preparation.
    run(["exiftool", "-overwrite_original", "-XMP:all=", str(output)], check=False)
    return "jpeg-ultrahdr"


def prepare_jpeg(source: Path, output: Path, config: Config, video: Path | None = None) -> str:
    metadata = exif_json(source, "-Orientation", "-HDRGainMapVersion")
    orientation = int(metadata.get("Orientation", 1) or 1)
    source_has_hdr_gain_map = bool(metadata.get("HDRGainMapVersion"))
    source_is_jpeg = _is_jpeg_file(source)
    if source_has_hdr_gain_map and source_is_jpeg and orientation == 1:
        shutil.copyfile(source, output)
        return "jpeg-copy-ultrahdr"
    if source_has_hdr_gain_map and config.enable_ultra_hdr and video is not None and not source_is_jpeg:
        try:
            return prepare_ultrahdr_jpeg(source, video, output, config)
        except UnsupportedMediaError:
            if not config.allow_hdr_sdr_fallback:
                raise
    if source_has_hdr_gain_map and not config.allow_hdr_sdr_fallback:
        raise UnsupportedMediaError(
            "HDR HEIC requires Ultra HDR conversion; refusing unsafe SDR fallback "
            "(set MOLIVE_ALLOW_HDR_SDR_FALLBACK=true only for explicit testing)"
        )
    if source_is_jpeg and orientation == 1 and not source_has_hdr_gain_map:
        shutil.copyfile(source, output)
        return "jpeg-copy"

    run([
        _image_tool(), str(source), "-auto-orient", "-quality", str(config.jpeg_quality),
        "-sampling-factor", "4:2:0", str(output),
    ])
    run([
        "exiftool", "-overwrite_original", "-TagsFromFile", str(source), "-all:all", "--icc_profile", "--makernotes",
        "-Orientation#=1", "-XMP-HDRGainMap:all=", str(output),
    ], check=False)
    return "jpeg-encode-once-sdr-hdr-source" if source_has_hdr_gain_map else "jpeg-encode-once"


def _rotation(stream: dict) -> int:
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return int(round(float(side["rotation"]))) % 360
    try:
        return int(stream.get("tags", {}).get("rotate", 0)) % 360
    except (TypeError, ValueError):
        return 0


def _cover_timestamp_us(video: Path, info: dict) -> int:
    result = run([
        "ffprobe", "-v", "error", "-select_streams", "d", "-show_entries", "packet=pts_time,size",
        "-of", "json", str(video),
    ], check=False)
    if result.returncode == 0:
        try:
            packets = json.loads(result.stdout or "{}").get("packets", [])
            values = [float(p["pts_time"]) for p in packets if 0 < int(p.get("size", 999)) <= 16 and float(p.get("pts_time", 0)) > 0]
            if values:
                return int(min(values) * 1_000_000)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
    duration = float(info.get("format", {}).get("duration") or 0)
    return int(max(0, duration / 2) * 1_000_000)


def prepare_video(
    source: Path,
    output: Path,
    config: Config,
    transcode_semaphore: threading.Semaphore | None = None,
) -> tuple[str, int]:
    info = ffprobe(source)
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not videos:
        raise ValueError("Live Photo companion has no video track")
    video = videos[0]
    audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    rotation = _rotation(video)
    compatible_video = video.get("codec_name") in {"h264", "hevc"}
    compatible_audio = not audios or all(s.get("codec_name") == "aac" for s in audios)
    timestamp_us = _cover_timestamp_us(source, info)

    if rotation == 0 and compatible_video:
        audio_args = ["-c:a", "copy"] if compatible_audio else ["-c:a", "aac", "-b:a", "192k"]
        run([
            "ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-c:v", "copy",
            *audio_args, "-map_metadata", "0", "-movflags", "+faststart", "-brand", "mp42", str(output),
        ])
        audio_mode = "audio-copy" if compatible_audio else "audio-aac"
        return f"video-copy+{audio_mode}", timestamp_us

    filters = {90: "transpose=clock", 180: "hflip,vflip", 270: "transpose=cclock"}
    vf = filters.get(rotation)
    command = [
        "ffmpeg", "-y", "-noautorotate", "-display_rotation:v:0", "0", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?",
    ]
    if vf:
        command += ["-vf", vf]
    common_tail = [
        "-metadata:s:v:0", "rotate=0", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-brand", "mp42", str(output),
    ]
    software_codec = [
        "-c:v", "libx264", "-preset", "fast", "-crf", str(config.video_crf), "-pix_fmt", "yuv420p",
    ]

    def transcode() -> str:
        if _qsv_available(config):
            qsv_codec = [
                "-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", str(config.video_crf),
                "-look_ahead", "0", "-pix_fmt", "nv12",
            ]
            try:
                run(command + qsv_codec + common_tail)
                return "qsv"
            except Exception as exc:
                log.warning("QSV unavailable for %s, falling back to libx264: %s", source, exc)
                output.unlink(missing_ok=True)
        run(command + software_codec + common_tail)
        return "libx264"

    if transcode_semaphore is None:
        encoder = transcode()
    else:
        with transcode_semaphore:
            encoder = transcode()
    return f"video-transcode-{encoder}-rotation-{rotation}", timestamp_us


def convert(
    image: Path,
    video: Path,
    output: Path,
    config: Config,
    transcode_semaphore: threading.Semaphore | None = None,
) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="molive-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        jpeg = temp / "image.jpg"
        mp4 = temp / "video.mp4"
        tagged = temp / "tagged.jpg"
        final = temp / "final.tmp"

        image_mode = prepare_jpeg(image, jpeg, config, video)
        video_mode, timestamp_us = prepare_video(video, mp4, config, transcode_semaphore)
        run([
            "exiftool", "-config", str(PROJECT_ROOT / ".exiftool_config"), "-overwrite_original",
            "-MicroVideo=1", "-XiaomiMicroVideo=1", "-EmbeddedVideo=1", str(jpeg),
        ])
        # ExifTool 可能会重写未注册的 XMP，因此 XMP 必须在所有 EXIF 操作完成后最后注入。
        inject_xmp(jpeg, tagged, mp4.stat().st_size, timestamp_us)

        with final.open("wb") as target:
            for source in (tagged, mp4):
                with source.open("rb") as stream:
                    shutil.copyfileobj(stream, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())

        report = validate(final)
        os.replace(final, output)
        os.utime(output, (image.stat().st_atime, image.stat().st_mtime))
        return {**report, "mode": f"{image_mode}+{video_mode}", "timestamp_us": timestamp_us}
