"""Liste des B-rolls à tourner : consolidée depuis le calendrier (plans « B-roll » + modèles de montage),
transformée par Claude en banque de plans RÉUTILISABLES groupés par lieu (on tourne une fois, on réutilise partout).
Stockée en base (broll_items) avec l'état « tourné » conservé entre deux régénérations."""
from __future__ import annotations

import datetime as dt
import difflib
import json
import re

from . import db, llm, log, principles
from .formats import SETUP_LABELS

logger = log.get("broll")

SCHEMA = """CREATE TABLE IF NOT EXISTS broll_items (
    id INTEGER PRIMARY KEY, setup TEXT, label TEXT, shot TEXT NOT NULL, duration_s REAL, tips TEXT,
    used_in TEXT, priority TEXT, done INTEGER DEFAULT 0, generated_at TEXT, source TEXT)"""

PROMPT = """Voici toutes les mentions de B-roll du calendrier du créateur (prochains {days} jours) :
{mentions}

Transforme-les en une BANQUE DE B-ROLLS RÉUTILISABLES à tourner en quelques sessions (on filme une fois, on réutilise dans
plusieurs vidéos). Regroupe par lieu de tournage parmi : {setups}. Fusionne les doublons, généralise ce qui peut l'être
(« gros plan Stripe sur le laptop » sert à 10 vidéos), garde le spécifique seulement s'il est indispensable.
Contraintes : plans réalistes pour le créateur (voir identité et contexte) ; jamais de données confidentielles ni de
personnes filmées sans autorisation ; flouter noms et données clients ; respecter l'identité et les règles éditoriales ;
plans verticaux 9:16, 2-5 s chacun, lumière naturelle si possible.
Priorité « haute » = utilisé dans beaucoup de vidéos ou dès la première semaine.

Renvoie un JSON : {{"groups": [{{"setup": "<un des lieux>", "items": [{{"shot": "description courte et filmable (en français)",
"duration_s": 3, "tips": "comment le filmer (cadrage, mouvement, lumière) en 1 phrase", "used_in": ["codes vidéo"],
"priority": "haute|moyenne|basse"}}]}}]}}, 30 à 45 plans au total."""


def _ensure(conn) -> None:
    conn.execute(SCHEMA)


def mentions(days: int = 14) -> list[dict]:
    today = dt.date.today()
    with db.session() as conn:
        rows = conn.execute("SELECT code, setup, data FROM calendar WHERE date BETWEEN ? AND ? ORDER BY date",
                            (today.isoformat(), (today + dt.timedelta(days=days)).isoformat())).fetchall()
    out = []
    for r in rows:
        e = db.loads(r["data"], {}) or {}
        for sh in e.get("shots") or []:
            if re.search(r"b-?roll", sh, re.I):
                out.append({"code": r["code"], "setup": r["setup"], "text": re.sub(r"^\s*b-?roll\s*:?\s*", "", sh, flags=re.I)})
        for b in (e.get("edit_template") or {}).get("broll") or []:
            out.append({"code": r["code"], "setup": r["setup"], "text": str(b)})
    return out


def _heuristic(ms: list[dict]) -> list[dict]:
    groups: dict[str, list] = {}
    seen: list[str] = []
    for m in ms:
        key = re.sub(r"\(.*?\)|\d+\s*s", "", m["text"].lower()).strip()
        match = next((s for s in seen if difflib.SequenceMatcher(None, s, key).ratio() > 0.75), None)
        if match:
            for g in groups.values():
                for it in g:
                    if it["_key"] == match and m["code"] not in it["used_in"]:
                        it["used_in"].append(m["code"])
            continue
        seen.append(key)
        groups.setdefault(m["setup"] or "bureau", []).append(
            {"_key": key, "shot": m["text"][:160], "duration_s": 3, "tips": "", "used_in": [m["code"]], "priority": "moyenne"})
    out = []
    for setup, items in groups.items():
        for it in items:
            it.pop("_key")
            it["priority"] = "haute" if len(it["used_in"]) >= 3 else "moyenne"
        out.append({"setup": setup, "items": items})
    return out


def generate(days: int = 14) -> dict:
    ms = mentions(days)
    source, groups = "heuristic", None
    if ms and llm.available():
        try:
            res = llm.complete_json(principles.system_prompt("Tu es le chef opérateur du créateur."),
                                    PROMPT.format(days=days, mentions=json.dumps(ms, ensure_ascii=False)[:30000],
                                                  setups=list(SETUP_LABELS)), max_tokens=8000)
            groups, source = res.get("groups"), "llm"
        except Exception as e:
            logger.warning("liste B-roll via Claude KO → heuristique : %s", e)
    if groups is None:
        groups = _heuristic(ms)
    now = dt.datetime.now().isoformat(timespec="seconds")
    with db.session() as conn:
        _ensure(conn)
        done_before = [r["shot"] for r in conn.execute("SELECT shot FROM broll_items WHERE done=1")]
        conn.execute("DELETE FROM broll_items")
        n = 0
        for g in groups:
            setup = g.get("setup") if g.get("setup") in SETUP_LABELS else "bureau"
            for it in g.get("items") or []:
                shot = str(it.get("shot", "")).strip()
                if not shot:
                    continue
                done = any(difflib.SequenceMatcher(None, shot.lower(), d.lower()).ratio() > 0.8 for d in done_before)
                conn.execute("INSERT INTO broll_items(setup, label, shot, duration_s, tips, used_in, priority, done, generated_at, source) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (setup, SETUP_LABELS.get(setup, setup), shot, it.get("duration_s"), it.get("tips"),
                              json.dumps(it.get("used_in") or []), it.get("priority") or "moyenne", int(done), now, source))
                n += 1
    logger.info("B-roll : %d plans (%s)", n, source)
    return {"count": n, "source": source}


def load() -> dict:
    with db.session() as conn:
        _ensure(conn)
        rows = conn.execute("SELECT * FROM broll_items ORDER BY CASE priority WHEN 'haute' THEN 0 WHEN 'moyenne' THEN 1 ELSE 2 END, id").fetchall()
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["setup"], {"setup": r["setup"], "label": r["label"], "items": []})
        g["items"].append({"id": r["id"], "shot": r["shot"], "duration_s": r["duration_s"], "tips": r["tips"],
                           "used_in": json.loads(r["used_in"] or "[]"), "priority": r["priority"], "done": bool(r["done"])})
    order = sorted(groups.values(), key=lambda g: -len(g["items"]))
    return {"generated_at": rows[0]["generated_at"] if rows else None, "source": rows[0]["source"] if rows else None, "groups": order}


def set_done(item_id: int, done: bool) -> None:
    with db.session() as conn:
        _ensure(conn)
        conn.execute("UPDATE broll_items SET done=? WHERE id=?", (int(done), item_id))


def markdown() -> str:
    d = load()
    L = ["# B-rolls à tourner", ""]
    for g in d["groups"]:
        L += [f"## {g['label']}", ""]
        for it in g["items"]:
            L.append(f"- [{'x' if it['done'] else ' '}] **{it['shot']}** ({it['duration_s'] or 3} s, priorité {it['priority']})"
                     + (f", {it['tips']}" if it.get("tips") else "") + f" · {len(it['used_in'])} vidéo(s)")
        L.append("")
    return "\n".join(L)
