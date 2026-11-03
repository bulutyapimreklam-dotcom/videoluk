#!/usr/bin/env python3
"""Videoluk MVP API and CPU render worker.

Runs without third-party Python packages. FFmpeg must be installed.
"""

from __future__ import annotations

import json
import hashlib
import html
import mimetypes
import math
import os
import base64
import binascii
import hmac
import secrets
from concurrent.futures import ThreadPoolExecutor
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
import uuid
import re
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
DATA = Path(os.getenv("VIDEOLUK_DATA_DIR", ROOT / "data"))
OUTPUTS = DATA / "renders"
VOICES = DATA / "voices"
MEDIA_CACHE = DATA / "media-cache"
GENERATED_IMAGES = DATA / "generated-images"
UPLOADS = DATA / "uploads"
TRAINING_VIDEOS = DATA / "training-videos"
DB_PATH = DATA / "videoluk.db"
FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_BIN", "ffprobe")
HOST = os.getenv("VIDEOLUK_HOST", "127.0.0.1")
PORT = int(os.getenv("VIDEOLUK_PORT", "8787"))
LLM_URL = os.getenv("VIDEOLUK_LLM_URL", "").rstrip("/")
LLM_MODEL = os.getenv("VIDEOLUK_LLM_MODEL", "")
LLM_API_KEY = os.getenv("VIDEOLUK_LLM_API_KEY", "")
LLM_TIMEOUT = int(os.getenv("VIDEOLUK_LLM_TIMEOUT", "60"))
IMAGE_URL = os.getenv("VIDEOLUK_IMAGE_URL", "").rstrip("/")
IMAGE_MODEL = os.getenv("VIDEOLUK_IMAGE_MODEL", "")
IMAGE_API_KEY = os.getenv("VIDEOLUK_IMAGE_API_KEY", "")
IMAGE_TIMEOUT = int(os.getenv("VIDEOLUK_IMAGE_TIMEOUT", "180"))
AUTH_REQUIRED = os.getenv("VIDEOLUK_AUTH_REQUIRED", "0").lower() in {"1", "true", "yes"}
ADMIN_EMAIL = os.getenv("VIDEOLUK_ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("VIDEOLUK_ADMIN_PASSWORD", "")
SECURE_COOKIES = os.getenv("VIDEOLUK_SECURE_COOKIES", "0").lower() in {"1", "true", "yes"}
SESSION_TTL_DAYS = max(1, min(90, int(os.getenv("VIDEOLUK_SESSION_TTL_DAYS", "14"))))
LOCAL_USER_ID = "local-owner"
PEXELS_API_KEY = os.getenv("VIDEOLUK_PEXELS_API_KEY", "")
MAX_MEDIA_BYTES = int(os.getenv("VIDEOLUK_MAX_MEDIA_BYTES", str(200 * 1024 * 1024)))
MAX_TRAINING_VIDEO_BYTES = int(os.getenv("VIDEOLUK_MAX_TRAINING_VIDEO_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_UPLOAD_BYTES = int(os.getenv("VIDEOLUK_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
MAX_PROJECTS_PER_USER = max(1, int(os.getenv("VIDEOLUK_MAX_PROJECTS_PER_USER", "50")))
MAX_STORAGE_BYTES_PER_USER = max(MAX_UPLOAD_BYTES, int(os.getenv("VIDEOLUK_MAX_STORAGE_BYTES_PER_USER", str(5 * 1024 * 1024 * 1024))))
MAX_MONTHLY_RENDERS_PER_USER = max(1, int(os.getenv("VIDEOLUK_MAX_MONTHLY_RENDERS_PER_USER", "60")))
STARTER_CREDITS = max(0, int(os.getenv("VIDEOLUK_STARTER_CREDITS", "120")))
IYZICO_API_KEY = os.getenv("VIDEOLUK_IYZICO_API_KEY", "")
IYZICO_SECRET_KEY = os.getenv("VIDEOLUK_IYZICO_SECRET_KEY", "")
IYZICO_BASE_URL = os.getenv("VIDEOLUK_IYZICO_BASE_URL", "https://sandbox-api.iyzipay.com").rstrip("/")
PUBLIC_BASE_URL = os.getenv("VIDEOLUK_PUBLIC_BASE_URL", "").rstrip("/")
CREDIT_PACKAGES = {
    "mini": {"name": "Başlangıç", "credits": 100, "price": "199.00"},
    "creator": {"name": "Üretici", "credits": 500, "price": "799.00"},
    "studio": {"name": "Stüdyo", "credits": 1200, "price": "1499.00"},
}
RENDER_WORKERS = max(1, min(4, int(os.getenv("VIDEOLUK_RENDER_WORKERS", "1"))))
MAX_QUEUED_RENDERS = max(1, int(os.getenv("VIDEOLUK_MAX_QUEUED_RENDERS", "8")))
ALLOWED_ORIGIN = os.getenv("VIDEOLUK_ALLOWED_ORIGIN", "").rstrip("/")
ALERT_WEBHOOK_URL = os.getenv("VIDEOLUK_ALERT_WEBHOOK_URL", "").strip()
ALERT_WEBHOOK_TOKEN = os.getenv("VIDEOLUK_ALERT_WEBHOOK_TOKEN", "").strip()
ALERT_COOLDOWN_SECONDS = max(60, int(os.getenv("VIDEOLUK_ALERT_COOLDOWN_SECONDS", "300")))
DB_LOCK = threading.Lock()
ALERT_LOCK = threading.Lock()
ALERT_LAST_SENT: dict[str, float] = {}
RENDER_EXECUTOR = ThreadPoolExecutor(max_workers=RENDER_WORKERS, thread_name_prefix="videoluk-render")
ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="videoluk-analysis")
ALERT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="videoluk-alert")


def ffmpeg_has_filter(filter_name: str) -> bool:
    try:
        result = subprocess.run(
            [FFMPEG, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return any(
            len(parts) > 1 and parts[1] == filter_name
            for line in result.stdout.splitlines()
            if (parts := line.split())
        )
    except (OSError, subprocess.SubprocessError):
        return False


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    VOICES.mkdir(parents=True, exist_ok=True)
    MEDIA_CACHE.mkdir(parents=True, exist_ok=True)
    GENERATED_IMAGES.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    TRAINING_VIDEOS.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS render_jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                output_path TEXT,
                subtitle_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS editing_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                rules TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS editing_feedback (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                project_id TEXT,
                note TEXT NOT NULL,
                before_state TEXT,
                after_state TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES editing_profiles(id)
            );
            CREATE TABLE IF NOT EXISTS training_videos (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                duration REAL,
                cut_count INTEGER,
                average_shot REAL,
                has_audio INTEGER,
                report TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES editing_profiles(id)
            );
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS user_limits (
                user_id TEXT PRIMARY KEY,
                project_limit INTEGER NOT NULL,
                storage_limit_bytes INTEGER NOT NULL,
                monthly_render_limit INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS media_assets (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                kind TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                thumbnail_path TEXT,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS usage_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 1,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                description TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS payment_orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                package_id TEXT NOT NULL,
                credits INTEGER NOT NULL,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                token TEXT,
                payment_id TEXT,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS system_events (
                id TEXT PRIMARY KEY,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_system_events_created_at ON system_events(created_at DESC);
            """
        )
        project_columns = {row["name"] for row in connection.execute("PRAGMA table_info(projects)").fetchall()}
        if "user_id" not in project_columns:
            connection.execute("ALTER TABLE projects ADD COLUMN user_id TEXT")
        connection.execute("UPDATE projects SET user_id = ? WHERE user_id IS NULL OR user_id = ''", (LOCAL_USER_ID,))
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        if "status" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        local_user = connection.execute("SELECT id FROM users WHERE id = ?", (LOCAL_USER_ID,)).fetchone()
        if not local_user:
            timestamp = now()
            connection.execute(
                "INSERT INTO users (id, email, name, password_hash, role, created_at, updated_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
                (LOCAL_USER_ID, "local@videoluk.internal", "Yerel Kullanıcı", "disabled", "owner", timestamp, timestamp),
            )
        if ADMIN_EMAIL and ADMIN_PASSWORD:
            existing_admin = connection.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
            if not existing_admin:
                timestamp = now()
                connection.execute(
                    "INSERT INTO users (id, email, name, password_hash, role, created_at, updated_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
                    (str(uuid.uuid4()), ADMIN_EMAIL, "Videoluk Yöneticisi", hash_password(ADMIN_PASSWORD), "owner", timestamp, timestamp),
                )
        for user_row in connection.execute("SELECT id FROM users").fetchall():
            has_credits = connection.execute("SELECT 1 FROM credit_transactions WHERE user_id = ? LIMIT 1", (user_row["id"],)).fetchone()
            if not has_credits and STARTER_CREDITS:
                connection.execute(
                    "INSERT INTO credit_transactions VALUES (?, ?, ?, 'starter', ?, ?, ?)",
                    (str(uuid.uuid4()), user_row["id"], STARTER_CREDITS, "Başlangıç kredisi", "{}", now()),
                )
        profile_count = connection.execute("SELECT COUNT(*) AS total FROM editing_profiles").fetchone()["total"]
        if not profile_count:
            timestamp = now()
            rules = {
                "hookSeconds": 3,
                "averageShotSeconds": 3.5,
                "rhythm": "Kontrollü dinamik",
                "narrativeStructure": "Kanca → merak → kanıt → duygu → net kapanış",
                "transitionPolicy": "Geçiş efektini yalnızca anlatı gerektiriyorsa kullan",
                "required": [],
                "forbidden": [],
            }
            connection.execute(
                "INSERT INTO editing_profiles VALUES (?, ?, ?, ?, ?, ?)",
                ("default", "Benim Kurgu DNA'm", "Kendi kurgu prensiplerinle doldurulacak ana profil.",
                 json.dumps(rules, ensure_ascii=False), timestamp, timestamp),
            )


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Parola en az 10 karakter olmalı")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derived).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    created_at = now()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    with DB_LOCK, db() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (created_at,))
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?)",
            (session_token_hash(token), user_id, expires_at, created_at),
        )
    return token, expires_at


def update_training_video(video_id: str, **values: object) -> None:
    values["updated_at"] = now()
    columns = ", ".join(f"{key} = ?" for key in values)
    with DB_LOCK, db() as connection:
        connection.execute(
            f"UPDATE training_videos SET {columns} WHERE id = ?",
            [*values.values(), video_id],
        )


def probe_training_video(path: Path) -> dict:
    probe = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if probe.returncode != 0:
        raise ValueError("Video bilgileri okunamadı")
    data = json.loads(probe.stdout or "{}")
    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("Video süresi belirlenemedi")
    streams = data.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    return {
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "hasAudio": any(stream.get("codec_type") == "audio" for stream in streams),
    }


def detect_scene_cuts(path: Path) -> list[float]:
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path), "-vf", "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    return [float(value) for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", combined)]


def analyze_training_video(video_id: str, path: Path) -> None:
    try:
        update_training_video(video_id, status="analyzing", progress=10, error=None)
        technical = probe_training_video(path)
        update_training_video(video_id, progress=35)
        cuts = detect_scene_cuts(path)
        duration = technical["duration"]
        shot_count = max(1, len(cuts) + 1)
        average_shot = round(duration / shot_count, 2)
        orientation = "dikey" if technical["height"] > technical["width"] else "yatay" if technical["width"] > technical["height"] else "kare"
        report = {
            **technical,
            "orientation": orientation,
            "cutTimes": cuts[:5000],
            "cutCount": len(cuts),
            "shotCount": shot_count,
            "averageShotSeconds": average_shot,
        }
        update_training_video(
            video_id, status="ready", progress=100, duration=duration,
            cut_count=len(cuts), average_shot=average_shot,
            has_audio=1 if technical["hasAudio"] else 0,
            report=json.dumps(report, ensure_ascii=False),
        )
    except Exception as exc:
        update_training_video(video_id, status="failed", progress=0, error=str(exc)[:1000])


def training_summary(profile_id: str) -> dict:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM training_videos WHERE profile_id = ? ORDER BY created_at DESC", (profile_id,)
        ).fetchall()
    items = []
    ready_shots = []
    total_duration = 0.0
    for row in rows:
        item = dict(row)
        item.pop("file_path", None)
        item["report"] = json.loads(item["report"]) if item["report"] else None
        items.append(item)
        if row["status"] == "ready" and row["average_shot"]:
            ready_shots.append(float(row["average_shot"]))
            total_duration += float(row["duration"] or 0)
    analyzed_average = round(sum(ready_shots) / len(ready_shots), 2) if ready_shots else None
    return {
        "profileId": profile_id,
        "total": len(rows),
        "ready": sum(1 for row in rows if row["status"] == "ready"),
        "processing": sum(1 for row in rows if row["status"] in {"queued", "analyzing"}),
        "failed": sum(1 for row in rows if row["status"] == "failed"),
        "totalDurationSeconds": round(total_duration, 1),
        "suggestedAverageShotSeconds": analyzed_average,
        "videos": items,
    }


def update_job(job_id: str, **values: object) -> None:
    values["updated_at"] = now()
    columns = ", ".join(f"{key} = ?" for key in values)
    with DB_LOCK, db() as connection:
        connection.execute(
            f"UPDATE render_jobs SET {columns} WHERE id = ?",
            [*values.values(), job_id],
        )


def active_render_count() -> int:
    with db() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM render_jobs WHERE status IN ('queued', 'rendering')"
        ).fetchone()
    return int(row["total"])


def month_start() -> str:
    current = datetime.now(timezone.utc)
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def limits_for_user(user_id: str) -> dict:
    with db() as connection:
        row = connection.execute("SELECT * FROM user_limits WHERE user_id = ?", (user_id,)).fetchone()
    return {
        "projects": int(row["project_limit"]) if row else MAX_PROJECTS_PER_USER,
        "storageBytes": int(row["storage_limit_bytes"]) if row else MAX_STORAGE_BYTES_PER_USER,
        "monthlyRenders": int(row["monthly_render_limit"]) if row else MAX_MONTHLY_RENDERS_PER_USER,
    }


def user_usage(user_id: str) -> dict:
    limits = limits_for_user(user_id)
    with db() as connection:
        projects = int(connection.execute("SELECT COUNT(*) AS total FROM projects WHERE user_id = ?", (user_id,)).fetchone()["total"])
        storage = int(connection.execute("SELECT COALESCE(SUM(size_bytes), 0) AS total FROM media_assets WHERE user_id = ?", (user_id,)).fetchone()["total"])
        renders = int(connection.execute(
            "SELECT COUNT(*) AS total FROM render_jobs JOIN projects ON projects.id = render_jobs.project_id "
            "WHERE projects.user_id = ? AND render_jobs.created_at >= ? AND render_jobs.status != 'failed'",
            (user_id, month_start()),
        ).fetchone()["total"])
        rendered_seconds = float(connection.execute(
            "SELECT COALESCE(SUM(value), 0) AS total FROM usage_events WHERE user_id = ? AND event_type = 'render_seconds' AND created_at >= ?",
            (user_id, month_start()),
        ).fetchone()["total"])
        credits = int(connection.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM credit_transactions WHERE user_id = ?", (user_id,)).fetchone()["total"])
    return {
        "projects": {"used": projects, "limit": limits["projects"]},
        "storage": {"usedBytes": storage, "limitBytes": limits["storageBytes"]},
        "renders": {"used": renders, "limit": limits["monthlyRenders"]},
        "renderedSeconds": round(rendered_seconds, 1),
        "credits": credits,
        "periodStartsAt": month_start(),
    }


def create_managed_user(payload: dict) -> dict:
    email = str(payload.get("email") or "").strip().lower()[:254]
    name = " ".join(str(payload.get("name") or "").split())[:120]
    password = str(payload.get("password") or "")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Geçerli bir e-posta adresi gerekli")
    if len(name) < 2:
        raise ValueError("Kullanıcı adı en az 2 karakter olmalı")
    if len(password) < 10:
        raise ValueError("Geçici parola en az 10 karakter olmalı")
    timestamp = now()
    user_id = str(uuid.uuid4())
    with DB_LOCK, db() as connection:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise ValueError("Bu e-posta adresi zaten kayıtlı")
        connection.execute(
            "INSERT INTO users (id, email, name, password_hash, role, created_at, updated_at, status) VALUES (?, ?, ?, ?, 'member', ?, ?, 'active')",
            (user_id, email, name, hash_password(password), timestamp, timestamp),
        )
        if STARTER_CREDITS:
            connection.execute(
                "INSERT INTO credit_transactions VALUES (?, ?, ?, 'starter', 'Başlangıç kredisi', '{}', ?)",
                (str(uuid.uuid4()), user_id, STARTER_CREDITS, timestamp),
            )
    return {"id": user_id, "email": email, "name": name, "role": "member", "status": "active"}


def update_managed_user(user_id: str, payload: dict, actor_id: str) -> dict:
    with DB_LOCK, db() as connection:
        row = connection.execute("SELECT id, email, name, role, status FROM users WHERE id = ? AND password_hash != 'disabled'", (user_id,)).fetchone()
        if not row:
            raise ValueError("Kullanıcı bulunamadı")
        status = str(payload.get("status") or row["status"])
        if status not in {"active", "suspended"}:
            raise ValueError("Geçersiz hesap durumu")
        if user_id == actor_id and status != "active":
            raise ValueError("Kendi yönetici hesabınızı pasifleştiremezsiniz")
        current_limits = limits_for_user(user_id)
        projects = max(1, min(1000, int(payload.get("projectLimit", current_limits["projects"]))))
        storage_gb = max(1, min(1000, int(payload.get("storageLimitGb", math.ceil(current_limits["storageBytes"] / 1024**3)))))
        renders = max(1, min(10000, int(payload.get("monthlyRenderLimit", current_limits["monthlyRenders"]))))
        adjustment = int(payload.get("creditAdjustment") or 0)
        if abs(adjustment) > 100_000:
            raise ValueError("Tek işlemde en fazla 100.000 kredi değiştirilebilir")
        balance = int(connection.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM credit_transactions WHERE user_id = ?", (user_id,)).fetchone()["total"])
        if balance + adjustment < 0:
            raise ValueError("Kredi bakiyesi sıfırın altına düşemez")
        timestamp = now()
        connection.execute("UPDATE users SET status = ?, updated_at = ? WHERE id = ?", (status, timestamp, user_id))
        connection.execute(
            "INSERT INTO user_limits (user_id, project_limit, storage_limit_bytes, monthly_render_limit, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET project_limit=excluded.project_limit, storage_limit_bytes=excluded.storage_limit_bytes, monthly_render_limit=excluded.monthly_render_limit, updated_at=excluded.updated_at",
            (user_id, projects, storage_gb * 1024**3, renders, timestamp),
        )
        if adjustment:
            connection.execute(
                "INSERT INTO credit_transactions VALUES (?, ?, ?, 'admin', 'Yönetici düzenlemesi', ?, ?)",
                (str(uuid.uuid4()), user_id, adjustment, json.dumps({"actorId": actor_id}), timestamp),
            )
        if status == "suspended":
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"id": user_id, "status": status, "limits": {"projects": projects, "storageGb": storage_gb, "monthlyRenders": renders}, "credits": balance + adjustment}


def send_webhook_alert(level: str, source: str, message: str) -> bool:
    if not ALERT_WEBHOOK_URL:
        return False
    parsed = urlparse(ALERT_WEBHOOK_URL)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Alarm webhook adresi HTTPS kullanmalı")
    key = f"{level}:{source}:{message[:160]}"
    with ALERT_LOCK:
        current = time.monotonic()
        last_sent = ALERT_LAST_SENT.get(key)
        if last_sent is not None and current - last_sent < ALERT_COOLDOWN_SECONDS:
            return False
        ALERT_LAST_SENT[key] = current
    title = f"Videoluk {level.upper()} · {source}"
    text = f"{title}\n{message[:1000]}"
    payload = json.dumps({"text": text, "content": text, "service": "videoluk", "level": level, "source": source}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Videoluk-Alert/1.0"}
    if ALERT_WEBHOOK_TOKEN:
        headers["Authorization"] = f"Bearer {ALERT_WEBHOOK_TOKEN}"
    request = Request(ALERT_WEBHOOK_URL, data=payload, method="POST", headers=headers)
    with urlopen(request, timeout=10) as response:
        response.read(1024)
    return True


def _deliver_system_alert(level: str, source: str, message: str) -> None:
    try:
        send_webhook_alert(level, source, message)
    except Exception as exc:
        traceback.print_exc()
        try:
            with DB_LOCK, db() as connection:
                connection.execute(
                    "INSERT INTO system_events VALUES (?, 'warning', 'alert', ?, NULL, ?)",
                    (str(uuid.uuid4()), f"Webhook bildirimi gönderilemedi: {str(exc)[:500]}", now()),
                )
        except Exception:
            traceback.print_exc()


def record_system_event(level: str, source: str, message: str, metadata: dict | None = None) -> None:
    safe_level = level if level in {"info", "warning", "error"} else "error"
    try:
        with DB_LOCK, db() as connection:
            connection.execute(
                "INSERT INTO system_events VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), safe_level, source[:80], message[:1000], json.dumps(metadata or {}, ensure_ascii=False), now()),
            )
            connection.execute(
                "DELETE FROM system_events WHERE id NOT IN (SELECT id FROM system_events ORDER BY created_at DESC LIMIT 1000)"
            )
    except Exception:
        traceback.print_exc()
    if safe_level == "error" and ALERT_WEBHOOK_URL:
        ALERT_EXECUTOR.submit(_deliver_system_alert, safe_level, source[:80], message[:1000])


def operational_status() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    disk = shutil.disk_usage(DATA)
    with db() as connection:
        queued = int(connection.execute("SELECT COUNT(*) AS total FROM render_jobs WHERE status IN ('queued', 'rendering')").fetchone()["total"])
        failed_renders = int(connection.execute("SELECT COUNT(*) AS total FROM render_jobs WHERE status = 'failed' AND updated_at >= ?", (cutoff,)).fetchone()["total"])
        failed_payments = int(connection.execute("SELECT COUNT(*) AS total FROM payment_orders WHERE status = 'failed' AND updated_at >= ?", (cutoff,)).fetchone()["total"])
        errors = int(connection.execute("SELECT COUNT(*) AS total FROM system_events WHERE level = 'error' AND created_at >= ?", (cutoff,)).fetchone()["total"])
    disk_percent = round((disk.used / max(1, disk.total)) * 100, 1)
    alerts = []
    if disk_percent >= 85:
        alerts.append({"level": "error" if disk_percent >= 95 else "warning", "message": f"Sunucu diski %{disk_percent} dolu"})
    if failed_renders:
        alerts.append({"level": "warning", "message": f"Son 24 saatte {failed_renders} render başarısız oldu"})
    if failed_payments:
        alerts.append({"level": "warning", "message": f"Son 24 saatte {failed_payments} ödeme başarısız oldu"})
    if errors:
        alerts.append({"level": "error", "message": f"Son 24 saatte {errors} sistem hatası kaydedildi"})
    return {
        "status": "degraded" if alerts else "healthy",
        "queue": queued,
        "failedRenders24h": failed_renders,
        "failedPayments24h": failed_payments,
        "errors24h": errors,
        "disk": {"usedBytes": disk.used, "totalBytes": disk.total, "percent": disk_percent},
        "alerts": alerts,
        "notificationsConfigured": bool(ALERT_WEBHOOK_URL),
    }


def admin_overview() -> dict:
    with db() as connection:
        metrics = {
            "users": int(connection.execute("SELECT COUNT(*) AS total FROM users WHERE password_hash != 'disabled'").fetchone()["total"]),
            "projects": int(connection.execute("SELECT COUNT(*) AS total FROM projects").fetchone()["total"]),
            "storageBytes": int(connection.execute("SELECT COALESCE(SUM(size_bytes), 0) AS total FROM media_assets").fetchone()["total"]),
            "rendersCompleted": int(connection.execute("SELECT COUNT(*) AS total FROM render_jobs WHERE status = 'completed'").fetchone()["total"]),
            "rendersActive": int(connection.execute("SELECT COUNT(*) AS total FROM render_jobs WHERE status IN ('queued', 'rendering')").fetchone()["total"]),
            "revenueTry": float(connection.execute("SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) AS total FROM payment_orders WHERE status = 'paid'").fetchone()["total"]),
        }
        users = connection.execute(
            "SELECT users.id, users.email, users.name, users.role, users.status, users.created_at, "
            "(SELECT COUNT(*) FROM projects WHERE projects.user_id = users.id) AS project_count, "
            "(SELECT COALESCE(SUM(size_bytes), 0) FROM media_assets WHERE media_assets.user_id = users.id) AS storage_bytes, "
            "(SELECT COALESCE(SUM(amount), 0) FROM credit_transactions WHERE credit_transactions.user_id = users.id) AS credits, "
            "COALESCE(user_limits.project_limit, ?) AS project_limit, COALESCE(user_limits.storage_limit_bytes, ?) AS storage_limit_bytes, "
            "COALESCE(user_limits.monthly_render_limit, ?) AS monthly_render_limit "
            "FROM users LEFT JOIN user_limits ON user_limits.user_id = users.id "
            "WHERE password_hash != 'disabled' ORDER BY users.created_at DESC LIMIT 100",
            (MAX_PROJECTS_PER_USER, MAX_STORAGE_BYTES_PER_USER, MAX_MONTHLY_RENDERS_PER_USER),
        ).fetchall()
        payments = connection.execute(
            "SELECT payment_orders.id, users.email, payment_orders.package_id, payment_orders.credits, payment_orders.amount, "
            "payment_orders.currency, payment_orders.status, payment_orders.created_at "
            "FROM payment_orders JOIN users ON users.id = payment_orders.user_id ORDER BY payment_orders.created_at DESC LIMIT 50"
        ).fetchall()
        renders = connection.execute(
            "SELECT render_jobs.id, projects.title, users.email, render_jobs.status, render_jobs.progress, render_jobs.created_at "
            "FROM render_jobs JOIN projects ON projects.id = render_jobs.project_id JOIN users ON users.id = projects.user_id "
            "ORDER BY render_jobs.created_at DESC LIMIT 50"
        ).fetchall()
        events = connection.execute(
            "SELECT id, level, source, message, created_at FROM system_events ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return {"metrics": metrics, "operations": operational_status(), "users": [dict(row) for row in users], "payments": [dict(row) for row in payments], "renders": [dict(row) for row in renders], "events": [dict(row) for row in events]}


def estimate_project_cost(payload: dict) -> dict:
    duration = max(3, min(300, int(payload.get("duration", 30))))
    scenes = payload.get("scenes") if isinstance(payload.get("scenes"), list) else []
    source = str(payload.get("source") or "").casefold()
    render_credits = max(1, math.ceil(duration / 15))
    voice_credits = max(1, math.ceil(duration / 30))
    ai_credits = len(scenes) * 2 if "yapay" in source else 0
    total = render_credits + voice_credits + ai_credits
    return {
        "totalCredits": total,
        "breakdown": {"render": render_credits, "voice": voice_credits, "aiMedia": ai_credits},
        "duration": duration,
        "sceneCount": len(scenes),
    }


def render_credit_cost(user_id: str, job_id: str) -> int:
    with db() as connection:
        rows = connection.execute(
            "SELECT amount, metadata FROM credit_transactions WHERE user_id = ? AND transaction_type = 'render' ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    for row in rows:
        try:
            if json.loads(row["metadata"] or "{}").get("jobId") == job_id:
                return abs(int(row["amount"]))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return 0


def iyzico_ready() -> bool:
    return bool(IYZICO_API_KEY and IYZICO_SECRET_KEY and PUBLIC_BASE_URL.startswith("https://"))


def iyzico_request(path: str, payload: dict) -> dict:
    if not iyzico_ready():
        raise ValueError("iyzico ödeme bağlantısı henüz yapılandırılmadı")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    random_key = f"{int(datetime.now(timezone.utc).timestamp() * 1000)}{secrets.randbelow(1_000_000_000):09d}"
    signature = hmac.new(IYZICO_SECRET_KEY.encode(), f"{random_key}{path}{body}".encode(), hashlib.sha256).hexdigest()
    authorization_text = f"apiKey:{IYZICO_API_KEY}&randomKey:{random_key}&signature:{signature}"
    authorization = "IYZWSv2 " + base64.b64encode(authorization_text.encode()).decode()
    request = Request(
        f"{IYZICO_BASE_URL}{path}", data=body.encode(), method="POST",
        headers={"Authorization": authorization, "x-iyzi-rnd": random_key, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        result = json.loads(exc.read().decode("utf-8") or "{}")
    if result.get("status") != "success":
        raise ValueError(str(result.get("errorMessage") or "iyzico işlemi başlatılamadı"))
    return result


def initialize_credit_checkout(user: dict, package_id: str, billing: dict, ip_address: str) -> dict:
    package = CREDIT_PACKAGES.get(package_id)
    if not package:
        raise ValueError("Geçersiz kredi paketi")
    required = {key: " ".join(str(billing.get(key) or "").split()) for key in ("name", "surname", "identityNumber", "gsmNumber", "address", "city")}
    if any(not value for value in required.values()):
        raise ValueError("Ödeme için ad, soyad, telefon, kimlik ve fatura adresi gerekli")
    order_id = str(uuid.uuid4())
    timestamp = now()
    with DB_LOCK, db() as connection:
        connection.execute(
            "INSERT INTO payment_orders VALUES (?, ?, 'iyzico', ?, ?, ?, 'TRY', NULL, NULL, 'created', NULL, ?, ?)",
            (order_id, user["id"], package_id, package["credits"], package["price"], timestamp, timestamp),
        )
    callback_url = f"{PUBLIC_BASE_URL}/api/payments/iyzico/callback?orderId={order_id}"
    contact_name = f"{required['name']} {required['surname']}"
    payload = {
        "locale": "tr", "conversationId": order_id, "price": package["price"], "paidPrice": package["price"],
        "currency": "TRY", "basketId": order_id, "paymentGroup": "PRODUCT", "callbackUrl": callback_url,
        "enabledInstallments": [1],
        "buyer": {"id": user["id"], "name": required["name"], "surname": required["surname"],
                  "identityNumber": required["identityNumber"], "email": user["email"], "gsmNumber": required["gsmNumber"],
                  "registrationAddress": required["address"], "city": required["city"], "country": "Türkiye", "ip": ip_address},
        "billingAddress": {"address": required["address"], "contactName": contact_name, "city": required["city"], "country": "Türkiye"},
        "basketItems": [{"id": package_id, "price": package["price"], "name": f"Videoluk {package['name']} Kredi Paketi", "category1": "Dijital Hizmet", "itemType": "VIRTUAL"}],
    }
    try:
        result = iyzico_request("/payment/iyzipos/checkoutform/initialize/auth/ecom", payload)
        with DB_LOCK, db() as connection:
            connection.execute("UPDATE payment_orders SET token = ?, status = 'pending', updated_at = ? WHERE id = ?", (result.get("token"), now(), order_id))
        return {"orderId": order_id, "paymentPageUrl": result.get("paymentPageUrl"), "token": result.get("token")}
    except Exception as exc:
        with DB_LOCK, db() as connection:
            connection.execute("UPDATE payment_orders SET status = 'failed', error = ?, updated_at = ? WHERE id = ?", (str(exc)[:500], now(), order_id))
        record_system_event("error", "payment", str(exc), {"orderId": order_id})
        raise


def complete_iyzico_order(order_id: str, token: str) -> bool:
    with db() as connection:
        row = connection.execute("SELECT * FROM payment_orders WHERE id = ? AND provider = 'iyzico'", (order_id,)).fetchone()
    if not row or row["status"] == "paid" or not token or (row["token"] and not hmac.compare_digest(row["token"], token)):
        return bool(row and row["status"] == "paid")
    result = iyzico_request("/payment/iyzipos/checkoutform/auth/ecom/detail", {"locale": "tr", "conversationId": order_id, "token": token})
    approved = (
        result.get("paymentStatus") == "SUCCESS" and int(result.get("fraudStatus") or 0) == 1
        and str(result.get("basketId")) == order_id and str(result.get("currency")) == "TRY"
        and f"{float(result.get('price') or 0):.2f}" == f"{float(row['amount']):.2f}"
    )
    with DB_LOCK, db() as connection:
        current = connection.execute("SELECT status FROM payment_orders WHERE id = ?", (order_id,)).fetchone()
        if approved and current and current["status"] != "paid":
            connection.execute(
                "UPDATE payment_orders SET status = 'paid', payment_id = ?, updated_at = ? WHERE id = ?",
                (str(result.get("paymentId") or ""), now(), order_id),
            )
            connection.execute(
                "INSERT INTO credit_transactions VALUES (?, ?, ?, 'purchase', ?, ?, ?)",
                (str(uuid.uuid4()), row["user_id"], row["credits"], "iyzico kredi paketi", json.dumps({"orderId": order_id, "paymentId": result.get("paymentId")}), now()),
            )
        elif not approved:
            connection.execute("UPDATE payment_orders SET status = 'failed', error = ?, updated_at = ? WHERE id = ?", ("Ödeme onaylanmadı", now(), order_id))
    if not approved:
        record_system_event("warning", "payment", "iyzico ödemesi onaylanmadı", {"orderId": order_id})
    return approved


def srt_time(seconds: float) -> str:
    millis = int(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def build_srt(scenes: list[dict], duration: int) -> str:
    if not scenes:
        scenes = [{"title": "Videoluk ile üretildi", "subtitle": "Videon hazır."}]
    fallback_duration = duration / len(scenes)
    entries = []
    cursor = 0.0
    for index, scene in enumerate(scenes, 1):
        scene_duration = max(0.25, float(scene.get("duration") or fallback_duration))
        start = cursor
        end = min(duration, cursor + scene_duration)
        cursor = end
        title = str(scene.get("title") or f"Sahne {index}").strip()
        subtitle = str(scene.get("subtitle") or scene.get("sub") or "").strip()
        text = title if not subtitle else f"{title}\n{subtitle}"
        entries.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
    return "\n".join(entries)


def validate_script_request(payload: dict) -> tuple[str, int, str, str]:
    idea = " ".join(str(payload.get("idea") or "").split()).strip()
    if len(idea) < 5:
        raise ValueError("Metin oluşturmak için fikrini biraz daha ayrıntılı yaz")
    if len(idea) > 600:
        raise ValueError("Fikir en fazla 600 karakter olabilir")
    duration = max(15, min(90, int(payload.get("duration", 30))))
    video_type = str(payload.get("type") or "Sosyal Medya")
    tone = str(payload.get("tone") or "Enerjik & dinamik")
    return idea, duration, video_type, tone


def normalize_editing_rules(rules: object) -> dict:
    if not isinstance(rules, dict):
        raise ValueError("Kurgu kuralları nesne biçiminde olmalı")
    required = [" ".join(str(item).split())[:240] for item in rules.get("required", []) if str(item).strip()][:20]
    forbidden = [" ".join(str(item).split())[:240] for item in rules.get("forbidden", []) if str(item).strip()][:20]
    return {
        "hookSeconds": max(1, min(10, float(rules.get("hookSeconds", 3)))),
        "averageShotSeconds": max(0.8, min(15, float(rules.get("averageShotSeconds", 3.5)))),
        "rhythm": " ".join(str(rules.get("rhythm") or "Kontrollü").split())[:120],
        "narrativeStructure": " ".join(str(rules.get("narrativeStructure") or "Kanca → gelişme → kapanış").split())[:300],
        "transitionPolicy": " ".join(str(rules.get("transitionPolicy") or "Anlatı gerektirmedikçe efekt kullanma").split())[:300],
        "required": required,
        "forbidden": forbidden,
    }


def get_editing_profile(profile_id: str | None) -> dict | None:
    try:
        with db() as connection:
            row = connection.execute(
                "SELECT * FROM editing_profiles WHERE id = ?", (profile_id or "default",)
            ).fetchone()
            if not row:
                row = connection.execute("SELECT * FROM editing_profiles ORDER BY created_at ASC LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    result = dict(row)
    result["rules"] = json.loads(result["rules"])
    return result


def editing_training_context(profile_id: str, limit: int = 5) -> list[dict]:
    with db() as connection:
        rows = connection.execute(
            "SELECT note, after_state FROM editing_feedback WHERE profile_id = ? "
            "ORDER BY created_at DESC LIMIT ?", (profile_id, limit),
        ).fetchall()
    return [{"note": row["note"], "approvedResult": json.loads(row["after_state"]) if row["after_state"] else None} for row in rows]


def editing_brief(profile: dict | None) -> str:
    if not profile:
        return ""
    rules = profile["rules"]
    required = "; ".join(rules.get("required") or []) or "Henüz tanımlanmadı"
    forbidden = "; ".join(rules.get("forbidden") or []) or "Henüz tanımlanmadı"
    examples = editing_training_context(profile["id"])
    example_notes = " | ".join(item["note"] for item in examples) or "Henüz düzeltme örneği yok"
    return (
        f"Kurgu DNA profili: {profile['name']}. Ritim: {rules['rhythm']}. "
        f"İlk kanca: en geç {rules['hookSeconds']} saniye. Ortalama plan: {rules['averageShotSeconds']} saniye. "
        f"Anlatı yapısı: {rules['narrativeStructure']}. Geçiş politikası: {rules['transitionPolicy']}. "
        f"Zorunlu kararlar: {required}. Yasak kararlar: {forbidden}. "
        f"Ustanın son düzeltme notları: {example_notes}."
    )


def apply_editing_profile(result: dict, profile: dict | None) -> dict:
    if not profile:
        return result
    scenes = result.get("scenes") or []
    if not scenes:
        return result
    rules = profile["rules"]
    total = float(result.get("duration") or 30)
    hook = min(float(rules["hookSeconds"]), total / max(1, len(scenes)))
    remaining = max(0.25, total - hook)
    regular = remaining / max(1, len(scenes) - 1)
    for index, scene in enumerate(scenes):
        scene["duration"] = round(hook if index == 0 else regular, 2)
        scene["transition"] = rules["transitionPolicy"]
        scene["editingReason"] = (
            f"{rules['rhythm']} ritim için {scene['duration']:.1f} sn; "
            + ("kanca önceliği" if index == 0 else "anlatı akışını koruyan plan süresi")
        )
    result["editingProfile"] = {"id": profile["id"], "name": profile["name"]}
    result["editingBrief"] = editing_brief(profile)
    return result


def generate_local_script(payload: dict) -> dict:
    idea, duration, video_type, tone = validate_script_request(payload)
    tone_openers = {
        "Enerjik & dinamik": "Hazır mısın?",
        "Sakin & güven veren": "Bazen iyi bir değişim, tek bir fikirle başlar.",
        "Sinematik & dramatik": "Her büyük hikâyenin görünmeyen bir başlangıcı vardır.",
        "Bilgilendirici": "Bilmen gereken en önemli nokta şu:",
    }
    opener = tone_openers.get(tone, "Şimdi yeni bir fikri keşfetme zamanı.")
    scene_count = 3 if duration <= 30 else 4 if duration <= 60 else 5
    scene_templates = [
        (opener, f"{idea.capitalize()} neden şimdi önemli, birlikte bakalım."),
        ("Fikrin merkezinde gerçek bir ihtiyaç var.", "İnsanların gündelik deneyimindeki sorunu görünür kılmak, doğru çözümün ilk adımıdır."),
        ("Değer, ayrıntılarda ortaya çıkar.", "Doğru yaklaşım; zamanı verimli kullanır, deneyimi sadeleştirir ve insanlara güven verir."),
        ("Şimdi bunu hayata geçirme zamanı.", f"{idea.capitalize()} ile ilk adımı bugün atabilir, sonucu kendi gözlerinle görebilirsin."),
        ("Gelecek, harekete geçenlerin olur.", "Fikrini erteleme; anlat, üret ve doğru insanlarla buluştur."),
    ]
    template_indexes = {3: [0, 1, 3], 4: [0, 1, 2, 3], 5: [0, 1, 2, 3, 4]}[scene_count]
    scene_templates = [scene_templates[index] for index in template_indexes]
    scenes = [
        {"title": title, "subtitle": subtitle, "purpose": "Kanca" if i == 0 else "Kapanış" if i == scene_count - 1 else "Ana fikir"}
        for i, (title, subtitle) in enumerate(scene_templates)
    ]
    script = "\n\n".join(f"{scene['title']} {scene['subtitle']}" for scene in scenes)
    result = {
        "idea": idea,
        "type": video_type,
        "tone": tone,
        "duration": duration,
        "script": script,
        "scenes": scenes,
        "provider": "local",
    }
    return apply_editing_profile(result, get_editing_profile(str(payload.get("profileId") or "default")))


def biography_subject(idea: str) -> str | None:
    lowered = idea.casefold()
    markers = (" biyograf", " hayatı", " kimdir", " yaşamı")
    if not any(marker in lowered for marker in markers):
        return None
    subject = idea
    for phrase in ("biyografisi", "biyografi", "hayatı", "kimdir", "yaşamı", "hakkında video", "hakkında"):
        subject = subject.replace(phrase, "").replace(phrase.capitalize(), "")
    return " ".join(subject.split()).strip(" ,.-") or None


def fetch_wikipedia_summary(subject: str) -> dict:
    search_params = urlencode({"action": "query", "list": "search", "srsearch": subject, "srlimit": 1, "format": "json", "utf8": 1})
    request = Request(f"https://tr.wikipedia.org/w/api.php?{search_params}", headers={"User-Agent": "Videoluk/0.1 (video research)"})
    with urlopen(request, timeout=20) as response:
        search_data = json.loads(response.read().decode("utf-8"))
    results = search_data.get("query", {}).get("search", [])
    if not results:
        raise ValueError("Wikipedia üzerinde ilgili kişi bulunamadı")
    title = results[0]["title"]
    summary_request = Request(
        f"https://tr.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe='')}",
        headers={"User-Agent": "Videoluk/0.1 (video research)"},
    )
    with urlopen(summary_request, timeout=20) as response:
        summary = json.loads(response.read().decode("utf-8"))
    extract = " ".join(str(summary.get("extract") or "").split())
    if len(extract) < 80:
        raise ValueError("Wikipedia özeti yeterli değil")
    return {
        "title": summary.get("title") or title,
        "extract": extract,
        "url": summary.get("content_urls", {}).get("desktop", {}).get("page"),
        "image": (summary.get("originalimage") or summary.get("thumbnail") or {}).get("source"),
    }


def generate_biography_script(payload: dict, subject: str) -> dict:
    idea, duration, video_type, tone = validate_script_request(payload)
    article = fetch_wikipedia_summary(subject)
    sentences = [part.strip() for part in article["extract"].replace(";", ".").split(".") if len(part.strip()) > 25]
    scene_count = 3 if duration <= 30 else 4 if duration <= 60 else 5
    if len(sentences) < scene_count:
        scene_count = max(2, len(sentences))
    groups = [[] for _ in range(scene_count)]
    for index, sentence in enumerate(sentences[: scene_count * 3]):
        groups[min(scene_count - 1, index * scene_count // min(len(sentences), scene_count * 3))].append(sentence)
    scenes = []
    labels = ["Kimdir?", "İlk yılları", "Siyasi yaşamı", "Dönüm noktaları", "Mirası"]
    for index, group in enumerate(groups):
        subtitle = ". ".join(group).strip() + "."
        scenes.append({
            "title": f"{article['title']} · {labels[min(index, len(labels) - 1)]}",
            "subtitle": subtitle,
            "purpose": "Kanca" if index == 0 else "Kapanış" if index == len(groups) - 1 else "Ana fikir",
            "mediaQuery": article["title"],
        })
    script = "\n\n".join(scene["subtitle"] for scene in scenes)
    result = {
        "idea": idea, "type": video_type, "tone": tone, "duration": duration,
        "script": script, "scenes": scenes, "provider": "wikipedia",
        "source": {"title": article["title"], "url": article["url"]},
    }
    return apply_editing_profile(result, get_editing_profile(str(payload.get("profileId") or "default")))


def llm_endpoint() -> str:
    if LLM_URL.endswith("/chat/completions"):
        return LLM_URL
    return f"{LLM_URL}/v1/chat/completions"


def extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model geçerli JSON döndürmedi")
    return json.loads(cleaned[start:end + 1])


def generate_ai_script(payload: dict) -> dict:
    idea, duration, video_type, tone = validate_script_request(payload)
    profile = get_editing_profile(str(payload.get("profileId") or "default"))
    if not LLM_URL or not LLM_MODEL:
        subject = biography_subject(idea)
        if subject:
            try:
                return generate_biography_script(payload, subject)
            except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError):
                pass
        return generate_local_script(payload)
    scene_count = 3 if duration <= 30 else 4 if duration <= 60 else 5
    system_prompt = (
        "Sen Videoluk adlı Türkçe video üretim platformunun kıdemli senaryo yazarısın. "
        "Kısa, doğal, klişeden uzak ve seslendirmeye uygun Türkçe yaz. Yalnızca geçerli JSON döndür. "
        "Kurgu yönetmeninin kurallarını yaratıcı öneri değil, zorunlu yapım şartı olarak uygula. "
        "Şema: {\"script\":\"tam metin\",\"scenes\":[{\"title\":\"kısa başlık\","
        "\"subtitle\":\"1-2 cümle seslendirme\",\"purpose\":\"Kanca|Ana fikir|Kapanış\","
        "\"editingReason\":\"kurgu kararının kısa gerekçesi\"}]}"
    )
    user_prompt = (
        f"Fikir: {idea}\nVideo türü: {video_type}\nTon: {tone}\nSüre: {duration} saniye\n"
        f"Kurgu yönetmeni şartnamesi: {editing_brief(profile)}\n"
        f"Tam olarak {scene_count} sahne oluştur. Son sahne net ama abartısız bir çağrı içersin."
    )
    request_body = {
        "model": LLM_MODEL,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    request = Request(
        llm_endpoint(),
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=LLM_TIMEOUT) as response:
            provider_response = json.loads(response.read().decode("utf-8"))
        content = provider_response["choices"][0]["message"]["content"]
        generated = extract_json(content)
        scenes = generated.get("scenes")
        script = str(generated.get("script") or "").strip()
        if not isinstance(scenes, list) or len(scenes) < 2 or not script:
            raise ValueError("Model yanıtında senaryo veya sahne bulunamadı")
        normalized_scenes = []
        for index, scene in enumerate(scenes[:6]):
            if not isinstance(scene, dict):
                continue
            title = str(scene.get("title") or f"Sahne {index + 1}").strip()[:180]
            subtitle = str(scene.get("subtitle") or "").strip()[:500]
            purpose = str(scene.get("purpose") or ("Kapanış" if index == len(scenes) - 1 else "Ana fikir"))[:40]
            normalized_scenes.append({
                "title": title,
                "subtitle": subtitle,
                "purpose": purpose,
                "editingReason": str(scene.get("editingReason") or "Kurgu DNA akışına uygun sahne")[:300],
            })
        if len(normalized_scenes) < 2:
            raise ValueError("Model yeterli sahne oluşturmadı")
        result = {
            "idea": idea,
            "type": video_type,
            "tone": tone,
            "duration": duration,
            "script": script[:4000],
            "scenes": normalized_scenes,
            "provider": "ai",
            "model": LLM_MODEL,
        }
        return apply_editing_profile(result, profile)
    except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError) as exc:
        fallback = generate_local_script(payload)
        fallback["provider"] = "local-fallback"
        fallback["providerError"] = str(exc)[:240]
        return fallback


def search_stock_videos(query: str, orientation: str, per_page: int = 8) -> dict:
    clean_query = " ".join(query.split()).strip()
    if len(clean_query) < 2:
        raise ValueError("Arama için en az iki karakter yaz")
    if not PEXELS_API_KEY:
        return search_commons_images(clean_query, per_page)
    orientation_map = {"vertical": "portrait", "horizontal": "landscape", "square": "square"}
    params = urlencode({
        "query": clean_query,
        "orientation": orientation_map.get(orientation, "portrait"),
        "size": "medium",
        "locale": "tr-TR",
        "per_page": max(1, min(20, per_page)),
    })
    request = Request(
        f"https://api.pexels.com/v1/videos/search?{params}",
        headers={"Authorization": PEXELS_API_KEY},
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = []
        for video in data.get("videos", []):
            files = [item for item in video.get("video_files", []) if item.get("file_type") == "video/mp4"]
            files.sort(key=lambda item: abs((item.get("width") or 0) - 1080))
            if not files:
                continue
            creator = video.get("user") or {}
            results.append({
                "id": str(video.get("id")),
                "thumbnail": video.get("image"),
                "videoUrl": files[0].get("link"),
                "duration": video.get("duration"),
                "width": video.get("width"),
                "height": video.get("height"),
                "creator": creator.get("name") or "Pexels üreticisi",
                "creatorUrl": creator.get("url"),
                "sourceUrl": video.get("url"),
            })
        return {"configured": True, "provider": "pexels", "results": results}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"Stok servisine ulaşılamadı: {exc}") from exc


def search_commons_images(query: str, per_page: int = 8) -> dict:
    stopwords = {"bir", "ve", "ile", "için", "neden", "şimdi", "önemli", "birlikte", "bakalım", "video", "videosu", "saniyelik", "tanıtım", "anlatan", "gerçek", "merkezinde", "hazır", "mısın"}
    words = [word.strip(".,!?;:()[]\"'") for word in query.split()]
    meaningful = [word for word in words if len(word) > 2 and word.casefold() not in stopwords]
    variants = [query, " ".join(meaningful[:4]), " ".join(meaningful[:2])]
    variants.extend(word for word in meaningful if word[:1].isupper())
    variants = list(dict.fromkeys(value.strip() for value in variants if len(value.strip()) >= 2))
    try:
        results = []
        used_variant = query
        for variant in variants:
            params = urlencode({
                "action": "query", "generator": "search", "gsrsearch": f"{variant} filetype:bitmap",
                "gsrnamespace": 6, "gsrlimit": max(1, min(20, per_page)), "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": 720, "format": "json", "formatversion": 2,
            })
            request = Request(
                f"https://commons.wikimedia.org/w/api.php?{params}",
                headers={"User-Agent": "Videoluk/0.1 (stock image search)"},
            )
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            for page in data.get("query", {}).get("pages", []):
                info = (page.get("imageinfo") or [{}])[0]
                metadata = info.get("extmetadata") or {}
                image_url = info.get("url")
                if not image_url:
                    continue
                creator = metadata.get("Artist", {}).get("value") or metadata.get("Credit", {}).get("value") or "Wikimedia Commons"
                creator = html.unescape(re.sub(r"<[^>]+>", " ", creator))
                creator = " ".join(creator.split())
                results.append({
                    "id": str(page.get("pageid")), "mediaType": "image",
                    "thumbnail": info.get("thumburl") or image_url, "imageUrl": image_url,
                    "creator": creator[:160], "duration": None,
                    "sourceUrl": info.get("descriptionurl"),
                    "license": metadata.get("LicenseShortName", {}).get("value") or "Commons lisansı",
                })
            if results:
                used_variant = variant
                break
        return {"configured": True, "provider": "wikimedia", "queryUsed": used_variant, "results": results}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"Wikimedia Commons servisine ulaşılamadı: {exc}") from exc


def generate_voice(text: str) -> dict:
    clean_text = " ".join(text.split()).strip()
    if len(clean_text) < 3:
        raise ValueError("Seslendirme için metin gerekli")
    if len(clean_text) > 4000:
        raise ValueError("Seslendirme metni en fazla 4000 karakter olabilir")
    voice_id = str(uuid.uuid4())
    target = VOICES / f"{voice_id}.wav"
    result = None
    if shutil.which("say"):
        intermediate = VOICES / f"{voice_id}.aiff"
        result = subprocess.run(["say", "-v", "Yelda", "-o", str(intermediate), clean_text], capture_output=True, text=True)
        if result.returncode == 0:
            result = subprocess.run([FFMPEG, "-y", "-i", str(intermediate), "-ar", "44100", "-ac", "2", str(target)], capture_output=True, text=True)
        intermediate.unlink(missing_ok=True)
    if (result is None or result.returncode != 0 or not target.is_file() or target.stat().st_size < 1024) and shutil.which("espeak-ng"):
        target.unlink(missing_ok=True)
        result = subprocess.run(["espeak-ng", "-v", "tr", "-s", "155", "-w", str(target), clean_text], capture_output=True, text=True)
    if result is None:
        raise ValueError("Sunucuda seslendirme motoru bulunamadı")
    if result.returncode != 0 or not target.is_file() or target.stat().st_size < 1024:
        target.unlink(missing_ok=True)
        raise ValueError("Seslendirme üretilemedi")
    return {"id": voice_id, "audioUrl": f"/api/voices/{voice_id}", "provider": "system-tts"}


def image_endpoint() -> str:
    if IMAGE_URL.endswith("/images/generations"):
        return IMAGE_URL
    return f"{IMAGE_URL}/v1/images/generations"


def generate_scene_image(prompt: str, orientation: str) -> dict:
    clean_prompt = " ".join(prompt.split()).strip()
    if len(clean_prompt) < 5:
        raise ValueError("Görsel üretmek için daha açıklayıcı bir istem yaz")
    if len(clean_prompt) > 1200:
        raise ValueError("Görsel istemi en fazla 1200 karakter olabilir")
    if not IMAGE_URL or not IMAGE_MODEL:
        raise ValueError("Yapay zekâ görsel motoru henüz yapılandırılmadı")
    size = {"vertical": "1024x1536", "horizontal": "1536x1024", "square": "1024x1024"}.get(orientation, "1024x1536")
    request_body = {
        "model": IMAGE_MODEL,
        "prompt": clean_prompt,
        "size": size,
        "n": 1,
        "response_format": "b64_json",
    }
    headers = {"Content-Type": "application/json"}
    if IMAGE_API_KEY:
        headers["Authorization"] = f"Bearer {IMAGE_API_KEY}"
    request = Request(
        image_endpoint(), data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST",
    )
    try:
        with urlopen(request, timeout=IMAGE_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
        encoded = ((result.get("data") or [{}])[0]).get("b64_json")
        if not encoded:
            raise ValueError("Görsel sağlayıcısı dosya verisi döndürmedi")
        image_bytes = base64.b64decode(encoded, validate=True)
        if len(image_bytes) < 1024 or len(image_bytes) > MAX_MEDIA_BYTES:
            raise ValueError("Üretilen görsel geçersiz veya boyut sınırını aşıyor")
        image_id = str(uuid.uuid4())
        target = GENERATED_IMAGES / f"{image_id}.png"
        target.write_bytes(image_bytes)
        return {
            "id": image_id, "assetId": image_id, "mediaType": "image",
            "thumbnail": f"/api/images/{image_id}", "imageUrl": f"/api/images/{image_id}",
            "creator": "Videoluk AI", "provider": "ai", "prompt": clean_prompt,
        }
    except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError, binascii.Error) as exc:
        raise ValueError(f"Yapay zekâ görseli üretilemedi: {exc}") from exc


def validate_stock_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    allowed = (
        hostname == "pexels.com" or hostname.endswith(".pexels.com")
        or hostname == "vimeo.com" or hostname.endswith(".vimeo.com")
        or hostname == "wikimedia.org" or hostname.endswith(".wikimedia.org")
    )
    if parsed.scheme != "https" or not allowed:
        raise ValueError("Stok medya adresine izin verilmiyor")
    return url


UPLOAD_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp"},
    "logo": {".jpg", ".jpeg", ".png", ".webp"},
    "video": {".mp4", ".mov", ".m4v", ".webm", ".mkv"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"},
}


def validate_uploaded_media(path: Path, kind: str) -> None:
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise ValueError("Yüklenen medya dosyası okunamadı")
    streams = json.loads(result.stdout or "{}").get("streams") or []
    stream_types = {stream.get("codec_type") for stream in streams}
    expected = "audio" if kind == "audio" else "video"
    if expected not in stream_types:
        raise ValueError("Dosya içeriği seçilen medya türüyle uyuşmuyor")


def create_upload_thumbnail(source: Path, kind: str, target: Path) -> Path | None:
    if kind == "audio":
        return None
    command = [FFMPEG, "-y"]
    if kind in {"image", "logo"}:
        command += ["-i", str(source)]
    else:
        command += ["-ss", "0.1", "-i", str(source)]
    command += ["-frames:v", "1", "-vf", "scale=480:-2:force_original_aspect_ratio=decrease", "-q:v", "4", str(target)]
    run_ffmpeg(command)
    return target if target.is_file() and target.stat().st_size > 512 else None


def uploaded_asset(asset_id: str, user_id: str | None = None) -> dict | None:
    query = "SELECT * FROM media_assets WHERE id = ?"
    params: tuple = (asset_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (asset_id, user_id)
    with db() as connection:
        row = connection.execute(query, params).fetchone()
    return dict(row) if row else None


def media_asset_payload(row: dict) -> dict:
    return {
        "id": row["id"], "uploadId": row["id"], "filename": row["filename"],
        "mediaType": row["kind"], "kind": row["kind"], "mimeType": row["mime_type"],
        "size": row["size_bytes"], "creator": "Yüklediğin medya",
        "thumbnail": f"/api/uploads/{row['id']}/thumbnail" if row.get("thumbnail_path") else None,
        "videoUrl": f"/api/uploads/{row['id']}" if row["kind"] == "video" else None,
        "imageUrl": f"/api/uploads/{row['id']}" if row["kind"] in {"image", "logo"} else None,
        "audioUrl": f"/api/uploads/{row['id']}" if row["kind"] == "audio" else None,
    }


def download_stock_video(media: dict, user_id: str | None = None) -> Path:
    upload_id = "".join(character for character in str(media.get("uploadId") or "") if character.isalnum() or character == "-")[:64]
    if upload_id:
        asset = uploaded_asset(upload_id, user_id)
        path = Path(asset["file_path"]) if asset else Path("/")
        if asset and path.is_file() and asset["kind"] in {"image", "logo", "video"}:
            return path
        raise ValueError("Yüklenen medya dosyası bulunamadı")
    asset_id = "".join(character for character in str(media.get("assetId") or "") if character.isalnum() or character == "-")[:64]
    if asset_id:
        local_image = GENERATED_IMAGES / f"{asset_id}.png"
        if local_image.is_file() and local_image.stat().st_size > 1024:
            return local_image
        raise ValueError("Üretilen görsel dosyası bulunamadı")
    media_type = "image" if media.get("imageUrl") else "video"
    url = validate_stock_url(str(media.get("videoUrl") or media.get("imageUrl") or ""))
    media_id = "".join(character for character in str(media.get("id") or "") if character.isalnum())[:64]
    if not media_id:
        media_id = hashlib.sha256(url.encode()).hexdigest()[:32]
    target = MEDIA_CACHE / f"stock-{media_id}{'.jpg' if media_type == 'image' else '.mp4'}"
    if target.is_file() and target.stat().st_size > 1024:
        return target
    temporary = target.with_suffix(".download")
    request = Request(url, headers={"User-Agent": "Videoluk/0.1"})
    try:
        with urlopen(request, timeout=90) as response, temporary.open("wb") as output:
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > MAX_MEDIA_BYTES:
                raise ValueError("Stok video dosyası boyut sınırını aşıyor")
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > MAX_MEDIA_BYTES:
                    raise ValueError("Stok video dosyası boyut sınırını aşıyor")
                output.write(chunk)
        if temporary.stat().st_size < 1024:
            raise ValueError("Stok video dosyası boş")
        temporary.replace(target)
        return target
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])


def build_scene_clip(source: Path | None, target: Path, width: int, height: int, duration: float, index: int) -> None:
    common = [
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30,format=yuv420p",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-t", f"{duration:.3f}", str(target),
    ]
    if source and source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        command = [FFMPEG, "-y", "-loop", "1", "-i", str(source), *common]
    elif source:
        command = [FFMPEG, "-y", "-stream_loop", "-1", "-i", str(source), *common]
    else:
        colors = ["#173e39", "#5c3f78", "#345c74", "#874e3e", "#315248"]
        command = [FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={colors[index % len(colors)]}:s={width}x{height}:r=30:d={duration}", *common]
    run_ffmpeg(command)


def build_scene_sequence(job_id: str, scenes: list[dict], duration: int, width: int, height: int, job_dir: Path, user_id: str | None = None) -> Path | None:
    if not any(isinstance(scene.get("media"), dict) and (scene["media"].get("videoUrl") or scene["media"].get("imageUrl")) for scene in scenes):
        return None
    fallback_duration = duration / max(1, len(scenes))
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
    clip_paths = []
    for index, scene in enumerate(scenes):
        media = scene.get("media") if isinstance(scene.get("media"), dict) else None
        source = download_stock_video(media, user_id) if media and (media.get("videoUrl") or media.get("imageUrl")) else None
        scene_duration = max(0.25, float(scene.get("duration") or fallback_duration))
        target = clips_dir / f"scene-{index:03}.mp4"
        build_scene_clip(source, target, width, height, scene_duration, index)
        clip_paths.append(target)
        update_job(job_id, progress=min(70, 25 + int((index + 1) / len(scenes) * 45)))
    concat_file = clips_dir / "concat.txt"
    concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in clip_paths), encoding="utf-8")
    sequence = job_dir / "scene-sequence.mp4"
    run_ffmpeg([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(sequence)])
    return sequence


def render(job_id: str, project: dict) -> None:
    try:
        update_job(job_id, status="rendering", progress=8)
        payload = project["payload"]
        duration = max(3, min(300, int(payload.get("duration", 30))))
        orientation = payload.get("orientation", "vertical")
        dimensions = {
            "vertical": (1080, 1920),
            "horizontal": (1920, 1080),
            "square": (1080, 1080),
        }
        width, height = dimensions.get(orientation, dimensions["vertical"])
        scenes = payload.get("scenes") or []
        job_dir = OUTPUTS / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = job_dir / "altyazi.srt"
        output_path = job_dir / "videoluk.mp4"
        subtitle_path.write_text(build_srt(scenes, duration), encoding="utf-8")
        update_job(job_id, progress=20, subtitle_path=str(subtitle_path))

        # Selected stock media is cached, normalized per scene and concatenated.
        # Projects without media keep the lightweight generated background.
        user_id = project.get("user_id")
        sequence = build_scene_sequence(job_id, scenes, duration, width, height, job_dir, user_id)
        escaped_srt = str(subtitle_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        if sequence:
            video_filters = "format=yuv420p"
            video_input = ["-i", str(sequence)]
        else:
            video_filters = (
                "format=yuv420p,"
                "drawbox=x=0:y=0:w=iw:h=ih:color=#173e39:t=fill,"
                "drawbox=x='-iw/3+mod(t*70,iw*1.4)':y=ih*0.55:w=iw*0.75:h=ih*0.6:color=#ff6b55@0.88:t=fill,"
                "drawbox=x='iw*0.62-mod(t*30,iw*0.3)':y=-ih*0.12:w=iw*0.52:h=ih*0.38:color=#c9ff5b@0.88:t=fill"
            )
            video_input = ["-f", "lavfi", "-i", f"color=c=#173e39:s={width}x{height}:r=30:d={duration}"]
        captions = payload.get("captions") if isinstance(payload.get("captions"), dict) else {}
        captions_enabled = captions.get("enabled", True) is not False
        caption_style = str(captions.get("style") or "classic")
        caption_position = str(captions.get("position") or "bottom")
        alignment = {"top": 8, "middle": 5, "bottom": 2}.get(caption_position, 2)
        margin = 90 if caption_position != "middle" else 20
        style_values = {
            "classic": "PrimaryColour=&H00FFFFFF,BackColour=&H9917211D,FontSize=28,BorderStyle=3",
            "bold": "PrimaryColour=&H0017211D,BackColour=&H005BFFC9,FontSize=32,Bold=1,BorderStyle=3",
            "minimal": "PrimaryColour=&H00FFFFFF,BackColour=&H00000000,FontSize=26,BorderStyle=1,Outline=2",
        }.get(caption_style, "PrimaryColour=&H00FFFFFF,BackColour=&H9917211D,FontSize=28,BorderStyle=3")
        if captions_enabled and ffmpeg_has_filter("subtitles"):
            video_filters += (
                f",subtitles=filename='{escaped_srt}':"
                f"force_style='Alignment={alignment},MarginV={margin},{style_values},"
                "OutlineColour=&H0017211D,Outline=1,Shadow=0'"
            )
        filter_graph = f"[0:v]{video_filters}[v]"
        voice_id = str(payload.get("voiceId") or "")
        voice_path = VOICES / f"{voice_id}.wav"
        audio_input = str(voice_path) if voice_id and voice_path.is_file() else f"anullsrc=channel_layout=stereo:sample_rate=44100:d={duration}"
        music_id = str(payload.get("musicId") or "")
        music_asset = uploaded_asset(music_id, user_id) if music_id else None
        music_path = Path(music_asset["file_path"]) if music_asset and music_asset["kind"] == "audio" else None
        if music_path and not music_path.is_file():
            music_path = None
        music_volume = max(0.0, min(1.0, float(payload.get("musicVolume", 0.18))))
        command = [
            FFMPEG, "-y",
            *video_input,
        ]
        if voice_id and voice_path.is_file():
            command += ["-i", audio_input]
        else:
            command += ["-f", "lavfi", "-i", audio_input]
        if music_path:
            command += ["-stream_loop", "-1", "-i", str(music_path)]
            fade_start = max(0.0, duration - 2.0)
            filter_graph += (
                f";[1:a]apad,atrim=0:{duration}[voice];"
                f"[2:a]volume={music_volume:.3f},atrim=0:{duration},afade=t=out:st={fade_start:.3f}:d=2[music];"
                "[voice][music]amix=inputs=2:duration=longest:normalize=0[a]"
            )
        command += [
            "-filter_complex", filter_graph,
            "-map", "[v]", "-map", "[a]" if music_path else "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        ]
        if not music_path:
            command += ["-af", "apad"]
        command += ["-c:a", "aac", "-b:a", "128k", "-t", str(duration), "-movflags", "+faststart", str(output_path)]
        update_job(job_id, progress=75 if sequence else 35)
        run_ffmpeg(command)
        update_job(
            job_id,
            status="completed",
            progress=100,
            output_path=str(output_path),
        )
        if user_id:
            with DB_LOCK, db() as connection:
                connection.execute(
                    "INSERT INTO usage_events VALUES (?, ?, 'render_seconds', ?, ?, ?)",
                    (str(uuid.uuid4()), user_id, duration, json.dumps({"jobId": job_id, "projectId": project.get("id")}), now()),
                )
    except Exception as exc:
        traceback.print_exc()
        update_job(job_id, status="failed", error=str(exc), progress=0)
        record_system_event("error", "render", str(exc), {"jobId": job_id, "projectId": project.get("id")})
        refund = int(project.get("credit_cost") or 0)
        refund_user = project.get("user_id")
        if refund and refund_user:
            with DB_LOCK, db() as connection:
                already_refunded = connection.execute(
                    "SELECT 1 FROM credit_transactions WHERE user_id = ? AND transaction_type = 'refund' AND metadata LIKE ? LIMIT 1",
                    (refund_user, f'%"jobId": "{job_id}"%'),
                ).fetchone()
                if not already_refunded:
                    connection.execute(
                        "INSERT INTO credit_transactions VALUES (?, ?, ?, 'refund', ?, ?, ?)",
                        (str(uuid.uuid4()), refund_user, refund, "Başarısız render iadesi", json.dumps({"jobId": job_id}), now()),
                    )


def submit_render(job_id: str, project: dict) -> None:
    RENDER_EXECUTOR.submit(render, job_id, project)


def resume_incomplete_renders() -> int:
    with DB_LOCK, db() as connection:
        rows = connection.execute(
            """
            SELECT render_jobs.id AS job_id, projects.id AS project_id, projects.payload AS payload, projects.user_id AS user_id
            FROM render_jobs
            JOIN projects ON projects.id = render_jobs.project_id
            WHERE render_jobs.status IN ('queued', 'rendering')
            ORDER BY render_jobs.created_at ASC
            """
        ).fetchall()
        connection.execute(
            "UPDATE render_jobs SET status = 'queued', progress = 0, error = NULL, updated_at = ? "
            "WHERE status IN ('queued', 'rendering')",
            (now(),),
        )
    for row in rows[:MAX_QUEUED_RENDERS]:
        submit_render(row["job_id"], {
            "id": row["project_id"], "payload": json.loads(row["payload"]), "user_id": row["user_id"],
            "credit_cost": render_credit_cost(row["user_id"], row["job_id"]),
        })
    for row in rows[MAX_QUEUED_RENDERS:]:
        update_job(row["job_id"], status="failed", error="Render kuyruğu sınırı aşıldı", progress=0)
    return min(len(rows), MAX_QUEUED_RENDERS)


class VideolukHandler(SimpleHTTPRequestHandler):
    server_version = "Videoluk/0.1"

    def __init__(self, *args, **kwargs):
        self._current_user_cache = None
        super().__init__(*args, directory=str(DIST), **kwargs)

    def current_user(self) -> dict | None:
        if self._current_user_cache is not None:
            return self._current_user_cache
        if not AUTH_REQUIRED:
            with db() as connection:
                row = connection.execute("SELECT id, email, name, role FROM users WHERE id = ? AND status = 'active'", (LOCAL_USER_ID,)).fetchone()
            self._current_user_cache = dict(row) if row else None
            return self._current_user_cache
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("videoluk_session")
        if not morsel:
            return None
        token_hash = session_token_hash(morsel.value)
        with db() as connection:
            row = connection.execute(
                "SELECT users.id, users.email, users.name, users.role FROM sessions "
                "JOIN users ON users.id = sessions.user_id WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND users.status = 'active'",
                (token_hash, now()),
            ).fetchone()
        self._current_user_cache = dict(row) if row else None
        return self._current_user_cache

    def require_user(self) -> dict | None:
        user = self.current_user()
        if not user:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Oturum açmanız gerekiyor", "authRequired": True})
        return user

    def require_owner(self) -> dict | None:
        user = self.require_user()
        if not user:
            return None
        if user.get("role") != "owner":
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Bu alan yalnızca Videoluk yöneticisine açıktır"})
            return None
        return user

    def end_headers(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        if ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Video-Name, X-File-Name, X-Media-Kind")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: https:; media-src 'self' blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; connect-src 'self'",
        )
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("İstek çok büyük")
        return json.loads(self.rfile.read(length) or b"{}")

    def send_json(self, status: int, payload: object, extra_headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def send_file(self, path: Path) -> None:
        if not path.is_file() or OUTPUTS not in path.resolve().parents:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                self.wfile.write(chunk)

    def receive_training_video(self, profile_id: str) -> None:
        profile = get_editing_profile(profile_id)
        if not profile:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Kurgu DNA profili bulunamadı"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_TRAINING_VIDEO_BYTES:
            raise ValueError("Video boş veya yükleme sınırını aşıyor")
        original_name = unquote(self.headers.get("X-Video-Name", "egitim-videosu.mp4"))
        original_name = " ".join(original_name.split())[:180]
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}:
            raise ValueError("Desteklenen video türleri: MP4, MOV, M4V, WEBM ve MKV")
        video_id = str(uuid.uuid4())
        target_dir = TRAINING_VIDEOS / profile_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{video_id}{suffix}"
        remaining = length
        try:
            with target.open("wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Video yüklemesi yarıda kesildi")
                    output.write(chunk)
                    remaining -= len(chunk)
            timestamp = now()
            with DB_LOCK, db() as connection:
                connection.execute(
                    "INSERT INTO training_videos (id, profile_id, filename, file_path, status, progress, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'queued', 0, ?, ?)",
                    (video_id, profile_id, original_name, str(target), timestamp, timestamp),
                )
            ANALYSIS_EXECUTOR.submit(analyze_training_video, video_id, target)
            self.send_json(HTTPStatus.ACCEPTED, {"id": video_id, "filename": original_name, "status": "queued"})
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def receive_media_upload(self, user: dict) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise ValueError("Dosya boş veya yükleme sınırını aşıyor")
        usage = user_usage(user["id"])
        if usage["storage"]["usedBytes"] + length > usage["storage"]["limitBytes"]:
            raise ValueError("Depolama kotan dolu. Kullanmadığın medyaları silerek yer açabilirsin")
        filename = " ".join(unquote(self.headers.get("X-File-Name", "medya-dosyasi")).split())[:180]
        kind = str(self.headers.get("X-Media-Kind", "")).lower()
        if kind not in UPLOAD_EXTENSIONS:
            raise ValueError("Medya türü image, video, logo veya audio olmalı")
        suffix = Path(filename).suffix.lower()
        if suffix not in UPLOAD_EXTENSIONS[kind]:
            raise ValueError("Bu dosya uzantısı seçilen medya türü için desteklenmiyor")
        asset_id = str(uuid.uuid4())
        user_dir = UPLOADS / user["id"]
        user_dir.mkdir(parents=True, exist_ok=True)
        target = user_dir / f"{asset_id}{suffix}"
        thumbnail = user_dir / f"{asset_id}-thumb.jpg"
        remaining = length
        try:
            with target.open("wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Dosya yüklemesi yarıda kesildi")
                    output.write(chunk)
                    remaining -= len(chunk)
            validate_uploaded_media(target, kind)
            thumbnail_path = create_upload_thumbnail(target, kind, thumbnail)
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            row = {
                "id": asset_id, "user_id": user["id"], "filename": filename, "kind": kind,
                "mime_type": mime_type, "file_path": str(target),
                "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
                "size_bytes": target.stat().st_size, "created_at": now(),
            }
            with DB_LOCK, db() as connection:
                connection.execute(
                    "INSERT INTO media_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    tuple(row[key] for key in ("id", "user_id", "filename", "kind", "mime_type", "file_path", "thumbnail_path", "size_bytes", "created_at")),
                )
            self.send_json(HTTPStatus.CREATED, media_asset_payload(row))
        except Exception:
            target.unlink(missing_ok=True)
            thumbnail.unlink(missing_ok=True)
            raise

    def do_POST(self) -> None:
        try:
            route = urlparse(self.path).path
            if route == "/api/payments/iyzico/callback":
                length = min(int(self.headers.get("Content-Length", "0")), 16_384)
                form = parse_qs(self.rfile.read(length).decode("utf-8"))
                order_id = parse_qs(urlparse(self.path).query).get("orderId", [""])[0]
                success = complete_iyzico_order(order_id, form.get("token", [""])[0])
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", f"/?payment={'success' if success else 'failed'}")
                self.end_headers()
                return
            if route == "/api/auth/login":
                body = self.read_json()
                email = str(body.get("email") or "").strip().lower()[:254]
                password = str(body.get("password") or "")
                with db() as connection:
                    row = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                if not row or row["status"] != "active" or not verify_password(password, row["password_hash"]):
                    self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "E-posta veya parola hatalı"})
                    return
                token, expires_at = create_session(row["id"])
                secure = "; Secure" if SECURE_COOKIES else ""
                cookie = f"videoluk_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_DAYS * 86400}{secure}"
                self.send_json(HTTPStatus.OK, {
                    "authenticated": True,
                    "user": {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]},
                    "expiresAt": expires_at,
                }, {"Set-Cookie": cookie})
                return
            if route == "/api/auth/logout":
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                morsel = cookie.get("videoluk_session")
                if morsel:
                    with DB_LOCK, db() as connection:
                        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (session_token_hash(morsel.value),))
                secure = "; Secure" if SECURE_COOKIES else ""
                self.send_json(HTTPStatus.OK, {"authenticated": False}, {
                    "Set-Cookie": f"videoluk_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}"
                })
                return
            user = self.require_user()
            if not user:
                return
            if route == "/api/uploads":
                self.receive_media_upload(user)
                return
            if route == "/api/training-videos":
                params = parse_qs(urlparse(self.path).query)
                self.receive_training_video(params.get("profileId", ["default"])[0])
                return
            body = self.read_json()
            if route == "/api/admin/users":
                owner = self.require_owner()
                if not owner:
                    return
                self.send_json(HTTPStatus.CREATED, create_managed_user(body))
                return
            if route.startswith("/api/admin/users/") and route.endswith("/update"):
                owner = self.require_owner()
                if not owner:
                    return
                user_id = route.strip("/").split("/")[3]
                self.send_json(HTTPStatus.OK, update_managed_user(user_id, body, owner["id"]))
                return
            if route == "/api/payments/iyzico/checkout":
                result = initialize_credit_checkout(user, str(body.get("packageId") or ""), body.get("billing") or {}, self.client_address[0])
                self.send_json(HTTPStatus.CREATED, result)
                return
            if route == "/api/cost-estimate":
                estimate = estimate_project_cost(body)
                estimate["availableCredits"] = user_usage(user["id"])["credits"]
                self.send_json(HTTPStatus.OK, estimate)
                return
            if route == "/api/scripts/generate":
                self.send_json(HTTPStatus.OK, generate_ai_script(body))
                return
            if route == "/api/editing-profiles":
                profile_id = str(body.get("id") or uuid.uuid4())
                if not profile_id.replace("-", "").isalnum():
                    raise ValueError("Geçersiz Kurgu DNA kimliği")
                name = " ".join(str(body.get("name") or "").split()).strip()[:120]
                description = " ".join(str(body.get("description") or "").split()).strip()[:600]
                if len(name) < 3:
                    raise ValueError("Kurgu DNA profili için bir ad yaz")
                rules = normalize_editing_rules(body.get("rules") or {})
                timestamp = now()
                with DB_LOCK, db() as connection:
                    exists = connection.execute("SELECT id FROM editing_profiles WHERE id = ?", (profile_id,)).fetchone()
                    if exists:
                        connection.execute(
                            "UPDATE editing_profiles SET name = ?, description = ?, rules = ?, updated_at = ? WHERE id = ?",
                            (name, description, json.dumps(rules, ensure_ascii=False), timestamp, profile_id),
                        )
                    else:
                        connection.execute(
                            "INSERT INTO editing_profiles VALUES (?, ?, ?, ?, ?, ?)",
                            (profile_id, name, description, json.dumps(rules, ensure_ascii=False), timestamp, timestamp),
                        )
                self.send_json(HTTPStatus.OK if exists else HTTPStatus.CREATED, get_editing_profile(profile_id))
                return
            if route == "/api/editing-feedback":
                profile_id = str(body.get("profileId") or "default")
                if not get_editing_profile(profile_id):
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Kurgu DNA profili bulunamadı"})
                    return
                note = " ".join(str(body.get("note") or "").split()).strip()[:1000]
                if len(note) < 5:
                    raise ValueError("Öğrenme kaydı için düzeltmenin nedenini yaz")
                feedback_id = str(uuid.uuid4())
                with DB_LOCK, db() as connection:
                    connection.execute(
                        "INSERT INTO editing_feedback VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (feedback_id, profile_id, str(body.get("projectId") or "") or None, note,
                         json.dumps(body.get("before"), ensure_ascii=False) if body.get("before") is not None else None,
                         json.dumps(body.get("after"), ensure_ascii=False) if body.get("after") is not None else None,
                         now()),
                    )
                self.send_json(HTTPStatus.CREATED, {"id": feedback_id, "profileId": profile_id, "learned": True})
                return
            if route == "/api/training/apply":
                profile_id = str(body.get("profileId") or "default")
                profile = get_editing_profile(profile_id)
                summary = training_summary(profile_id)
                suggested = summary.get("suggestedAverageShotSeconds")
                if not profile or not suggested:
                    raise ValueError("Kurgu DNA'ya uygulanacak tamamlanmış video analizi yok")
                rules = dict(profile["rules"])
                rules["averageShotSeconds"] = suggested
                learned_rule = f"Referans videolardaki yaklaşık {suggested:g} saniyelik ortalama plan ritmini koru"
                required = [rule for rule in rules.get("required", []) if not rule.startswith("Referans videolardaki yaklaşık ")]
                rules["required"] = [learned_rule, *required][:20]
                with DB_LOCK, db() as connection:
                    connection.execute(
                        "UPDATE editing_profiles SET rules = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(normalize_editing_rules(rules), ensure_ascii=False), now(), profile_id),
                    )
                self.send_json(HTTPStatus.OK, {"profile": get_editing_profile(profile_id), "summary": summary})
                return
            if route == "/api/voices/generate":
                self.send_json(HTTPStatus.CREATED, generate_voice(str(body.get("text") or "")))
                return
            if route == "/api/images/generate":
                self.send_json(HTTPStatus.CREATED, generate_scene_image(
                    str(body.get("prompt") or ""), str(body.get("orientation") or "vertical")
                ))
                return
            if route == "/api/projects":
                requested_id = str(body.get("id") or "")
                project_id = requested_id if requested_id.replace("-", "").isalnum() else str(uuid.uuid4())
                timestamp = now()
                title = str(body.get("title") or "Adsız Videoluk Projesi")[:120]
                with DB_LOCK, db() as connection:
                    exists = connection.execute(
                        "SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
                    ).fetchone()
                    collision = connection.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
                    if collision and not exists:
                        project_id = str(uuid.uuid4())
                    if not exists:
                        project_total = connection.execute("SELECT COUNT(*) AS total FROM projects WHERE user_id = ?", (user["id"],)).fetchone()["total"]
                        if project_total >= user_usage(user["id"])["projects"]["limit"]:
                            raise ValueError("Proje kotan dolu. Yeni proje açmak için eski bir projeyi silebilirsin")
                    if exists:
                        connection.execute(
                            "UPDATE projects SET title = ?, payload = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                            (title, json.dumps(body, ensure_ascii=False), timestamp, project_id, user["id"]),
                        )
                    else:
                        connection.execute(
                            "INSERT INTO projects (id, title, payload, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                            (project_id, title, json.dumps(body, ensure_ascii=False), timestamp, timestamp, user["id"]),
                        )
                self.send_json(HTTPStatus.OK if exists else HTTPStatus.CREATED, {"id": project_id, "title": title, "saved": True})
                return
            if route.startswith("/api/projects/") and route.endswith("/duplicate"):
                project_id = route.strip("/").split("/")[2]
                with DB_LOCK, db() as connection:
                    row = connection.execute(
                        "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
                    ).fetchone()
                    if not row:
                        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Proje bulunamadı"})
                        return
                    project_total = connection.execute("SELECT COUNT(*) AS total FROM projects WHERE user_id = ?", (user["id"],)).fetchone()["total"]
                    if project_total >= user_usage(user["id"])["projects"]["limit"]:
                        raise ValueError("Proje kotan dolu. Çoğaltmak için eski bir projeyi silebilirsin")
                    duplicate_id = str(uuid.uuid4())
                    timestamp = now()
                    payload = json.loads(row["payload"])
                    payload.pop("id", None)
                    duplicate_title = f"{row['title']} · Kopya"[:120]
                    payload["title"] = duplicate_title
                    connection.execute(
                        "INSERT INTO projects (id, title, payload, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (duplicate_id, duplicate_title, json.dumps(payload, ensure_ascii=False), timestamp, timestamp, user["id"]),
                    )
                self.send_json(HTTPStatus.CREATED, {"id": duplicate_id, "title": duplicate_title, "saved": True})
                return
            if route == "/api/renders":
                project_id = str(body.get("projectId") or "")
                job_id = str(uuid.uuid4())
                timestamp = now()
                render_usage = user_usage(user["id"])["renders"]
                if render_usage["used"] >= render_usage["limit"]:
                    self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Aylık render kotan doldu. Yeni dönem başladığında tekrar render alabilirsin."})
                    return
                with DB_LOCK, db() as connection:
                    active = connection.execute(
                        "SELECT COUNT(*) AS total FROM render_jobs WHERE status IN ('queued', 'rendering')"
                    ).fetchone()["total"]
                    if active >= MAX_QUEUED_RENDERS:
                        self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {
                            "error": "Render kuyruğu dolu. Lütfen mevcut işlerin tamamlanmasını bekleyin."
                        })
                        return
                    row = connection.execute(
                        "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
                    ).fetchone()
                    if not row:
                        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Proje bulunamadı"})
                        return
                    project_payload = json.loads(row["payload"])
                    estimate = estimate_project_cost(project_payload)
                    balance = int(connection.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM credit_transactions WHERE user_id = ?", (user["id"],)).fetchone()["total"])
                    if balance < estimate["totalCredits"]:
                        self.send_json(HTTPStatus.PAYMENT_REQUIRED, {
                            "error": f"Bu işlem {estimate['totalCredits']} kredi gerektiriyor; bakiyende {balance} kredi var.",
                            "requiredCredits": estimate["totalCredits"], "availableCredits": balance,
                        })
                        return
                    connection.execute(
                        "INSERT INTO render_jobs (id, project_id, status, progress, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (job_id, project_id, "queued", 0, timestamp, timestamp),
                    )
                    connection.execute(
                        "INSERT INTO credit_transactions VALUES (?, ?, ?, 'render', ?, ?, ?)",
                        (str(uuid.uuid4()), user["id"], -estimate["totalCredits"], "Video üretimi", json.dumps({"jobId": job_id, "projectId": project_id, "estimate": estimate}), timestamp),
                    )
                project = {"id": row["id"], "payload": project_payload, "user_id": row["user_id"], "credit_cost": estimate["totalCredits"]}
                submit_render(job_id, project)
                self.send_json(HTTPStatus.ACCEPTED, {"id": job_id, "status": "queued", "progress": 0})
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Bilinmeyen uç nokta"})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            record_system_event("error", "api", str(exc), {"method": "POST", "path": urlparse(self.path).path})
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "İşlem sırasında beklenmeyen bir sunucu hatası oluştu"})

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/health":
            operations = operational_status()
            self.send_json(HTTPStatus.OK, {
                "service": "videoluk-api",
                "status": "ok" if operations["status"] == "healthy" else "degraded",
                "textEngine": "ai" if LLM_URL and LLM_MODEL else "local",
                "model": LLM_MODEL or None,
                "imageEngine": "ai" if IMAGE_URL and IMAGE_MODEL else "stock-fallback",
                "imageModel": IMAGE_MODEL or None,
                "stockProvider": "pexels" if PEXELS_API_KEY else None,
                "voiceEngine": "system-tts" if shutil.which("say") or shutil.which("espeak-ng") else None,
                "authRequired": AUTH_REQUIRED,
                "authReady": bool(not AUTH_REQUIRED or (ADMIN_EMAIL and ADMIN_PASSWORD)),
                "queue": operations["queue"],
            })
            return
        if route == "/api/auth/status":
            user = self.current_user()
            self.send_json(HTTPStatus.OK, {
                "required": AUTH_REQUIRED,
                "ready": bool(not AUTH_REQUIRED or (ADMIN_EMAIL and ADMIN_PASSWORD)),
                "authenticated": bool(user),
                "user": user,
            })
            return
        if route.startswith("/api/") and not self.require_user():
            return
        if route == "/api/admin/overview":
            if not self.require_owner():
                return
            self.send_json(HTTPStatus.OK, admin_overview())
            return
        if route == "/api/editing-profiles":
            with db() as connection:
                rows = connection.execute("SELECT * FROM editing_profiles ORDER BY updated_at DESC").fetchall()
            profiles = []
            for row in rows:
                profile = dict(row)
                profile["rules"] = json.loads(profile["rules"])
                profile["feedbackCount"] = len(editing_training_context(profile["id"], 100))
                profiles.append(profile)
            self.send_json(HTTPStatus.OK, {"profiles": profiles})
            return
        if route == "/api/projects":
            with db() as connection:
                rows = connection.execute(
                    "SELECT id, title, created_at, updated_at FROM projects WHERE user_id = ? ORDER BY updated_at DESC LIMIT 50",
                    (self.current_user()["id"],),
                ).fetchall()
            self.send_json(HTTPStatus.OK, {"projects": [dict(row) for row in rows]})
            return
        if route == "/api/usage":
            self.send_json(HTTPStatus.OK, user_usage(self.current_user()["id"]))
            return
        if route == "/api/credit-packages":
            self.send_json(HTTPStatus.OK, {
                "provider": "iyzico", "configured": iyzico_ready(),
                "packages": [{"id": package_id, **package, "currency": "TRY"} for package_id, package in CREDIT_PACKAGES.items()],
            })
            return
        if route.startswith("/api/projects/"):
            project_id = route.rsplit("/", 1)[-1]
            with db() as connection:
                row = connection.execute(
                    "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, self.current_user()["id"])
                ).fetchone()
            if not row:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Proje bulunamadı"})
                return
            payload = json.loads(row["payload"])
            payload.update({"id": row["id"], "title": row["title"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]})
            self.send_json(HTTPStatus.OK, payload)
            return
        if route == "/api/training-videos":
            params = parse_qs(urlparse(self.path).query)
            profile_id = params.get("profileId", ["default"])[0]
            if not get_editing_profile(profile_id):
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Kurgu DNA profili bulunamadı"})
                return
            self.send_json(HTTPStatus.OK, training_summary(profile_id))
            return
        if route == "/api/uploads":
            params = parse_qs(urlparse(self.path).query)
            kind = params.get("kind", [""])[0]
            query = "SELECT * FROM media_assets WHERE user_id = ?"
            values: list[object] = [self.current_user()["id"]]
            if kind in UPLOAD_EXTENSIONS:
                query += " AND kind = ?"
                values.append(kind)
            query += " ORDER BY created_at DESC LIMIT 100"
            with db() as connection:
                rows = connection.execute(query, values).fetchall()
            self.send_json(HTTPStatus.OK, {"assets": [media_asset_payload(dict(row)) for row in rows]})
            return
        if route == "/api/media/search":
            params = parse_qs(urlparse(self.path).query)
            query = params.get("q", [""])[0]
            orientation = params.get("orientation", ["vertical"])[0]
            try:
                self.send_json(HTTPStatus.OK, search_stock_videos(query, orientation))
            except ValueError as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if route.startswith("/api/voices/"):
            voice_id = route.rsplit("/", 1)[-1]
            if not voice_id.replace("-", "").isalnum():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            path = VOICES / f"{voice_id}.wav"
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()
            with path.open("rb") as source:
                shutil.copyfileobj(source, self.wfile)
            return
        if route.startswith("/api/uploads/"):
            parts = route.strip("/").split("/")
            asset_id = parts[2] if len(parts) >= 3 else ""
            asset = uploaded_asset(asset_id, self.current_user()["id"])
            if not asset:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            thumbnail_request = len(parts) == 4 and parts[3] == "thumbnail"
            path = Path(asset["thumbnail_path"] if thumbnail_request else asset["file_path"])
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = "image/jpeg" if thumbnail_request else asset["mime_type"]
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(asset['filename'])}")
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            with path.open("rb") as source:
                shutil.copyfileobj(source, self.wfile)
            return
        if route.startswith("/api/images/"):
            image_id = route.rsplit("/", 1)[-1]
            if not image_id.replace("-", "").isalnum():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            path = GENERATED_IMAGES / f"{image_id}.png"
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Cache-Control", "private, max-age=31536000, immutable")
            self.end_headers()
            with path.open("rb") as source:
                shutil.copyfileobj(source, self.wfile)
            return
        if route.startswith("/api/renders/"):
            parts = route.strip("/").split("/")
            job_id = parts[2] if len(parts) >= 3 else ""
            with db() as connection:
                row = connection.execute(
                    "SELECT render_jobs.* FROM render_jobs JOIN projects ON projects.id = render_jobs.project_id "
                    "WHERE render_jobs.id = ? AND projects.user_id = ?", (job_id, self.current_user()["id"])
                ).fetchone()
            if not row:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Render işi bulunamadı"})
                return
            if len(parts) == 4 and parts[3] in {"download", "subtitles"}:
                key = "output_path" if parts[3] == "download" else "subtitle_path"
                path = Path(row[key]) if row[key] else Path("/")
                self.send_file(path)
                return
            payload = dict(row)
            payload["downloadUrl"] = f"/api/renders/{job_id}/download" if row["status"] == "completed" else None
            payload["subtitleUrl"] = f"/api/renders/{job_id}/subtitles" if row["subtitle_path"] else None
            payload.pop("output_path", None)
            payload.pop("subtitle_path", None)
            self.send_json(HTTPStatus.OK, payload)
            return
        super().do_GET()

    def do_DELETE(self) -> None:
        try:
            route = urlparse(self.path).path
            user = self.require_user()
            if not user:
                return
            if route.startswith("/api/uploads/"):
                asset_id = route.rsplit("/", 1)[-1]
                asset = uploaded_asset(asset_id, user["id"])
                if not asset:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Medya bulunamadı"})
                    return
                with DB_LOCK, db() as connection:
                    connection.execute("DELETE FROM media_assets WHERE id = ? AND user_id = ?", (asset_id, user["id"]))
                Path(asset["file_path"]).unlink(missing_ok=True)
                if asset.get("thumbnail_path"):
                    Path(asset["thumbnail_path"]).unlink(missing_ok=True)
                self.send_json(HTTPStatus.OK, {"deleted": True, "id": asset_id})
                return
            if not route.startswith("/api/projects/"):
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Bilinmeyen uç nokta"})
                return
            project_id = route.rsplit("/", 1)[-1]
            with DB_LOCK, db() as connection:
                row = connection.execute(
                    "SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
                ).fetchone()
                if not row:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Proje bulunamadı"})
                    return
                active = connection.execute(
                    "SELECT COUNT(*) AS total FROM render_jobs WHERE project_id = ? AND status IN ('queued', 'rendering')",
                    (project_id,),
                ).fetchone()["total"]
                if active:
                    self.send_json(HTTPStatus.CONFLICT, {"error": "Render devam ederken proje silinemez"})
                    return
                job_rows = connection.execute("SELECT id FROM render_jobs WHERE project_id = ?", (project_id,)).fetchall()
                connection.execute("DELETE FROM render_jobs WHERE project_id = ?", (project_id,))
                connection.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"]))
            for job in job_rows:
                shutil.rmtree(OUTPUTS / job["id"], ignore_errors=True)
            self.send_json(HTTPStatus.OK, {"deleted": True, "id": project_id})
        except Exception as exc:
            traceback.print_exc()
            record_system_event("error", "api", str(exc), {"method": "DELETE", "path": urlparse(self.path).path})
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "İşlem sırasında beklenmeyen bir sunucu hatası oluştu"})


if __name__ == "__main__":
    initialize()
    resumed = resume_incomplete_renders()
    server = ThreadingHTTPServer((HOST, PORT), VideolukHandler)
    print(f"Videoluk hazır: http://{HOST}:{PORT} (render worker: {RENDER_WORKERS}, devam eden: {resumed})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        RENDER_EXECUTOR.shutdown(wait=False, cancel_futures=False)
        ANALYSIS_EXECUTOR.shutdown(wait=False, cancel_futures=False)
        ALERT_EXECUTOR.shutdown(wait=False, cancel_futures=False)
