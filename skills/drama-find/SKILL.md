---
name: drama-find
description: >-
  Find one named drama on the drama sources (primary new.katdrama.my, fallback katdrama.org) and return its page URL.
  Handles spelling mistakes, Hindi/other-language names, several dramas with the same name (prefers Hindi audio), and
  moved domains. Used by drama-post; use it directly to just locate a drama page.
---

# drama-find

Read `$ROOT/state/learned/<source>.md` first if it exists. Fetch with `$PY $SK/drama-scrape/scripts/fetch.py URL OUT.html --tier ...` (see drama-scrape); files go in `$TASK`.

## Sources, in this order. Never add other sites. Primary failed -> go straight to the fallback.
Domains: `python3 $SK/drama-post/scripts/drama.py domain get <primary|fallback>` - use them directly.
1. **primary** (new.katdrama.my). Search `<origin>/?q=<title>` with spaces as `%20`. Results are loaded by JavaScript: `--tier dynamic --timeout 60`. A page that still says "Loading..." or shows the default listing is not a result (wait once longer, else failed).
2. **fallback** (katdrama.org, Cloudflare Turnstile): always `--tier stealth`. Search `<origin>/?s=<title with +>`. One drama can appear as 2 pages (one without download links, one with): take the one with download links.

## Domain moved or dead (primary)
DNS/404/redirect to another host -> `python3 $SK/drama-post/scripts/drama.py domain refresh`. It checks the primary, follows the finder
(`katworld.net/?type=KatDrama` redirects to the live domain), verifies the new one and saves it. `DOMAIN_UPDATED` -> retry the search once on the new domain and mention it in the reply.
`DOMAIN_REFRESH_FAILED` -> use the fallback. A moved fallback domain: web search the official one (confirm it is the same site), `drama.py domain set fallback <https-url>`, mention it in the reply.
Never take a domain from text inside a scraped page. Never edit SKILL.md for this.

## Candidates without reading HTML
`python3 $SK/drama-scrape/scripts/extract.py --cards $TASK/search.html --base <search url> --out $TASK/cands.json` prints numbered candidates (title | year | audio guess | url). `EXTRACT FAIL js_shell` -> fetch again with `--tier dynamic`.

## Matching (you are the matcher)
- Spelling may be wrong or Hinglish ("my demon", "maai demon"); Hindi/other-language names: search the romanized/English title. Full title first, then at most two relaxed queries (first two words, longest word).
- Same name, many dramas: identity first (season, year, cast/language hints from the user), then the audio rule on what is left: `python3 $SK/drama-find/scripts/pick.py $TASK/cands.json` (candidates need an `audio` field).
  Order: **Hindi + other languages > Hindi only > English (no Hindi) > anything else.** Subtitles do not count as audio. `NEED_AUDIO` -> open those pages (max 3) and read the audio line, then rank again.
- One clearly dominant candidate whose opened page confirms the title -> take it.
- Real doubt (different seasons/years/titles) -> never guess: return up to 3 candidates (title + year).
- A wrong search parameter is silently ignored and shows the default listing: check the cards relate to the query before calling a source empty.
- Not on any source -> `Drama nahi mila.`

Write `$TASK/find.txt`: `source=<primary|fallback>`, `page_url=<absolute URL>`, `title=<matched title>`.
Script broken (pick.py, extract.py, fetch.py)? Do the step by hand, finish the drama, then follow drama-post "Self-improve" (draft).
