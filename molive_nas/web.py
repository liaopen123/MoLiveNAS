from __future__ import annotations

import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .database import Database


def start(db: Database, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self._send("text/plain", b"ok")
                return
            if self.path == "/api/status":
                self._send("application/json", json.dumps({"stats": db.stats(), "recent": db.recent()}, ensure_ascii=False).encode())
                return
            if self.path != "/":
                self.send_error(404)
                return
            stats = db.stats()
            rows = "".join(
                f"<tr><td>{job['id']}</td><td>{html.escape(job['status'])}</td><td>{html.escape(job['image_path'])}</td>"
                f"<td>{html.escape(job.get('mode') or '')}</td><td>{html.escape(job.get('error') or '')}</td></tr>"
                for job in db.recent()
            )
            body = f"""<!doctype html><meta charset='utf-8'><meta http-equiv='refresh' content='30'>
<title>MoLive NAS</title><style>body{{font:14px system-ui;margin:32px;color:#222}}.cards{{display:flex;gap:12px}}.card{{padding:16px 24px;background:#f4f5f7;border-radius:12px}}table{{margin-top:24px;border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}td:nth-child(3){{max-width:500px;word-break:break-all}}</style>
<h1>MoLive NAS</h1><div class='cards'>{''.join(f"<div class='card'><b>{html.escape(k)}</b><br>{v}</div>" for k,v in stats.items())}</div>
<table><thead><tr><th>ID</th><th>状态</th><th>原图</th><th>处理方式</th><th>错误</th></tr></thead><tbody>{rows}</tbody></table>"""
            self._send("text/html; charset=utf-8", body.encode())

        def _send(self, content_type: str, payload: bytes):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="web", daemon=True).start()
    return server
