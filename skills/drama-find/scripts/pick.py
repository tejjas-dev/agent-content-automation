#!/usr/bin/env python3
"""Rank candidate pages of the SAME drama by audio language (zero tokens, stdlib).

  pick.py candidates.json            [{"title","url","audio":"Hindi, Korean","year":"2024"}, ...]  (already filtered to the right drama/season/year)
  pick.py --audio "Hindi + English"  show how one audio string is read

Preference (the owner's rule):
  tier 0  Hindi together with other languages (multi audio WITH Hindi)
  tier 1  Hindi only
  tier 2  no Hindi, English present
  tier 3  any other known audio
  tier 4  audio unknown (open the page and read its audio line, at most 3 pages)
Inside a tier: more languages first, then the original order. Subtitles never count as audio ("Hindi Subs" is not Hindi).
Prints one line per candidate and  BEST <number>  (or NEED_AUDIO <numbers> when the best known tier is unknown)."""
import argparse
import json
import re
import sys

LANGS = {
    "hindi": r"hindi|hin", "english": r"english|eng", "korean": r"korean|kor", "chinese": r"chinese|mandarin|cantonese",
    "japanese": r"japanese|jpn", "thai": r"thai", "turkish": r"turkish", "tamil": r"tamil", "telugu": r"telugu",
    "malayalam": r"malayalam", "kannada": r"kannada", "bengali": r"bengali|bangla", "urdu": r"urdu", "punjabi": r"punjabi",
    "marathi": r"marathi", "gujarati": r"gujarati", "spanish": r"spanish", "indonesian": r"indonesian", "malay": r"malay",
    "vietnamese": r"vietnamese", "arabic": r"arabic", "russian": r"russian", "french": r"french", "german": r"german",
    "portuguese": r"portuguese", "tagalog": r"tagalog|filipino", "persian": r"persian|farsi",
}
SUB = re.compile(r"(?i)\bsub(?:s|title|titles)?\b")
MULTI = re.compile(r"(?i)\b(?:dual|multi|triple)\W*audio\b|\bmulti(?:ple)?\W*(?:language|lang)s?\b")


def read_audio(text):
    """-> (set of languages heard, multi flag). Subtitle-only mentions are dropped first."""
    t = re.sub(r"\([^)]*sub[^)]*\)|\[[^\]]*sub[^\]]*\]", " ", str(text or ""), flags=re.I)
    segs = [s for s in re.split(r"[|;\n]+", t) if not SUB.search(s)]
    t = " ".join(segs)
    found = {n for n, rx in LANGS.items() if re.search(rf"(?i)\b(?:{rx})\b", t)}
    return found, bool(MULTI.search(t)) or len(found) >= 2


def tier(audio):
    langs, multi = read_audio(audio)
    if "hindi" in langs:
        return (0 if multi else 1), langs
    if "english" in langs:
        return 2, langs
    return (3 if langs else 4), langs


def rank(cands):
    rows = []
    for i, c in enumerate(cands, 1):
        t, langs = tier(c.get("audio", ""))
        rows.append((t, -len(langs), i, c, langs))
    return sorted(rows, key=lambda r: r[:3])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?")
    ap.add_argument("--audio")
    a = ap.parse_args(argv)
    if a.audio is not None:
        t, langs = tier(a.audio)
        print(f"tier={t} languages={','.join(sorted(langs)) or '-'}")
        return 0
    if not a.file:
        ap.error("give candidates.json or --audio")
    try:
        with open(a.file, encoding="utf-8") as fh:
            cands = json.load(fh)
        assert isinstance(cands, list) and cands and all(isinstance(c, dict) for c in cands)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR bad candidates file ({type(e).__name__})")
        return 2
    rows = rank(cands)
    for t, _, i, c, langs in rows:
        print(f"{i} tier={t} audio={','.join(sorted(langs)) or '?'} year={c.get('year', '?')} {c.get('title', '')} {c.get('url', '')}")
    best = rows[0]
    if best[0] == 4:
        print("NEED_AUDIO " + " ".join(str(r[2]) for r in rows if r[0] == 4)[:60])
    else:
        unknown = [r[2] for r in rows if r[0] == 4]
        print(f"BEST {best[2]}" + (f" (candidates {unknown} have no audio info; open them only if you doubt)" if unknown else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
