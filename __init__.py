"""Hermes plugin entry. The plugin only makes the bundled skills visible to Hermes; the skills themselves
are plain SKILL.md folders (+ stdlib scripts), so the same repo works in any agent that reads skills."""
import os
import shutil
from pathlib import Path

SKILLS = Path(__file__).parent / "skills"


def _names():
    return [d.name for d in sorted(SKILLS.iterdir()) if (d / "SKILL.md").exists()]


def _copy_fallback(names):
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    for n in names:
        shutil.copytree(SKILLS / n, home / "skills" / n, dirs_exist_ok=True)


def register(ctx):
    names = _names()
    reg = getattr(ctx, "register_skill", None)
    try:
        if reg is None:
            raise AttributeError("register_skill unavailable")
        for n in names:
            reg(n, SKILLS / n / "SKILL.md")
    except Exception:  # noqa: BLE001  older/newer Hermes: fall back to copying into the skills folder
        _copy_fallback(names)
