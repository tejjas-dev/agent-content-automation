---
name: drama-scrape
description: >-
  Extract title, audio, episodes, genre, poster and all download links from a drama page using Scrapling
  and a compact extractor script, and save them as data.json and links.json. Used by drama-post after drama-find.
---

# drama-scrape

Input `$TASK/find.txt`. Output `$TASK/data.json`, `$TASK/links.json`. Everything you write stays inside `$TASK`.
Known site details: `references/katdrama.md` (and `$ROOT/state/learned/<source>.md`). Error codes: `drama-post/references/recovery.md`.

## 1. Fetch (one script, it retries and climbs by itself)
`$PY $SK/drama-scrape/scripts/fetch.py <URL> $TASK/page.html --tier auto`
`auto` = http -> dynamic (JavaScript) -> stealth (Cloudflare Turnstile, ~15 s), exponential backoff on timeouts/429/5xx, max 4 attempts. Known source: primary -> `--tier dynamic`, fallback -> `--tier stealth` directly. Never write your own fetch scripts. Never print a whole page.

## 2. Extract (script first, AI only for the gaps)
`python3 $SK/drama-scrape/scripts/extract.py $TASK/page.html --base <page url> --write $TASK --check-poster`
- `EXTRACT OK ...` -> `data.json` + `links.json` written; glance at the printed line (is it the right drama, season?) and go on.
- `EXTRACT PARTIAL missing=...` -> complete only the missing fields yourself from the saved page (grep/sed a few lines or a few CSS selectors) and write/extend the two files.
- `EXTRACT FAIL js_shell` -> fetch again with `--tier dynamic`.
Rules to follow when you fill gaps by hand:
- **title**: the pure drama name. Drop `(Chinese Drama)`, `Hindi Dubbed`, `All Episodes`, quality (720p, WEB-DL), year in brackets, site name. Keep a season only if the page names one (`Moon Tales Season 2`).
- **audio, episodes, genre**: from the info block. Genres comma-separated. Omit anything missing; never invent.
- **poster**: `og:image`, then `twitter:image`, then the main poster `<img>` (often TMDB). Absolute public `https://` URL, 200, image/jpeg|png|webp, <= 5 MB. Encode spaces `%20`, parentheses `%28` `%29`.
- **links**: download / mirror / file-host / per-episode links from `href` or `data-*`. Absolute URLs, no tracking params, no duplicates, page order, the label shown beside each link (else the host). Skip dead (404) or non-download links.

`data.json`: `{"title","audio","episodes","genre","poster","page_url","source"}` (omit empty keys).
`links.json`: `[{"label": "...", "url": "https://..."}, ...]` - label on one line, label and URL from the SAME element.

## Failure (this source failed -> drama-post retries drama-find on the next source)
No title -> `Zaroori details extract nahi ho payi: title.` | no usable poster -> `Poster available nahi hai.` | no links -> `Download links nahi mile, post send nahi kiya.`
Site structure changed (extract.py keeps missing the same field)? Finish by hand, then follow drama-post "Self-improve": the draft may change `references/hints.json` (extra link hosts / hosts to skip) or `scripts/extract.py`.
