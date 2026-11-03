#!/usr/bin/env python3
"""Create a consistent, portable Videoluk data archive."""

from __future__ import annotations

import argparse
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def create_backup(data_dir: Path, output_dir: Path) -> Path:
    database = data_dir / "videoluk.db"
    if not database.is_file():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {database}")
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / f"videoluk-{stamp}.tar.gz"
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / "videoluk.db"
        with sqlite3.connect(database) as source, sqlite3.connect(snapshot) as destination:
            source.backup(destination)
        with tarfile.open(target, "w:gz") as archive:
            archive.add(snapshot, arcname="videoluk.db")
            for item in data_dir.iterdir():
                if item.name in {"videoluk.db", "backups"}:
                    continue
                archive.add(item, arcname=item.name, recursive=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/data")
    parser.add_argument("--output", default="/backups")
    args = parser.parse_args()
    target = create_backup(Path(args.data), Path(args.output))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
