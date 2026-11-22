"""Backend Instaloader (Instagram). Nécessite une session d'un compte SECONDAIRE :
    .venv/bin/instaloader --login <compte_secondaire>   (crée le fichier de session)
puis IG_SCRAPER_USERNAME=<compte_secondaire> dans .env.
Sans session, Instagram renvoie 401 quasi systématiquement (testé le 2026-10-18)."""
from __future__ import annotations

import datetime as dt
import itertools

from ..config import env
from .common import iso, polite_sleep, to_int, with_retries


def fetch(platform: str, handle: str, since: dt.datetime, limit: int) -> list[dict]:
    if platform != "instagram":
        raise ValueError("instaloader = Instagram uniquement")
    import instaloader

    L = instaloader.Instaloader(download_pictures=False, download_videos=False, download_comments=False,
                                save_metadata=False, quiet=True, max_connection_attempts=2)
    user = env("IG_SCRAPER_USERNAME")
    if not user:
        raise RuntimeError("IG_SCRAPER_USERNAME absent (session instaloader requise)")
    L.load_session_from_file(user)

    profile = with_retries(lambda: instaloader.Profile.from_username(L.context, handle), f"profil @{handle}")
    out = []
    for post in itertools.islice(profile.get_posts(), limit * 2):
        if post.date_utc < since:
            if not post.is_pinned:
                break
            continue
        if not post.is_video:
            continue
        out.append({
            "external_id": post.shortcode,
            "url": f"https://www.instagram.com/reel/{post.shortcode}/",
            "video_url": post.video_url,
            "caption": post.caption,
            "posted_at": iso(post.date_utc),
            "duration_s": post.video_duration,
            "views": to_int(getattr(post, "video_play_count", None) or post.video_view_count),
            "likes": to_int(post.likes),
            "comments": to_int(post.comments),
            "shares": None,
            "saves": None,
        })
        if len(out) >= limit:
            break
        polite_sleep(0.3)
    return out
