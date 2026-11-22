"""Registre des commandes longues en cours (data/run/<pid>.json) → visibles et arrêtables depuis le dashboard,
même lancées depuis le terminal ou le cron."""
from __future__ import annotations

import atexit
import datetime as dt
import json
import os
import signal
import subprocess
import time

from .config import DATA_DIR

RUN_DIR = DATA_DIR / "run"
LABELS = {"weekly": "Pipeline de la semaine", "daily": "Routine du jour", "calendar": "Régénération du calendrier",
          "analyze": "Analyse des outliers", "synthesize": "Synthèse", "scrape": "Scraping", "scout": "Scout des feeds",
          "references": "Recherche des références", "regen": "Régénération d'une vidéo", "broll": "Liste B-roll",
          "stats": "Stats Instagram", "login": "Connexion compte scout"}


def register(cmd: str, argv: list[str]) -> None:
    if cmd not in LABELS:
        return
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    f = RUN_DIR / f"{os.getpid()}.json"
    f.write_text(json.dumps({"pid": os.getpid(), "cmd": cmd, "argv": argv, "label": LABELS[cmd],
                             "started": dt.datetime.now().isoformat(timespec="seconds")}))
    atexit.register(lambda: f.unlink(missing_ok=True))


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def running() -> list[dict]:
    out = []
    for f in RUN_DIR.glob("*.json") if RUN_DIR.exists() else []:
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if alive(int(d["pid"])):
            out.append(d)
        else:
            f.unlink(missing_ok=True)
    return out


def kill_tree(pid: int, grace: float = 4.0) -> None:
    """SIGTERM au processus + à tous ses descendants (claude -p, Chrome, ffmpeg…), puis SIGKILL si besoin."""
    def descendants(p: int) -> list[int]:
        r = subprocess.run(["pgrep", "-P", str(p)], capture_output=True, text=True)
        kids = [int(x) for x in r.stdout.split()]
        return kids + [d for k in kids for d in descendants(k)]

    tree = descendants(pid) + [pid]
    for p in tree:
        try:
            os.kill(p, signal.SIGTERM)
        except ProcessLookupError:
            pass
    end = time.time() + grace
    while time.time() < end and any(alive(p) for p in tree):
        time.sleep(0.3)
    for p in tree:
        if alive(p):
            try:
                os.kill(p, signal.SIGKILL)
            except ProcessLookupError:
                pass
    (RUN_DIR / f"{pid}.json").unlink(missing_ok=True)
