---
name: drama-format
description: >-
  Build the final Telegram caption text (locked layout, simple direct links, proper spacing, split
  into balanced posts) from data.json and short.json. Used by drama-post after link-short.
---

# drama-format

Input `$TASK/data.json` + `$TASK/short.json`. Output `$TASK/caption1.txt`, `caption2.txt`, ... (plain text: no bold/italic/code, no buttons, no JSON).

## Layout (exact)
```
📺 TITLE : <title>
🎙 AUDIO : <audio>
📺 EPISODES : <episodes>
🎭 GENRE : <genres>

📁 <label> : <short-URL>

📁 <label> : <short-URL>

```
- Header values come only from `data.json`; omit a header line when its value is missing. Never add or reword values.
- Use only entries whose `short` is not null, in the original order, each `label` with its own `short`. A null entry loses its tag. No entries left -> `Links short nahi ho paye.`, stop.
- Replace `[` `]` in labels with `(` `)`. Blank line after the header and after EVERY link.
- Max 12 links per post and <= 950 UTF-16 units per caption (emoji count 2). Fewest posts, then balanced (differ by at most 1, original order). Get the split from the script: `python3 scripts/measure.py plan <N>` (13 -> `7 6`).
- Every post repeats the same header; no "Part" labels; same poster for all.
- Measure each file: `python3 scripts/measure.py "$TASK"/caption*.txt`. Over 950 -> split into one more post and rebuild. If header + one link cannot fit -> `Post format nahi ban paya: header bahut lamba hai.`
