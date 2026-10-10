"""Telegram Bot API: sendPhoto (URL first, then uploaded file), getMe/getChat for doctor."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import config

_PERMANENT = ("chat not found", "not enough rights", "bot is not a member", "bot was kicked",
              "forbidden", "have no rights", "bot was blocked")


def _call(method: str, req: urllib.request.Request, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "replace"))
        except ValueError:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": config.redact(e)[:120]}


def _url(method: str) -> str:
    return f"{config.telegram_api()}/bot{config.env('TELEGRAM_BOT_TOKEN')}/{method}"


def _form(method: str, fields: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(_url(method), data=urllib.parse.urlencode(fields).encode())
    return _call(method, req, timeout)


def _multipart(method: str, fields: dict, fname: str, data: bytes, ctype: str, timeout=120) -> dict:
    b = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n').encode()
    body += (f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="{fname}"\r\n'
             f"Content-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(_url(method), data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return _call(method, req, timeout)


def get_me() -> bool:
    return bool(_form("getMe", {}, 20).get("ok"))


def get_chat(chat_id: str) -> bool:
    return bool(_form("getChat", {"chat_id": chat_id}, 20).get("ok"))


def send_photo(chat: str, caption: str, poster_url: str, poster_bytes: bytes, ctype: str):
    """-> (ok, reason). Tries URL, then upload (twice); honours retry_after; stops on permanent errors."""
    cap = config.number("DEVX_RETRY_CAP", 30)
    ext = {"image/png": "png", "image/webp": "webp"}.get(ctype, "jpg")
    reason = "unknown"
    for mode in ("url", "file", "file"):
        if mode == "url":
            resp = _form("sendPhoto", {"chat_id": chat, "photo": poster_url, "caption": caption})
        else:
            resp = _multipart("sendPhoto", {"chat_id": chat, "caption": caption},
                              f"poster.{ext}", poster_bytes, ctype)
        if resp.get("ok"):
            return True, ""
        reason = config.redact(resp.get("description") or "unknown")
        if any(p in reason.lower() for p in _PERMANENT):
            break
        wait = (resp.get("parameters") or {}).get("retry_after") or 2
        time.sleep(min(float(wait), cap))
    return False, reason
