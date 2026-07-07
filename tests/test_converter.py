import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molive_nas.config import Config
from molive_nas.converter import prepare_jpeg


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
                with self.assertRaisesRegex(ValueError, "requires Ultra HDR"):
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


if __name__ == "__main__":
    unittest.main()
