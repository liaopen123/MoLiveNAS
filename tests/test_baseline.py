import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molive_nas.config import Config
from molive_nas.service import Service


def create_pair(directory: Path, stem: str) -> None:
    (directory / f"{stem}.HEIC").write_bytes(b"image")
    (directory / f"{stem}.MOV").write_bytes(b"video")


class BaselineTests(unittest.TestCase):
    def test_first_run_skips_existing_pair_but_processes_future_pair_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, data = root / "source", root / "output", root / "data"
            source.mkdir()
            create_pair(source, "IMG_OLD")
            config = Config(
                input_dir=source,
                output_dir=output,
                data_dir=data,
                stable_seconds=0,
                baseline_on_first_run=True,
            )

            first_service = Service(config)
            with patch("molive_nas.service.convert") as convert:
                self.assertEqual(first_service.process_once(), 0)
                convert.assert_not_called()
            self.assertEqual(first_service.db.stats().get("baseline"), 1)
            self.assertEqual(first_service.db.pending(), [])

            create_pair(source, "IMG_NEW")
            restarted_service = Service(config)
            with patch(
                "molive_nas.service.convert",
                return_value={"mode": "test", "timestamp_us": 0},
            ) as convert:
                self.assertEqual(restarted_service.process_once(), 1)
                convert.assert_called_once()
            self.assertEqual(restarted_service.db.stats().get("success"), 1)
            self.assertEqual(restarted_service.db.stats().get("baseline"), 1)


if __name__ == "__main__":
    unittest.main()
