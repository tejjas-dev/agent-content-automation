"""Locked caption format + splitting. Plain text only; blank line after header and every link."""
from __future__ import annotations

import math

from . import config


class CaptionError(Exception):
    pass


def utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def header(spec, data: dict) -> str:
    return "\n".join(f"{hdr} : {data[k]}" for k, hdr in spec.fields if data.get(k))


def _trim(label: str, cap: int) -> str:
    label = label.replace("[", "(").replace("]", ")").replace("\n", " ").strip()
    return label if len(label) <= cap else label[: cap - 1].rstrip() + "…"


def _sizes(total: int, n: int) -> list[int]:
    q, r = divmod(total, n)          # 13 -> 7+6, 25 -> 9+8+8
    return [q + 1] * r + [q] * (n - r)


def build(spec, data: dict, links: list[tuple[str, str]]) -> list[str]:
    """links = [(label, short_url)] in page order -> captions (fewest posts, balanced)."""
    head = header(spec, data).replace("[", "(").replace("]", ")")
    for cap in (40, 28, 18):
        items = [(_trim(lbl, cap), url) for lbl, url in links]
        for n in range(max(1, math.ceil(len(items) / config.MAX_LINKS_PER_POST)), len(items) + 1):
            out, i = [], 0
            for size in _sizes(len(items), n):
                chunk = items[i:i + size]
                i += size
                out.append(head + "\n\n" + "".join(f"📁 {lbl} : {url}\n\n" for lbl, url in chunk))
            if all(utf16(c) <= config.CAPTION_LIMIT for c in out):
                return out
    raise CaptionError("header bahut lamba hai")
