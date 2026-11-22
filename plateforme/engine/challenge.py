"""Défi 90 jours : date de lancement choisie par le créateur (config/engine.yaml → challenge.start_date).
start_date: null = pas encore lancé → le contenu perso n'en parle pas du tout (ni « Day X », ni compteur, ni objectif).
Le défi n'est actif qu'entre le Jour 1 et le dernier jour : avant/après, même règle que null."""
from __future__ import annotations

import datetime as dt
import re

from . import db
from .config import CONFIG_DIR, settings


# principes de la skill propres au défi (compteur Day X/90, objectif public chiffré, enjeu sur 90 jours)
CHALLENGE_PRINCIPLES = {"D1", "D2", "D4", "P37"}

# ce qui trahit le défi dans une vidéo : placeholders, « Day 3/90 », « 90-day », « challenge », objectif chiffré…
_MENTION_RE = re.compile(
    r"\{(?:jour|jour_suivant|total|objectif)\}"
    r"|\b(?:day|jour)\s*(?:\d+|x)\s*(?:/|of|sur)\s*90\b"
    # « 90 jours » seul n'est pas le défi (« 90 jours pour lancer ton offre ») : seul « défi/challenge 90 jours » compte
    r"|\b90[\s-]?(?:day|days|jours?)[\s-]+(?:challenge|d[ée]fi)\b"
    r"|\bchallenge\b|\bd[ée]fi\b|\bcountdown\b|compte à rebours"
    r"|^\s*(?:day|jour)\s+\d+\b"
    r"|\b(?:duel|episode|épisode)\s+(?:day|jour)\s+\d+"
    r"|\bout-?earn",
    re.I | re.M)
_SKIP_KEYS = {"reference_query", "reference", "principles", "code", "id", "topic_id", "inspiration_urls", "inspired_by",
              "citation", "citation_candidates", "no_challenge", "account_name", "regen_instruction"}

NO_CHALLENGE_RULE = (
    "DÉFI 90 JOURS NON LANCÉ : aucune mention du défi ni du « challenge », pas de « Day X » / « Day X/90 », pas de compteur "
    "d'épisode, pas de compte à rebours, pas d'objectif chiffré sur 90 jours. "
    "N'applique pas D1, D2, D4, P37. Le compte reste centré sur le créateur et son parcours, tel que décrit dans l'identité et le contexte. "
    "Les CTA de série renvoient au parcours ou à la prochaine vidéo, jamais à un « Day X+1 ».")


def mentions(obj) -> list[str]:
    """Extraits qui font référence au défi (vide = rien à signaler). Parcourt str/list/dict, hors champs techniques."""
    found: list[str] = []

    def walk(x):
        if isinstance(x, str):
            found.extend(m.group(0).strip() for m in _MENTION_RE.finditer(x))
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, dict):
            for k, v in x.items():
                if k not in _SKIP_KEYS:
                    walk(v)

    walk(obj)
    return list(dict.fromkeys(found))


def format_mentions(fmt: dict) -> list[str]:
    """Mentions du défi dans ce qu'un format met à l'écran (nom, structure, montage). Les notes internes en français
    (adaptation, description) et les variantes (filtrées une par une) ne comptent pas : « sans compte à rebours » n'est pas
    une mention."""
    return mentions({k: v for k, v in neutral(fmt).items() if k in ("name", "script_structure", "edit_template")})


def neutral(fmt: dict) -> dict:
    """Version hors défi d'un format : applique son bloc `no_challenge` (banque) par-dessus les champs du format."""
    over = fmt.get("no_challenge") or {}
    if not over:
        return fmt
    out = {**fmt, **{k: v for k, v in over.items() if k != "edit_template"}}
    if over.get("edit_template"):
        out["edit_template"] = {**(fmt.get("edit_template") or {}), **over["edit_template"]}
    return out


def active_in(start: dt.date, days: int = 7) -> bool:
    """Le défi est-il actif au moins un jour de la période ?"""
    return any(settings().challenge_day(start + dt.timedelta(days=i)) for i in range(days))


def set_start(day: dt.date | None) -> None:
    p = CONFIG_DIR / "engine.yaml"
    txt = p.read_text(encoding="utf-8")
    value = day.isoformat() if day else "null"
    txt, n = re.subn(r"(?m)^(\s+start_date:\s*)\S+", lambda m: m.group(1) + value, txt, count=1)
    if not n:
        raise RuntimeError("challenge.start_date introuvable dans config/engine.yaml")
    p.write_text(txt, encoding="utf-8")
    settings().raw.setdefault("challenge", {})["start_date"] = day


def status() -> dict:
    s = settings()
    start = s.get("challenge.start_date")
    started = start is not None and str(start) not in ("", "None", "null")
    today = dt.date.today()
    length = int(s.get("challenge.length_days", 90))
    day_n = None
    if started:
        d0 = start if isinstance(start, dt.date) else dt.date.fromisoformat(str(start))
        day_n = (today - d0).days + 1
        start = d0.isoformat()
    return {"started": started and (day_n or 0) >= 1, "scheduled": started, "start_date": start if started else None,
            "day_number": day_n if started and 1 <= day_n <= length else None, "length": length,
            "objectif": s.get("challenge.objectif")}


def challenge_map() -> dict:
    st = status()
    if not st["start_date"]:
        return {"start_date": None, "days": []}
    d0 = dt.date.fromisoformat(st["start_date"])
    end = d0 + dt.timedelta(days=st["length"] - 1)
    with db.session() as conn:
        rows = conn.execute("SELECT date, status, COUNT(*) n FROM calendar WHERE account='personal' AND date BETWEEN ? AND ? "
                            "GROUP BY date, status", (d0.isoformat(), end.isoformat())).fetchall()
    agg: dict[str, dict] = {}
    for r in rows:
        agg.setdefault(r["date"], {"planned": 0, "filmed": 0, "published": 0})[r["status"]] = r["n"]
    days = []
    for i in range(st["length"]):
        d = (d0 + dt.timedelta(days=i)).isoformat()
        days.append({"day_number": i + 1, "date": d, **agg.get(d, {"planned": 0, "filmed": 0, "published": 0})})
    return {"start_date": st["start_date"], "days": days}
