"""Module 1, Scraper hebdomadaire.

Backends (config scraper.backend) :
  apify, le plus fiable (APIFY_TOKEN), Instagram + TikTok
  browser, session de ton compte scout dédié (engine login instagram|tiktok), profils en connecté
  instaloader, Instagram avec session d'un compte secondaire (IG_SCRAPER_USERNAME)
  ytdlp, TikTok (cookies navigateur optionnels) + YouTube Shorts (fonctionne sans compte)
  mock, données réalistes générées localement (marquées is_mock=1)
  auto, apify si token, sinon instaloader/ytdlp, sinon mock
Cache : un compte scrapé il y a moins de `rescrape_after_days` jours est sauté ;
les vidéos déjà connues sont seulement mises à jour (UNIQUE account_id+external_id).
"""
from __future__ import annotations

import datetime as dt
import random
import time
from typing import Callable

from .. import db, log
from ..config import env, settings
from . import apify_backend, instaloader_backend, mock_backend, ytdlp_backend
from ..browser import has_session

logger = log.get("scraper")

BACKENDS: dict[str, Callable] = {
    "apify": apify_backend.fetch,
    "instaloader": instaloader_backend.fetch,
    "ytdlp": ytdlp_backend.fetch,
    "mock": mock_backend.fetch,
    "browser": lambda *a, **k: __import__("engine.browser.profile", fromlist=["fetch"]).fetch(*a, **k),
}


def iter_config_accounts():
    """(owner, category, platform, handle, niche_label) pour tous les comptes configurés."""
    for owner, cfg in settings().accounts.items():
        for a in cfg.get("reference_accounts") or []:
            yield owner, "niche", a["platform"], a["handle"].lstrip("@"), cfg.get("niche")
        for a in cfg.get("other_niche_accounts") or []:
            yield owner, "other", a["platform"], a["handle"].lstrip("@"), a.get("niche")


def _backend_chain(platform: str, forced: str | None) -> list[str]:
    choice = forced or settings().get("scraper.backend", "auto")
    if choice != "auto":
        return [choice]
    chain = []
    if env("APIFY_TOKEN"):
        chain.append("apify")
    if platform in ("instagram", "tiktok") and has_session(platform):
        chain.append("browser")  # session du compte scout (engine login)
    if platform == "instagram" and env("IG_SCRAPER_USERNAME"):
        chain.append("instaloader")
    if platform in ("tiktok", "youtube"):
        chain.append("ytdlp")
    if settings().get("scraper.mock_fallback", False) or not chain:
        chain.append("mock")  # mock seulement si demandé ou si aucun backend réel n'existe pour cette plateforme
    return chain


def _upsert_account(conn, owner, category, platform, handle, niche_label) -> int:
    conn.execute(
        "INSERT INTO accounts(platform, handle, owner, category, niche_label) VALUES (?,?,?,?,?) "
        "ON CONFLICT(platform, handle, owner) DO UPDATE SET category=excluded.category, niche_label=excluded.niche_label",
        (platform, handle, owner, category, niche_label),
    )
    return conn.execute(
        "SELECT id FROM accounts WHERE platform=? AND handle=? AND owner=?", (platform, handle, owner)
    ).fetchone()["id"]


def _upsert_videos(conn, account_id: int, platform: str, items: list[dict], is_mock: bool) -> int:
    now = dt.datetime.now().isoformat(timespec="seconds")
    n = 0
    for it in items:
        if not it.get("external_id"):
            continue
        conn.execute(
            """INSERT INTO videos(account_id, platform, external_id, url, video_url, caption, posted_at, duration_s,
                   views, likes, comments, shares, saves, scraped_at, is_mock, thumb_url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(account_id, external_id) DO UPDATE SET
                   views=excluded.views, likes=excluded.likes, comments=excluded.comments,
                   shares=excluded.shares, saves=excluded.saves, scraped_at=excluded.scraped_at,
                   video_url=COALESCE(excluded.video_url, videos.video_url),
                   thumb_url=COALESCE(excluded.thumb_url, videos.thumb_url)""",
            (
                account_id, platform, str(it["external_id"]), it.get("url"), it.get("video_url"), it.get("caption"),
                it.get("posted_at"), it.get("duration_s"), it.get("views"), it.get("likes"), it.get("comments"),
                it.get("shares"), it.get("saves"), now, int(is_mock), it.get("thumb_url"),
            ),
        )
        n += 1
    return n


def run(force: bool = False, backend: str | None = None, only_owner: str | None = None) -> dict:
    s = settings()
    lookback = int(s.get("scraper.lookback_days", 30))
    limit = int(s.get("scraper.max_videos_per_account", 50))
    rescrape_days = int(s.get("scraper.rescrape_after_days", 6))
    since = dt.datetime.now() - dt.timedelta(days=lookback)
    stats = {"accounts": 0, "skipped_cache": 0, "videos": 0, "mock_accounts": 0, "errors": 0}

    with db.session() as conn:
        for owner, category, platform, handle, niche_label in iter_config_accounts():
            if only_owner and owner != only_owner:
                continue
            acc_id = _upsert_account(conn, owner, category, platform, handle, niche_label)
            row = conn.execute("SELECT last_scraped_at FROM accounts WHERE id=?", (acc_id,)).fetchone()
            if not force and row["last_scraped_at"]:
                age = dt.datetime.now() - dt.datetime.fromisoformat(row["last_scraped_at"])
                if age.days < rescrape_days:
                    stats["skipped_cache"] += 1
                    logger.info("cache : @%s (%s) scrapé il y a %d j → sauté", handle, platform, age.days)
                    continue

            items, used = None, None
            for name in _backend_chain(platform, backend):
                try:
                    logger.info("scrape @%s (%s, %s) via %s", handle, platform, category, name)
                    items = BACKENDS[name](platform, handle, since=since, limit=limit)
                    used = name
                    break
                except Exception as e:
                    stats["errors"] += 1
                    logger.warning("backend %s KO pour @%s : %s", name, handle, str(e)[:200])
            if items is None:
                continue
            # filtre fenêtre 30 jours
            items = [i for i in items if not i.get("posted_at") or i["posted_at"] >= since.isoformat()]
            n = _upsert_videos(conn, acc_id, platform, items, is_mock=(used == "mock"))
            conn.execute(
                "UPDATE accounts SET last_scraped_at=?, last_backend=? WHERE id=?",
                (dt.datetime.now().isoformat(timespec="seconds"), used, acc_id),
            )
            conn.commit()
            stats["accounts"] += 1
            stats["videos"] += n
            stats["mock_accounts"] += int(used == "mock")
            if used != "mock":  # rate limiting prudent entre comptes réels
                time.sleep(random.uniform(float(s.get("scraper.min_delay_s", 4)), float(s.get("scraper.max_delay_s", 12))))
        db.log_run(conn, "scrape", "scrape", "ok", db.dumps(stats))
    logger.info("scrape terminé : %s", stats)
    return stats


def download(video_row) -> str | None:
    """Télécharge une vidéo retenue (outlier) dans data/media. Renvoie le chemin ou None."""
    from .downloader import download_video

    return download_video(video_row)
