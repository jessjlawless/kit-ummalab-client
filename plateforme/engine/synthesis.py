"""Module 4, Synthèse hebdomadaire (par compte).

- Ma niche : top hooks, formats visuels, structures, CTA (pondérés par score outlier).
- Autres niches : formats qui surperforment → 1 format test adapté par compte et par semaine
  (LLM si dispo, sinon format test de la banque + exemples d'inspiration réels).
- Mes stats (module 6) : médiane, perf par format ; promotion test → éprouvé si
  ≥ promotion.min_videos vidéos dépassent ma médiane de promotion.uplift_pct %.
- Identité/halal : un format qui repose sur la musique est signalé et adapté sans musique.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from collections import defaultdict

from . import challenge, db, ethics, llm, log, principles
from .config import settings
from .formats import infer_visual_format, proven_formats, test_formats
from .planner import default_week_start, week_index

logger = log.get("synthesis")


def _rank(rows, field: str, top_n: int) -> list[dict]:
    agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "score_sum": 0.0, "examples": []})
    for r in rows:
        val = r[field] or "other"
        a = agg[val]
        a["count"] += 1
        a["score_sum"] += r["outlier_score"] or 0
        if len(a["examples"]) < 3:
            a["examples"].append({"hook": r["hook_text"], "url": r["url"], "score": r["outlier_score"], "handle": r["handle"]})
    out = [{"value": k, "count": v["count"], "avg_score": round(v["score_sum"] / v["count"], 2),
            "weight": round(v["score_sum"], 2), "examples": v["examples"]} for k, v in agg.items()]
    return sorted(out, key=lambda x: -x["weight"])[:top_n]


def _analysed(conn, owner: str, category: str):
    """Outliers analysés, en excluant ceux dont le succès ne vient pas de la technique (célébrité, animal, son…)."""
    rows = _analysed_all(conn, owner, category)
    keep = []
    for r in rows:
        drv = (db.loads(r["data"], {}) or {}).get("success_driver")
        if drv in (None, "technique"):
            keep.append(r)
    return keep


def _analysed_all(conn, owner: str, category: str):
    return conn.execute(
        """SELECT v.url, v.outlier_score, v.is_mock, a.handle, a.niche_label, an.hook_text, an.hook_type, an.visual_format,
                  an.script_structure, an.cta_type, an.data, an.method
           FROM analyses an JOIN videos v ON v.id=an.video_id JOIN accounts a ON a.id=v.account_id
           WHERE a.owner=? AND (a.category=? OR (?='niche' AND a.category='discovery')) ORDER BY v.outlier_score DESC""",
        (owner, category, category),
    ).fetchall()


def my_stats(conn, account: str, include_mock: bool = False) -> dict:
    s = settings()
    uplift = float(s.get("promotion.uplift_pct", 20)) / 100
    min_n = int(s.get("promotion.min_videos", 3))
    rows = conn.execute(
        f"SELECT format_id, views FROM my_videos WHERE account=? AND views IS NOT NULL {'' if include_mock else 'AND is_mock=0'}",
        (account,),
    ).fetchall()
    if not rows:
        return {"n_videos": 0, "median_views": None, "by_format": [], "promotions": []}
    med = statistics.median(r["views"] for r in rows)
    by: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        by[r["format_id"] or "inconnu"].append(r["views"])
    tests = test_formats(account)
    promos_row = {r["format_id"] for r in conn.execute("SELECT format_id FROM format_status WHERE account=? AND status='proven'", (account,))}
    by_format, promotions = [], []
    for fid, views in by.items():
        above = sum(1 for v in views if v >= med * (1 + uplift))
        by_format.append({"format_id": fid, "n": len(views), "median_views": statistics.median(views),
                          "uplift_pct": round((statistics.median(views) / med - 1) * 100, 1) if med else None,
                          "n_above_threshold": above})
        if fid in tests or fid.startswith("llm_"):
            promoted = above >= min_n
            promotions.append({"format_id": fid, "n_above": above, "required": min_n,
                               "status": "promu → éprouvé" if promoted else "en test"})
            if promoted and fid not in promos_row:
                data = tests.get(fid) or {}
                conn.execute(
                    "INSERT INTO format_status(account, format_id, status, origin, data) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(account, format_id) DO UPDATE SET status='proven', updated_at=datetime('now','localtime')",
                    (account, fid, "proven", "promoted", db.dumps({k: v for k, v in data.items() if k != "variants"})),
                )
                logger.info("🎉 format %s promu en éprouvé pour %s (%d vidéos > médiane +%d%%)", fid, account, above, uplift * 100)
    return {"n_videos": len(rows), "median_views": med, "by_format": sorted(by_format, key=lambda x: -(x["uplift_pct"] or 0)),
            "promotions": promotions, "rule": f"≥{min_n} vidéos ≥ médiane +{int(uplift * 100)}%"}


TEST_FORMAT_PROMPT = """Voici les formats d'AUTRES niches qui surperforment cette semaine (score = vues / médiane du compte) :
{others}

