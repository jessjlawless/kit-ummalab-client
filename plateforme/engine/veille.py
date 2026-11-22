"""Veille de la niche, obligatoire avant d'écrire des idées.

1. discover()     : Claude cherche sur le web les créateurs qui cartonnent dans la niche (TikTok, YouTube),
                    on garde ceux dont yt-dlp lit vraiment les vidéos → config/accounts/<compte>.yaml
2. scraper / outliers / analysis (déjà dans le moteur) : reels ≥ 3x la médiane du compte, hook décortiqué
3. youtube_long() : vidéos YouTube longues de la niche qui font ≥ 3x la médiane de leur chaîne,
                    transcription (sous-titres YouTube, gratuit) → 3 à 5 grandes idées chacune, à refaire en reels
4. sources()      : le bloc « SOURCES » injecté dans le planner : chaque vidéo part d'un reel gagnant (hook + format)
                    et d'une grande idée, avec les 2 liens dans la fiche.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

from . import db, llm, log, principles
from .config import CONFIG_DIR, settings
from .scraper import ytdlp_backend

logger = log.get("veille")
YTDLP = ytdlp_backend.YTDLP
MIN_ACCOUNTS = 5

SCHEMA = """CREATE TABLE IF NOT EXISTS big_ideas (
    id          INTEGER PRIMARY KEY,
    owner       TEXT NOT NULL,
    video_id    TEXT NOT NULL,
    url         TEXT,
    title       TEXT,
    channel     TEXT,
    views       INTEGER,
    score       REAL,
    idea        TEXT NOT NULL,
    data        TEXT,
    used        INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(owner, video_id, idea)
)"""


def _system() -> str:
    return principles.system_prompt("Tu fais la veille concurrentielle d'un créateur de contenu. Tu ne cites que des comptes "
                                    "et des vidéos qui existent vraiment, vérifiés par ta recherche web.")


def _niche(account: str) -> str:
    cfg = settings().accounts.get(account, {})
    return f"{cfg.get('name', '')} : {cfg.get('niche', '')}"


# ------------------------------------------------------------------ 1. comptes de la niche
DISCOVER = """Niche du créateur : {niche}
Contexte (qui il est, son offre, son audience) :
{ctx}

