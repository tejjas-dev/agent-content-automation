# Repairing a source (only when a line carried `[REPAIR source=<id> dump=<dir>]`)

Sites change layout. You fix the *profile* (a small JSON describing the site), never the code.
Do this at most **twice per title**. If it still fails, tell the user in one line and stop.

## 1. Look at what the script saved
`<dump>/digest.txt` is a compact view of the page: meta tags, headings, "Label: value" lines,
images and anchors, each with a CSS-ish path (`div.entry-content < p < a.btn`). `meta.json` says what failed:
- `title`  -> title selector/meta wrong or page opened is not the drama
- `links`  -> download anchors not recognised (selector/text filter/container)
- poster reason -> image candidates wrong (try other `detail.poster.css`)
Only open `page.html` if the digest is not enough (it is large).

## 2. Write a candidate profile
Start from the current one: `python3 ${HERMES_SKILL_DIR}/scripts/content_post.py profiles drama`
shows ids/origins; the template with every allowed key is `${HERMES_SKILL_DIR}/sources/_template.json`.
Save your JSON anywhere (e.g. `/tmp/cand.json`). Keep it minimal: only keys you need to change are fine;
everything else falls back to defaults. Allowed keys, nothing else:

- `entry_urls` (https list), `order` (int, lower = tried first)
- `fetch.search_tier` / `fetch.detail_tier`: `http` | `dynamic` (JS pages) | `stealth` (Cloudflare); `fetch.wait_selector`
- `search.mode`: `template` (+ `search.path` containing `{query}`, e.g. `/?q={query}`) or `auto` (reads the site's search form)
- `listing.card` / `listing.link` / `listing.title`: CSS for result cards on the search page
- `detail.title.meta|css`, `detail.poster.meta|css`
- `detail.fields.<audio|episodes|genre>.css` and/or `.label` (regex of the label word)
- `detail.links.container|css|text_include|text_exclude|host_exclude` (`text_include: ""` = take every anchor in the container)
- `title_noise`: extra words to strip from titles (e.g. the site name)

Domain moved or site dead: web-search for the new domain and change `entry_urls`.
New source: same flow with a new lowercase `id` (e.g. `site3`); it is added as an extra fallback source.

## 3. Test and save in one step
```
python3 ${HERMES_SKILL_DIR}/scripts/content_post.py profile-apply drama <source-id> --file /tmp/cand.json --title "<the title>"
```
- `APPLIED` -> the profile passed a real dry-run (search, extract, poster, links) and is saved. Rerun the title once.
- `REJECTED: <reason>` -> fix exactly that reason and retry (counts toward the 2 tries).

## Never
Edit files inside the skill folder, change scripts, or send/scrape manually. A saved profile that later fails
is rolled back to the shipped one automatically.
