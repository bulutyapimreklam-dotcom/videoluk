import tempfile
import unittest
from pathlib import Path

import server


class VideolukCoreTests(unittest.TestCase):
    def test_local_script_has_distinct_scenes(self):
        result = server.generate_local_script({
            "idea": "Mahalle esnafı için teslimat uygulaması",
            "duration": 45,
            "type": "Tanıtım",
            "tone": "Bilgilendirici",
        })
        self.assertEqual(4, len(result["scenes"]))
        self.assertEqual(4, len({scene["subtitle"] for scene in result["scenes"]}))

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


if __name__ == "__main__":
    unittest.main()
