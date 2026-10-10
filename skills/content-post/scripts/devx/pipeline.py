"""One title, end to end. Every outcome is a Result with a stable code; nothing raises out."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

from . import caption, checks, config, dom, extract as ex, fetch, media, shorten, store, telegram
from . import profile as pf
from . import search as sr

REPAIRABLE = ("EXTRACT_FAIL", "NO_LINKS", "POSTER_FAIL")


@dataclass
class Result:
    code: str
    query: str
    title: str = ""
    detail: str = ""
    source: str = ""
    dump: str = ""
    channels: int = 0
    posts: int = 0
    preview: str = ""

    def line(self) -> str:
        c, q, d = self.code, self.query, self.detail
        t = self.title or q
        rep = f" [REPAIR source={self.source} dump={self.dump}]" if c in REPAIRABLE and self.dump else ""
        table = {
            "OK": f"✅ Post bhej diya: {t} → {self.channels} channel(s), {self.posts} post(s).",
            "DRYRUN_OK": f"🧪 Dry-run OK: {t} — {d}",
            "PARTIAL": f"⚠️ {t}: {d}",
            "ALREADY_POSTED": f"⏭️ {t}: pehle hi post ho chuka hai (dobara chahiye to 'force' bolo).",
            "AMBIGUOUS": f"❓ {q}: title ambiguous hai — exact drama confirm karo: {d}",
            "NOT_FOUND": f"❌ {q}: Drama nahi mila.",
            "EXTRACT_FAIL": f"🔧 {q}: Zaroori details extract nahi ho payi: {d}.{rep}",
            "NO_LINKS": f"🔧 {q}: Download links nahi mile, post send nahi kiya.{rep}",
            "POSTER_FAIL": f"🔧 {q}: Poster available nahi hai.{rep}",
            "FETCH_FAIL": f"❌ {q}: Primary source par issue hai, backup bhi fail hua. ({d})",
            "CHALLENGE": f"❌ {q}: Cloudflare challenge solve nahi hua.",
            "SETUP_NEEDED": f"⚙️ Setup adhura hai: {d}. (`content_post.py setup` chalao)",
            "SHORTEN_FAIL": f"❌ {q}: Links short nahi ho paye.",
            "CAPTION_FAIL": f"❌ {q}: Post format nahi ban paya: {d}.",
            "CHECKS_FAIL": f"❌ {q}: Post format nahi ban paya: {d}.",
            "SEND_FAIL": f"❌ {t}: Channel me post send nahi ho paya: {d}.",
            "INTERNAL": f"❌ {q}: Internal error ({d}). Log: ~/.devx-content/logs/runs.log",
        }
        return table.get(c, f"❌ {q}: {c} {d}")


@dataclass
class Outcome:
    kind: str                    # ok|ambiguous|notfound|fetch|extract|nolinks|poster
    data: dict | None = None
    detail: str = ""
    cands: list = field(default_factory=list)
    dump: str = ""
    fetch_reason: str = ""


class Runner:
    def __init__(self, spec, force=False, dry=False, profiles=None):
        self.spec, self.force, self.dry, self.profiles = spec, force, dry, profiles

    # ---- public ------------------------------------------------------------------------
    def run_title(self, query: str) -> Result:
        work = store.make_workdir(query)
        try:
            res = self._run(query, work)
        except Exception as e:  # noqa: BLE001
            store.log({"event": "internal_error", "query": query,
                       "trace": traceback.format_exc()[-1500:]})
            res = Result("INTERNAL", query, detail=config.redact(e)[:80])
        finally:
            store.cleanup(work)
        store.log({"event": "result", "code": res.code, "query": query, "source": res.source})
        return res

    # ---- orchestration -----------------------------------------------------------------
    def _run(self, query: str, work) -> Result:
        profs = self.profiles or pf.effective_profiles(self.spec.name)
        if not profs:
            return Result("SETUP_NEEDED", query, detail="no source profiles found")
        failed: list[tuple[str, Outcome]] = []
        for p in profs:
            o = self._source(p, query)
            if o.kind == "ambiguous":
                return Result("AMBIGUOUS", query, source=p.id,
                              detail=" | ".join(c.title for c in o.cands[:3]))
            if o.kind == "ok":
                return self._publish(query, o.data, work)
            failed.append((p.id, o))
        return self._failure(query, failed)

    def _failure(self, query: str, failed: list[tuple[str, Outcome]]) -> Result:
        code_of = {"extract": "EXTRACT_FAIL", "nolinks": "NO_LINKS", "poster": "POSTER_FAIL"}
        for kind in ("extract", "nolinks", "poster"):
            for sid, o in failed:
                if o.kind == kind:
                    return Result(code_of[kind], query, detail=o.detail, source=sid, dump=o.dump)
        if any(o.kind == "notfound" for _, o in failed):
            return Result("NOT_FOUND", query)
        reasons = {o.fetch_reason for _, o in failed}
        if reasons == {"engine_missing"}:
            return Result("SETUP_NEEDED", query, detail="browser engine (scrapling) missing")
        if "blocked" in reasons:
            return Result("CHALLENGE", query)
        return Result("FETCH_FAIL", query, detail=",".join(sorted(r for r in reasons if r)) or "unknown")

    # ---- one source (with automatic rollback of a bad override) ---------------------------
    def _source(self, p: pf.Prof, query: str) -> Outcome:
        o = self._source_once(p.id, p.data, query)
        if o.kind != "ok" and p.origin == "override" and p.shipped:
            o2 = self._source_once(p.id, p.shipped, query)
            if o2.kind == "ok":
                pf.mark_bad(self.spec.name, p.id)
                store.log({"event": "override_rolled_back", "source": p.id})
                return o2
        return o

    def _fetch_fail(self, r: fetch.Fetched) -> Outcome:
        return Outcome("fetch", detail=r.reason, fetch_reason=r.reason)

    def _source_once(self, sid: str, prof: dict, query: str) -> Outcome:
        spec, F = self.spec, prof["fetch"]
        ladder = fetch.Ladder()
        noise = list(spec.noise) + prof.get("title_noise", [])
        home, last = None, fetch.Fetched(False, reason="no_entry_url")
        for eu in prof["entry_urls"]:
            last = fetch.fetch_page(eu, "http", ladder=ladder)
            if last.ok:
                home = last
                break
        if home is None:
            return self._fetch_fail(last)
        u = urlsplit(home.url)
        origin = f"{u.scheme}://{u.netloc}"
        home_soup = dom.parse(home.html)
        home_urls = {c.url for c in sr.extract_candidates(home_soup, home.url, prof["listing"])}

        mode = prof["search"]["mode"]
        variants = sr.discover_params(home_soup, home.url) if mode == "auto" else [None]
        chosen, searched, last = None, False, fetch.Fetched(False, reason="no_search")
        for q in sr.relaxed_queries(query):
            for pair in variants:
                if pair:
                    a, n = pair
                    url = f"{a}{'&' if '?' in a else '?'}{urlencode({n: q})}"
                else:
                    url = sr.search_url(origin, prof["search"]["path"], q)
                r = fetch.fetch_page(url, F["search_tier"], F["wait_selector"], ladder)
                if not r.ok:
                    last = r
                    continue
                searched = True
                cands = sr.extract_candidates(dom.parse(r.html), r.url, prof["listing"])
                if pair:
                    if sr.is_default_listing(cands, home_urls):
                        continue                  # param silently ignored: try the next one
                    variants = [pair]             # lock in the working param for later queries
                kind, val = sr.pick(query, sr.rank(query, cands, noise))
                if kind == "ambiguous":
                    return Outcome("ambiguous", cands=val)
                if kind == "accept":
                    chosen = val
                break
            if chosen:
                break
        if chosen is None:
            return Outcome("notfound") if searched else self._fetch_fail(last)

        r = fetch.fetch_page(chosen.url, F["detail_tier"], F["wait_selector"], ladder)
        if not r.ok:
            return self._fetch_fail(r)
        data = ex.extract(r.html, r.url, prof, spec)
        tiers = pf.TIERS
        if not data["links"] and tiers.index(r.tier) < len(tiers) - 1:      # escalate only as needed
            r2 = fetch.fetch_page(chosen.url, tiers[tiers.index(r.tier) + 1], F["wait_selector"], ladder)
            if r2.ok:
                d2 = ex.extract(r2.html, r2.url, prof, spec)
                if d2["links"]:
                    r, data = r2, d2

        def fail(kind: str, detail: str) -> Outcome:
            dump = store.dump_failure(spec.name, query, sid, r.html, ex.make_digest(r.html, r.url),
                                      {"kind": kind, "detail": detail, "query": query,
                                       "page_url": r.url, "tier": r.tier})
            return Outcome(kind, detail=detail, dump=dump)

        if not data["title"] or sr.similarity(query, data["title"], noise) < 0.6:
            return fail("extract", "title")
        if not data["links"]:
            return fail("nolinks", "links")
        poster = media.first_valid(data["poster_candidates"])
        if not poster.ok:
            return fail("poster", poster.reason)
        data.update(poster=poster.url, _poster=poster, source=sid)
        return Outcome("ok", data=data)

    # ---- shorten -> caption -> checks -> send -------------------------------------------
    def _publish(self, query: str, data: dict, work) -> Result:
        spec = self.spec
        chs = config.channels(spec.channels_env)
        links = data["links"]
        key = store.key_of(data["title"])
        chash = store.content_hash(spec.name, key, [u for _, u in links])
        mk = lambda code, d="": Result(code, query, data["title"], d, data["source"])  # noqa: E731
        if not self.dry and not self.force and store.already_complete(spec.name, chash, chs):
            return mk("ALREADY_POSTED")
        if self.dry:
            short = [f"https://arolinks.com/dry{i}" for i in range(len(links))]
        else:
            short = shorten.shorten_all([u for _, u in links])
            if any(not s for s in short):
                return mk("SHORTEN_FAIL")
        try:
            caps = caption.build(spec, data, [(lbl, s) for (lbl, _), s in zip(links, short)])
        except caption.CaptionError as e:
            return mk("CAPTION_FAIL", str(e))
        errs = checks.run(spec, data, short, caps, query)
        if errs:
            return mk("CHECKS_FAIL", errs[0])
        if self.dry:
            res = mk("DRYRUN_OK", f"{len(links)} links, {len(caps)} post(s), poster {data['_poster'].ctype}, "
                                  f"source={data['source']}")
            res.preview = caps[0]
            return res

        poster = data["_poster"]
        done = {} if self.force else store.sent_posts(spec.name, chash)
        ok, failures = 0, []
        for ci, ch in enumerate(chs):
            for i, cap in enumerate(caps, 1):
                if i in done.get(ch, set()):
                    ok += 1
                    continue
                good, why = telegram.send_photo(ch, cap, poster.url, poster.data, poster.ctype)
                if good:
                    store.record_sent(spec.name, key, chash, data["title"], ch, i, len(caps))
                    ok += 1
                else:
                    failures.append((ch, why))
                if not (ci == len(chs) - 1 and i == len(caps)):
                    time.sleep(config.number("DEVX_SEND_DELAY", 3))
        total = len(chs) * len(caps)
        if not failures:
            r = mk("OK")
            r.channels, r.posts = len(chs), len(caps)
            return r
        ch, why = failures[0]
        if ok == 0:
            return mk("SEND_FAIL", f"{ch} — {why}")
        return mk("PARTIAL", f"{ok}/{total} post gaye. Fail: {ch} — {why}")
