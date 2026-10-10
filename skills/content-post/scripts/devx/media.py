"""Poster validation (public https image, jpeg/png/webp, <= 5 MB)."""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

from . import config

_OK_TYPES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}


@dataclass
class Poster:
    ok: bool
    url: str = ""
    data: bytes = b""
    ctype: str = ""
    reason: str = ""


def normalize_url(u: str) -> str:
    return u.strip().replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def _magic_ok(b: bytes) -> bool:
    return b[:2] == b"\xff\xd8" or b[:4] == b"\x89PNG" or (b[:4] == b"RIFF" and b[8:12] == b"WEBP")


def validate(url: str) -> Poster:
    url = normalize_url(url)
    if not (url.startswith("https://") or (config.allow_http() and url.startswith("http://"))):
        return Poster(False, url, reason="not https")
    req = urllib.request.Request(url, headers={"User-Agent": config.UA, "Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = (r.headers.get_content_type() or "").lower()
            if r.status != 200:
                return Poster(False, url, reason=f"status {r.status}")
            if ctype not in _OK_TYPES:
                return Poster(False, url, reason=f"type {ctype}")
            data = r.read(config.POSTER_MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        return Poster(False, url, reason=f"status {e.code}")
    except Exception as e:  # noqa: BLE001
        return Poster(False, url, reason=config.redact(e)[:80])
    if len(data) > config.POSTER_MAX_BYTES:
        return Poster(False, url, reason="over 5 MB")
    if not _magic_ok(data):
        return Poster(False, url, reason="not a real image")
    return Poster(True, url, data, ctype)


def first_valid(candidates: list[str]) -> Poster:
    last = Poster(False, reason="no poster candidates")
    for u in candidates[:6]:
        last = validate(u)
        if last.ok:
            return last
    return last
