import tempfile
import unittest
import json
from pathlib import Path

import server


class VideolukCoreTests(unittest.TestCase):
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
                        "INSERT INTO users VALUES (?, ?, ?, ?, 'member', ?, ?)",
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
                self.assertNotIn("metadata", overview["events"][0])
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
