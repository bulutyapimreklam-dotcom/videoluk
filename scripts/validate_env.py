#!/usr/bin/env python3
"""Validate Videoluk production configuration without printing secrets."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def validate(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    required = ("VIDEOLUK_DOMAIN", "VIDEOLUK_ADMIN_EMAIL", "VIDEOLUK_ADMIN_PASSWORD", "VIDEOLUK_BASIC_AUTH_HASH")
    for key in required:
        value = values.get(key, "")
        if not value or "BURAYA" in value or "example.com" in value:
            errors.append(f"{key} gerçek üretim değeriyle doldurulmalı")
    if values.get("VIDEOLUK_AUTH_REQUIRED", "").lower() not in {"1", "true", "yes"}:
        errors.append("VIDEOLUK_AUTH_REQUIRED üretimde açık olmalı")
    if values.get("VIDEOLUK_SECURE_COOKIES", "").lower() not in {"1", "true", "yes"}:
        errors.append("VIDEOLUK_SECURE_COOKIES üretimde açık olmalı")
    if len(values.get("VIDEOLUK_ADMIN_PASSWORD", "")) < 14:
        errors.append("VIDEOLUK_ADMIN_PASSWORD en az 14 karakter olmalı")
    domain = values.get("VIDEOLUK_DOMAIN", "")
    if domain and not re.fullmatch(r"[A-Za-z0-9.-]+", domain):
        errors.append("VIDEOLUK_DOMAIN yalnızca alan adı içermeli; protokol veya yol yazılmamalı")
    public_url = values.get("VIDEOLUK_PUBLIC_BASE_URL", "")
    if public_url and public_url != f"https://{domain}":
        errors.append("VIDEOLUK_PUBLIC_BASE_URL, HTTPS ile VIDEOLUK_DOMAIN değerini kullanmalı")
    iyzico_values = (values.get("VIDEOLUK_IYZICO_API_KEY", ""), values.get("VIDEOLUK_IYZICO_SECRET_KEY", ""))
    if any(iyzico_values) and not all(iyzico_values):
        errors.append("iyzico API ve secret anahtarları birlikte girilmeli")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".env")
    args = parser.parse_args()
    path = Path(args.path)
    if not path.is_file():
        print(f"HATA: {path} bulunamadı")
        return 1
    errors = validate(read_env(path))
    if errors:
        for error in errors:
            print(f"HATA: {error}")
        return 1
    print("Videoluk üretim ayarları geçerli.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
