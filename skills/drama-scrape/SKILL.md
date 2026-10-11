---
name: drama-scrape
description: >-
  Extract title, audio, episodes, genre, poster and all download links from a drama page using
  Scrapling, and save them as data.json and links.json. Used by drama-post after drama-find.
---

# drama-scrape

Input: `$TASK/find.txt`. Output: `$TASK/data.json`, `$TASK/links.json`.

## Fetching (Scrapling)
Python with Scrapling: `$DATA/venv/bin/python` if it exists (created by `drama-post/scripts/setup.sh`), else `python3`.
Escalate only as needed: `Fetcher` -> `DynamicFetcher` (`network_idle`) -> `StealthyFetcher(solve_cloudflare=True)` (only when a Cloudflare/bot check appears). Timeouts: Fetcher in seconds, Dynamic/Stealthy in milliseconds. Max 4 attempts per source. Save pages as `.html` in `$TASK` and inspect with grep/sed or a few CSS selectors; never print a whole page.

## What to extract
- **title**: JSON-LD / `og:title` first, then the info block. Strip SEO noise (Download, 720p, WEB-DL, Hindi Dubbed, site name).
- **audio, episodes, genre**: info block (katdrama.org uses `span.info-label` / `span.info-value` pairs). Genres comma-separated. Omit anything missing; never invent.
- **poster**: `og:image`, then `twitter:image`, then the main poster `<img>` (often a TMDB URL). Must be an absolute public `https://` URL. Check: `curl -sL -o /dev/null --max-time 20 -w "%{http_code} %{content_type} %{size_download}" "<url>"` -> 200, image/jpeg|png|webp, <= 5 MB. Encode spaces as `%20`, parentheses as `%28` `%29`. Else try the next candidate.
- **links**: download / mirror / file-host / per-episode links from `href` or `data-*` URL attributes (katdrama.org: `links.dramashindi.online/archives/<id>` with labels like "480p Single Episode", "720p 10Bit Zip File"). Resolve relative URLs, strip tracking params (`utm_*`, `fbclid`), drop duplicates, keep page order, keep the label shown beside each link (else the site name). Skip links that are obviously dead (404) or not downloads (social, nav).

## Files
`data.json`: `{"title","audio","episodes","genre","poster","page_url","source"}` (omit empty keys).
`links.json`: `[{"label": "...", "url": "https://..."}, ...]` - one entry per link, label on a single line, label and URL taken from the SAME element.

## Failure (this source failed -> tell drama-post, which retries drama-find on the next source)
No title -> `Zaroori details extract nahi ho payi: title.` | no usable poster -> `Poster available nahi hai.` | no links -> `Download links nahi mile, post send nahi kiya.` All sources failed -> that reply. If a source's structure changed, add what you learned to `$DATA/learned/<source>.md`.
