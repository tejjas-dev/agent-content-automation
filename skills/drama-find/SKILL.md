---
name: drama-find
description: >-
  Find one named drama on the drama sources (katworld, fallback katdrama) and return its page URL.
  Handles spelling mistakes, Hindi/other-language names, and several dramas with the same name. Used by
  drama-post; use it directly to just locate a drama page.
---

# drama-find

Read `$ROOT/state/learned/<source>.md` first if it exists. Fetch with `$PY $SK/drama-scrape/scripts/fetch.py URL OUT.html --tier ...` (see drama-scrape); files go in `$TASK`.

## Sources, in this order. Never add other sites. If #1 fails, go straight to #2 (no retries).
Domain: `python3 $SK/drama-post/scripts/drama.py domain get <katworld|katdrama>` - use it directly, no redirect hunting.
1. **katworld** (no Cloudflare). Search `<domain-origin>/?q=<title>` (spaces `%20`). Results load by JavaScript: `--tier dynamic`; a page still showing "Loading..." or the default listing is not a result (wait once longer, else failed).
2. **katdrama** (Cloudflare Turnstile): always `--tier stealth`. Search `<domain-origin>/?s=<title with +>`. One drama can appear as 2 pages (one without download links, one with): open the candidates and take the one with download links.

## Domain moved or dead
If the domain gives DNS/not-found errors or lands on a different host: find the new official domain (web search; confirm it is the same site), then
`python3 $SK/drama-post/scripts/drama.py domain set <source> <https-url>` and
`python3 $SK/drama-post/scripts/drama.py notify "<source> domain badla: <old> -> <new>"` (if it says NOTIFY_SKIPPED, put one line about it in your reply). Never edit SKILL.md for this.

## Matching (you are the matcher)
- Spelling may be wrong or Hinglish ("my demon", "maai demon"); Hindi/other-language names: search the romanized/English title. Full title first, then at most two relaxed queries (first two words, longest word).
- Same name, many dramas: use season, year, language/dubbed, cast hints from the user. One clearly dominant candidate whose opened page confirms the title -> take it.
- Real doubt (different seasons/years/titles) -> never guess: return up to 3 candidates (title + year).
- A wrong search parameter is silently ignored and shows the default listing: check the cards relate to the query before calling a source empty.
- Not on any source -> `Drama nahi mila.`

Write `$TASK/find.txt`: `source=<katworld|katdrama>`, `page_url=<absolute URL>`, `title=<matched title>`.
