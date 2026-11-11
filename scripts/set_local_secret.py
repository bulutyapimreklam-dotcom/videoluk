#!/usr/bin/env python3
"""Safely update one allow-listed Videoluk secret in the ignored local .env file."""

from __future__ import annotations

import getpass
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"
ALLOWED = {"VIDEOLUK_COVERR_API_KEY", "VIDEOLUK_PEXELS_API_KEY", "VIDEOLUK_OPENAI_API_KEY"}


def main() -> None:
    name = os.environ.get("VIDEOLUK_SECRET_NAME", "")
    if name not in ALLOWED:
        raise SystemExit("Desteklenmeyen gizli ayar")
    value = getpass.getpass(f"{name}: ").strip()
    if len(value) < 12 or any(character.isspace() for character in value):
        raise SystemExit("Anahtar biçimi geçersiz")
    source = ENV_FILE if ENV_FILE.exists() else EXAMPLE
    lines = source.read_text(encoding="utf-8").splitlines()
    replacement = f"{name}={value}"
    updated = False
    for index, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[index] = replacement
            updated = True
            break
    if not updated:
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
    print("Yerel anahtar kaydedildi.")


if __name__ == "__main__":
    main()
