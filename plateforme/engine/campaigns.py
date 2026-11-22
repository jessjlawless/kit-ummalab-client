"""Campagnes : config/campaigns/*.yaml imposent, pour un compte et une période, le type et l'angle de chaque slot
(présentation, témoignage, objection, fonctionnalité, rappel…) à la place de la rotation formats éprouvés + format test.
Le planner génère chaque slot selon son type (LLM) ; sans LLM, le fallback assemble une fiche à compléter depuis le YAML."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import yaml

from . import log
from .config import CONFIG_DIR

logger = log.get("campaigns")
DIR = CONFIG_DIR / "campaigns"


def _date(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


@lru_cache(maxsize=1)
def _load_all() -> tuple[dict, ...]:
    out = []
    for p in sorted(DIR.glob("*.yaml")) if DIR.exists() else []:
        try:
            c = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            c["start"], c["end"] = _date(c["start"]), _date(c["end"])
            c["days"] = {_date(k): v for k, v in (c.get("days") or {}).items()}
            c.setdefault("id", p.stem)
            out.append(c)
        except Exception as e:
            logger.warning("campagne %s illisible : %s", p.name, e)
    return tuple(out)


def reload() -> None:
    _load_all.cache_clear()


def for_day(account: str, day: dt.date) -> tuple[dict, list[dict]] | None:
    """(campagne, slots résolus) si une campagne couvre ce jour pour ce compte, sinon None."""
    for c in _load_all():
        if c.get("account") == account and c["start"] <= day <= c["end"] and c["days"].get(day):
            return c, [resolve_slot(c, s) for s in c["days"][day]]
    return None


def resolve_slot(c: dict, s: dict | str) -> dict:
    s = {"type": s} if isinstance(s, str) else dict(s)
    t = (c.get("types") or {}).get(s["type"]) or {}
    feature = (c.get("features") or {}).get(s.get("feature")) if s.get("feature") else None
    angle = s.get("angle") or feature or t.get("name") or s["type"]
    return {"type": s["type"], "name": t.get("name", s["type"]), "angle": angle, "feature": s.get("feature"),
            "instructions": " ".join(str(t.get("instructions", "")).split()), "funnel": t.get("funnel"),
            "setup": t.get("setup"), "theme": t.get("theme"), "is_rappel": s["type"] == "rappel"}


def fallback_item(c: dict, slot: dict) -> dict:
    """Fiche sans LLM : sujet + hook depuis l'angle, script à écrire (jamais de faux contenu)."""
    hook = slot["angle"].strip("« »")
    return {"subject": slot["angle"], "hooks": [hook, hook], "text_hook": " ".join(hook.split()[:7]),
            "visual_hook": "[à compléter : action visible en 1re seconde]",
            "script": f"[à écrire, {slot['name']} : {slot['instructions']}]",
            "cta": c.get("cta") or "Envoie [à compléter : mot-clé] en DM", "cta_type": "dm",
            "setup": slot.get("setup") or "bureau", "shots": [], "funnel_stage": slot.get("funnel")}


def tag(c: dict, slot: dict, item: dict) -> dict:
    return {"id": c["id"], "title": c.get("title", c["id"]), "type": slot["type"], "label": slot["name"],
            "angle": slot["angle"], "notes": item.get("notes") or ""}
