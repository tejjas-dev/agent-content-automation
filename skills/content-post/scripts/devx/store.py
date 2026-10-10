"""Run lock, per-run workspace, posted ledger (dedupe), failure dumps, tiny rotating log."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

try:
    import fcntl
except ImportError:      # non-Linux: run without a lock
    fcntl = None


class Busy(Exception):
    pass


@contextmanager
def run_lock(wait: float):
    if fcntl is None:
        yield
        return
    f = open(config.data_dir() / "run.lock", "w")
    deadline = time.time() + wait
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() > deadline:
                f.close()
                raise Busy()
            time.sleep(2)
    try:
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "x"


def key_of(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def make_workdir(name: str) -> Path:
    p = config.sub("work") / f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{slug(name)}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup(p: Path) -> None:
    shutil.rmtree(p, ignore_errors=True)


def prune_stale(hours: float = 6) -> None:
    cutoff = time.time() - hours * 3600
    for d in config.sub("work").iterdir():
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


# ---- ledger: one JSON line per (channel, post) successfully sent --------------------------
def _ledger() -> Path:
    return config.data_dir() / "posted.jsonl"


def content_hash(type_name: str, key: str, urls: list[str]) -> str:
    return hashlib.sha1("|".join([type_name, key, *sorted(urls)]).encode()).hexdigest()[:16]


def sent_posts(type_name: str, chash: str) -> dict[str, set[int]]:
    """channel -> post indexes already delivered for exactly this content."""
    out: dict[str, set[int]] = {}
    try:
        for line in _ledger().read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("type") == type_name and r.get("hash") == chash:
                out.setdefault(str(r["channel"]), set()).add(int(r["post"]))
    except (OSError, ValueError):
        pass
    return out


def record_sent(type_name: str, key: str, chash: str, title: str, channel: str, post: int, of: int):
    with open(_ledger(), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time()), "type": type_name, "key": key, "hash": chash,
                            "title": title, "channel": channel, "post": post, "of": of},
                           ensure_ascii=False) + "\n")


# ---- failure dumps (what the AI repairs from) ---------------------------------------------
def dump_failure(type_name: str, title: str, source: str, html: str, digest: str, meta: dict) -> str:
    d = config.sub("failures") / f"{int(time.time())}-{type_name}-{slug(title)}-{source}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "page.html").write_text(html[:400_000], encoding="utf-8")
    (d / "digest.txt").write_text(digest, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    for old in sorted(config.sub("failures").iterdir())[:-5]:
        shutil.rmtree(old, ignore_errors=True)
    return str(d)


def log(event: dict) -> None:
    f = config.sub("logs") / "runs.log"
    try:
        if f.exists() and f.stat().st_size > 1_000_000:
            f.rename(f.with_suffix(".log.1"))
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(config.redact(json.dumps({"ts": int(time.time()), **event},
                                              ensure_ascii=False)) + "\n")
    except OSError:
        pass


def already_complete(type_name: str, chash: str, channels: list[str]) -> bool:
    """True when every channel already received every post of exactly this content."""
    posts: dict[str, set[int]] = {}
    of = 0
    try:
        for line in _ledger().read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("type") == type_name and r.get("hash") == chash:
                posts.setdefault(str(r["channel"]), set()).add(int(r["post"]))
                of = max(of, int(r.get("of", 0)))
    except (OSError, ValueError):
        return False
    need = set(range(1, of + 1))
    return bool(channels) and of > 0 and all(need <= posts.get(c, set()) for c in channels)
