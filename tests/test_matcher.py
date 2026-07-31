import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molive_nas.config import Config
from molive_nas.database import Database
from molive_nas.matcher import scan


class MatcherTests(unittest.TestCase):
    def test_disappearing_file_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            self.assertEqual(db.observe_file(Path(directory) / "removed.heic", "image"), 0)

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
            job = db.pending()[0]
            self.assertEqual(Path(job["output_path"]).parent, output)
            self.assertTrue(Path(job["output_path"]).name.startswith("IMG_0001_"))

    def test_removed_output_is_not_requeued_after_success(self):
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
            self.assertIsNone(db.stats().get("retry"))
            self.assertEqual(db.stats().get("success"), 1)

    def test_flat_outputs_do_not_collide_for_same_name_in_different_dirs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            data = root / "data"
            first = source / "2024"
            second = source / "2025"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            output.mkdir()
            data.mkdir()
            for folder in (first, second):
                (folder / "IMG_0001.HEIC").write_bytes(b"image")
                (folder / "IMG_0001.MOV").write_bytes(b"video")
            config = Config(input_dir=source, output_dir=output, data_dir=data, stable_seconds=0)
            db = Database(data / "test.sqlite3")
            scan(config, db)
            paths = [Path(job["output_path"]) for job in db.pending()]
            self.assertEqual(len(paths), 2)
            self.assertEqual({path.parent for path in paths}, {output})
            self.assertEqual(len({path.name for path in paths}), 2)


if __name__ == "__main__":
    unittest.main()
