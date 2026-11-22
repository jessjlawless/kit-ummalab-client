"""Navigateur piloté (Playwright + ton Google Chrome) avec un profil persistant PAR plateforme,
pour les comptes « scout » dédiés que le créateur connecte lui-même.

  engine login instagram|tiktok|youtube   → ouvre Chrome, TU te connectes (Claude ne tape jamais de mot de passe),
                                            ferme la fenêtre : la session reste dans data/browser/<plateforme>/
  backend de scraping « browser »          → profils des comptes de référence, en connecté (engine/browser/profile.py)
  engine scout                              → scrolle les feeds Reels / For You / Shorts, entraîne l'algo,
                                            découvre des vidéos qui surperforment (engine/browser/scout.py)

Sécurité : rythme humain, plafond de minutes par session, arrêt immédiat sur checkpoint / captcha / page de
connexion (jamais de contournement) → message dans data/logs + TODO."""
from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Iterator

from .. import log
from ..config import DATA_DIR, settings

logger = log.get("browser")

PLATFORMS = {
    "instagram": {"login": "https://www.instagram.com/accounts/login/", "home": "https://www.instagram.com/",
                  "feed": "https://www.instagram.com/reels/", "cookie": "sessionid", "domain": "instagram.com"},
    "tiktok": {"login": "https://www.tiktok.com/login", "home": "https://www.tiktok.com/",
               "feed": "https://www.tiktok.com/foryou", "cookie": "sessionid", "domain": "tiktok.com"},
    "youtube": {"login": "https://accounts.google.com/ServiceLogin?service=youtube&continue=https://www.youtube.com/",
                "home": "https://www.youtube.com/", "feed": "https://www.youtube.com/shorts",
                "cookie": "LOGIN_INFO", "domain": "youtube.com"},
}
BLOCK_PATTERNS = re.compile(r"(challenge|checkpoint|captcha|verify|suspended|two_factor|/accounts/login|unusual|/terms/|unblock)", re.I)


class Blocked(RuntimeError):
    """La plateforme demande une vérification humaine : on s'arrête, le créateur doit intervenir."""


def profile_dir(platform: str) -> Path:
    p = DATA_DIR / "browser" / platform
    p.mkdir(parents=True, exist_ok=True)
    return p


def has_session(platform: str) -> bool:
    return (profile_dir(platform) / ".logged_in").exists()


@contextlib.contextmanager
def context(platform: str, headless: bool | None = None) -> Iterator:
    from playwright.sync_api import sync_playwright

    if headless is None:
        headless = bool(settings().get("scout.headless", False))
    with sync_playwright() as p:
        kwargs = dict(user_data_dir=str(profile_dir(platform)), headless=headless,
                      viewport={"width": 1280, "height": 900}, locale="en-US",
                      args=["--disable-blink-features=AutomationControlled"])
        try:
            ctx = p.chromium.launch_persistent_context(channel="chrome", **kwargs)
        except Exception as e:  # Chrome absent → Chromium de Playwright (nécessite `playwright install chromium`)
            logger.warning("Chrome indisponible (%s) → Chromium", e)
            ctx = p.chromium.launch_persistent_context(**kwargs)
        try:
            yield ctx
        finally:
            ctx.close()


def logged_in(ctx, platform: str) -> bool:
    cfg = PLATFORMS[platform]
    return any(c["name"] == cfg["cookie"] and cfg["domain"] in c["domain"] and c.get("value") for c in ctx.cookies())


def check_blocked(page, platform: str) -> None:
    url = page.url
    if BLOCK_PATTERNS.search(url):
        raise Blocked(f"{platform} demande une vérification ({url}). Ouvre `engine login {platform}` et règle-la à la main.")


REJECT_RE = re.compile(r"^\s*(Reject all|Alle ablehnen|Tout refuser|Decline optional cookies|Only allow essential cookies|"
                       r"Optionale Cookies ablehnen|Refuser les cookies optionnels|Decline all)\s*$", re.I)


def dismiss_consent(page) -> None:
    """Bannières cookies : toujours l'option la plus respectueuse de la vie privée (refuser le non-essentiel)."""
    try:
        btn = page.get_by_role("button", name=REJECT_RE).first
        if btn.is_visible(timeout=2500):
            btn.click()
            page.wait_for_timeout(2500)
    except Exception:
        pass


def goto(page, url: str, platform: str) -> None:
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    dismiss_consent(page)
    check_blocked(page, platform)


def login(platform: str, timeout_min: int = 15) -> bool:
    """Ouvre Chrome sur la page de connexion. Le créateur se connecte lui-même ; dès que la session est détectée
    (cookie de connexion), elle est enregistrée et la fenêtre se ferme toute seule."""
    import time

    cfg = PLATFORMS[platform]
    print(f"\n→ Une fenêtre Chrome s'ouvre sur {platform}. Connecte-toi avec ton compte SCOUT dédié "
          "(pas ton compte principal). Elle se fermera toute seule une fois connecté.\n")
    marker = profile_dir(platform) / ".logged_in"
    ok = False
    with context(platform, headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not logged_in(ctx, platform):
            page.goto(cfg["login"])
        deadline = time.time() + timeout_min * 60
        while time.time() < deadline:
            try:
                if logged_in(ctx, platform):
                    ok = True
                    marker.write_text("ok")
                    try:
                        page.wait_for_timeout(4000)  # laisse la plateforme finir d'écrire ses cookies
                    except Exception:
                        pass
                    break
                if not ctx.pages:  # fenêtre fermée par l'utilisateur
                    break
                time.sleep(2)
            except Exception:
                break
    if ok:
        print(f"✓ Session {platform} enregistrée dans {profile_dir(platform)}")
    else:
        marker.unlink(missing_ok=True)
        print(f"✗ Pas de session {platform} détectée (cookie {cfg['cookie']} absent). Relance `engine login {platform}`.")
    logger.info("login %s : %s", platform, "OK" if ok else "échec")
    return ok

