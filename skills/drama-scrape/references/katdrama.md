# katdrama (what worked in practice)
- Cloudflare Turnstile: plain HTTP / Playwright get 403 -> `fetch.py ... --tier stealth` (~15 s).
- Search `?s=<title+with+plus>` can return 2 pages for one drama (one without download links, one with; slug often ends `-2/`). Take the one with links.
- Info block: `span.info-label` / `span.info-value` pairs (title, audio, episodes, genres).
- Poster: an `<img>` with a TMDB URL (`image.tmdb.org/t/p/...`).
- Links: anchors to `links.dramashindi.online/archives/<id>`, labels like `480p Single Episode`, `480p Zip File`, `720p 10Bit Single Episode`, `1080p AV1 Zip File`. Old `linksdrama.blogspot.com` pages may 404: ignore.
- If any of this stopped being true, fix your extraction and add 1-2 lines to `$ROOT/state/learned/katdrama.md`.
