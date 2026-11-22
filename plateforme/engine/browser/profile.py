"""Backend de scraping « browser » : ouvre le profil d'un compte de référence avec la session scout,
scrolle, et récupère les vidéos (vues, likes, commentaires…) depuis les réponses JSON interceptées.
Suit le compte (option scout.follow_reference_accounts) pour pousser l'algo vers la niche."""
from __future__ import annotations

import datetime as dt
import json
import random
import re

from .. import log
from ..config import DATA_DIR, settings
from . import PLATFORMS, Blocked, check_blocked, context, goto, logged_in
from .extract import attach_collector

logger = log.get("browser.profile")
STATE = DATA_DIR / "browser" / "state.json"
PROFILE_URL = {"instagram": "https://www.instagram.com/{h}/reels/", "tiktok": "https://www.tiktok.com/@{h}"}
FOLLOW_RE = re.compile(r"^\s*(Follow|Suivre|Folgen)\s*$", re.I)


def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1))


def maybe_follow(page, platform: str, handle: str) -> bool:
    s = settings()
    if not s.get("scout.follow_reference_accounts", True):
        return False
    st = _state()
    today = dt.date.today().isoformat()
    day = st.setdefault("follows", {}).setdefault(today, [])
    followed = st.setdefault("followed", {}).setdefault(platform, [])
    if handle in followed or len(day) >= int(s.get("scout.max_follows_per_day", 5)):
        return False
    try:
        btn = page.get_by_role("button", name=FOLLOW_RE).first
        if btn.is_visible(timeout=3000):
            page.wait_for_timeout(random.uniform(1500, 4000))
            btn.click()
            day.append(f"{platform}:{handle}")
            followed.append(handle)
            _save_state(st)
            logger.info("suivi @%s sur %s (signal de niche pour l'algo)", handle, platform)
            return True
    except Exception as e:
        logger.debug("follow @%s impossible : %s", handle, e)
    return False


def fetch(platform: str, handle: str, since: dt.datetime, limit: int) -> list[dict]:
    if platform not in PROFILE_URL:
        raise ValueError("backend browser : instagram / tiktok (YouTube passe par yt-dlp)")
    sink: dict = {}
    with context(platform, headless=bool(settings().get("scout.profile_headless", True))) as ctx:
        if not logged_in(ctx, platform):
            raise RuntimeError(f"pas de session {platform}, lance `engine login {platform}`")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        attach_collector(page, platform, sink)
        goto(page, PROFILE_URL[platform].format(h=handle), platform)
        page.wait_for_timeout(random.uniform(3000, 6000))
        check_blocked(page, platform)
        maybe_follow(page, platform, handle)
        for _ in range(int(settings().get("scout.profile_scrolls", 10))):
            mine = [i for i in sink.values() if (i.get("author") or handle).lower() == handle.lower()]
            if len(mine) >= limit:
                break
            page.mouse.wheel(0, random.randint(1400, 2600))
            page.wait_for_timeout(random.uniform(1800, 4200))
            check_blocked(page, platform)
        if platform == "instagram":  # la grille principale apporte caption + date (l'onglet Reels n'a que les vues)
            goto(page, f"https://www.instagram.com/{handle}/", platform)
            for _ in range(4):
                page.mouse.wheel(0, random.randint(1400, 2600))
                page.wait_for_timeout(random.uniform(1800, 3500))
    items = [i for i in sink.values() if (i.get("author") or handle).lower() == handle.lower()]
    if not items:
        raise RuntimeError(f"aucune vidéo interceptée sur le profil @{handle}")
    return items[:limit]


__all__ = ["fetch", "Blocked", "PLATFORMS"]
