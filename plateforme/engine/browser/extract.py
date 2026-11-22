"""Extraction générique des vidéos depuis les réponses JSON interceptées (robuste aux changements d'endpoint :
on parcourt tout le JSON et on reconnaît les objets « média » à leurs clés)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterator


def walk(obj: Any) -> Iterator[dict]:
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            yield o
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)


def _iso(ts) -> str | None:
    try:
        return dt.datetime.fromtimestamp(int(ts)).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def instagram_items(data: Any) -> list[dict]:
    out = {}
    for d in walk(data):
        code = d.get("code")
        views = d.get("play_count") or d.get("ig_play_count") or d.get("view_count") or d.get("video_view_count")
        if not code or views is None or not isinstance(views, int):
            continue
        user = d.get("user") or d.get("owner") or {}
        cap = d.get("caption")
        out[code] = {
            "platform": "instagram", "external_id": code, "url": f"https://www.instagram.com/reel/{code}/",
            "video_url": ((d.get("video_versions") or [{}])[0] or {}).get("url"),
            "thumb_url": (((d.get("image_versions2") or {}).get("candidates") or [{}])[0] or {}).get("url"),
            "caption": cap.get("text") if isinstance(cap, dict) else cap,
            "posted_at": _iso(d.get("taken_at")), "duration_s": d.get("video_duration"),
            "views": views, "likes": d.get("like_count"), "comments": d.get("comment_count"),
            "shares": d.get("reshare_count"), "saves": None,
            "author": user.get("username"), "author_followers": user.get("follower_count"),
        }
    return list(out.values())


def tiktok_items(data: Any) -> list[dict]:
    out = {}
    for d in walk(data):
        stats = d.get("stats") or d.get("statsV2")
        author = d.get("author")
        if not (d.get("id") and isinstance(stats, dict) and isinstance(author, dict) and "playCount" in stats):
            continue
        a_stats = d.get("authorStats") or {}
        handle = author.get("uniqueId")
        out[d["id"]] = {
            "platform": "tiktok", "external_id": str(d["id"]), "url": f"https://www.tiktok.com/@{handle}/video/{d['id']}",
            "video_url": (d.get("video") or {}).get("playAddr"), "caption": d.get("desc"),
            "thumb_url": (d.get("video") or {}).get("originCover") or (d.get("video") or {}).get("cover"),
            "posted_at": _iso(d.get("createTime")), "duration_s": (d.get("video") or {}).get("duration"),
            "views": int(stats.get("playCount") or 0), "likes": int(stats.get("diggCount") or 0),
            "comments": int(stats.get("commentCount") or 0), "shares": int(stats.get("shareCount") or 0),
            "saves": int(stats.get("collectCount") or 0) if stats.get("collectCount") is not None else None,
            "author": handle, "author_followers": a_stats.get("followerCount"),
        }
    return list(out.values())


EXTRACTORS = {"instagram": instagram_items, "tiktok": tiktok_items}
API_HINTS = {
    "instagram": ("/api/v1/", "/graphql", "/api/graphql"),
    "tiktok": ("/api/recommend/item_list", "/api/post/item_list", "/api/search", "/api/item/detail", "/api/"),
}


def attach_collector(page, platform: str, sink: dict) -> None:
    """Branche un collecteur sur toutes les réponses JSON de l'API de la plateforme → sink[id] = item."""
    hints = API_HINTS.get(platform, ())
    extractor = EXTRACTORS.get(platform)
    if not extractor:
        return
    raw: dict[str, dict] = {}  # Instagram : infos éclatées entre endpoints (vues ≠ caption/date) → fusion par code

    def on_response(resp):
        try:
            if not any(h in resp.url for h in hints):
                return
            if "json" not in (resp.headers.get("content-type") or "") and "graphql" not in resp.url:
                return
            data = resp.json()
            if platform == "instagram":
                for d in walk(data):
                    code = d.get("code")
                    if code and (d.get("taken_at") or "play_count" in d or "ig_play_count" in d):
                        merged = raw.setdefault(code, {})
                        merged.update({k: v for k, v in d.items() if v is not None})
                        for it in instagram_items(merged):
                            sink[it["external_id"]] = it
                return
            for it in extractor(data):
                sink[it["external_id"]] = it
        except Exception:
            pass

    page.on("response", on_response)
