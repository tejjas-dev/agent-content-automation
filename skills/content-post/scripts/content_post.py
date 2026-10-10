#!/usr/bin/env python3
"""Entry point. Self-heals: re-execs into the data-dir venv, auto-installs light deps once."""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _bootstrap() -> None:
    if (len(sys.argv) > 1 and sys.argv[1] in ("setup", "version")) or os.environ.get("DEVX_REEXEC"):
        return
    from devx import config
    vpy = config.venv_python()
    in_venv = Path(sys.prefix).resolve() == (config.data_dir() / "venv").resolve()
    if vpy.exists() and not in_venv:
        os.environ["DEVX_REEXEC"] = "1"
        os.execv(str(vpy), [str(vpy), __file__, *sys.argv[1:]])
    try:
        import bs4  # noqa: F401
    except ImportError:
        print("⚙️ Pehli baar setup (light) chal raha hai...", flush=True)
        if subprocess.call([sys.executable, __file__, "setup", "--light"]) != 0:
            print("SETUP_NEEDED: python deps install nahi hue. Chalao: python3 "
                  f"{__file__} setup")
            sys.exit(2)
        if vpy.exists():
            os.environ["DEVX_REEXEC"] = "1"
            os.execv(str(vpy), [str(vpy), __file__, *sys.argv[1:]])


if __name__ == "__main__":
    _bootstrap()
    from devx.cli import main
    sys.exit(main())
