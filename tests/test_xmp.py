import tempfile
import unittest
from pathlib import Path

from molive_nas.validator import video_length
from molive_nas.xmp import inject_xmp, packet


class XMPTests(unittest.TestCase):
    def test_packet_contains_modern_and_legacy_length(self):
        data = packet(123456, 1500000)
        self.assertEqual(video_length(data), 123456)
        self.assertIn(b'MicroVideoOffset="123456"', data)
        self.assertIn(b'MotionPhotoPresentationTimestampUs="1500000"', data)

    def test_injection_does_not_modify_jpeg_body(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jpg"
            output = Path(directory) / "output.jpg"
            body = b"\xff\xd8\xff\xda\x00\x02pixels\xff\xd9"
            source.write_bytes(body)
            inject_xmp(source, output, 100, 50)
            result = output.read_bytes()
            self.assertTrue(result.startswith(b"\xff\xd8\xff\xe1"))
            self.assertTrue(result.endswith(body[2:]))


if __name__ == "__main__":
    unittest.main()
