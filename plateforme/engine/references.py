"""Vidéo de référence pour chaque vidéo planifiée : un VRAI lien d'une vidéo qui a marché avec le même
format/angle. Jamais d'URL inventée.

Ordre :
  1. outlier réel analysé (non mock) du même compte cible, même format visuel → « x7.2 vs médiane de @handle »
  2. recherche YouTube Shorts (yt-dlp, sans compte) sur `reference_query` (ou le sujet) : durée ≤ 90 s,
     pertinence par mots-clés, classement par vues
Cache : data/cache/references.json (une requête n'est cherchée qu'une fois).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from . import db, log
from .config import DATA_DIR

logger = log.get("references")
YTDLP = str(Path(sys.executable).parent / "yt-dlp")
CACHE = DATA_DIR / "cache" / "references.json"
STOP = set("""a an the of to in on for and or with my your i you me is are was it this that how what why from at by be
de la le les des du un une et en pour que qui dans sur mon ma mes ton ta tes je tu il est shorts short video vs""".split())


def _cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(c: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ÿ0-9$€]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def _flat(target: str, n: int) -> list[dict]:
    cmd = [YTDLP, "--flat-playlist", "-J", "--no-warnings", "--socket-timeout", "30", "--playlist-end", str(n), target]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "yt-dlp KO").strip()[-200:])
    return json.loads(p.stdout).get("entries") or []


def search_youtube(query: str, n: int = 40) -> list[dict]:
    from urllib.parse import quote_plus

    # 1) filtre « Shorts » de la recherche YouTube (sp=EgIQCQ%253D%253D) ; 2) recherche classique filtrée ≤ 90 s
    entries = _flat(f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp=EgIQCQ%253D%253D", n)
    entries += _flat(f"ytsearch{n}:{query} shorts", n)
    out, seen = [], set()
    for e in entries:
        if not e or e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        dur = e.get("duration")
        url = e.get("url") or ""
        if (dur and dur > 90) or (not dur and "/shorts/" not in url):
            continue
        out.append({"url": url.replace("watch?v=", "shorts/") if dur and dur <= 90 else url, "title": e.get("title"),
                    "channel": e.get("channel") or e.get("uploader"), "views": e.get("view_count") or 0, "duration": dur})
    return out


def best_youtube(query: str, min_views: int = 20_000) -> dict | None:
    cache = _cache()
    if query in cache:
        return cache[query]
    try:
        results = search_youtube(query)
    except Exception as e:
        logger.warning("recherche référence KO (%s) : %s", query, e)
        return None
    q = _words(query)
    scored = []
    from . import ethics

    for r in results:
        if ethics.check_text(r["title"] or ""):
            continue
        rel = len(q & _words(r["title"]))
        if rel >= (1 if len(q) <= 3 else 2) and r["views"] >= min_views:
            scored.append((rel, r["views"], r))
    best = None
    if scored:
        rel, views, r = max(scored, key=lambda x: (x[0], x[1]))
        best = {**r, "source": "youtube_search", "query": query,
                "why": f"{views:,} vues sur YouTube Shorts, même angle (« {query} »)".replace(",", " ")}
    cache[query] = best
    _save(cache)
    return best


def from_outliers(conn, entry: dict, used: set) -> dict | None:
    """Secours sans Claude : meilleur outlier ÉLIGIBLE (même funnel si possible) par mots communs avec le sujet."""
    pool = [p for p in _pool(conn, entry["account"], entry.get("slot_type", "proven"), entry.get("funnel_stage")) if p["url"] not in used]
    if not pool:
        return None
    q = _words(" ".join([entry.get("reference_query") or "", entry.get("subject") or ""]))
    best = max(pool, key=lambda p: ((p["funnel_stage"] == entry.get("funnel_stage")) * 2 + len(q & _words(p["title"] + " " + p["hook"])),
                                    p["replicability"] or 0, p["score"]))
    return {"url": best["url"], "video_id": best["id"], "title": best["title"], "channel": best["handle"], "platform": best["platform"], "source": "outlier",
            "funnel_stage": best["funnel_stage"], "replicability": best["replicability"], "hook_strength": best["hook_strength"],
            "success_driver": "technique", "why": f"x{best['score']} vs la médiane de @{best['handle']} · {best['why_it_works']}"}


PROFANITY = re.compile(r"(f[u*]+c?k|sh[i*]t|b[i*]tch|damn|\bass\b|wtf)", re.I)


def _pool(conn, owner: str, slot_type: str = "proven", funnel: str | None = None) -> list[dict]:
    """Vrais outliers ÉLIGIBLES (quality.eligibility) pour ce compte et ce type de slot."""
    from . import ethics, quality

    cats = ("other",) if slot_type == "test" else ("niche", "discovery")
    rows = conn.execute(
        f"""SELECT v.id, v.url, v.caption, v.outlier_score, v.eng_comment_rel, a.handle, a.platform, a.category, a.niche_label,
                  an.hook_text, an.hook_type, an.visual_format, an.script_structure, an.data, an.method FROM videos v
           JOIN accounts a ON a.id=v.account_id JOIN analyses an ON an.video_id=v.id
           WHERE v.is_mock=0 AND v.is_outlier=1 AND a.owner=? AND a.category IN ({",".join("?" * len(cats))})
           ORDER BY v.outlier_score DESC LIMIT 200""",
        (owner, *cats),
    ).fetchall()
    out = []
    for r in rows:
        title = (r["caption"] or "").split("\n")[0][:140]
        if ethics.check_text(r["caption"] or "") or PROFANITY.search(f"{title} {r['hook_text'] or ''}"):
            continue
        an = {**(db.loads(r["data"], {}) or {}), "method": r["method"]}
        ok, _ = quality.eligibility(an, r["platform"], slot_type, r["eng_comment_rel"], funnel)
        if not ok:
            continue
        out.append({"id": r["id"], "video_id": r["id"], "url": r["url"], "title": title, "handle": r["handle"], "platform": r["platform"],
                    "category": r["category"], "niche": r["niche_label"], "score": round(r["outlier_score"] or 0, 1),
                    "hook": (r["hook_text"] or "")[:140], "hook_type": r["hook_type"], "visual_format": r["visual_format"],
                    "structure": r["script_structure"], "funnel_stage": an.get("funnel_stage"),
                    "replicability": an.get("replicability"), "hook_strength": an.get("hook_strength"),
                    "conversion": an.get("conversion_mechanism"), "why_it_works": (an.get("why_it_works") or "")[:200]})
    return out


MATCH_PROMPT = """Pour chaque vidéo planifiée, choisis dans le POOL la vidéo réelle qui sert le mieux de RÉFÉRENCE au créateur :
même ÉTAPE DE FUNNEL (tofu/mofu/bofu) en priorité, puis même format / mécanique de hook / structure (le sujet peut différer).
Le pool ne contient que des vidéos qui ont marché grâce à leur TECHNIQUE (réplicables par un inconnu). Une BOFU doit avoir un
mécanisme de conversion. Slot « test » : vidéos d'autres niches qui utilisent le format d'origine.
N'utilise chaque vidéo du pool qu'une fois. Si rien n'est pertinent, mets null.

