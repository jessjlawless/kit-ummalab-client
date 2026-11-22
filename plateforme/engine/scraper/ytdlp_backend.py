"""Backend yt-dlp (TikTok surtout). Métadonnées seules, pas de téléchargement.
Instable sans cookies : mettre YTDLP_COOKIES_BROWSER=chrome dans .env si besoin."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from ..config import env
from .common import iso, to_int, with_retries

YTDLP = str(Path(sys.executable).parent / "yt-dlp")


def _cmd(url: str, limit: int) -> list[str]:
    cmd = [YTDLP, "--socket-timeout", "30", "--playlist-end", str(limit), "-J", "--no-warnings", "--ignore-errors"]  # une vidéo illisible (carrousel photo) ne fait plus échouer tout le profil
    if "youtube.com" in url:
        cmd.append("--flat-playlist")  # onglet Shorts : vues dispo en flat, beaucoup plus rapide
    if env("YTDLP_COOKIES_BROWSER"):
        cmd += ["--cookies-from-browser", env("YTDLP_COOKIES_BROWSER")]
    return cmd + [url]


def fetch(platform: str, handle: str, since: dt.datetime, limit: int) -> list[dict]:
    url = {"tiktok": f"https://www.tiktok.com/@{handle}", "instagram": f"https://www.instagram.com/{handle}/reels/",
           "youtube": f"https://www.youtube.com/@{handle}/shorts"}[platform]

    def call():
        p = subprocess.run(_cmd(url, limit), capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "yt-dlp a échoué")
        return json.loads(p.stdout)

    data = with_retries(call, f"yt-dlp @{handle}")
    out = []
    for e in data.get("entries") or []:
        if not e:
            continue
        out.append({
            "external_id": e.get("id"),
            "url": e.get("webpage_url") or e.get("url") or (f"https://www.youtube.com/shorts/{e.get('id')}" if platform == "youtube" else None),
            "video_url": None,
            "thumb_url": ((e.get("thumbnails") or [{}])[-1] or {}).get("url") or e.get("thumbnail"),
            "caption": e.get("description") or e.get("title"),  # YouTube flat : titre du Short
            "posted_at": iso(e.get("timestamp")),
            "duration_s": e.get("duration"),
            "views": to_int(e.get("view_count")),
            "likes": to_int(e.get("like_count")),
            "comments": to_int(e.get("comment_count")),
            "shares": to_int(e.get("repost_count")),
            "saves": None,
        })
    if not out:
        raise RuntimeError("aucune vidéo renvoyée")
    return out
