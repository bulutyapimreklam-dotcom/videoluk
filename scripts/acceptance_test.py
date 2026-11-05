#!/usr/bin/env python3
"""Run Videoluk's complete local production path without paid providers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def request(base_url: str, path: str, method: str = "GET", payload: dict | None = None,
            data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else data
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    http_request = Request(f"{base_url}{path}", data=body, headers=request_headers, method=method)
    try:
        with urlopen(http_request, timeout=120) as response:
            return response.read(), response.headers.get_content_type()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} returned {exc.code}: {detail}") from exc


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None,
                 data: bytes | None = None, headers: dict[str, str] | None = None) -> dict:
    raw, content_type = request(base_url, path, method, payload, data, headers)
    assert content_type == "application/json", f"{path} returned {content_type}"
    return json.loads(raw.decode("utf-8"))


def configure_temporary_data(root: Path) -> None:
    server.DATA = root
    server.OUTPUTS = root / "renders"
    server.VOICES = root / "voices"
    server.MEDIA_CACHE = root / "media-cache"
    server.GENERATED_IMAGES = root / "generated-images"
    server.UPLOADS = root / "uploads"
    server.TRAINING_VIDEOS = root / "training-videos"
    server.DB_PATH = root / "videoluk.db"
    server.AUTH_REQUIRED = False


def generate_test_image(path: Path) -> None:
    result = subprocess.run([
        server.FFMPEG, "-y", "-f", "lavfi", "-i", "color=c=#c9ff5b:s=640x360",
        "-frames:v", "1", str(path),
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and path.stat().st_size > 1024, result.stderr[-2000:]


def generate_synthetic_test_voice() -> dict:
    voice_id = str(uuid.uuid4())
    target = server.VOICES / f"{voice_id}.wav"
    result = subprocess.run([
        server.FFMPEG, "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=3",
        "-ac", "2", str(target),
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and target.stat().st_size > 1024, result.stderr[-2000:]
    return {"id": voice_id, "audioUrl": f"/api/voices/{voice_id}", "provider": "synthetic-test"}


def run() -> dict:
    with tempfile.TemporaryDirectory(prefix="videoluk-acceptance-") as temporary:
        root = Path(temporary)
        configure_temporary_data(root)
        server.initialize()
        http_server = ThreadingHTTPServer(("127.0.0.1", 0), server.VideolukHandler)
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{http_server.server_port}"
        try:
            health = request_json(base_url, "/api/health")
            assert health["service"] == "videoluk-api"

            generated = request_json(base_url, "/api/scripts/generate", "POST", {
                "idea": "Mahalle üreticilerini müşterilerle buluşturan sürdürülebilir pazar",
                "duration": 15,
                "type": "Tanıtım",
                "tone": "Bilgilendirici",
            })
            assert len(generated["scenes"]) >= 3
            assert len({scene["subtitle"] for scene in generated["scenes"]}) == len(generated["scenes"])

            image_path = root / "acceptance.png"
            generate_test_image(image_path)
            media = request_json(base_url, "/api/uploads", "POST", data=image_path.read_bytes(), headers={
                "X-File-Name": "kabul-gorseli.png",
                "X-Media-Kind": "image",
                "Content-Type": "image/png",
            })
            assert media["imageUrl"] and media["uploadId"]

            narration = " ".join(scene["subtitle"] for scene in generated["scenes"])
            try:
                voice = request_json(base_url, "/api/voices/generate", "POST", {"text": narration})
            except AssertionError:
                if os.getenv("VIDEOLUK_ACCEPTANCE_ALLOW_SYNTHETIC_VOICE") != "1":
                    raise
                voice = generate_synthetic_test_voice()
            voice_bytes, voice_type = request(base_url, voice["audioUrl"])
            assert voice_type in {"audio/wav", "audio/x-wav"} and len(voice_bytes) > 1024

            scenes = []
            for scene in generated["scenes"]:
                scenes.append({**scene, "duration": 1, "media": media})
            project_payload = {
                "title": "Otomatik kabul testi",
                "duration": len(scenes),
                "orientation": "horizontal",
                "source": "Stok görüntü",
                "script": generated["script"],
                "scenes": scenes,
                "voiceId": voice["id"],
                "captions": {"enabled": True, "style": "classic", "position": "bottom"},
            }

            stock_cost = request_json(base_url, "/api/cost-estimate", "POST", project_payload)
            ai_cost = request_json(base_url, "/api/cost-estimate", "POST", {**project_payload, "source": "Yapay zekâ"})
            assert ai_cost["totalCredits"] > stock_cost["totalCredits"]

            saved = request_json(base_url, "/api/projects", "POST", project_payload)
            loaded = request_json(base_url, f"/api/projects/{saved['id']}")
            assert loaded["title"] == project_payload["title"] and len(loaded["scenes"]) == len(scenes)

            usage_before = request_json(base_url, "/api/usage")
            render_job = request_json(base_url, "/api/renders", "POST", {"projectId": saved["id"]})
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                status = request_json(base_url, f"/api/renders/{render_job['id']}")
                if status["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.5)
            else:
                raise AssertionError("Render did not finish within 120 seconds")
            assert status["status"] == "completed", status.get("error")
            assert status["progress"] == 100 and status["downloadUrl"] and status["subtitleUrl"]

            with server.db() as connection:
                stored_render = connection.execute(
                    "SELECT output_path, subtitle_path FROM render_jobs WHERE id = ?", (render_job["id"],)
                ).fetchone()
            assert stored_render and Path(stored_render["output_path"]).is_file(), stored_render["output_path"] if stored_render else None
            assert Path(stored_render["subtitle_path"]).is_file(), stored_render["subtitle_path"]

            video, video_type = request(base_url, status["downloadUrl"])
            subtitles, subtitle_type = request(base_url, status["subtitleUrl"])
            assert video_type == "video/mp4" and len(video) > 10_000
            assert subtitle_type in {"application/x-subrip", "text/plain"} and b"00:00:00,000" in subtitles
            usage_after = request_json(base_url, "/api/usage")
            assert usage_after["credits"] == usage_before["credits"] - stock_cost["totalCredits"]
            assert usage_after["renders"]["used"] == usage_before["renders"]["used"] + 1

            return {
                "scenes": len(scenes), "orientation": project_payload["orientation"],
                "voice": voice["provider"], "renderBytes": len(video),
                "subtitleBytes": len(subtitles), "credits": stock_cost["totalCredits"],
            }
        finally:
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    print(json.dumps({"ok": True, "acceptance": run()}, ensure_ascii=False))
