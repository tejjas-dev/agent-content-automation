#!/usr/bin/env python3
"""Draft updates. The agent may propose changes (script fixes, new hints, SKILL.md/reference text); they run as a DRAFT overlay
so the pipeline keeps working without the owner, but the main skill files are changed only after the owner approves.

  proposal.py new "<title>" --why "<why>" [--note "<one instruction for the agent while the draft is active>"]   -> prints the id
  proposal.py add ID <skill>/<path>      copy the current file into the draft (new files allowed); edit the PRINTED path, never the main file
  proposal.py check ID                   syntax + offline selftest with the draft applied; pass -> READY (active in the overlay), fail -> FAILED
  proposal.py list | show ID | reject ID
  proposal.py approve ID --user-approved apply to the main skills, tests again, write state/patches/<id>.patch, clean the draft
                                         (ONLY after the owner said approve; never on your own)

How a READY draft is used: `drama.py env` prints SK = a view of the skills (symlinks to main files, draft files copied over);
publish.py uses the same view for its sub-scripts. NOTES=<file> lists one-line instructions of READY drafts (read it once per run).
Changing a draft file after `check` deactivates it until it is checked again. A draft is STALE (inactive, cannot be approved) when a main file
it changes was updated after the draft started (plugin update): reject it and make a new one. Max 5 open drafts.
Data: DATA/drama/state/draft/<id>/{meta.json,files/..}, state/view/<key>/, state/backup/<id>/, state/patches/<id>.patch."""
import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILLS = Path(__file__).absolute().parents[2]
ALLOWED = {".py", ".sh", ".md", ".json"}
MAX_OPEN = 5
ID_RE = re.compile(r"^d\d{8}-\d{6}-[a-z0-9-]{1,31}$")


class Err(Exception):
    pass


def data_dir():
    e = os.environ.get("DEVX_DATA_DIR")
    if e:
        return Path(e)
    w = Path("/workspace")
    return w if w.is_dir() and os.access(w, os.W_OK) else Path.home() / ".devx-content"


def state():
    p = data_dir() / "drama" / "state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def droot():
    p = state() / "draft"
    p.mkdir(exist_ok=True)
    return p


def main_of(sk):
    sk = Path(sk)
    m = sk / ".main"
    return Path(m.read_text(encoding="utf-8").strip()) if m.is_file() else sk


def skills():
    return main_of(os.environ.get("DEVX_SKILLS_DIR") or SKILLS)


def clean(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def atomic(p, text):
    t = p.with_name(p.name + ".tmp")
    t.write_text(text, encoding="utf-8")
    os.replace(t, p)


def load(i):
    try:
        m = json.loads((droot() / i / "meta.json").read_text(encoding="utf-8"))
        return m if isinstance(m, dict) else None
    except (OSError, ValueError):
        return None


def save(m):
    atomic(droot() / m["id"] / "meta.json", json.dumps(m, indent=1, ensure_ascii=False))


def all_drafts():
    return [m for p in sorted(droot().iterdir()) if p.is_dir() for m in [load(p.name)] if m]


def need(i):
    if not ID_RE.fullmatch(i or ""):
        raise Err(f"bad draft id {i!r}")
    m = load(i)
    if not m:
        raise Err(f"no such draft {i}")
    return m


def files_of(i):
    base = droot() / i / "files"
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()) if base.exists() else []


def files_hash(i):
    h = hashlib.sha1()
    for rel in files_of(i):
        h.update(rel.encode())
        h.update((droot() / i / "files" / rel).read_bytes())
    return h.hexdigest()


def safe_rel(rel, main):
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or not 2 <= len(p.parts) <= 4 or any(x.startswith(".") for x in p.parts):
        raise Err("path must be <skill>/<file> inside a skill folder")
    if not (main / p.parts[0]).is_dir():
        raise Err(f"unknown skill {p.parts[0]}")
    if p.suffix not in ALLOWED:
        raise Err(f"only {', '.join(sorted(ALLOWED))} files")
    return p.as_posix()


def main_hash(rel):
    """sha1 of the main file, or "-" when it does not exist (a file the draft adds)."""
    try:
        return hashlib.sha1((skills() / rel).read_bytes()).hexdigest()
    except OSError:
        return "-"


def stale(m):
    """True when a main file this draft changes is no longer the one the draft started from (e.g. the plugin was updated):
    using or approving it would silently undo the newer main version."""
    bases = m.get("bases") or {}
    return any(rel in bases and bases[rel] != main_hash(rel) for rel in files_of(m["id"]))


def ready_ids():
    """READY drafts whose files are exactly what was tested and whose base files are unchanged."""
    return [m["id"] for m in all_drafts()
            if m.get("status") == "ready" and (m.get("tests") or {}).get("passed") and (m["tests"].get("hash") == files_hash(m["id"]))
            and not stale(m)]