Compte cible : « {name} », {niche}
Formats déjà éprouvés sur ce compte (ne pas reprendre) : {proven}

Choisis LE format le plus prometteur et adapte-le à ce compte. Si le format original repose sur une musique ou un son
tendance, adapte-le SANS musique (voix, rythme des coupes, texte à l'écran, sound design neutre).
{challenge}
Renvoie un JSON :
{{"id": "llm_<snake_case>", "name": "...", "source_niche": "...", "source_description": "...", "adaptation": "...",
  "inspired_by": ["urls des exemples"], "script_structure": "...",
  "edit_template": {{"format": "...", "pacing": "...", "subtitles": "...", "broll": ["..."], "on_screen_text": "...",
                    "music": "AUCUNE musique, voix + sound design neutre sans instruments"}},
  "principles": ["IDs"],
  "variants": [7 objets (un par jour, hooks TOUS différents) : {{"subject": "...", "hooks": ["A", "B"], "text_hook": "...",
     "visual_hook": "...", "script": "130-160 mots oral FR", "cta": "...", "cta_type": "...",
     "setup": "bureau|chambre|exterieur|fac|cuisine|voiture|salle_sport|ecran", "shots": ["..."], "principles": ["IDs"]}}]}}"""


def _test_format_llm(account: str, others: list[dict], proven: dict, week_start: dt.date | None = None) -> dict | None:
    cfg = settings().accounts.get(account, {})
    prompt = TEST_FORMAT_PROMPT.format(
        others=json.dumps(others, ensure_ascii=False)[:8000], name=cfg.get("name"), niche=cfg.get("niche"),
        proven=list(proven), challenge=_challenge_rule(account, week_start or default_week_start()),
    )
    tf = llm.complete_json(principles.system_prompt("Tu es stratège de formats courts."), prompt, max_tokens=8000)
    if len(tf.get("variants") or []) < 7:
        raise ValueError("format test LLM incomplet")
    if account == "personal" and not challenge.active_in(week_start or default_week_start()):
        bad = challenge.format_mentions(tf) + [m for v in tf["variants"] for m in challenge.mentions(v)]
        if bad:
            raise ValueError(f"format test écrit pour le défi alors qu'il n'est pas lancé : {bad[:5]}")
    tf["edit_template"] = ethics.enforce_no_music(tf.get("edit_template"))
    tf["origin"] = "llm"
    flagged = [v for v in tf["variants"] if ethics.check(v)]
    if flagged:
        raise ValueError(f"format test rejeté par le garde-fou éthique ({len(flagged)} variantes)")
    return tf


def _challenge_rule(account: str, week_start: dt.date) -> str:
    if account != "personal":
        return ""
    if challenge.active_in(week_start):
        return "Les vidéos du compte affichent « Jour {jour}/90 » (placeholder {jour} rendu par le moteur)."
    return challenge.NO_CHALLENGE_RULE


def run_account(conn, account: str, week_start: dt.date, include_mock: bool = True) -> dict:
    top_n = int(settings().get("synthesis.top_n", 5))
    niche = _analysed(conn, account, "niche")
    other = _analysed(conn, account, "other")
    if not include_mock:
        niche = [r for r in niche if not r["is_mock"]]
        other = [r for r in other if not r["is_mock"]]
    all_rows = list(niche) + list(other)
    mock_share = round(sum(r["is_mock"] for r in all_rows) / len(all_rows), 2) if all_rows else None

    syn: dict = {
        "account": account, "week_start": week_start.isoformat(),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "data_quality": {"niche_outliers_analysed": len(niche), "other_outliers_analysed": len(other),
                         "mock_share": mock_share,
                         "methods": dict(sorted({m: sum(1 for r in all_rows if r["method"] == m) for m in {r["method"] for r in all_rows}}.items()))},
        "niche": {
            "top_hook_types": _rank(niche, "hook_type", top_n),
            "top_visual_formats": _rank(niche, "visual_format", top_n),
            "top_structures": _rank(niche, "script_structure", top_n),
            "top_ctas": _rank(niche, "cta_type", top_n),
            "top_hooks": [{"hook": r["hook_text"], "url": r["url"], "score": r["outlier_score"], "handle": r["handle"],
                           "hook_type": r["hook_type"]} for r in niche[:10]],
        },
    }
    # autres niches : couples (format visuel, structure)
    combos: dict[tuple, list] = defaultdict(list)
    for r in other:
        combos[(r["visual_format"] or "other", r["script_structure"] or "other")].append(r)
    top_other = sorted(
        ({"visual_format": k[0], "script_structure": k[1], "count": len(v),
          "avg_score": round(statistics.mean(x["outlier_score"] or 0 for x in v), 2),
          "niches": sorted({x["niche_label"] or "?" for x in v}),
          "relies_on_music": any((db.loads(x["data"], {}) or {}).get("relies_on_music") for x in v),
          "examples": [{"url": x["url"], "hook": x["hook_text"], "handle": x["handle"], "score": x["outlier_score"]} for x in v[:3]]}
         for k, v in combos.items()),
        key=lambda x: -(x["avg_score"] * x["count"]),
    )[:top_n]
    for f in top_other:
        if f["relies_on_music"] and ethics.islamic():
            f["halal_adaptation"] = "repose sur la musique → à adapter sans musique (voix, rythme des coupes, texte, SFX neutres)"
    syn["other_niches"] = {"top_formats": top_other}

    # inspiration par format visuel (URLs réelles des outliers, pas les mocks)
    insp: dict[str, list] = defaultdict(list)
    for r in all_rows:
        if not r["is_mock"] and r["visual_format"] and len(insp[r["visual_format"]]) < 5:
            insp[r["visual_format"]].append(r["url"])
    syn["inspiration_by_visual_format"] = dict(insp)

    # mes stats + promotions
    syn["my_stats"] = my_stats(conn, account, include_mock=include_mock)
    syn["promotions"] = syn["my_stats"].get("promotions", [])

    # classement des formats éprouvés : poids du format visuel dans ma niche + mon uplift
    fmts = proven_formats(conn, account)
    vf_weight = {x["value"]: x["weight"] for x in syn["niche"]["top_visual_formats"]}
    my_uplift = {x["format_id"]: (x["uplift_pct"] or 0) for x in syn["my_stats"].get("by_format", [])}
    syn["format_ranking"] = sorted(fmts, key=lambda f: -(vf_weight.get(infer_visual_format(fmts[f]), 0) + my_uplift.get(f, 0) / 10))

    # format test de la semaine
    tf = None
    if llm.available() and top_other:
        try:
            tf = _test_format_llm(account, top_other, fmts, week_start)
        except Exception as e:
            logger.warning("format test LLM KO (%s) → banque : %s", account, e)
    if tf is None:
        bank = list(test_formats(account).values())
        if bank:
            tf = dict(bank[week_index(week_start) % len(bank)])
            tf["origin"] = "bank"
            tf["inspired_by"] = [e["url"] for f in top_other[:2] for e in f["examples"] if "mock" not in (e["url"] or "")][:4]
    syn["test_format"] = tf
    syn["test_format_summary"] = {k: (tf or {}).get(k) for k in ("id", "name", "source_niche", "adaptation", "origin", "inspired_by")}

    conn.execute("INSERT INTO syntheses(week_start, account, data) VALUES (?,?,?) "
                 "ON CONFLICT(week_start, account) DO UPDATE SET data=excluded.data, created_at=datetime('now','localtime')",
                 (week_start.isoformat(), account, db.dumps(syn)))
    return syn


def synthesis_md(syn: dict) -> str:
    n = syn["niche"]
    dq = syn["data_quality"]
    L = [f"# Synthèse, {syn['account']}, semaine du {syn['week_start']}", "",
         f"Données : {dq['niche_outliers_analysed']} outliers niche, {dq['other_outliers_analysed']} autres niches, "
         f"part mock : {dq['mock_share']}, méthodes : {dq['methods']}", ""]
    if dq.get("mock_share"):
        L += ["> ⚠ Une partie des données est MOCK : les tendances ci-dessous servent à tester le pipeline, pas à décider.", ""]
    for title, key in (("Types de hook", "top_hook_types"), ("Formats visuels", "top_visual_formats"),
                       ("Structures", "top_structures"), ("CTA", "top_ctas")):
        L += [f"## {title}", ""] + [f"- **{x['value']}**, {x['count']} vidéos, score moyen x{x['avg_score']}" for x in n[key]] + [""]
    L += ["## Meilleurs hooks de la niche", ""] + [f"- x{h['score']} @{h['handle']}, « {h['hook']} » {h['url']}" for h in n["top_hooks"]] + [""]
    L += ["## Autres niches, formats qui surperforment", ""]
    for f in syn["other_niches"]["top_formats"]:
        L.append(f"- **{f['visual_format']} / {f['script_structure']}** ({', '.join(f['niches'])}), x{f['avg_score']} sur {f['count']} vidéos"
                 + (f", {f['halal_adaptation']}" if f.get("halal_adaptation") else ""))
    tf = syn.get("test_format_summary") or {}
    L += ["", "## Format test de la semaine", "", f"**{tf.get('name')}** (niche : {tf.get('source_niche')}, origine : {tf.get('origin')})",
          "", f"{tf.get('adaptation') or ''}", ""]
    ms = syn["my_stats"]
    L += ["## Mes vidéos", "", f"{ms['n_videos']} vidéos, médiane {ms['median_views']} vues. Règle de promotion : {ms.get('rule', '-')}", ""]
    L += [f"- {x['format_id']} : {x['n']} vidéos, médiane {x['median_views']}, {x['uplift_pct']}% vs ma médiane" for x in ms.get("by_format", [])]
    L += [""] + [f"- Promotion {p['format_id']} : {p['n_above']}/{p['required']} → {p['status']}" for p in syn.get("promotions", [])]
    return "\n".join(L)


def run(week_start: dt.date | None = None, include_mock: bool = True) -> dict:
    from .config import OUTPUT_DIR

    week_start = week_start or default_week_start()
    out = {}
    with db.session() as conn:
        for account in settings().accounts:
            syn = run_account(conn, account, week_start, include_mock=include_mock)
            p = OUTPUT_DIR / "synthesis" / week_start.isoformat() / f"{account}.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(synthesis_md(syn), encoding="utf-8")
            (p.with_suffix(".json")).write_text(json.dumps(syn, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            out[account] = syn
            logger.info("synthèse %s → %s (format test : %s)", account, p, (syn.get("test_format") or {}).get("name"))
        db.log_run(conn, "synthesis", "synthesis", "ok", week_start.isoformat())
    return out
