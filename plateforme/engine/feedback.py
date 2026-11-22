"""Module 6, Boucle de retour : stats de MES vidéos via l'Instagram Graph API.

Par compte : IG_<COMPTE>_USER_ID + IG_<COMPTE>_TOKEN (token long-lived) dans .env.
Métriques Reels : views, reach, likes, comments, shares, saved, total_interactions,
ig_reels_avg_watch_time, ig_reels_video_view_total_time (si dispo, sinon on retombe sur un sous-ensemble).
Chaque vidéo publiée est liée à son entrée du calendrier (date ± N jours + similarité caption/hook),
ou manuellement : engine link <media_id|url> <code>.
TikTok : pas d'API pour l'instant (saisie manuelle possible via engine link --views).
"""
from __future__ import annotations

import datetime as dt
import difflib
import random

import requests

from . import db, log
from .config import env, settings

logger = log.get("feedback")

METRICS_FULL = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
METRICS_MIN = ["reach", "likes", "comments", "shares", "saved"]


def _creds(account: str) -> tuple[str | None, str | None]:
    k = account.upper()
    return env(f"IG_{k}_USER_ID"), env(f"IG_{k}_TOKEN")


def _base() -> str:
    return f"https://{env('IG_GRAPH_HOST', 'graph.facebook.com')}/{env('IG_GRAPH_VERSION', 'v23.0')}"


def _get(url: str, params: dict) -> dict:
    for attempt in range(3):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503):
            import time

            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"Graph API {r.status_code} : {r.text[:300]}")
    raise RuntimeError("Graph API indisponible")


METRICS_CONVERSION = METRICS_FULL + ["follows", "profile_visits"]  # signaux de conversion (si dispo pour les Reels)


