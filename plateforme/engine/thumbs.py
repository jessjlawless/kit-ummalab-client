"""Miniatures servies par le dashboard (/api/thumb/<id>), mises en cache dans data/thumbs/ :
cache → YouTube (i.ytimg) → thumb_url capturée au scraping (CDN Instagram/TikTok, récupérée côté serveur)
→ image extraite de la vidéo téléchargée (ffmpeg, 1 s)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import requests

from . import db
from .config import DATA_DIR

CACHE = DATA_DIR / "thumbs"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


def _save(url: str, out: Path) -> bool:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": UA})
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") and len(r.content) > 2000:
            out.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


def thumbnail(video_id: int) -> str | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{int(video_id)}.jpg"
    if out.exists() and out.stat().st_size > 2000:
        return str(out)
    with db.session() as conn:
        v = conn.execute("SELECT platform, url, external_id, thumb_url, media_path FROM videos WHERE id=?", (video_id,)).fetchone()
    if not v:
        return None
    if v["platform"] == "youtube":
        vid = (re.search(r"(?:shorts/|v=)([\w-]{6,})", v["url"] or "") or [None, v["external_id"]])[1]
        for q in ("oardefault", "hqdefault"):
            if _save(f"https://i.ytimg.com/vi/{vid}/{q}.jpg", out):
                return str(out)
    if v["thumb_url"] and _save(v["thumb_url"], out):
        return str(out)
    if v["media_path"] and Path(v["media_path"]).exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", v["media_path"], "-frames:v", "1",
                        "-vf", "scale=540:-2", "-q:v", "4", str(out)], check=False)
        if out.exists():
            return str(out)
    return None
