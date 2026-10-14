# Source notes (what worked in practice; learned facts go to `$ROOT/state/learned/<source>.md`)
- **primary** `new.katdrama.my`: search `/?q=<title with %20>`; the HTML is a shell ("Search Results for ..." + "Loading...") and the cards are filled by JavaScript -> `fetch.py --tier dynamic`. `katworld.net/?type=KatDrama` redirects (302) to the live primary domain: that is how a moved domain is found (`drama.py domain refresh`).
- **fallback** `katdrama.org`: Cloudflare Turnstile, plain HTTP / Playwright get 403 -> `--tier stealth` (~15 s). Search `/?s=<title+with+plus>`; it can return 2 pages for one drama (one without download links, one with; slug often ends `-2/`). Take the one with links.
- Info block: `span.info-label` / `span.info-value` pairs (title, audio, episodes, genres). `extract.py` reads these generically (also dt/dd, th/td, "Label: value").
- Poster: an `<img>` with a TMDB URL (`image.tmdb.org/t/p/...`) or `og:image`.
- Links: anchors to `links.dramashindi.online/archives/<id>`, labels like `480p Single Episode`, `480p Zip File`, `720p 10Bit Single Episode`, `1080p AV1 Zip File`. Old `linksdrama.blogspot.com` pages may 404: ignore.
- Not yet seen on a live page of the primary: the exact card/page markup. If extract.py misses fields there, fix by hand and draft a change (`references/hints.json` or `scripts/extract.py`).
