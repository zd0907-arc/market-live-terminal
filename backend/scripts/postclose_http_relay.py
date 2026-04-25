from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


def _safe_path(root: Path, raw_path: str) -> Path:
    parsed = urlparse(raw_path)
    rel = unquote(parsed.path or "").lstrip("/")
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise PermissionError(f"illegal path: {raw_path}")
    return target


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "PostcloseRelay/1.0"

    @property
    def relay_root(self) -> Path:
        return self.server.relay_root  # type: ignore[attr-defined]

    @property
    def relay_token(self) -> str:
        return self.server.relay_token  # type: ignore[attr-defined]

    def _authorized(self) -> bool:
        return self.headers.get("X-Relay-Token", "") == self.relay_token

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/__health__":
            self._json(
                HTTPStatus.OK,
                {"ok": True, "root": str(self.relay_root), "pid": os.getpid()},
            )
            return
        try:
            target = _safe_path(self.relay_root, self.path)
        except PermissionError as exc:
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": str(exc)})
            return
        if not target.exists() or not target.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        size = target.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(target, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return
        try:
            target = _safe_path(self.relay_root, self.path)
        except PermissionError as exc:
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": str(exc)})
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        length = int(self.headers.get("Content-Length", "0") or "0")
        remaining = length
        tmp = target.with_suffix(target.suffix + ".part")
        with open(tmp, "wb") as fh:
            while remaining > 0:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                fh.write(chunk)
                remaining -= len(chunk)
        if remaining != 0:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "incomplete body"})
            return
        tmp.replace(target)
        self._json(HTTPStatus.OK, {"ok": True, "path": str(target), "bytes": target.stat().st_size})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Postclose HTTP relay")
    parser.add_argument("--root", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    relay_root = Path(args.root).expanduser().resolve()
    relay_root.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.host, int(args.port)), RelayHandler)
    server.relay_root = relay_root  # type: ignore[attr-defined]
    server.relay_token = str(args.token)  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == "__main__":
    main()
