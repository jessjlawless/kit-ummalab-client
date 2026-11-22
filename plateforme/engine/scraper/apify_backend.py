"""Backend Apify (recommandé). Acteurs configurables dans engine.yaml (scraper.apify_actors)."""
from __future__ import annotations

import datetime as dt

import requests

from ..config import env, settings
from .common import iso, to_int, with_retries

API = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


def _run(actor: str, payload: dict) -> list[dict]:
    token = env("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN absent")

    def call():
        r = requests.post(API.format(actor=actor), params={"token": token}, json=payload, timeout=300)
        r.raise_for_status()
        return r.json()

    return with_retries(call, f"apify {actor}")


def fetch(platform: str, handle: str, since: dt.datetime, limit: int) -> list[dict]:
    actors = settings().get("scraper.apify_actors", {})
    if platform == "instagram":
        items = _run(actors.get("instagram", "apify~instagram-reel-scraper"), {"username": [handle], "resultsLimit": limit})
        out = []
        for it in items:
            if it.get("error"):
                continue
            out.append({
                "external_id": it.get("shortCode") or it.get("id"),
                "url": it.get("url"),
                "video_url": it.get("videoUrl"),
                "thumb_url": it.get("displayUrl"),
                "caption": it.get("caption"),
                "posted_at": iso(it.get("timestamp")),
                "duration_s": it.get("videoDuration"),
                "views": to_int(it.get("videoPlayCount") or it.get("videoViewCount")),
                "likes": to_int(it.get("likesCount")),
                "comments": to_int(it.get("commentsCount")),
                "shares": to_int(it.get("sharesCount")),
                "saves": None,
            })
        return out
    if platform == "tiktok":
        items = _run(
            actors.get("tiktok", "clockworks~tiktok-scraper"),
            {"profiles": [handle], "resultsPerPage": limit, "shouldDownloadVideos": False},
        )
        out = []
        for it in items:
            meta = it.get("videoMeta") or {}
            out.append({
                "external_id": it.get("id"),
                "url": it.get("webVideoUrl"),
                "video_url": meta.get("downloadAddr"),
                "thumb_url": meta.get("coverUrl") or meta.get("originalCoverUrl"),
                "caption": it.get("text"),
                "posted_at": iso(it.get("createTimeISO") or it.get("createTime")),
                "duration_s": meta.get("duration"),
                "views": to_int(it.get("playCount")),
                "likes": to_int(it.get("diggCount")),
                "comments": to_int(it.get("commentCount")),
                "shares": to_int(it.get("shareCount")),
                "saves": to_int(it.get("collectCount")),
            })
        return out
    raise ValueError(f"plateforme inconnue : {platform}")
