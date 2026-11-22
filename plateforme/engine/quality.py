"""Qualité des références + funnel TOFU / MOFU / BOFU.

Une vidéo n'est proposée comme référence que si elle a marché GRÂCE À SA TECHNIQUE (analyse Claude :
success_driver = technique, réplicabilité et force du hook suffisantes), sur un canal d'inspiration pertinent
(Reels/TikTok pour tes formats, YouTube Shorts seulement pour les formats test d'autres niches), et, pour le
BOFU, avec un vrai signal de conversion (CTA mot-clé / lead magnet / DM, ou taux de commentaires élevé)."""
from __future__ import annotations

import random

from . import db
from .config import settings

STAGES = ("tofu", "mofu", "bofu")
STAGE_LABEL = {"tofu": "Notoriété (TOFU)", "mofu": "Confiance (MOFU)", "bofu": "Conversion (BOFU)"}
STAGE_DEF = {  # TOFU qui touche, MOFU qui filtre, BOFU qui vend
    "tofu": "TOFU : décrit une situation ou une émotion que l'avatar vit dans sa vie de tous les jours. Aucune méthode, aucun jargon (leads, offre, clients = MOFU), aucune promesse de solution. Pas de mot-clé : finit sur une phrase-morale ; on mesure abonnés et partages.",
    "mofu": "MOFU : méthode, diagnostic, comment faire, pour quelqu'un qui connaît son problème ; valeur concrète avec un exemple réel de la niche. Finit par « Envoie MOT-CLÉ en DM ».",
    "bofu": "BOFU : offre, preuve, cas client, objections. Finit par « Envoie MOT-CLÉ en DM » ou l'appel. Aucun résultat inventé : [à compléter : ...].",
}


def eligibility(analysis: dict | None, platform: str, slot_type: str = "proven", eng_comment_rel: float | None = None,
                funnel: str | None = None) -> tuple[bool, str]:
    """(éligible, raison)."""
    r = settings().get("references", {}) or {}
    if not analysis or analysis.get("method") != "llm":
        return False, "pas encore analysée par Claude"
    allowed = (r.get("platforms") or {}).get(slot_type, ["instagram", "tiktok"])
    if platform not in allowed:
        return False, f"{platform} pas utilisé comme inspiration pour ce type de vidéo"
    drv = analysis.get("success_driver") or "other"
    if drv not in (r.get("allowed_drivers") or ["technique"]):
        return False, f"succès lié à : {drv}"
    if (analysis.get("replicability") or 0) < float(r.get("min_replicability", 7)):
        return False, f"réplicabilité {analysis.get('replicability')}/10"
    if (analysis.get("hook_strength") or 0) < float(r.get("min_hook_strength", 6)):
        return False, f"hook {analysis.get('hook_strength')}/10"
    if funnel == "bofu" and r.get("bofu_requires_conversion", True):
        conv = analysis.get("conversion_mechanism") not in (None, "none") or (eng_comment_rel or 0) >= 1.5
        if not conv:
            return False, "pas de signal de conversion"
    return True, "ok"


def infer_stage(item: dict) -> str:
    """Étape funnel d'un sujet de la banque (sans analyse) à partir de son CTA / thème."""
    if item.get("funnel_stage") in STAGES:
        return item["funnel_stage"]
    if item.get("theme") or item.get("is_rappel"):
        return "mofu"
    cta = (item.get("cta_type") or "").lower()
    if cta in ("comment_keyword", "dm"):
        return "bofu"
    if cta in ("save",):
        return "mofu"
    return "tofu"


def week_plan(account: str, days: int, slots_per_day: int, seed: str = "") -> list[list[str]]:
    """Répartit le mix TOFU/MOFU/BOFU sur la semaine : [[stage slot1, slot2, slot3], …], ≥ 1 TOFU par jour."""
    mix = (settings().get("funnel") or {}).get(account) or {"tofu": 0.45, "mofu": 0.35, "bofu": 0.2}
    total = days * slots_per_day
    counts = {s: int(round(mix.get(s, 0) * total)) for s in STAGES}
    while sum(counts.values()) > total:
        counts[max(counts, key=counts.get)] -= 1
    while sum(counts.values()) < total:
        counts["tofu"] += 1
    rng = random.Random(f"{account}{seed}")
    pool = [s for s in STAGES for _ in range(counts[s])]
    rng.shuffle(pool)
    plan = [pool[d * slots_per_day:(d + 1) * slots_per_day] for d in range(days)]
    for d in plan:  # au moins un TOFU par jour (portée quotidienne)
        if "tofu" not in d:
            for other in plan:
                if other.count("tofu") > 1:
                    i, j = other.index("tofu"), next(k for k, s in enumerate(d))
                    other[i], d[j] = d[j], other[i]
                    break
    return plan


def analysis_of(conn, video_id: int) -> dict:
    r = conn.execute("SELECT data, method FROM analyses WHERE video_id=?", (video_id,)).fetchone()
    if not r:
        return {}
    a = db.loads(r["data"], {}) or {}
    a["method"] = r["method"]
    return a
