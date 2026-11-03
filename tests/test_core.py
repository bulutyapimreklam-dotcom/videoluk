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


if __name__ == "__main__":
    unittest.main()
