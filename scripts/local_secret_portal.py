#!/usr/bin/env python3
"""One-shot localhost form for saving the Videoluk OpenAI key securely."""

from __future__ import annotations

import html
import os
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"
TOKEN = secrets.token_urlsafe(24)


def save_secret(value: str) -> None:
    value = value.strip()
    if len(value) < 20 or any(character.isspace() for character in value):
        raise ValueError("Anahtar biçimi geçersiz")
    source = ENV_FILE if ENV_FILE.exists() else EXAMPLE
    lines = source.read_text(encoding="utf-8").splitlines()
    name = "VIDEOLUK_OPENAI_API_KEY"
    replacement = f"{name}={value}"
    for index, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[index] = replacement
            break
    else:
        lines.extend(["", replacement])
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env-", dir=ROOT, text=True)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
        temporary.chmod(0o600)
        temporary.replace(ENV_FILE)
    finally:
        temporary.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def send_page(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if urlparse(self.path).path != f"/{TOKEN}":
            self.send_error(404)
            return
        self.send_page(f"""<!doctype html><html lang=\"tr\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>Videoluk · OpenAI bağlantısı</title>
<style>body{{margin:0;background:#071b18;color:#f5f7f3;font:16px system-ui;display:grid;place-items:center;min-height:100vh}}main{{width:min(560px,calc(100% - 48px));background:#102a25;border:1px solid #315048;border-radius:24px;padding:32px;box-shadow:0 24px 80px #0008}}b{{color:#c9ff5b}}h1{{font-size:28px;margin:10px 0}}p{{color:#b8c8c2;line-height:1.55}}input{{box-sizing:border-box;width:100%;padding:15px;border:1px solid #49665e;border-radius:12px;background:#071b18;color:white;font-size:16px;margin:12px 0}}button{{width:100%;padding:15px;border:0;border-radius:12px;background:#c9ff5b;color:#071b18;font-weight:800;font-size:16px}}small{{display:block;color:#91a69f;margin-top:14px}}</style>
<main><b>VİDEOLUK</b><h1>OpenAI API anahtarını bağla</h1><p>Anahtar yalnızca bu bilgisayardaki gizli <code>.env</code> dosyasına kaydedilir. GitHub'a gönderilmez ve ekranda gösterilmez.</p><form method=\"post\" action=\"/{TOKEN}\" autocomplete=\"off\"><input type=\"password\" name=\"key\" required minlength=\"20\" placeholder=\"OpenAI API anahtarı\" autofocus><button>Güvenli biçimde kaydet</button></form><small>Tek kullanımlık yerel bağlantı · 127.0.0.1</small></main></html>""")

    def do_POST(self) -> None:
        if urlparse(self.path).path != f"/{TOKEN}":
            self.send_error(404)
            return
        length = min(int(self.headers.get("Content-Length", "0")), 16_384)
        try:
            value = parse_qs(self.rfile.read(length).decode("utf-8")).get("key", [""])[0]
            save_secret(value)
            self.send_page("<!doctype html><html lang='tr'><meta charset='utf-8'><style>body{background:#071b18;color:white;font:20px system-ui;display:grid;place-items:center;min-height:100vh}div{text-align:center}b{color:#c9ff5b;font-size:32px}</style><div><b>Kaydedildi</b><p>Bu sekmeyi kapatabilirsiniz.</p></div></html>")
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        except ValueError as exc:
            self.send_page(f"<h1>Kaydedilemedi</h1><p>{html.escape(str(exc))}</p>", 400)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(f"http://127.0.0.1:{server.server_port}/{TOKEN}", flush=True)
    server.serve_forever()
