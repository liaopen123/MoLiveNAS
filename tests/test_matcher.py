import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molive_nas.config import Config
from molive_nas.database import Database
from molive_nas.matcher import scan


class MatcherTests(unittest.TestCase):
    def test_same_stem_pair_is_enqueued_after_stable_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            data = root / "data"
            source.mkdir()
            output.mkdir()
            data.mkdir()
            (source / "IMG_0001.HEIC").write_bytes(b"image")
            (source / "IMG_0001.MOV").write_bytes(b"video")
            config = Config(input_dir=source, output_dir=output, data_dir=data, stable_seconds=0)
            db = Database(data / "test.sqlite3")
            scan(config, db)
            self.assertEqual(db.stats().get("pending"), 1)

    def test_removed_output_is_requeued(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / "test.sqlite3")
            image, video, output = root / "a.heic", root / "a.mov", root / "a_MP.jpg"
            image.write_bytes(b"image")
            video.write_bytes(b"video")
            output.write_bytes(b"result")
            db.enqueue(image, video, output, "fingerprint")
            job = db.pending()[0]
            db.mark(job["id"], "success")
            output.unlink()
            db.enqueue(image, video, output, "fingerprint")
            self.assertEqual(db.stats().get("retry"), 1)


if __name__ == "__main__":
    unittest.main()
