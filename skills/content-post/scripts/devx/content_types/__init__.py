"""Content types. To add one (movie, anime...): drop <name>.py here that defines SPEC,
add sources/<name>/*.json, and set <NAME>_POST_CHANNEL_IDS. Nothing else to touch."""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass


@dataclass(frozen=True)
class TypeSpec:
    name: str
    channels_env: str
    fields: tuple          # (key, header label) in caption order; first must be "title"
    labels: dict           # key -> regex of label words used in "Label: value" lines
    noise: tuple = ()      # words stripped from scraped titles


def get(name: str):
    try:
        mod = importlib.import_module(f"devx.content_types.{name}")
    except ModuleNotFoundError:
        return None
    return getattr(mod, "SPEC", None)


def available() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))
