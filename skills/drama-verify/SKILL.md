---
name: drama-verify
description: >-
  Last check before sending a post: deterministic checker (title, poster, caption layout, every label
  attached to its own link, only short links) plus a sanity look that the page really is the requested
  drama. Normally run by publish.py; open this skill when publish.py reports verify problems.
---

# drama-verify

`python3 $SK/drama-verify/scripts/check.py --task "$TASK" --title "<title as the user asked>"` -> `PASS`, or `FAIL` with one problem per line.
It checks: title matches the request, poster is https, header equals data.json, caption limits, only arolinks URLs, **each label sits next to its own short link**, blank lines, balanced posts, every short link used exactly once.

- `FAIL`: fix only the listed problems (rerun build.py or correct the data), then run `publish.py` ONE more time. Still failing -> `Post format nahi ban paya: <first problem>.` and do not send.
- Also confirm by eye that `data.json` is the drama (and season/year) the user asked for, from this run's live page. Doubt -> do not send.
- No extra checks or loops: one run, at most one retry.
