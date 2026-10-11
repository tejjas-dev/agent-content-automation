---
name: drama-verify
description: >-
  Last check before sending a post - run the deterministic checker (title, poster, caption layout,
  every label attached to its own link, only short links) and confirm the page really is the requested
  drama. Used by drama-post before telegram-send.
---

# drama-verify

```
python3 scripts/check.py --task "$TASK" --title "<title as the user asked>"
```
Prints `PASS`, or `FAIL` with one problem per line. It checks: title matches the request, poster is https, header equals data.json, caption limits, only arolinks URLs, **each label sits next to its own short link**, blank lines, balanced posts, every short link used exactly once.

- `FAIL`: fix only the listed problems (rebuild the affected caption), run it ONE more time. Still FAIL -> `Post format nahi ban paya: <first problem>.` and do not send.
- `PASS`: also confirm by eye that `data.json` is the drama (and season/year) the user asked for, taken from this run's live page. Doubt -> do not send.
- Entries that failed to shorten were already dropped from the captions; that is fine. A post with zero links is never sent.
- No extra checks, no loops: one run, at most one retry.
