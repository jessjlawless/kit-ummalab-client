"""Scout : scrolle les feeds (Reels Instagram, For You TikTok, Shorts YouTube) avec les comptes dédiés,
pour (1) entraîner l'algorithme vers tes niches et (2) découvrir des vidéos qui surperforment hors de ta liste.

Entraînement : une vidéo pertinente (mots-clés de niche dans la caption) est regardée 12-35 s, les autres
sont passées en 1,5-4 s (le temps de visionnage est le signal n°1) ; recherches sur les mots-clés de niche ;
suivi des comptes de référence (profile.py). Pas de like, pas de commentaire, pas de publication.

Découverte : chaque vidéo vue/interceptée est enregistrée (accounts.category='discovery'). Score de découverte
= vues / abonnés de l'auteur ; outlier si ≥ scout.outlier_ratio et ≥ scout.min_views vues.
Rapport : output/discovery/<date>.md (+ comptes à ajouter à ta liste de référence)."""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from .. import db, log
from ..config import OUTPUT_DIR, settings
from . import PLATFORMS, Blocked, check_blocked, context, goto, has_session, logged_in
from .extract import attach_collector

logger = log.get("scout")
YTDLP = str(Path(sys.executable).parent / "yt-dlp")
SEARCH_URL = {
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={q}",
    "tiktok": "https://www.tiktok.com/search/video?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}&sp=EgIQCQ%253D%253D",
}
CURRENT_JS = """() => {
  const c = window.innerHeight / 2; let best = null, bd = 1e9;
  for (const a of document.querySelectorAll('a[href*="/video/"], a[href*="/reel/"], a[href*="/shorts/"]')) {
    const r = a.getBoundingClientRect(); if (r.height === 0) continue;
    const d = Math.abs((r.top + r.bottom) / 2 - c); if (d < bd) { bd = d; best = a.href; }
  }
  return [location.href, best];
}"""
ID_RE = {"instagram": re.compile(r"/reels?/([\w-]+)"), "tiktok": re.compile(r"/video/(\d+)"),
         "youtube": re.compile(r"/shorts/([\w-]{6,})")}


def _keywords() -> dict[str, list[str]]:
    return {k: [w.lower() for w in v] for k, v in (settings().get("scout.keywords") or {}).items()}