Cherche sur le web (WebSearch) {want} créateurs qui font BEAUCOUP de vues en vidéo courte avec un contenu proche de cette niche
et qui parlent à la même audience : moitié francophones, moitié anglophones (marché US d'abord). Uniquement des comptes
TikTok ou des chaînes YouTube qui publient des Shorts, actifs ces 3 derniers mois, faits par de vrais créateurs face caméra
(pas de pages de repost, pas de marques). Vérifie chaque @ en ouvrant sa page.

Renvoie UNIQUEMENT un tableau JSON :
[{{"platform": "tiktok" | "youtube", "handle": "sans @, exactement comme dans l'URL", "lang": "fr" | "en",
   "why": "1 phrase : pourquoi c'est la bonne audience"}}]"""


def discover(account: str = "personal", want: int = 14, rounds: int = 2) -> list[dict]:
    kept, rejected = [], []
    for _ in range(rounds):
        prompt = DISCOVER.format(niche=_niche(account), ctx=principles.context_text(6000), want=want)
        if rejected or kept:
            prompt += ("\n\nDéjà testés, ne les repropose pas : " + ", ".join(f"@{h}" for h in rejected + [k["handle"] for k in kept])
                       + ". Ceux-là n'avaient pas de vidéos lisibles : propose des comptes plus gros et plus actifs.")
        cands = llm.web_json(_system(), prompt)
        _verify(cands, kept, rejected)
        if len(kept) >= MIN_ACCOUNTS:
            break
    if kept:
        _save_accounts(account, kept)
    return kept


def _verify(cands, kept: list[dict], rejected: list[str]) -> None:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=120)
    for c in cands if isinstance(cands, list) else []:
        plat, handle = c.get("platform"), str(c.get("handle") or "").strip().lstrip("@")
        if plat not in ("tiktok", "youtube") or not handle or handle in rejected or any(k["handle"] == handle for k in kept):
            continue
        try:
            vids = [v for v in ytdlp_backend.fetch(plat, handle, since, 15) if v.get("views")]
        except Exception as e:
            logger.info("@%s (%s) écarté : %s", handle, plat, str(e)[:120])
            rejected.append(handle)
            continue
        if len(vids) < 5:
            logger.info("@%s (%s) écarté : %d vidéos lisibles", handle, plat, len(vids))
            rejected.append(handle)
            continue
        med = statistics.median(v["views"] for v in vids)
        kept.append({"platform": plat, "handle": handle, "status": "vérifié",
                     "note": f"{c.get('lang', '')}, médiane {int(med)} vues, {str(c.get('why', ''))[:120]}"})
        logger.info("@%s (%s) gardé : médiane %d vues", handle, plat, med)


def _save_accounts(account: str, accounts: list[dict]) -> None:
    p = CONFIG_DIR / "accounts" / f"{account}.yaml"
    text = p.read_text(encoding="utf-8")
    lines = ["reference_accounts:", f"  # trouvés et vérifiés par la veille le {dt.date.today():%d/%m/%Y}"]
    for a in accounts:
        lines.append("  - " + json.dumps(a, ensure_ascii=False))
    block = "\n".join(lines) + "\n\n"
    new = re.sub(r"reference_accounts:.*?(?=\n# Comptes d'AUTRES|\nother_niche_accounts:)", block.rstrip("\n") + "\n",
                 text, count=1, flags=re.S)
    p.write_text(new, encoding="utf-8")
    import engine.config as cfgmod
    cfgmod._settings = None  # relit le compte au prochain settings()


# ------------------------------------------------------------------ 3. vidéos YouTube longues → grandes idées
QUERIES = """Niche : {niche}
Donne 6 recherches YouTube (3 en français, 3 en anglais, 3 à 6 mots) qui trouvent les vidéos LONGUES les plus vues
que l'audience de ce créateur regarde (les problèmes, envies et questions de son client idéal, pas le métier du créateur).
Renvoie UNIQUEMENT un tableau JSON de chaînes."""

IDEAS = """Vidéo YouTube longue qui a surperformé (x{score:.1f} la médiane de sa chaîne {channel}) : « {title} ».
Niche du créateur qui va s'en inspirer : {niche}

Transcription (extrait) :
{transcript}

Sors les 3 à 5 GRANDES IDÉES de cette vidéo qui peuvent devenir chacune un reel de 30 à 60 s pour l'audience du créateur.
Une grande idée = une thèse forte, contre-intuitive ou très concrète, tirée de la vidéo (pas un résumé).
Renvoie UNIQUEMENT un tableau JSON :
[{{"idea": "la grande idée en 1 phrase", "why": "pourquoi elle accroche (1 phrase)",
   "reel_angle": "comment le créateur la refait en reel pour SA niche (1 phrase)", "funnel_stage": "tofu" | "mofu" | "bofu"}}]"""


def _ytdlp_json(args: list[str], timeout: int = 300) -> dict:
    p = subprocess.run([YTDLP, "--no-warnings", "--ignore-errors", "-J", *args], capture_output=True, text=True, timeout=timeout)
    return json.loads(p.stdout or "{}")


def _subtitles(video_id: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([YTDLP, "--no-warnings", "--skip-download", "--write-subs", "--write-auto-subs",
                        "--sub-langs", "fr.*,en.*,fr,en", "--sub-format", "vtt", "-o", f"{d}/%(id)s.%(ext)s",
                        f"https://www.youtube.com/watch?v={video_id}"], capture_output=True, text=True, timeout=300)
        files = sorted(Path(d).glob("*.vtt"), key=lambda f: (".fr" not in f.name, f.name))
        if not files:
            return ""
        out, last = [], ""
        for line in files[0].read_text(encoding="utf-8", errors="ignore").splitlines():
            line = re.sub(r"<[^>]+>", "", line).strip()
            if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:")) or line == last:
                continue
            out.append(line)
            last = line
        return " ".join(out)


def _audio_transcript(video_id: str, minutes: int = 15) -> str:
    """Plan B quand YouTube refuse les sous-titres (429) : les 15 premières minutes de son, transcrites en local."""
    from .analysis import transcribe
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([YTDLP, "--no-warnings", "-f", "bestaudio[ext=m4a]/bestaudio", "--download-sections", f"*0-{minutes * 60}",
                        "-o", f"{d}/a.%(ext)s", f"https://www.youtube.com/watch?v={video_id}"],
                       capture_output=True, text=True, timeout=900)
        files = list(Path(d).glob("a.*"))
        if not files:
            return ""
        try:
            return (transcribe(str(files[0])) or {}).get("text") or ""
        except Exception as ex:
            logger.warning("transcription de %s KO : %s", video_id, ex)
            return ""


def youtube_long(account: str = "personal", top: int = 8, min_score: float = 3.0) -> int:
    niche = _niche(account)
    queries = llm.complete_json(_system(), QUERIES.format(niche=niche))
    found: dict[str, dict] = {}
    for q in queries[:6] if isinstance(queries, list) else []:
        for e in (_ytdlp_json(["--flat-playlist", f"ytsearch15:{q}"]).get("entries") or []):
            if e and (e.get("duration") or 0) >= 300 and e.get("view_count") and e.get("channel_id"):
                found[e["id"]] = e
    by_channel: dict[str, list[dict]] = {}
    for e in found.values():
        by_channel.setdefault(e["channel_id"], []).append(e)
    scored = []
    for cid, es in sorted(by_channel.items(), key=lambda kv: -max(x["view_count"] for x in kv[1]))[:15]:
        chan = _ytdlp_json(["--flat-playlist", "--playlist-end", "20", f"https://www.youtube.com/channel/{cid}/videos"])
        views = [x.get("view_count") for x in chan.get("entries") or [] if x and x.get("view_count")]
        if len(views) < 5:
            continue
        med = statistics.median(views)
        for e in es:
            scored.append({**e, "score": e["view_count"] / med if med else 0})
    scored.sort(key=lambda e: -e["score"])
    picked = [e for e in scored if e["score"] >= min_score][:top] or scored[: max(3, top // 2)]
    with db.session() as conn:
        conn.execute(SCHEMA)
        done = {r[0] for r in conn.execute("SELECT DISTINCT video_id FROM big_ideas WHERE owner=?", (account,))}
    n = 0
    for e in [x for x in picked if x["id"] not in done]:  # pas de session ouverte pendant les appels longs (sinon la base reste verrouillée)
        tr = _subtitles(e["id"]) or _audio_transcript(e["id"])
        if len(tr) < 500:
            logger.info("%s : ni sous-titres ni son exploitable", e["id"])
            continue
        try:
            ideas = llm.complete_json(_system(), IDEAS.format(score=e["score"], channel=e.get("channel"), title=e.get("title"),
                                                              niche=niche, transcript=tr[:24000]))
        except Exception as ex:
            logger.warning("grandes idées de %s KO : %s", e["id"], ex)
            continue
        with db.session() as conn:
            conn.execute(SCHEMA)
            for it in ideas if isinstance(ideas, list) else []:
                if not it.get("idea"):
                    continue
                conn.execute("INSERT OR IGNORE INTO big_ideas (owner, video_id, url, title, channel, views, score, idea, data) "
                             "VALUES (?,?,?,?,?,?,?,?,?)",
                             (account, e["id"], f"https://www.youtube.com/watch?v={e['id']}", e.get("title"), e.get("channel"),
                              e.get("view_count"), round(e["score"], 1), it["idea"], db.dumps(it)))
                n += 1
        logger.info("« %s » (x%.1f) : %d grandes idées", e.get("title"), e["score"], len(ideas or []))
    return n


# ------------------------------------------------------------------ 4. bloc SOURCES pour le planner
def sources(account: str = "personal", n_reels: int = 15, n_ideas: int = 24) -> tuple[str, dict, dict]:
    """(texte pour le prompt, {R1: reel}, {I1: idée})."""
    reels, ideas = {}, {}
    with db.session() as conn:
        conn.execute(SCHEMA)
        rows = conn.execute(
            "SELECT v.id, v.url, v.platform, v.views, v.outlier_score, a.handle, an.data FROM videos v "
            "JOIN accounts a ON a.id=v.account_id JOIN analyses an ON an.video_id=v.id "
            "WHERE a.owner=? AND a.category IN ('niche','discovery') AND v.is_outlier=1 AND v.is_mock=0 AND an.method='llm' "
            "ORDER BY v.outlier_score DESC", (account,)).fetchall()
        for r in rows:
            d = db.loads(r["data"], {}) or {}
            if (d.get("replicability") or 0) < 5 or d.get("success_driver") in ("celebrity", "brand_ip", "shock"):
                continue
            reels[f"R{len(reels) + 1}"] = {
                "video_id": r["id"], "url": r["url"], "platform": r["platform"], "handle": r["handle"], "views": r["views"],
                "score": round(r["outlier_score"] or 0, 1), "hook_text": d.get("hook_text"), "text_hook": d.get("text_hook"),
                "visual_hook": d.get("visual_hook"), "hook_type": d.get("hook_type"), "visual_format": d.get("visual_format"),
                "script_structure": d.get("script_structure"), "funnel_stage": d.get("funnel_stage"), "why": d.get("why_it_works")}
            if len(reels) >= n_reels:
                break
        for r in conn.execute("SELECT * FROM big_ideas WHERE owner=? ORDER BY used, score DESC LIMIT ?", (account, n_ideas)):
            d = db.loads(r["data"], {}) or {}
            ideas[f"I{len(ideas) + 1}"] = {"id": r["id"], "url": r["url"], "title": r["title"], "channel": r["channel"],
                                          "views": r["views"], "score": r["score"], "idea": r["idea"],
                                          "reel_angle": d.get("reel_angle"), "funnel_stage": d.get("funnel_stage")}
    if not reels and not ideas:
        return "", {}, {}
    lines = ["SOURCES DE LA VEILLE (obligatoires) : chaque vidéo part d'UN reel gagnant de la niche (Rn) ET d'UNE grande idée (In).",
             "- Hook A = le MODÈLE du hook de Rn (même mécanique, même longueur, même structure de phrase), réécrit pour la niche",
             "  du créateur. Hook B = autre mécanique. Texte écran et 1re seconde = ceux de Rn adaptés.",
             "- Format, structure et rythme = ceux de Rn. Le fond = la grande idée In, refaite pour l'audience du créateur.",
             "- N'utilise jamais deux fois la même source dans la journée, ni deux idées de la même vidéo longue (même titre).",
             "  Renvoie \"source_reel\": \"Rn\" et \"source_idea\": \"In\". Ne recopie JAMAIS les codes Rn / In dans les textes :",
             "  écris « le reel de @compte » ou le titre de la vidéo longue.",
             "", "Reels gagnants :"]
    for k, r in reels.items():
        lines.append(f"{k} · @{r['handle']} ({r['platform']}) x{r['score']} · {r['funnel_stage']} · hook : « {r['hook_text']} »"
                     f" · texte écran : « {r['text_hook'] or ''} » · 1re seconde : {r['visual_hook']} · format {r['visual_format']},"
                     f" structure {r['script_structure']} · pourquoi : {r['why']}")
    lines += ["", "Grandes idées (vidéos YouTube longues qui ont surperformé) :"]
    for k, i in ideas.items():
        lines.append(f"{k} · « {i['title']} » ({i['channel']}, x{i['score']}) · {i['funnel_stage']} · idée : {i['idea']}"
                     f" · en reel : {i['reel_angle']}")
    return "\n".join(lines)[:14000], reels, ideas


def mark_used(idea_ids: list[int], conn=None) -> None:
    """conn : la connexion déjà ouverte par l'appelant (sinon une 2e connexion attend son verrou d'écriture)."""
    if conn is None:
        with db.session() as c:
            return mark_used(idea_ids, c)
    conn.execute(SCHEMA)
    conn.executemany("UPDATE big_ideas SET used=used+1 WHERE id=?", [(i,) for i in idea_ids])


def status(account: str = "personal") -> dict:
    _, reels, ideas = sources(account)
    return {"reels": len(reels), "ideas": len(ideas),
            "accounts": len(settings().accounts.get(account, {}).get("reference_accounts") or [])}


# ------------------------------------------------------------------ tout enchaîner
def run(account: str = "personal", rediscover: bool = False, analyze_limit: int = 15) -> dict:
    from . import analysis, outliers, scraper

    out = {}
    accs = settings().accounts.get(account, {}).get("reference_accounts") or []
    if rediscover or len(accs) < MIN_ACCOUNTS:
        out["comptes"] = len(discover(account))
    out["scrape"] = scraper.run(only_owner=account)
    out["outliers"] = outliers.run()
    out["analyse"] = analysis.run(limit=analyze_limit)
    out["grandes_idees"] = youtube_long(account)
    out["sources"] = status(account)
    return out
