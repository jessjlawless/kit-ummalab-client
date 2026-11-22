"""Téléchargement des SEULES vidéos retenues par le module 2 (outliers)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import requests

from .. import log
from ..config import DATA_DIR, env
from .common import polite_sleep

logger = log.get("download")
YTDLP = str(Path(sys.executable).parent / "yt-dlp")


def download_video(v) -> str | None:
    if v["is_mock"]:
        return None
    media_dir = DATA_DIR / "media" / v["platform"]
    media_dir.mkdir(parents=True, exist_ok=True)
    target = media_dir / f"{v['external_id']}.mp4"
    if target.exists() and target.stat().st_size > 10_000:
        return str(target)  # cache

    if v["video_url"]:
        try:
            r = requests.get(v["video_url"], timeout=120, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            target.write_bytes(r.content)
            return str(target)
        except Exception as e:
            logger.warning("téléchargement direct KO (%s), essai yt-dlp", e)

    if not v["url"]:
        return None
    cmd = [YTDLP, "--socket-timeout", "30", "-f", "b[ext=mp4]/bv*+ba/b", "--merge-output-format", "mp4", "-o", str(target), "--no-warnings", "--no-playlist"]
    if v["platform"] == "tiktok":  # yt-dlp lit TikTok sans compte : plus rapide que le navigateur
        p = subprocess.run(cmd + [v["url"]], capture_output=True, text=True, timeout=600)
        if p.returncode == 0 and target.exists():
            return str(target)
    if v["platform"] in ("instagram", "tiktok"):  # via le navigateur du compte scout (jamais de cookies hors navigateur)
        try:
            from ..browser.download import download as browser_download

            got = browser_download(v["platform"], v["url"], v["external_id"], target)
            if got:
                return got
        except Exception as e:
            logger.warning("téléchargement navigateur KO : %s", e)
    if env("YTDLP_COOKIES_BROWSER"):
        cmd += ["--cookies-from-browser", env("YTDLP_COOKIES_BROWSER")]
    p = subprocess.run(cmd + [v["url"]], capture_output=True, text=True, timeout=600)
    polite_sleep(0.5)
    if p.returncode != 0 or not target.exists():
        logger.warning("yt-dlp KO pour %s : %s", v["url"], (p.stderr or "").strip()[-200:])
        return None
    return str(target)
