---
name: drama-find
description: >-
  Find one named drama on the drama sources (katworld.net, fallback katdrama.org) and return its page
  URL. Handles spelling mistakes, Hindi/other-language names, and several dramas with the same name.
  Used by drama-post; use it directly to just locate a drama page.
---

# drama-find

Read `$DATA/learned/<source>.md` first if it exists. Use the `scrapling` skill/tools for fetching (see drama-scrape for tiers).

## Sources, in this order. Never add other sites. On any failure of #1 go straight to #2 (no retries).
1. **katworld.net** (no Cloudflare). Entry `https://katworld.net/?type=KatDrama`; follow redirects, the resolved host is task-only state. Search `https://<host>/?q=<title>` (spaces `%20`). Results load by JavaScript: use DynamicFetcher with `network_idle`; a page still showing "Loading..." or the default listing is not a result - wait once longer, else treat as failed.
2. **katdrama.org** (Cloudflare Turnstile): plain HTTP/Playwright get 403. Use StealthyFetcher with `solve_cloudflare=True` (~16 s, one internal retry is normal). Search `https://katdrama.org/?s=<title with +>`. The same drama can appear as 2 pages (one without download links, one with, slug often ends `-2/`): open the candidates and take the one that has download links.

## Matching (you are the matcher)
- User spelling may be wrong or Hinglish ("my demon", "maai demon"); Hindi/other-language names: search the romanized/English title. Try the full title, then at most two relaxed queries (first two words, longest word).
- Same name, many dramas: use season, year, language/dubbed, cast hints from the user. One clearly dominant candidate whose opened page confirms the title -> take it.
- Real doubt (different seasons/years/titles) -> do not guess: return up to 3 candidates (title + year) so drama-post can ask the user.
- Wrong search parameter is silently ignored and shows the default listing: check the cards actually relate to the query before calling a source empty.
- Not on any source -> `Drama nahi mila.`

Write `$TASK/find.txt`: `source=<katworld|katdrama>`, `page_url=<absolute URL>`, `title=<matched title>`.
