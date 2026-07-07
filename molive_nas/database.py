from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY,
  size INTEGER NOT NULL,
  mtime REAL NOT NULL,
  first_stable_seen REAL NOT NULL,
  content_id TEXT,
  kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  image_path TEXT NOT NULL,
  video_path TEXT NOT NULL,
  output_path TEXT NOT NULL,
  fingerprint TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  mode TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()
        self.connection().executescript(SCHEMA)

    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def observe_file(self, path: Path, kind: str) -> float:
        stat = path.stat()
        now = time.time()
        row = self.connection().execute("SELECT size,mtime,first_stable_seen FROM files WHERE path=?", (str(path),)).fetchone()
        if row and row["size"] == stat.st_size and row["mtime"] == stat.st_mtime:
            return now - row["first_stable_seen"]
        self.connection().execute(
            "INSERT INTO files(path,size,mtime,first_stable_seen,kind) VALUES(?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,first_stable_seen=excluded.first_stable_seen,kind=excluded.kind",
            (str(path), stat.st_size, stat.st_mtime, now, kind),
        )
        return 0

    def enqueue(self, image: Path, video: Path, output: Path, fingerprint: str) -> None:
        now = time.time()
        self.connection().execute(
            "INSERT OR IGNORE INTO jobs(image_path,video_path,output_path,fingerprint,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (str(image), str(video), str(output), fingerprint, "pending", now, now),
        )
        row = self.connection().execute(
            "SELECT id,status,output_path FROM jobs WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if row and row["status"] == "success" and not Path(row["output_path"]).exists():
            self.connection().execute(
                "UPDATE jobs SET status='retry',error='output file was removed',updated_at=? WHERE id=?",
                (now, row["id"]),
            )

    def pending(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(self.connection().execute(
            "SELECT * FROM jobs WHERE status IN ('pending','retry') ORDER BY id LIMIT ?", (limit,)
        ))

    def mark(self, job_id: int, status: str, *, error: str | None = None, mode: str | None = None) -> None:
        self.connection().execute(
            "UPDATE jobs SET status=?,error=?,mode=COALESCE(?,mode),attempts=attempts+CASE WHEN ?='running' THEN 1 ELSE 0 END,updated_at=? WHERE id=?",
            (status, error, mode, status, time.time(), job_id),
        )

    def stats(self) -> dict[str, int]:
        rows = self.connection().execute("SELECT status,COUNT(*) count FROM jobs GROUP BY status")
        result = {row["status"]: row["count"] for row in rows}
        result["total"] = sum(result.values())
        return result

    def recent(self, limit: int = 50) -> list[dict]:
        rows = self.connection().execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in rows]