VIDÉOS PLANIFIÉES :
{entries}

POOL (vrais outliers, score = vues / médiane du compte) :
{pool}

Réponds en JSON : {{"<code>": {{"id": <id du pool ou null>, "why": "en français, 1 phrase : ce qu'il faut copier (format/hook/rythme)"}}}}"""


def match_llm(conn, entries: list[dict]) -> dict:
    from . import llm, principles

    out = {}
    for owner in sorted({e["account"] for e in entries}):
        es = [e for e in entries if e["account"] == owner]
        pool = {p["id"]: p for st in ("proven", "test") for p in _pool(conn, owner, st)}
        pool = list(pool.values())
        if not pool or not es:
            continue
        brief = [{"code": e["code"], "slot": e["slot_type"], "format": (e.get("format") or {}).get("name"),
                  "source_niche": (e.get("format") or {}).get("source_niche"), "subject": e.get("subject"),
                  "hook": (e.get("hooks") or [{}])[0].get("verbal"), "funnel_stage": e.get("funnel_stage"),
                  "visual_format": (e.get("edit_template") or {}).get("visual_format")} for e in es]
        res = llm.complete_json(principles.system_prompt("Tu es directeur artistique de contenu court."),
                                MATCH_PROMPT.format(entries=json.dumps(brief, ensure_ascii=False),
                                                    pool=json.dumps(pool, ensure_ascii=False)), max_tokens=6000)
        by_id = {p["id"]: p for p in pool}
        allowed = {e["code"]: {p["id"] for p in _pool(conn, owner, e["slot_type"], e.get("funnel_stage"))} for e in es}
        for code, m in (res or {}).items():
            p = by_id.get((m or {}).get("id"))
            if p and p["id"] in allowed.get(code, set()):
                out[code] = {"url": p["url"], "video_id": p["id"], "title": p["title"], "channel": p["handle"], "platform": p["platform"],
                             "source": "outlier+llm", "funnel_stage": p["funnel_stage"], "replicability": p["replicability"],
                             "hook_strength": p["hook_strength"], "success_driver": "technique",
                             "why": f"x{p['score']} vs la médiane de @{p['handle']}, {m.get('why', '')}"}
    return out


def attach(entries: list[dict]) -> int:
    """Ajoute entry['reference'] (en place) et met à jour la base. Renvoie le nombre trouvé."""
    from . import llm

    found = 0
    with db.session() as conn:
        used: set[str] = set()
        picked = {}
        if llm.available():
            try:
                picked = match_llm(conn, entries)
            except Exception as ex:
                logger.warning("matching LLM des références KO → heuristique : %s", ex)
        for e in entries:
            if (e.get("reference") or {}).get("source") == "veille":  # déjà choisie à l'écriture : on la garde
                used.add(e["reference"]["url"])
                found += 1
                continue
            ref = picked.get(e["code"])
            if ref and ref["url"] in used:
                ref = None
            ref = ref or from_outliers(conn, e, used)
            # plus de recherche YouTube générique : mieux vaut aucune référence qu'une référence sans qualité vérifiée
            e["reference"] = ref
            if ref:
                used.add(ref["url"])
                found += 1
            conn.execute("UPDATE calendar SET data=? WHERE code=?", (db.dumps({k: v for k, v in e.items() if k not in ("calendar_id",)}), e["code"]))
    logger.info("références : %d/%d vidéos avec un lien réel", found, len(entries))
    return found
