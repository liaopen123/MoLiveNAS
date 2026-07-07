from __future__ import annotations

import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .commands import require_tools
from .config import Config
from .converter import convert
from .database import Database
from .matcher import scan
from .web import start as start_web

log = logging.getLogger(__name__)


class Service:
    def __init__(self, config: Config):
        self.config = config
        config.ensure_directories()
        self.db = Database(config.database_path)
        self.transcode_semaphore = threading.Semaphore(config.transcode_workers)

    @staticmethod
    def _inside(path: str, root: Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError(f"job path escapes configured root: {resolved}")
        return resolved

    def process_once(self) -> None:
        scan(self.config, self.db)
        jobs = self.db.pending()
        if not jobs:
            return
        with ThreadPoolExecutor(max_workers=self.config.workers, thread_name_prefix="convert") as pool:
            futures = {}
            for job in jobs:
                self.db.mark(job["id"], "running")
                future = pool.submit(
                    convert,
                    image=self._inside(job["image_path"], self.config.input_dir),
                    video=self._inside(job["video_path"], self.config.input_dir),
                    output=self._inside(job["output_path"], self.config.output_dir),
                    config=self.config,
                    transcode_semaphore=self.transcode_semaphore,
                )
                futures[future] = job
            for future in as_completed(futures):
                job = futures[future]
                try:
                    report = future.result()
                    self.db.mark(job["id"], "success", mode=report["mode"])
                    log.info("converted: %s (%s)", job["image_path"], report["mode"])
                except Exception as exc:
                    status = "retry" if job["attempts"] < 3 else "failed"
                    self.db.mark(job["id"], status, error=str(exc)[-4000:])
                    log.exception("conversion failed: %s", job["image_path"])

    def daemon(self) -> None:
        require_tools()
        start_web(self.db, self.config.web_port)
        log.info("MoLive NAS started: input=%s output=%s", self.config.input_dir, self.config.output_dir)
        while True:
            try:
                self.process_once()
            except Exception:
                log.exception("scan cycle failed")
            time.sleep(self.config.scan_interval)
