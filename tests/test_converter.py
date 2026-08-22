import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molive_nas.config import Config
from molive_nas.converter import UnsupportedMediaError, prepare_jpeg

JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"


class ConverterSafetyTests(unittest.TestCase):
    def test_hdr_is_rejected_without_explicit_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.heic"
            output = Path(directory) / "output.jpg"
            source.write_bytes(b"placeholder")
            config = Config(allow_hdr_sdr_fallback=False)
            with patch(
                "molive_nas.converter.exif_json",
                return_value={"Orientation": 1, "HDRGainMapVersion": "0.2.0.0"},
            ):
                with self.assertRaisesRegex(UnsupportedMediaError, "requires Ultra HDR"):
                    prepare_jpeg(source, output, config)

    def test_hdr_jpeg_with_explicit_sdr_fallback_is_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jpg"
            output = Path(directory) / "output.jpg"
            source.write_bytes(b"placeholder")
            config = Config(allow_hdr_sdr_fallback=True)
            with patch(
                "molive_nas.converter.exif_json",
                return_value={"Orientation": 1, "HDRGainMapVersion": "1.0"},
            ), patch("molive_nas.converter.run") as mocked_run:
                mode = prepare_jpeg(source, output, config)
            self.assertEqual(mode, "jpeg-encode-once-sdr-hdr-source")
            self.assertEqual(mocked_run.call_count, 2)

    def test_hdr_heic_uses_ultrahdr_bridge_when_video_is_available(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.heic"
            video = Path(directory) / "source.mov"
            output = Path(directory) / "output.jpg"
            source.write_bytes(b"placeholder")
            video.write_bytes(b"video")
            config = Config(enable_ultra_hdr=True, allow_hdr_sdr_fallback=False)
            with patch(
                "molive_nas.converter.exif_json",
                return_value={"Orientation": 1, "HDRGainMapVersion": "0.2.0.0"},
            ), patch("molive_nas.converter.prepare_ultrahdr_jpeg", return_value="jpeg-ultrahdr") as bridge:
                mode = prepare_jpeg(source, output, config, video)
            self.assertEqual(mode, "jpeg-ultrahdr")
            bridge.assert_called_once_with(source, video, output, config)

    def test_hdr_heic_falls_back_to_sdr_when_bridge_fails_and_fallback_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.heic"
            video = Path(directory) / "source.mov"
            output = Path(directory) / "output.jpg"
            source.write_bytes(b"placeholder")
            video.write_bytes(b"video")
            config = Config(enable_ultra_hdr=True, allow_hdr_sdr_fallback=True)
            with patch(
                "molive_nas.converter.exif_json",
                return_value={"Orientation": 1, "HDRGainMapVersion": "0.2.0.0"},
            ), patch(
                "molive_nas.converter.prepare_ultrahdr_jpeg",
                side_effect=UnsupportedMediaError("bridge failed"),
            ), patch("molive_nas.converter.run") as mocked_run:
                mode = prepare_jpeg(source, output, config, video)
            self.assertEqual(mode, "jpeg-encode-once-sdr-hdr-source")
            self.assertEqual(mocked_run.call_count, 2)

    def test_existing_ultrahdr_jpeg_is_copied_without_reencoding(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.HEIC"
            output = Path(directory) / "output.jpg"
            source.write_bytes(JPEG_HEADER + b"ultrahdr")
            config = Config(enable_ultra_hdr=True, allow_hdr_sdr_fallback=False)
            with patch(
                "molive_nas.converter.exif_json",
                return_value={"Orientation": 1, "HDRGainMapVersion": "1.0"},
            ), patch("molive_nas.converter.run") as mocked_run:
                mode = prepare_jpeg(source, output, config)
            self.assertEqual(mode, "jpeg-copy-ultrahdr")
            self.assertEqual(output.read_bytes(), source.read_bytes())
            mocked_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
