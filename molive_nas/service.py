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

    def process_once(self) -> int:
        scan(self.config, self.db)
        jobs = self.db.pending()
        if not jobs:
            return 0
        with ThreadPoolExecutor(max_workers=self.config.workers, thread_name_prefix="convert") as pool:
            futures = {}
            for job in jobs:
                future = pool.submit(
                    self._run_job,
                    job["id"],
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
                    attempt_number = job["attempts"] + 1
                    status = "retry" if attempt_number < 3 else "failed"
                    self.db.mark(job["id"], status, error=str(exc)[-4000:])
                    log.exception("conversion failed: %s", job["image_path"])
        return len(jobs)

    def _run_job(self, job_id: int, **kwargs):
        # 只有线程池真正开始执行任务时，才标记 running 并增加尝试次数。
        self.db.mark(job_id, "running")
        return convert(**kwargs)

    def daemon(self) -> None:
        require_tools()
        start_web(self.db, self.config.web_port)
        log.info("MoLive NAS started: input=%s output=%s", self.config.input_dir, self.config.output_dir)
        while True:
            try:
                processed = self.process_once()
            except Exception:
                log.exception("scan cycle failed")
                processed = 0
            # 队列仍有积压时立即处理下一批；只在无任务时等待扫描周期。
            if processed and self.db.pending(limit=1):
                continue
            time.sleep(self.config.scan_interval)