def classify(caption: str) -> tuple[str | None, int]:
    """(compte cible, score), None si hors niche. Mot-clé composé = 2 points, mot simple = 1 ;
    pertinent si score ≥ scout.min_relevance (défaut 2) → évite les faux positifs (« ai », « money »…)."""
    t = (caption or "").lower()
    best, top = None, 0
    for owner, kws in _keywords().items():
        sc = sum(2 if " " in k else 1 for k in kws if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", t))
        if sc > top:
            best, top = owner, sc
    if top < int(settings().get("scout.min_relevance", 2)):
        return None, top
    return best, top


def _current_id(page, platform: str) -> str | None:
    try:
        href, nearest = page.evaluate(CURRENT_JS)
    except Exception:
        return None
    for u in (href, nearest):
        m = ID_RE[platform].search(u or "")
        if m:
            return m.group(1)
    return None


def _yt_meta(ids: list[str]) -> dict[str, dict]:
    out = {}
    for vid in ids[:60]:
        p = subprocess.run([YTDLP, "-J", "--skip-download", "--no-warnings", "--socket-timeout", "30",
                            f"https://www.youtube.com/shorts/{vid}"], capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            continue
        try:
            e = json.loads(p.stdout)
        except json.JSONDecodeError:
            continue
        out[vid] = {"platform": "youtube", "external_id": vid, "url": f"https://www.youtube.com/shorts/{vid}",
                    "video_url": None, "caption": f"{e.get('title') or ''}\n{(e.get('description') or '')[:500]}",
                    "posted_at": dt.datetime.strptime(e["upload_date"], "%Y%m%d").isoformat() if e.get("upload_date") else None,
                    "duration_s": e.get("duration"), "views": e.get("view_count"), "likes": e.get("like_count"),
                    "comments": e.get("comment_count"), "shares": None, "saves": None,
                    "author": (e.get("uploader_id") or e.get("channel") or "").lstrip("@"),
                    "author_followers": e.get("channel_follower_count")}
        time.sleep(random.uniform(1, 3))
    return out


def _dwell(page, seconds: float, platform: str) -> None:
    end = time.time() + seconds
    while time.time() < end:
        page.wait_for_timeout(min(2000, max(100, (end - time.time()) * 1000)))
        check_blocked(page, platform)


def browse(platform: str, minutes: float) -> dict:
    """Scrolle le feed + recherches de niche. Renvoie {id: item}."""
    cfg = PLATFORMS[platform]
    sink: dict = {}
    watched: dict[str, float] = {}
    with context(platform) as ctx:
        if platform != "youtube" and not logged_in(ctx, platform):
            raise RuntimeError(f"pas de session {platform}, lance `engine login {platform}`")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        attach_collector(page, platform, sink)

        # 1) recherches de niche (signal d'intérêt + collecte)
        kws = [k for v in _keywords().values() for k in v]
        for q in random.sample(kws, k=min(int(settings().get("scout.searches_per_session", 2)), len(kws))):
            goto(page, SEARCH_URL[platform].format(q=q.replace(" ", "+")), platform)
            _dwell(page, random.uniform(4, 8), platform)
            for _ in range(3):
                page.mouse.wheel(0, random.randint(900, 1800))
                _dwell(page, random.uniform(2, 4), platform)

        # 2) feed vertical
        goto(page, cfg["feed"], platform)
        _dwell(page, random.uniform(4, 7), platform)
        try:
            page.mouse.click(640, 450)  # focus sur la vidéo (pas sur un bouton)
        except Exception:
            pass
        end = time.time() + minutes * 60
        while time.time() < end:
            check_blocked(page, platform)
            vid = _current_id(page, platform)
            item = sink.get(vid) if vid else None
            if item is None and vid and platform == "youtube":  # pas d'API interceptée : titre affiché
                item = {"caption": re.sub(r"\s*-\s*YouTube$", "", page.title() or "")}
            owner, hits = classify((item or {}).get("caption", ""))
            if item is None:
                d = random.uniform(3, 7)
            elif owner:
                d = random.uniform(12, 35)  # pertinent → on regarde (signal fort)
            else:
                d = random.uniform(1.5, 4)  # hors niche → on passe vite
            if vid:
                watched[vid] = watched.get(vid, 0) + d
            _dwell(page, d, platform)
            page.keyboard.press("ArrowDown")
            if random.random() < 0.06:
                _dwell(page, random.uniform(5, 15), platform)  # pause humaine
    if platform == "youtube":
        sink.update(_yt_meta([v for v in watched if v not in sink]))
    for vid, secs in watched.items():
        if vid in sink:
            sink[vid]["watched_s"] = round(secs, 1)
    logger.info("scout %s : %d vidéos vues, %d interceptées", platform, len(watched), len(sink))
    return sink


def save(items: list[dict]) -> dict:
    s = settings()
    ratio = float(s.get("scout.outlier_ratio", 1.0))
    min_views = int(s.get("scout.min_views", 30000))
    now = dt.datetime.now().isoformat(timespec="seconds")
    stats = {"saved": 0, "relevant": 0, "outliers": 0}
    with db.session() as conn:
        for it in items:
            owner, hits = classify(it.get("caption", ""))
            if not owner or not it.get("author"):
                continue
            stats["relevant"] += 1
            conn.execute("INSERT INTO accounts(platform, handle, owner, category, niche_label, followers) VALUES (?,?,?,?,?,?) "
                         "ON CONFLICT(platform, handle, owner) DO UPDATE SET followers=COALESCE(excluded.followers, accounts.followers)",
                         (it["platform"], it["author"], owner, "discovery", "découverte scout", it.get("author_followers")))
            acc = conn.execute("SELECT id, category FROM accounts WHERE platform=? AND handle=? AND owner=?",
                               (it["platform"], it["author"], owner)).fetchone()
            f = it.get("author_followers")
            score = round(it["views"] / f, 2) if f and it.get("views") else None
            is_out = int(bool(score and score >= ratio and (it.get("views") or 0) >= min_views))
            conn.execute(
                """INSERT INTO videos(account_id, platform, external_id, url, video_url, caption, posted_at, duration_s, views,
                       likes, comments, shares, saves, scraped_at, outlier_score, is_outlier, is_mock)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                   ON CONFLICT(account_id, external_id) DO UPDATE SET views=excluded.views, likes=excluded.likes,
                       comments=excluded.comments, scraped_at=excluded.scraped_at,
                       outlier_score=COALESCE(videos.outlier_score, excluded.outlier_score),
                       is_outlier=MAX(videos.is_outlier, excluded.is_outlier)""",
                (acc["id"], it["platform"], it["external_id"], it["url"], it.get("video_url"), it.get("caption"),
                 it.get("posted_at"), it.get("duration_s"), it.get("views"), it.get("likes"), it.get("comments"),
                 it.get("shares"), it.get("saves"), now, score if acc["category"] == "discovery" else None,
                 is_out if acc["category"] == "discovery" else 0),
            )
            stats["saved"] += 1
            stats["outliers"] += is_out
        db.log_run(conn, "scout", "save", "ok", db.dumps(stats))
    return stats


def report(day: dt.date | None = None) -> Path:
    day = day or dt.date.today()
    known = {(a.get("platform"), a.get("handle", "").lower()) for cfg in settings().accounts.values()
             for a in (cfg.get("reference_accounts") or []) + (cfg.get("other_niche_accounts") or [])}
    L = [f"# Découvertes du scout, {day:%d/%m/%Y}", "",
         "Vidéos repérées en scrollant tes feeds. Score = vues / abonnés de l'auteur (≥ 1 = la vidéo a dépassé l'audience du compte).", ""]
    with db.session() as conn:
        for owner in settings().accounts:
            rows = conn.execute(
                """SELECT v.url, v.views, v.outlier_score, v.caption, a.handle, a.platform, a.followers FROM videos v
                   JOIN accounts a ON a.id=v.account_id WHERE a.owner=? AND a.category='discovery' AND v.is_outlier=1
                   ORDER BY v.outlier_score DESC LIMIT 15""", (owner,)).fetchall()
            L += [f"## {owner}", ""]
            L += [f"- x{r['outlier_score']} · {r['views']:,} vues · @{r['handle']} ({r['platform']}, {r['followers'] or '?'} abonnés), "
                  f"{(r['caption'] or '').splitlines()[0][:90]} {r['url']}".replace(",", " ") for r in rows] or ["- rien encore"]
            sugg = sorted({(r["platform"], r["handle"]) for r in rows if (r["platform"], r["handle"].lower()) not in known})
            if sugg:
                L += ["", "**Comptes à ajouter à `config/accounts/" + owner + ".yaml` (À VALIDER)** :"]
                L += [f"- {{platform: {p}, handle: {h}, status: \"À VALIDER\", note: \"découvert par le scout\"}}" for p, h in sugg]
            L.append("")
    p = OUTPUT_DIR / "discovery" / f"{day.isoformat()}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def run(platforms: list[str] | None = None, minutes: float | None = None) -> dict:
    s = settings()
    minutes = minutes or float(s.get("scout.minutes_per_platform", 8))
    st_path = Path(s.db_path).parent / "browser" / "scout_minutes.json"
    try:
        used = json.loads(st_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        used = {}
    today = dt.date.today().isoformat()
    cap = float(s.get("scout.max_minutes_per_day", 30))
    platforms = platforms or [p for p in PLATFORMS if p == "youtube" or has_session(p)]
    out = {}
    for p in platforms:
        if used.get(today, 0) + minutes > cap:
            logger.info("plafond quotidien de scout atteint (%s min)", cap)
            break
        try:
            items = browse(p, minutes)
            out[p] = save(list(items.values()))
        except Blocked as e:
            logger.error("⛔ %s", e)
            out[p] = {"blocked": str(e)}
        except Exception as e:
            logger.warning("scout %s KO : %s", p, e)
            out[p] = {"error": str(e)[:200]}
        used[today] = used.get(today, 0) + minutes
        st_path.parent.mkdir(parents=True, exist_ok=True)
        st_path.write_text(json.dumps(used))
    out["report"] = str(report())
    logger.info("scout : %s", out)
    return out
