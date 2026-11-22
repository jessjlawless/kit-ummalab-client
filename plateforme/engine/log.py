"""Logs lisibles en console + fichier data/logs/engine.log."""
from __future__ import annotations

import logging
import sys

from .config import DATA_DIR

_configured = False


def setup(verbose: bool = False) -> None:
    global _configured
    if _configured:
        return
    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s", "%H:%M:%S"))
    root.addHandler(console)

    fileh = logging.FileHandler(DATA_DIR / "logs" / "engine.log", encoding="utf-8")
    fileh.setLevel(logging.DEBUG)
    fileh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s"))
    root.addHandler(fileh)

    for noisy in ("urllib3", "httpx", "httpcore", "anthropic", "instaloader"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"engine.{name}")
