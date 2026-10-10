# Adding a new content type (movie, anime, ...)

The engine is generic; a type is three small things.

1. `skills/content-post/scripts/devx/content_types/movie.py`
   Copy `drama.py`, change `name`, `channels_env` (e.g. `MOVIE_POST_CHANNEL_IDS`), `fields`
   (caption header lines, `title` first), `labels` (regex of label words per field) and `noise` words.
2. `skills/content-post/sources/movie/<site>.json`
   One profile per site (copy `sources/_template.json`, set `"type": "movie"`).
   Don't know the selectors? Leave them out and let the AI repair flow (`references/repair.md`) fill them.
3. `SKILL.md`: add `MOVIE_POST_CHANNEL_IDS` to `required_environment_variables`, and one line
   "movies: `content_post.py run movie "Title"`".

No other file changes. Bump `VERSION`, push, `hermes skills update`.
Run `python3 -m unittest discover -s skills/content-post/scripts/tests` before pushing.

## Adding a source to an existing type
Drop a new JSON in `sources/<type>/` (or let the AI create it as a local override, then copy it from
`~/.devx-content/overrides/<type>/` into the repo once it has proven itself).

## Where things live
| What | Where | Survives `skills update`? |
|---|---|---|
| Code, shipped profiles | skill folder (from GitHub) | replaced by the new version |
| Venv, overrides, failure dumps, `posted.jsonl`, logs | `~/.devx-content/` (`DEVX_DATA_DIR`) | yes |
| Secrets | profile `.env` / env vars, never in the repo | yes |
