---
name: drama-scrape
description: >-
  Extract title, audio, episodes, genre, poster and all download links from a drama page using Scrapling,
  and save them as data.json and links.json. Used by drama-post after drama-find.
---

# drama-scrape

Input `$TASK/find.txt`. Output `$TASK/data.json`, `$TASK/links.json`. Everything you write stays inside `$TASK`.
Known site details: `references/katdrama.md` (and `$ROOT/state/learned/<source>.md`).

## Fetch (Scrapling, via one script)
`$PY $SK/drama-scrape/scripts/fetch.py <URL> $TASK/page.html --tier http|dynamic|stealth [--wait CSS]`
Escalate only as needed: `http` -> `dynamic` (JavaScript) -> `stealth` (Cloudflare Turnstile; katdrama always starts here, ~15 s). Max 4 attempts per source. Then inspect the saved HTML with grep/sed or a few CSS selectors; never print a whole page. Do not write your own fetch scripts.

## Extract
- **title**: JSON-LD / `og:title` / info block. The pure drama name only: drop qualifiers like `(Chinese Drama)`, `(Korean Drama)`, `Hindi Dubbed`, `All Episodes`, quality (720p, WEB-DL), year in brackets and the site name. Keep a season only if the page names one (e.g. `Moon Tales Season 2`).
- **audio, episodes, genre**: info block (katdrama: `span.info-label` / `span.info-value`). Genres comma-separated. Omit anything missing; never invent.
- **poster**: `og:image`, then `twitter:image`, then the main poster `<img>` (often TMDB). Absolute public `https://` URL. Check: `curl -sL -o /dev/null --max-time 20 -w "%{http_code} %{content_type} %{size_download}" "<url>"` -> 200, image/jpeg|png|webp, <= 5 MB. Encode spaces `%20`, parentheses `%28` `%29`. Else try the next candidate.
- **links**: download / mirror / file-host / per-episode links from `href` or `data-*` attributes. Resolve relative URLs, strip tracking params, drop duplicates, keep page order, keep the label shown beside each link (else the site name). Skip dead (404) or non-download links.

`data.json`: `{"title","audio","episodes","genre","poster","page_url","source"}` (omit empty keys).
`links.json`: `[{"label": "...", "url": "https://..."}, ...]` - label on one line, label and URL from the SAME element.

## Failure (this source failed -> drama-post retries drama-find on the next source)
No title -> `Zaroori details extract nahi ho payi: title.` | no usable poster -> `Poster available nahi hai.` | no links -> `Download links nahi mile, post send nahi kiya.` If a source's structure changed, note it in `$ROOT/state/learned/<source>.md`.