def _insights(media_id: str, token: str) -> dict:
    for metrics in (METRICS_CONVERSION, METRICS_FULL, METRICS_MIN):
        try:
            d = _get(f"{_base()}/{media_id}/insights", {"metric": ",".join(metrics), "access_token": token})
            return {m["name"]: (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value"))
                    for m in d.get("data", [])}
        except RuntimeError as e:
            logger.debug("insights %s (%s) : %s", media_id, metrics[0], e)
    return {}


def fetch_account(account: str) -> list[dict]:
    from .ig_auth import refresh_if_needed

    refresh_if_needed(account)  # token Instagram Login : rafraîchi automatiquement avant expiration
    user_id, token = _creds(account)
    if not (user_id and token):
        raise RuntimeError(f"IG_{account.upper()}_USER_ID / IG_{account.upper()}_TOKEN absents")
    since = dt.datetime.now() - dt.timedelta(days=int(settings().get("feedback.lookback_days", 30)))
    url = f"{_base()}/{user_id}/media"
    params = {"fields": "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count",
              "limit": 50, "access_token": token}
    out = []
    while url:
        d = _get(url, params)
        for m in d.get("data", []):
            ts = dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")).replace(tzinfo=None)
            if ts < since:
                return out
            if m.get("media_type") != "VIDEO" and m.get("media_product_type") != "REELS":
                continue
            ins = _insights(m["id"], token)
            awt = ins.get("ig_reels_avg_watch_time")
            out.append({
                "external_id": m["id"], "url": m.get("permalink"), "caption": m.get("caption"),
                "posted_at": ts.isoformat(timespec="seconds"),
                "views": ins.get("views"), "reach": ins.get("reach"),
                "likes": ins.get("likes", m.get("like_count")), "comments": ins.get("comments", m.get("comments_count")),
                "shares": ins.get("shares"), "saves": ins.get("saved"),
                "avg_watch_time_s": awt / 1000 if awt else None,
                "total_watch_time_s": (ins.get("ig_reels_video_view_total_time") or 0) / 1000 or None,
                "raw": ins,  # contient follows / profile_visits quand l'API les fournit
            })
        url = (d.get("paging") or {}).get("next")
        params = {}
    return out


def mock_account(conn, account: str) -> list[dict]:
    """Stats simulées pour les entrées passées du calendrier (tests de la boucle/promotion)."""
    rows = conn.execute("SELECT * FROM calendar WHERE account=? AND date < ?", (account, dt.date.today().isoformat())).fetchall()
    out = []
    for r in rows:
        e = db.loads(r["data"], {})
        rng = random.Random(r["code"])
        base = 4000
        views = int(base * rng.lognormvariate(0, 0.5) * (1.6 if r["slot_type"] == "test" else 1))
        out.append({
            "external_id": f"mock_{r['code']}", "url": f"https://www.instagram.com/reel/mock_{r['code']}/",
            "caption": f"{e['hooks'][0]['verbal'] if e.get('hooks') else e.get('subject')}",
            "posted_at": f"{r['date']}T18:00:00", "views": views, "reach": int(views * 0.8),
            "likes": int(views * 0.05), "comments": int(views * 0.006), "shares": int(views * 0.01),
            "saves": int(views * 0.012), "avg_watch_time_s": round(rng.uniform(8, 25), 1),
            "total_watch_time_s": None, "raw": {}, "_calendar_id": r["id"],
        })
    return out


def _upsert(conn, account: str, items: list[dict], is_mock: bool) -> int:
    now = dt.datetime.now().isoformat(timespec="seconds")
    for it in items:
        conn.execute(
            """INSERT INTO my_videos(account, platform, external_id, url, caption, posted_at, views, reach, likes, comments,
                   shares, saves, avg_watch_time_s, total_watch_time_s, raw, is_mock, updated_at, calendar_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(platform, external_id) DO UPDATE SET views=excluded.views, reach=excluded.reach,
                   likes=excluded.likes, comments=excluded.comments, shares=excluded.shares, saves=excluded.saves,
                   avg_watch_time_s=excluded.avg_watch_time_s, total_watch_time_s=excluded.total_watch_time_s,
                   raw=excluded.raw, updated_at=excluded.updated_at""",
            (account, "instagram", it["external_id"], it["url"], it["caption"], it["posted_at"], it["views"], it["reach"],
             it["likes"], it["comments"], it["shares"], it["saves"], it["avg_watch_time_s"], it["total_watch_time_s"],
             db.dumps(it.get("raw")), int(is_mock), now, it.get("_calendar_id")),
        )
    return len(items)


def _entry_text(e: dict) -> str:
    return " ".join([e.get("subject", "")] + [h.get("verbal", "") for h in e.get("hooks", [])] + [e.get("script", "")[:300]]).lower()


def link_videos(conn, account: str) -> int:
    window = int(settings().get("feedback.match_window_days", 2))
    linked = 0
    for v in conn.execute("SELECT * FROM my_videos WHERE account=? AND calendar_id IS NULL AND posted_at IS NOT NULL", (account,)).fetchall():
        d = dt.datetime.fromisoformat(v["posted_at"]).date()
        cands = conn.execute(
            """SELECT * FROM calendar WHERE account=? AND date BETWEEN ? AND ?
               AND id NOT IN (SELECT calendar_id FROM my_videos WHERE calendar_id IS NOT NULL)""",
            (account, (d - dt.timedelta(days=window)).isoformat(), (d + dt.timedelta(days=window)).isoformat()),
        ).fetchall()
        best, best_score = None, 0.0
        for c in cands:
            score = difflib.SequenceMatcher(None, (v["caption"] or "").lower()[:400], _entry_text(db.loads(c["data"], {}))).ratio()
            score -= abs((dt.date.fromisoformat(c["date"]) - d).days) * 0.05
            if score > best_score:
                best, best_score = c, score
        if best is not None and best_score >= 0.2:
            conn.execute("UPDATE my_videos SET calendar_id=?, format_id=? WHERE id=?", (best["id"], best["format_id"], v["id"]))
            conn.execute("UPDATE calendar SET status='published' WHERE id=?", (best["id"],))
            linked += 1
    # format_id pour les liens déjà posés (mock / manuel)
    conn.execute("""UPDATE my_videos SET format_id=(SELECT format_id FROM calendar c WHERE c.id=my_videos.calendar_id)
                    WHERE calendar_id IS NOT NULL AND format_id IS NULL""")
    conn.execute("UPDATE calendar SET status='published' WHERE id IN (SELECT calendar_id FROM my_videos WHERE calendar_id IS NOT NULL)")
    return linked


def manual_link(media: str, code: str, views: int | None = None, platform: str = "instagram") -> str:
    with db.session() as conn:
        c = conn.execute("SELECT * FROM calendar WHERE code=?", (code,)).fetchone()
        if not c:
            return f"code calendrier inconnu : {code}"
        row = conn.execute("SELECT id FROM my_videos WHERE external_id=? OR url=?", (media, media)).fetchone()
        if row:
            conn.execute("UPDATE my_videos SET calendar_id=?, format_id=?, views=COALESCE(?, views) WHERE id=?",
                         (c["id"], c["format_id"], views, row["id"]))
        else:  # saisie manuelle (ex. TikTok)
            conn.execute("INSERT INTO my_videos(account, platform, external_id, url, posted_at, calendar_id, format_id, views, updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                         (c["account"], platform, media, media if media.startswith("http") else None, c["date"] + "T18:00:00",
                          c["id"], c["format_id"], views))
        conn.execute("UPDATE calendar SET status='published' WHERE id=?", (c["id"],))
    return f"{media} lié à {code}"


def run(mock: bool = False) -> dict:
    stats = {}
    with db.session() as conn:
        for account in settings().accounts:
            try:
                if mock:
                    items, is_mock = mock_account(conn, account), True
                else:
                    items, is_mock = fetch_account(account), False
                n = _upsert(conn, account, items, is_mock)
                linked = link_videos(conn, account)
                stats[account] = {"videos": n, "linked": linked, "mock": is_mock}
            except Exception as e:
                logger.warning("stats %s indisponibles : %s (voir GUIDE.md § Instagram)", account, e)
                stats[account] = {"error": str(e)[:200]}
        db.log_run(conn, "stats", "feedback", "ok", db.dumps(stats))
    logger.info("stats : %s", stats)
    return stats
