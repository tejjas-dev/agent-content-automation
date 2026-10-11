---
name: drama-format
description: >-
  Build the final Telegram caption text (locked layout, simple direct links, proper spacing, balanced
  split into posts) from data.json and short.json with a script. Normally run by publish.py; open this
  skill only when publish.py reports a build problem.
---

# drama-format

`python3 $SK/drama-format/scripts/build.py --task "$TASK"` writes `caption1.txt`, `caption2.txt`, ... (publish.py runs it for you).
It reads `data.json` + `short.json` and applies the locked layout (plain text, no bold/italic/code, no buttons):
```
📺 TITLE : <title>
🎙 AUDIO : <audio>
📺 EPISODES : <episodes>
🎭 GENRE : <genres>

📁 <label> : <short-URL>

📁 <label> : <short-URL>

```
- Header values only from `data.json` (missing value = line omitted). Entries with `short = null` lose their tag; none left -> `Links short nahi ho paye.`
- `[` `]` become `(` `)`. Blank line after the header and after every link. Max 12 links and <= 950 UTF-16 units per post, fewest posts, balanced (13 -> 7+6). Long labels are trimmed only when needed.
- Exit 3 = no links, 4 = header too long (`Post format nahi ban paya: header bahut lamba hai.`).
- Helpers: `scripts/measure.py plan <N>` (split sizes), `scripts/measure.py FILE...` (UTF-16 units).
- If build.py itself breaks, fix it minimally (stdlib only), tell the user, suggest committing.
