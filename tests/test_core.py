import tempfile
import unittest
import json
from pathlib import Path

import server


class VideolukCoreTests(unittest.TestCase):
    def test_free_subscription_is_persisted_and_exported(self):
        originals = {"DATA": server.DATA, "OUTPUTS": server.OUTPUTS, "VOICES": server.VOICES, "MEDIA_CACHE": server.MEDIA_CACHE, "GENERATED_IMAGES": server.GENERATED_IMAGES, "TRAINING_VIDEOS": server.TRAINING_VIDEOS, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH}
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root; server.OUTPUTS = root / "renders"; server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"; server.GENERATED_IMAGES = root / "generated-images"
                server.TRAINING_VIDEOS = root / "training-videos"; server.UPLOADS = root / "uploads"; server.DB_PATH = root / "videoluk.db"
                server.initialize()
                selected = server.select_free_subscription(server.LOCAL_USER_ID)
                self.assertEqual("free", selected["planId"])
                self.assertEqual("active", selected["status"])
                exported = server.account_data_export(server.LOCAL_USER_ID)
                self.assertEqual("free", exported["subscription"]["plan_id"])
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_account_deletion_request_requires_password_and_tracks_review(self):
        originals = {
            "DATA": server.DATA, "OUTPUTS": server.OUTPUTS, "VOICES": server.VOICES,
            "MEDIA_CACHE": server.MEDIA_CACHE, "GENERATED_IMAGES": server.GENERATED_IMAGES,
            "TRAINING_VIDEOS": server.TRAINING_VIDEOS, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH,
            "AUTH_REQUIRED": server.AUTH_REQUIRED,
        }
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root; server.OUTPUTS = root / "renders"; server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"; server.GENERATED_IMAGES = root / "generated-images"
                server.TRAINING_VIDEOS = root / "training-videos"; server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"; server.AUTH_REQUIRED = True
                server.initialize()
                member = server.create_managed_user({"name": "Silme Talebi", "email": "delete@example.com", "password": "guvenli-parola-123"})
                with self.assertRaisesRegex(ValueError, "Parola"):
                    server.create_deletion_request(member["id"], "yanlis-parola", "Deneme")
                requested = server.create_deletion_request(member["id"], "guvenli-parola-123", "Hesabımı kapatıyorum")
                self.assertEqual("requested", requested["status"])
                owner = {"id": server.LOCAL_USER_ID, "role": "owner"}
                reviewed = server.update_deletion_request(requested["id"], "in_review", owner)
                self.assertEqual("in_review", reviewed["status"])
                completed = server.update_deletion_request(requested["id"], "completed", owner, "Manuel doğrulama tamamlandı")
                self.assertEqual("completed", completed["status"])
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_account_export_is_portable_and_excludes_secrets(self):
        originals = {
            "DATA": server.DATA, "OUTPUTS": server.OUTPUTS, "VOICES": server.VOICES,
            "MEDIA_CACHE": server.MEDIA_CACHE, "GENERATED_IMAGES": server.GENERATED_IMAGES,
            "TRAINING_VIDEOS": server.TRAINING_VIDEOS, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH,
        }
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.OUTPUTS = root / "renders"
                server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"
                server.GENERATED_IMAGES = root / "generated-images"
                server.TRAINING_VIDEOS = root / "training-videos"
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                user = server.create_managed_user({"name": "Dışa Aktarım", "email": "export@example.com", "password": "guvenli-parola-123"})
                timestamp = server.now()
                with server.db() as connection:
                    connection.execute(
                        "INSERT INTO projects (id, title, payload, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                        ("project-export", "Örnek proje", json.dumps({"script": "Taşınabilir metin"}), timestamp, timestamp, user["id"]),
                    )
                    connection.execute(
                        "INSERT INTO payment_orders VALUES (?, ?, 'iyzico', 'mini', 100, '199.00', 'TRY', ?, ?, 'paid', NULL, ?, ?)",
                        ("payment-export", user["id"], "secret-payment-token", "provider-payment-id", timestamp, timestamp),
                    )
                exported = server.account_data_export(user["id"])
                encoded = json.dumps(exported, ensure_ascii=False)
                self.assertEqual("videoluk-account-export-v1", exported["format"])
                self.assertEqual("Taşınabilir metin", exported["projects"][0]["script"])
                self.assertEqual("paid", exported["payments"][0]["status"])
                for secret in ("password_hash", "secret-payment-token", "provider-payment-id", "file_path", "token_hash"):
                    self.assertNotIn(secret, encoded)
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_account_email_uses_smtp_without_exposing_credentials(self):
        originals = {
            "DATA": server.DATA, "OUTPUTS": server.OUTPUTS, "VOICES": server.VOICES,
            "MEDIA_CACHE": server.MEDIA_CACHE, "GENERATED_IMAGES": server.GENERATED_IMAGES,
            "TRAINING_VIDEOS": server.TRAINING_VIDEOS, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH,
            "PUBLIC_BASE_URL": server.PUBLIC_BASE_URL, "SMTP_HOST": server.SMTP_HOST,
            "SMTP_PORT": server.SMTP_PORT, "SMTP_USER": server.SMTP_USER,
            "SMTP_PASSWORD": server.SMTP_PASSWORD, "SMTP_FROM": server.SMTP_FROM,
            "SMTP_SECURITY": server.SMTP_SECURITY, "SMTP": server.smtplib.SMTP,
        }
        clients = []

        class FakeSmtp:
            def __init__(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout
                self.started_tls = False
                self.login_args = None
                self.message = None
                clients.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def starttls(self, context):
                self.started_tls = context is not None

            def login(self, user, password):
                self.login_args = (user, password)

            def send_message(self, message):
                self.message = message

        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.OUTPUTS = root / "renders"
                server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"
                server.GENERATED_IMAGES = root / "generated-images"
                server.TRAINING_VIDEOS = root / "training-videos"
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                user = server.create_managed_user({"name": "E-posta Üyesi", "email": "uye@example.com"})
                server.PUBLIC_BASE_URL = "https://app.videoluk.test"
                server.SMTP_HOST = "smtp.example.test"
                server.SMTP_PORT = 587
                server.SMTP_USER = "smtp-user"
                server.SMTP_PASSWORD = "smtp-secret"
                server.SMTP_FROM = "Videoluk <hesap@videoluk.test>"
                server.SMTP_SECURITY = "starttls"
                server.smtplib.SMTP = FakeSmtp
                self.assertTrue(server.deliver_account_email(user["id"], user["activation"]))
                client = clients[0]
                self.assertTrue(client.started_tls)
                self.assertEqual(("smtp-user", "smtp-secret"), client.login_args)
                self.assertEqual("uye@example.com", client.message["To"])
                self.assertIn("https://app.videoluk.test/?authToken=", client.message.get_content())
                self.assertNotIn("smtp-secret", client.message.as_string())
                with server.db() as connection:
                    connection.execute("UPDATE users SET status = 'active' WHERE id = ?", (user["id"],))
                server.PASSWORD_RESET_LAST_SENT.clear()
                self.assertTrue(server.request_password_reset("UYE@example.com", "127.0.0.1"))
                self.assertFalse(server.request_password_reset("uye@example.com", "127.0.0.1"))
                self.assertFalse(server.request_password_reset("yok@example.com", "127.0.0.2"))
                self.assertEqual(2, len(clients))
                self.assertIn("parolanı yenile", clients[-1].message["Subject"].lower())
        finally:
            for name, value in originals.items():
                if name == "SMTP":
                    server.smtplib.SMTP = value
                else:
                    setattr(server, name, value)

    def test_voice_falls_back_to_default_macos_voice(self):
        originals = {"VOICES": server.VOICES, "FFMPEG": server.FFMPEG, "EDGE_TTS": server.EDGE_TTS, "which": server.shutil.which, "run": server.subprocess.run, "valid_audio_file": server.valid_audio_file}
        calls = []

        class Result:
            def __init__(self, returncode=0):
                self.returncode = returncode
                self.stderr = ""

        try:
            with tempfile.TemporaryDirectory() as temporary:
                server.VOICES = Path(temporary)
                server.EDGE_TTS = Path(temporary) / "missing-edge-tts"
                server.shutil.which = lambda command: "/usr/bin/say" if command == "say" else None
                server.valid_audio_file = lambda path: path.is_file() and path.stat().st_size >= 1024

                def fake_run(command, **_kwargs):
                    calls.append(command)
                    if command[0] == "say" and "Yelda" in command:
                        return Result(1)
                    output = Path(command[command.index("-o") + 1]) if command[0] == "say" else Path(command[-1])
                    output.write_bytes(b"0" * 2048)
                    return Result()

                server.subprocess.run = fake_run
                voice = server.generate_voice("Varsayılan sesle devam et")
                self.assertEqual("system-tts", voice["provider"])
                self.assertEqual("Yelda", calls[0][2])
                self.assertEqual("say", calls[1][0])
                self.assertNotIn("-v", calls[1])
        finally:
            for name, value in originals.items():
                if name == "which":
                    server.shutil.which = value
                elif name == "run":
                    server.subprocess.run = value
                else:
                    setattr(server, name, value)

    def test_biography_script_has_distinct_scenes_and_verified_portrait(self):
        original = server.fetch_wikipedia_summary
        try:
            server.fetch_wikipedia_summary = lambda _subject: {
                "title": "Örnek Kişi",
                "extract": (
                    "Örnek Kişi 1925 yılında doğdu. Eğitimini Ankara'da tamamladı. "
                    "Siyasi yaşama genç yaşta katıldı. Ülkenin dönüşüm yıllarında önemli görevler üstlendi. "
                    "Toplumsal uzlaşmayı savundu. Çalışmaları sonraki kuşaklar üzerinde iz bıraktı."
                ),
                "url": "https://tr.wikipedia.org/wiki/%C3%96rnek_Ki%C5%9Fi",
                "image": "https://upload.wikimedia.org/example-person.jpg",
            }
            result = server.generate_biography_script({"idea": "Örnek Kişi biyografisi", "duration": 30}, "Örnek Kişi")
        finally:
            server.fetch_wikipedia_summary = original
        self.assertEqual(3, len(result["scenes"]))
        self.assertEqual(3, len({scene["mediaQuery"] for scene in result["scenes"]}))
        self.assertEqual("https://upload.wikimedia.org/example-person.jpg", result["scenes"][0]["suggestedMedia"]["imageUrl"])

    def test_password_hash_is_salted_and_verifiable(self):
        first = server.hash_password("uzun-guvenli-parola")
        second = server.hash_password("uzun-guvenli-parola")
        self.assertNotEqual(first, second)
        self.assertTrue(server.verify_password("uzun-guvenli-parola", first))
        self.assertFalse(server.verify_password("yanlis-parola", first))

    def test_local_script_has_distinct_scenes(self):
        result = server.generate_local_script({
            "idea": "Mahalle esnafı için teslimat uygulaması",
            "duration": 45,
            "type": "Tanıtım",
            "tone": "Bilgilendirici",
        })
        self.assertEqual(4, len(result["scenes"]))
        self.assertEqual(4, len({scene["subtitle"] for scene in result["scenes"]}))
        self.assertEqual("Kapanış", result["scenes"][-1]["purpose"])
        short = server.generate_local_script({"idea": "Temiz ulaşım", "duration": 30})
        self.assertIn("hayata geçirme", short["scenes"][-1]["title"].casefold())

    def test_biography_subject_detection(self):
        self.assertEqual("Bülent Ecevit", server.biography_subject("Bülent Ecevit biyografisi"))
        self.assertIsNone(server.biography_subject("Yeni kahve deneyimi"))

    def test_stock_url_guard(self):
        self.assertTrue(server.validate_stock_url("https://upload.wikimedia.org/example.jpg"))
        with self.assertRaises(ValueError):
            server.validate_stock_url("http://127.0.0.1/private.mp4")
        with self.assertRaises(ValueError):
            server.validate_stock_url("https://example.com/video.mp4")

    def test_srt_uses_scene_durations(self):
        srt = server.build_srt([
            {"title": "Bir", "subtitle": "Başlangıç", "duration": 2},
            {"title": "İki", "subtitle": "Devam", "duration": 4},
        ], 6)
        self.assertIn("00:00:00,000 --> 00:00:02,000", srt)
        self.assertIn("00:00:02,000 --> 00:00:06,000", srt)

    def test_editing_rules_are_bounded_and_applied(self):
        rules = server.normalize_editing_rules({
            "hookSeconds": 99,
            "averageShotSeconds": 0.1,
            "rhythm": "  Kontrollü ritim  ",
            "required": ["İlk planda insan yüzü"],
            "forbidden": ["Gereksiz glitch"],
        })
        self.assertEqual(10, rules["hookSeconds"])
        self.assertEqual(0.8, rules["averageShotSeconds"])
        profile = {"id": "test", "name": "Usta", "rules": rules}
        original_brief = server.editing_brief
        try:
            server.editing_brief = lambda _profile: "test brief"
            result = server.apply_editing_profile({
                "duration": 30,
                "scenes": [{"title": "Kanca"}, {"title": "Gelişme"}, {"title": "Final"}],
            }, profile)
        finally:
            server.editing_brief = original_brief
        self.assertEqual(10, result["scenes"][0]["duration"])
        self.assertEqual(10, result["scenes"][1]["duration"])
        self.assertIn("kanca önceliği", result["scenes"][0]["editingReason"])
        self.assertEqual("Usta", result["editingProfile"]["name"])

    def test_incomplete_renders_are_resumed_after_restart(self):
        originals = {
            "DATA": server.DATA,
            "OUTPUTS": server.OUTPUTS,
            "VOICES": server.VOICES,
            "MEDIA_CACHE": server.MEDIA_CACHE,
            "GENERATED_IMAGES": server.GENERATED_IMAGES,
            "UPLOADS": server.UPLOADS,
            "DB_PATH": server.DB_PATH,
            "submit_render": server.submit_render,
        }
        submitted = []
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.OUTPUTS = root / "renders"
                server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"
                server.GENERATED_IMAGES = root / "generated-images"
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.submit_render = lambda job_id, project: submitted.append((job_id, project))
                server.initialize()
                stamp = server.now()
                payload = json.dumps({"duration": 3, "scenes": []})
                with server.db() as connection:
                    connection.execute(
                        "INSERT INTO projects (id, title, payload, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                        ("project-1", "Test", payload, stamp, stamp, server.LOCAL_USER_ID),
                    )
                    for job_id, status in (("job-1", "queued"), ("job-2", "rendering"), ("job-3", "completed")):
                        connection.execute(
                            "INSERT INTO render_jobs (id, project_id, status, progress, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (job_id, "project-1", status, 50, stamp, stamp),
                        )
                self.assertEqual(2, server.active_render_count())
                self.assertEqual(2, server.resume_incomplete_renders())
                self.assertEqual(["job-1", "job-2"], [item[0] for item in submitted])
                with server.db() as connection:
                    states = dict(connection.execute("SELECT id, status FROM render_jobs"))
                    owner = connection.execute("SELECT user_id FROM projects WHERE id = 'project-1'").fetchone()["user_id"]
                self.assertEqual("queued", states["job-1"])
                self.assertEqual("queued", states["job-2"])
                self.assertEqual("completed", states["job-3"])
                self.assertEqual(server.LOCAL_USER_ID, owner)
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_training_summary_calculates_editing_rhythm(self):
        originals = {
            "DATA": server.DATA,
            "OUTPUTS": server.OUTPUTS,
            "VOICES": server.VOICES,
            "MEDIA_CACHE": server.MEDIA_CACHE,
            "GENERATED_IMAGES": server.GENERATED_IMAGES,
            "TRAINING_VIDEOS": server.TRAINING_VIDEOS,
            "UPLOADS": server.UPLOADS,
            "DB_PATH": server.DB_PATH,
        }
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.OUTPUTS = root / "renders"
                server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"
                server.GENERATED_IMAGES = root / "generated-images"
                server.TRAINING_VIDEOS = root / "training-videos"
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                stamp = server.now()
                with server.db() as connection:
                    for index, shot in enumerate((2.0, 4.0), 1):
                        connection.execute(
                            "INSERT INTO training_videos "
                            "(id, profile_id, filename, file_path, status, progress, duration, cut_count, average_shot, has_audio, created_at, updated_at) "
                            "VALUES (?, 'default', ?, ?, 'ready', 100, 30, 9, ?, 1, ?, ?)",
                            (f"video-{index}", f"video-{index}.mp4", f"/tmp/video-{index}.mp4", shot, stamp, stamp),
                        )
                summary = server.training_summary("default")
                self.assertEqual(2, summary["ready"])
                self.assertEqual(3.0, summary["suggestedAverageShotSeconds"])
                self.assertEqual(60.0, summary["totalDurationSeconds"])
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_generated_image_asset_is_resolved_without_network(self):
        original = server.GENERATED_IMAGES
        try:
            with tempfile.TemporaryDirectory() as temporary:
                server.GENERATED_IMAGES = Path(temporary)
                asset = server.GENERATED_IMAGES / "asset-1.png"
                asset.write_bytes(b"x" * 2048)
                self.assertEqual(asset, server.download_stock_video({"assetId": "asset-1"}))
                with self.assertRaises(ValueError):
                    server.download_stock_video({"assetId": "missing"})
        finally:
            server.GENERATED_IMAGES = original

    def test_uploaded_asset_is_scoped_to_owner(self):
        originals = {"DATA": server.DATA, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH}
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                asset = server.UPLOADS / "test.png"
                asset.write_bytes(b"x" * 2048)
                with server.db() as connection:
                    connection.execute(
                        "INSERT INTO media_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ("upload-1", server.LOCAL_USER_ID, "test.png", "image", "image/png", str(asset), None, asset.stat().st_size, server.now()),
                    )
                self.assertEqual(asset, server.download_stock_video({"uploadId": "upload-1"}, server.LOCAL_USER_ID))
                with self.assertRaises(ValueError):
                    server.download_stock_video({"uploadId": "upload-1"}, "another-user")
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_user_usage_counts_projects_storage_and_monthly_renders(self):
        originals = {"DATA": server.DATA, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH}
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                stamp = server.now()
                with server.db() as connection:
                    connection.execute(
                        "INSERT INTO projects (id, title, payload, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                        ("quota-project", "Kota", "{}", stamp, stamp, server.LOCAL_USER_ID),
                    )
                    connection.execute(
                        "INSERT INTO media_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ("quota-media", server.LOCAL_USER_ID, "test.mp4", "video", "video/mp4", "/tmp/test.mp4", None, 2048, stamp),
                    )
                    connection.execute(
                        "INSERT INTO render_jobs (id, project_id, status, progress, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        ("quota-render", "quota-project", "completed", 100, stamp, stamp),
                    )
                    connection.execute(
                        "INSERT INTO usage_events VALUES (?, ?, ?, ?, ?, ?)",
                        ("quota-event", server.LOCAL_USER_ID, "render_seconds", 30, "{}", stamp),
                    )
                usage = server.user_usage(server.LOCAL_USER_ID)
                self.assertEqual(1, usage["projects"]["used"])
                self.assertEqual(2048, usage["storage"]["usedBytes"])
                self.assertEqual(1, usage["renders"]["used"])
                self.assertEqual(30, usage["renderedSeconds"])
                self.assertEqual(server.STARTER_CREDITS, usage["credits"])
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_project_cost_estimate_distinguishes_stock_and_ai(self):
        stock = server.estimate_project_cost({"duration": 30, "source": "Stok görüntü", "scenes": [{}, {}]})
        ai = server.estimate_project_cost({"duration": 30, "source": "Yapay zekâ", "scenes": [{}, {}]})
        self.assertEqual(3, stock["totalCredits"])
        self.assertEqual(7, ai["totalCredits"])
        self.assertEqual(4, ai["breakdown"]["aiMedia"])

    def test_admin_overview_aggregates_operations_without_secrets(self):
        originals = {
            "DATA": server.DATA,
            "OUTPUTS": server.OUTPUTS,
            "VOICES": server.VOICES,
            "MEDIA_CACHE": server.MEDIA_CACHE,
            "GENERATED_IMAGES": server.GENERATED_IMAGES,
            "TRAINING_VIDEOS": server.TRAINING_VIDEOS,
            "UPLOADS": server.UPLOADS,
            "DB_PATH": server.DB_PATH,
        }
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.OUTPUTS = root / "renders"
                server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"
                server.GENERATED_IMAGES = root / "generated-images"
                server.TRAINING_VIDEOS = root / "training-videos"
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                stamp = server.now()
                with server.db() as connection:
                    connection.execute(
                        "INSERT INTO users (id, email, name, password_hash, role, created_at, updated_at, status) VALUES (?, ?, ?, ?, 'member', ?, ?, 'active')",
                        ("member-1", "uye@example.com", "Üye", server.hash_password("guvenli-parola-123"), stamp, stamp),
                    )
                    connection.execute(
                        "INSERT INTO projects (id, title, payload, created_at, updated_at, user_id) VALUES (?, ?, '{}', ?, ?, ?)",
                        ("admin-project", "Yönetim Testi", stamp, stamp, "member-1"),
                    )
                    connection.execute(
                        "INSERT INTO media_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ("admin-media", "member-1", "test.mp4", "video", "video/mp4", "/tmp/test.mp4", None, 4096, stamp),
                    )
                    connection.execute(
                        "INSERT INTO render_jobs (id, project_id, status, progress, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        ("admin-render", "admin-project", "completed", 100, stamp, stamp),
                    )
                    connection.execute(
                        "INSERT INTO payment_orders VALUES (?, ?, 'iyzico', 'mini', 100, '199.00', 'TRY', NULL, 'payment-1', 'paid', NULL, ?, ?)",
                        ("admin-payment", "member-1", stamp, stamp),
                    )
                    connection.execute(
                        "INSERT INTO credit_transactions VALUES (?, ?, 100, 'purchase', 'Test', NULL, ?)",
                        ("admin-credit", "member-1", stamp),
                    )
                server.record_system_event("error", "test", "Kontrollü test hatası", {"secret": "yanıta çıkmamalı"})
                server.record_admin_action(server.LOCAL_USER_ID, "member-1", "user.updated", {"creditAdjustment": 25})
                overview = server.admin_overview()
                self.assertEqual(1, overview["metrics"]["users"])
                self.assertEqual(1, overview["metrics"]["projects"])
                self.assertEqual(4096, overview["metrics"]["storageBytes"])
                self.assertEqual(1, overview["metrics"]["rendersCompleted"])
                self.assertEqual(199.0, overview["metrics"]["revenueTry"])
                self.assertEqual(100, overview["users"][0]["credits"])
                self.assertEqual("degraded", overview["operations"]["status"])
                self.assertEqual(1, overview["operations"]["errors24h"])
                self.assertEqual("test", overview["events"][0]["source"])
                self.assertEqual("user.updated", overview["audit"][0]["action"])
                self.assertEqual("Yerel Kullanıcı", overview["audit"][0]["actor_name"])
                self.assertEqual("Üye", overview["audit"][0]["target_name"])
                self.assertEqual(25, overview["audit"][0]["details"]["creditAdjustment"])
                self.assertNotIn("metadata", overview["events"][0])
                self.assertNotIn("password_hash", overview["audit"][0])
                self.assertNotIn("password_hash", overview["users"][0])
                self.assertNotIn("token", overview["payments"][0])
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_webhook_alert_is_authenticated_and_deduplicated(self):
        originals = {
            "ALERT_WEBHOOK_URL": server.ALERT_WEBHOOK_URL,
            "ALERT_WEBHOOK_TOKEN": server.ALERT_WEBHOOK_TOKEN,
            "urlopen": server.urlopen,
        }
        requests = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"ok"

        try:
            server.ALERT_WEBHOOK_URL = "https://alerts.example.test/videoluk"
            server.ALERT_WEBHOOK_TOKEN = "secret-token"
            server.ALERT_LAST_SENT.clear()
            server.urlopen = lambda request, timeout: requests.append((request, timeout)) or Response()
            self.assertTrue(server.send_webhook_alert("error", "render", "Render başarısız"))
            self.assertFalse(server.send_webhook_alert("error", "render", "Render başarısız"))
            self.assertEqual(1, len(requests))
            request, timeout = requests[0]
            self.assertEqual(10, timeout)
            self.assertEqual("Bearer secret-token", request.get_header("Authorization"))
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual("videoluk", payload["service"])
            self.assertIn("Render başarısız", payload["text"])
        finally:
            server.ALERT_LAST_SENT.clear()
            for name, value in originals.items():
                setattr(server, name, value)

    def test_owner_can_create_and_manage_user_limits(self):
        originals = {
            "DATA": server.DATA, "OUTPUTS": server.OUTPUTS, "VOICES": server.VOICES,
            "MEDIA_CACHE": server.MEDIA_CACHE, "GENERATED_IMAGES": server.GENERATED_IMAGES,
            "TRAINING_VIDEOS": server.TRAINING_VIDEOS, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH,
        }
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.OUTPUTS = root / "renders"
                server.VOICES = root / "voices"
                server.MEDIA_CACHE = root / "media-cache"
                server.GENERATED_IMAGES = root / "generated-images"
                server.TRAINING_VIDEOS = root / "training-videos"
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                user = server.create_managed_user({"name": "Test Üye", "email": "UYE@example.com", "password": "guvenli-parola-123"})
                self.assertEqual("uye@example.com", user["email"])
                token, _expires = server.create_session(user["id"])
                result = server.update_managed_user(user["id"], {
                    "projectLimit": 12, "storageLimitGb": 9, "monthlyRenderLimit": 25,
                    "creditAdjustment": 30, "status": "suspended",
                }, server.LOCAL_USER_ID)
                self.assertEqual("suspended", result["status"])
                self.assertEqual(server.STARTER_CREDITS + 30, result["credits"])
                usage = server.user_usage(user["id"])
                self.assertEqual(12, usage["projects"]["limit"])
                self.assertEqual(9 * 1024**3, usage["storage"]["limitBytes"])
                self.assertEqual(25, usage["renders"]["limit"])
                with server.db() as connection:
                    self.assertIsNone(connection.execute("SELECT 1 FROM sessions WHERE token_hash = ?", (server.session_token_hash(token),)).fetchone())
                with self.assertRaisesRegex(ValueError, "zaten kayıtlı"):
                    server.create_managed_user({"name": "Tekrar", "email": "uye@example.com", "password": "guvenli-parola-456"})
                invited = server.create_managed_user({"name": "Davetli Üye", "email": "davet@example.com"})
                self.assertEqual("invited", invited["status"])
                invite_token = invited["activation"]["token"]
                self.assertEqual("invite", server.inspect_auth_token(invite_token)["purpose"])
                completed = server.complete_auth_token(invite_token, "yeni-guvenli-parola")
                self.assertTrue(completed["completed"])
                with self.assertRaisesRegex(ValueError, "geçersiz"):
                    server.complete_auth_token(invite_token, "baska-guvenli-parola")
                with server.db() as connection:
                    activated = connection.execute("SELECT status, password_hash FROM users WHERE id = ?", (invited["id"],)).fetchone()
                self.assertEqual("active", activated["status"])
                self.assertTrue(server.verify_password("yeni-guvenli-parola", activated["password_hash"]))
                reset = server.create_auth_token(invited["id"], "reset")
                self.assertEqual("reset", server.inspect_auth_token(reset["token"])["purpose"])
                server.update_managed_user(invited["id"], {"status": "suspended"}, "owner-1")
                server.complete_auth_token(reset["token"], "yenilenen-guvenli-parola")
                with server.db() as connection:
                    reset_user = connection.execute("SELECT status FROM users WHERE id = ?", (invited["id"],)).fetchone()
                self.assertEqual("suspended", reset_user["status"])
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_iyzico_callback_credits_order_only_once(self):
        originals = {"DATA": server.DATA, "UPLOADS": server.UPLOADS, "DB_PATH": server.DB_PATH, "iyzico_request": server.iyzico_request}
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                server.DATA = root
                server.UPLOADS = root / "uploads"
                server.DB_PATH = root / "videoluk.db"
                server.initialize()
                stamp = server.now()
                with server.db() as connection:
                    connection.execute(
                        "INSERT INTO payment_orders VALUES (?, ?, 'iyzico', 'mini', 100, '199.00', 'TRY', 'secure-token', NULL, 'pending', NULL, ?, ?)",
                        ("order-1", server.LOCAL_USER_ID, stamp, stamp),
                    )
                server.iyzico_request = lambda _path, _payload: {
                    "status": "success", "paymentStatus": "SUCCESS", "fraudStatus": 1, "basketId": "order-1",
                    "currency": "TRY", "price": 199, "paymentId": "payment-1",
                }
                self.assertTrue(server.complete_iyzico_order("order-1", "secure-token"))
                self.assertTrue(server.complete_iyzico_order("order-1", "secure-token"))
                self.assertEqual(server.STARTER_CREDITS + 100, server.user_usage(server.LOCAL_USER_ID)["credits"])
        finally:
            for name, value in originals.items():
                setattr(server, name, value)


if __name__ == "__main__":
    unittest.main()
