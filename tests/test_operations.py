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