# ---- overlay view ---------------------------------------------------------------------------
def build_view(main, ids):
    h = hashlib.sha1()
    for i in ids:
        h.update(i.encode())
        h.update(files_hash(i).encode())
    key = h.hexdigest()[:10]
    v = state() / "view" / key
    if v.exists():
        try:
            os.utime(v, None)                         # mark as in use: cleanup removes views by age
        except OSError:
            pass
        return v
    v.parent.mkdir(parents=True, exist_ok=True)
    tmp = v.with_name(f"{key}.{os.getpid()}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    for skill in sorted(p for p in main.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for root, dirs, fs in os.walk(skill):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            rel = Path(root).relative_to(main)
            (tmp / rel).mkdir(parents=True, exist_ok=True)
            for f in fs:
                if not f.endswith(".pyc"):
                    os.symlink(Path(root) / f, tmp / rel / f)
    for i in ids:
        for rel in files_of(i):
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            shutil.copy2(droot() / i / "files" / rel, dst)
    (tmp / ".main").write_text(str(main), encoding="utf-8")
    try:
        os.replace(tmp, v)
    except OSError:                                   # another process built the same view first
        shutil.rmtree(tmp, ignore_errors=True)
    return v


def effective(sk):
    """Skills folder to run: the draft view when READY drafts exist, else the main folder."""
    main = main_of(sk)
    ids = ready_ids()
    return str(build_view(main, ids)) if ids else str(main)


def refresh(sk):
    """-> (effective skills path, extra env lines for `drama.py env`). Demotes READY drafts changed after their test."""
    main = main_of(sk)
    ok = set(ready_ids())
    ds = all_drafts()
    for m in ds:
        if m.get("status") == "ready" and m["id"] not in ok:
            m["status"], m["tests"] = ("stale" if stale(m) else "draft"), None
            save(m)
    notes = droot() / "active.md"
    lines = [f"- [{m['id']}] {m['title']}: {m['note']}" for m in ds if m["id"] in ok and m.get("note")]
    if lines:
        atomic(notes, "Draft updates active now (owner has not approved them yet; follow them):\n" + "\n".join(lines) + "\n")
    else:
        notes.unlink(missing_ok=True)
    extra = {}
    if ds:
        extra["DRAFTS"] = f"{len(ok)} ready, {len(ds) - len(ok)} other - awaiting owner approval (proposal.py list)"
    if lines:
        extra["NOTES"] = str(notes)
    return (str(build_view(main, sorted(ok))) if ok else str(main)), extra


def summary():
    c = {}
    for m in all_drafts():
        c[m["status"]] = c.get(m["status"], 0) + 1
    return ", ".join(f"{n} {s}" for s, n in sorted(c.items()))


# ---- tests / diff ---------------------------------------------------------------------------
def run_selftest(sk):
    sc = Path(sk) / "drama-post" / "scripts" / "selftest.py"
    if not sc.is_file():
        return False, "selftest.py missing"
    try:
        p = subprocess.run([sys.executable, str(sc)], capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        return False, "selftest timeout"
    return p.returncode == 0, " | ".join((p.stdout + p.stderr).strip().splitlines()[-3:])[:300]


def _lines(text):
    ls = text.splitlines(True)
    if ls and not ls[-1].endswith("\n"):
        ls[-1] += "\n\\ No newline at end of file\n"
    return ls


def diff_of(i, main):
    out = []
    for rel in files_of(i):
        new = (droot() / i / "files" / rel).read_text(encoding="utf-8", errors="replace")
        src = main / rel
        old = src.read_text(encoding="utf-8", errors="replace") if src.is_file() else None
        out += difflib.unified_diff(_lines(old or ""), _lines(new), fromfile=f"a/skills/{rel}" if old is not None else "/dev/null",
                                    tofile=f"b/skills/{rel}")
    return "".join(out)


# ---- commands -------------------------------------------------------------------------------
def cmd_new(a):
    ds = all_drafts()
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())  # noqa: E731
    for m in ds:
        if norm(m["title"]) == norm(a.title):
            print(f"DRAFT_EXISTS {m['id']}")
            return 0
    if len(ds) >= MAX_OPEN:
        print(f"DRAFT_LIMIT {len(ds)} drafts are open; tell the owner to approve or reject some first")
        return 2
    slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")[:30].strip("-") or "x"
    i, n = f"d{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{slug}", 1
    while (droot() / i).exists():                       # same second + same slug: never share a folder
        n += 1
        i = f"d{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{slug[:27].strip('-') or 'x'}-{n}"
    (droot() / i / "files").mkdir(parents=True, exist_ok=True)
    save({"id": i, "title": clean(a.title)[:80], "why": clean(a.why)[:400], "note": clean(a.note or "")[:300],
          "created": int(time.time()), "status": "draft", "tests": None})
    print(i)
    return 0


def cmd_add(a):
    m = need(a.id)
    main = skills()
    rel = safe_rel(a.path, main)
    dst = droot() / m["id"] / "files" / rel
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        m.setdefault("bases", {})[rel] = main_hash(rel)
        src = main / rel
        if src.is_file():
            shutil.copy2(src, dst)
        else:
            dst.write_text("", encoding="utf-8")
    m["status"], m["tests"] = "draft", None
    save(m)
    refresh(skills())
    print(dst)
    return 0


def cmd_check(a):
    m = need(a.id)
    files = files_of(m["id"])
    if not files:
        raise Err("draft has no files (use add first)")
    base = droot() / m["id"] / "files"

    def verdict(ok, summary):
        m["tests"] = {"passed": ok, "ts": int(time.time()), "summary": summary, "hash": files_hash(m["id"])}
        m["status"] = "ready" if ok else "failed"
        save(m)
        refresh(skills())
        print(f"{'READY' if ok else 'FAILED'} {m['id']} - {summary}")
        return 0 if ok else 1

    if stale(m):
        return verdict(False, "STALE: a main file changed after this draft started (plugin updated?); reject it and make a new draft from the current files")
    for rel in files:
        text = (base / rel).read_text(encoding="utf-8", errors="replace")
        try:
            if rel.endswith(".py"):
                compile(text, rel, "exec")
            elif rel.endswith(".json"):
                json.loads(text)
        except (SyntaxError, ValueError) as e:
            return verdict(False, f"{rel}: {type(e).__name__} {str(e)[:80]}")
    others = [i for i in ready_ids() if i != m["id"]]
    for o in others:
        both = set(files_of(o)) & set(files)
        if both:
            return verdict(False, f"{sorted(both)[0]} is also changed by READY draft {o}; owner must approve/reject that first")
    ok, summary = run_selftest(build_view(skills(), sorted(others + [m["id"]])))
    return verdict(ok, summary)


def cmd_list(a):
    ds = all_drafts()
    if not ds:
        print("NO_DRAFTS")
    for m in ds:
        print(f"{m['id']} {m['status']} {m['title']}")
    return 0


def cmd_show(a):
    m = need(a.id)
    t = m.get("tests") or {}
    print(f"id: {m['id']}\nstatus: {m['status']}" + (f" (tests {'passed' if t.get('passed') else 'failed'}: {t.get('summary', '')})" if t else ""))
    print(f"title: {m['title']}\nwhy: {m['why']}" + (f"\nnote: {m['note']}" if m.get("note") else ""))
    print("files: " + (", ".join(files_of(m["id"])) or "-"))
    d = diff_of(m["id"], skills()).splitlines()
    print(f"--- diff ({len(d)} lines{', first 120 shown' if len(d) > 120 else ''})")
    print("\n".join(d[:120]))
    return 0


def cmd_reject(a):
    m = need(a.id)
    shutil.rmtree(droot() / m["id"], ignore_errors=True)
    refresh(skills())
    print(f"REJECTED {m['id']} (draft cleaned, main untouched)")
    return 0


def cmd_approve(a):
    if not a.user_approved:
        raise Err("approve needs the owner's OK: rerun with --user-approved only after the owner said approve")
    m = need(a.id)
    if cmd_check(argparse.Namespace(id=a.id)) != 0:
        print("APPROVE_REFUSED tests do not pass; main untouched")
        return 1
    m = need(a.id)                                    # reload: check just wrote the test result
    main, base, bak = skills(), droot() / m["id"] / "files", state() / "backup" / m["id"]
    files, patch, done = files_of(m["id"]), diff_of(m["id"], skills()), []
    ok, summary = True, ""
    try:
        for rel in files:
            dst = main / rel
            if dst.is_file():
                (bak / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, bak / rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".new")
            shutil.copy2(base / rel, tmp)
            os.replace(tmp, dst)
            done.append(rel)
        ok, summary = run_selftest(main)
    except OSError as e:
        ok, summary = False, f"{type(e).__name__}: {str(e)[:80]}"
        for rel in files:
            (main / rel).with_name(Path(rel).name + ".new").unlink(missing_ok=True)
    if not ok:
        for rel in done:
            if (bak / rel).is_file():
                shutil.copy2(bak / rel, main / rel)
            else:
                (main / rel).unlink(missing_ok=True)
        m["status"] = "failed"
        save(m)
        print(f"APPROVE_FAILED rolled back, main unchanged: {summary}")
        return 1
    pdir = state() / "patches"
    pdir.mkdir(exist_ok=True)
    pf = pdir / f"{m['id']}.patch"
    atomic(pf, patch)
    shutil.rmtree(droot() / m["id"], ignore_errors=True)
    refresh(skills())
    print(f"APPROVED {m['id']} files={len(files)} patch={pf} (git apply it in the repo to keep it in version control)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    n = sp.add_parser("new")
    n.add_argument("title")
    n.add_argument("--why", required=True)
    n.add_argument("--note")
    ad = sp.add_parser("add")
    ad.add_argument("id")
    ad.add_argument("path")
    for name in ("check", "show", "reject"):
        sp.add_parser(name).add_argument("id")
    sp.add_parser("list")
    ap_ = sp.add_parser("approve")
    ap_.add_argument("id")
    ap_.add_argument("--user-approved", action="store_true")
    a = ap.parse_args(argv)
    f = {"new": cmd_new, "add": cmd_add, "check": cmd_check, "list": cmd_list, "show": cmd_show,
         "reject": cmd_reject, "approve": cmd_approve}[a.cmd]
    try:
        return f(a) or 0
    except Err as e:
        print(f"ERROR {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
