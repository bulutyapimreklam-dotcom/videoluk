import importlib.util
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_env = load_script("validate_env")
backup_data = load_script("backup_data")


class OperationsTests(unittest.TestCase):
    def test_legal_transparency_pages_are_linked_and_complete(self):
        index = (ROOT / "dist" / "index.html").read_text(encoding="utf-8")
        pages = ("gizlilik.html", "kullanim-kosullari.html", "cerezler.html")
        for page in pages:
            self.assertIn(f'href="{page}"', index)
            content = (ROOT / "dist" / page).read_text(encoding="utf-8")
            self.assertIn("Videoluk", content)
            self.assertIn("5 Kasım 2026", content)
            self.assertIn('href="./"', content)
            self.assertIn('href="videoluk-mark.svg"', content)
            self.assertIn('href="brand-system.css?v=1"', content)
        privacy = (ROOT / "dist" / "gizlilik.html").read_text(encoding="utf-8")
        self.assertIn("Veri sorumlusu", privacy)
        self.assertIn("haklarınız", privacy)
        cookies = (ROOT / "dist" / "cerezler.html").read_text(encoding="utf-8")
        self.assertIn("videoluk_session", cookies)
        self.assertIn("videoluk-draft", cookies)

    def test_saas_pages_and_subscription_are_visible(self):
        index = (ROOT / "dist" / "index.html").read_text(encoding="utf-8")
        pricing = (ROOT / "dist" / "fiyatlandirma.html").read_text(encoding="utf-8")
        faq = (ROOT / "dist" / "sss.html").read_text(encoding="utf-8")
        for page in ("fiyatlandirma.html", "sss.html", "gizlilik.html"):
            self.assertIn(f'href="{page}"', index)
        for plan in ("Başlangıç", "Creator", "Studio"):
            self.assertIn(plan, pricing)
        self.assertIn("Ücretli abonelik tahsilatı henüz açılmadı", pricing)
        self.assertGreaterEqual(faq.count("<details"), 10)
        self.assertIn("KVKK", faq)

    def test_brand_assets_are_connected_to_application(self):
        index = (ROOT / "dist" / "index.html").read_text(encoding="utf-8")
        mark = (ROOT / "dist" / "videoluk-mark.svg").read_text(encoding="utf-8")
        styles = (ROOT / "dist" / "brand-system.css").read_text(encoding="utf-8")
        self.assertIn('rel="icon" href="videoluk-mark.svg"', index)
        self.assertIn('href="brand-system.css?v=1"', index)
        self.assertIn("<svg", mark)
        self.assertIn("#d8ff6a", mark)
        self.assertIn(":focus-visible", styles)
        self.assertIn("videoluk-mark.svg", styles)

    def test_ubuntu_bootstrap_has_required_hardening(self):
        script = (ROOT / "deploy" / "bootstrap-ubuntu.sh").read_text(encoding="utf-8")
        for requirement in ("set -euo pipefail", "ufw default deny incoming", "fail2ban", "unattended-upgrades", "docker-ce", "chmod 600 /swapfile"):
            self.assertIn(requirement, script)

    def test_pages_workflow_publishes_static_application(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yaml").read_text(encoding="utf-8")
        self.assertIn("actions/upload-pages-artifact@v3", workflow)
        self.assertIn("path: dist", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)

    def test_production_environment_validation(self):
        valid = {
            "VIDEOLUK_DOMAIN": "app.videoluk.com",
            "VIDEOLUK_PUBLIC_BASE_URL": "https://app.videoluk.com",
            "VIDEOLUK_ADMIN_EMAIL": "admin@videoluk.com",
            "VIDEOLUK_ADMIN_PASSWORD": "uzun-ve-guvenli-parola",
            "VIDEOLUK_BASIC_AUTH_HASH": "$2a$14$hash",
            "VIDEOLUK_AUTH_REQUIRED": "1",
            "VIDEOLUK_SECURE_COOKIES": "1",
        }
        self.assertEqual([], validate_env.validate(valid))
        invalid = dict(valid, VIDEOLUK_SECURE_COOKIES="0", VIDEOLUK_PUBLIC_BASE_URL="http://app.videoluk.com")
        errors = validate_env.validate(invalid)
        self.assertTrue(any("SECURE_COOKIES" in error for error in errors))
        self.assertTrue(any("PUBLIC_BASE_URL" in error for error in errors))
        webhook_errors = validate_env.validate(dict(valid, VIDEOLUK_ALERT_WEBHOOK_URL="http://alerts.example.com"))
        self.assertTrue(any("ALERT_WEBHOOK_URL" in error for error in webhook_errors))

    def test_backup_contains_consistent_database_and_media(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            output = root / "output"
            data.mkdir()
            with sqlite3.connect(data / "videoluk.db") as connection:
                connection.execute("CREATE TABLE sample (value TEXT)")
                connection.execute("INSERT INTO sample VALUES ('ok')")
            (data / "uploads").mkdir()
            (data / "uploads" / "asset.txt").write_text("media", encoding="utf-8")
            archive_path = backup_data.create_backup(data, output)
            with tarfile.open(archive_path, "r:gz") as archive:
                names = archive.getnames()
                self.assertIn("videoluk.db", names)
                self.assertIn("uploads/asset.txt", names)


if __name__ == "__main__":
    unittest.main()
