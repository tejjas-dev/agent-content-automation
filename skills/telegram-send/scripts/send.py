#!/usr/bin/env python3
"""Send finished posts (poster + caption) to every channel.  send.py --task DIR [--channels-env NAME] [--force]
Reads TASK/data.json (title, poster) and TASK/caption<N>.txt. Env: TELEGRAM_BOT_TOKEN, <channels-env>.
Tries the poster URL first, then uploads the image; honours retry_after; never prints the token.
A (title, channel, post) already delivered is skipped unless --force, so retries never duplicate.
Exit 0 if every post is delivered, 1 otherwise."""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = os.environ.get("DEVX_TELEGRAM_API", "https://api.telegram.org")
PERMANENT = ("chat not found", "not enough rights", "bot is not a member", "bot was kicked", "forbidden", "have no rights")
TYPES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}


def data_dir():
    e = os.environ.get("DEVX_DATA_DIR")
    if e:
        return e
    return "/workspace" if os.path.isdir("/workspace") and os.access("/workspace", os.W_OK) else os.path.join(os.path.expanduser("~"), ".devx-content")


def state_dir(task):
    """<root>/state next to <root>/work/<task>; the ledger must outlive the daily cleanup of work/."""
    parent = os.path.dirname(os.path.realpath(task))
    root = os.path.dirname(parent) if os.path.basename(parent) == "work" else os.path.join(data_dir(), "drama")
    d = os.path.join(root, "state")
    os.makedirs(d, exist_ok=True)
    return d


def redact(s):
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    return str(s).replace(t, "***") if t else str(s)


def call(method, data, headers=None, timeout=60):
    req = urllib.request.Request(f"{API}/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}", data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "replace"))
        except ValueError:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": redact(e)[:120]}


def multipart(fields, fname, blob, ctype):
    b = uuid.uuid4().hex
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    body += f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
    return body + blob + f"\r\n--{b}--\r\n".encode(), {"Content-Type": f"multipart/form-data; boundary={b}"}


def fetch_poster(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ct = r.headers.get_content_type()
            blob = r.read(5 * 1024 * 1024 + 1)
        return (blob, ct) if ct in TYPES and len(blob) <= 5 * 1024 * 1024 else (None, "")
    except Exception:  # noqa: BLE001
        return None, ""


def send_photo(chat, caption, url, blob, ctype, cap):
    why = "unknown"
    for mode in ("url", "file", "file"):
        if mode == "file" and not blob:
            break
        if mode == "url":
            resp = call("sendPhoto", urllib.parse.urlencode({"chat_id": chat, "photo": url, "caption": caption}).encode())
        else:
            body, h = multipart({"chat_id": chat, "caption": caption}, f"poster.{TYPES[ctype]}", blob, ctype)
            resp = call("sendPhoto", body, h, 120)
        if resp.get("ok"):
            return True, ""
        why = redact(resp.get("description") or "unknown")
        if any(p in why.lower() for p in PERMANENT):
            break
        time.sleep(min(float((resp.get("parameters") or {}).get("retry_after") or 2), cap))
    return False, why


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--channels-env", default="DRAMA_POST_CHANNEL_IDS")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("ERROR: TELEGRAM_BOT_TOKEN is not set")
        return 2
    chans = [c for c in re.split(r"[,;\s]+", os.environ.get(a.channels_env, "")) if c]
    caps = sorted(glob.glob(os.path.join(a.task, "caption*.txt")), key=lambda f: int(re.findall(r"\d+", os.path.basename(f))[0]))
    try:
        data = json.load(open(os.path.join(a.task, "data.json"), encoding="utf-8"))
        poster, title = data["poster"], data["title"]
    except Exception:  # noqa: BLE001
        print("ERROR: data.json needs title and poster")
        return 2
    if not chans or not caps:
        print(f"ERROR: need channels in ${a.channels_env} and caption files")
        return 2
    texts = [open(f, encoding="utf-8").read() for f in caps]
    bad = [i + 1 for i, t in enumerate(texts) if len(t.encode("utf-16-le")) // 2 > 1024]
    if bad:
        print(f"ERROR: caption {bad} longer than Telegram's 1024 limit")
        return 2
    ledger = os.path.join(state_dir(a.task), "posted.jsonl")
    key = re.sub(r"[^a-z0-9]+", "", title.lower())
    done = set()
    if os.path.exists(ledger) and not a.force:
        for ln in open(ledger, encoding="utf-8"):
            try:
                r = json.loads(ln)
                if r["key"] == key and r["of"] == len(texts):
                    done.add((str(r["channel"]), r["post"]))
            except (ValueError, KeyError):
                pass
    blob, ctype = fetch_poster(poster)
    cap = float(os.environ.get("DEVX_RETRY_CAP", "30"))
    delay = float(os.environ.get("DEVX_SEND_DELAY", "3"))
    ok = fail = 0
    for ci, ch in enumerate(chans):
        for i, t in enumerate(texts, 1):
            if (ch, i) in done:
                print(f"SKIP {ch} post{i} (already sent)")
                ok += 1
                continue
            good, why = send_photo(ch, t, poster, blob, ctype, cap)
            if good:
                with open(ledger, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": int(time.time()), "key": key, "title": title, "channel": ch, "post": i, "of": len(texts)}, ensure_ascii=False) + "\n")
                print(f"OK   {ch} post{i}")
                ok += 1
            else:
                print(f"FAIL {ch} post{i} {why}")
                fail += 1
            if not (ci == len(chans) - 1 and i == len(texts)):
                time.sleep(delay)
    print(f"ok={ok} fail={fail} channels={len(chans)} posts={len(texts)}")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
