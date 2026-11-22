"""Helpers communs sur les formats (banque + formats promus)."""
from __future__ import annotations

from . import db
from .config import load_content_bank

SETUP_LABELS = {
    "bureau": "Bureau, laptop, lumière fenêtre de face",
    "chambre": "Chambre, lit/étagère en fond, lumière douce",
    "exterieur": "Extérieur, rue/Main/campus, caméra à la main",
    "fac": "Fac / bibliothèque, discret, plans POV",
    "cuisine": "Cuisine, plan large + gros plans",
    "voiture": "Voiture / transports, face cam, téléphone fixé",
    "salle_sport": "Salle de sport, plans POV + face cam",
    "ecran": "Écran, screen recording (laptop/téléphone) + voix",
}


def infer_visual_format(fmt: dict) -> str:
    """Mappe le texte libre edit_template.format vers la taxonomie d'analyse."""
    t = " ".join(str(v) for v in (fmt.get("edit_template") or {}).values()).lower() + " " + str(fmt.get("name", "")).lower()
    if "split" in t:
        return "split_screen"
    if "green" in t or "fond vert" in t:
        return "green_screen"
    if "screen" in t or "écran" in t or "enregistrement" in t:
        return "screen_record"
    if "pov" in t or "vlog" in t or "portée" in t:
        return "pov_vlog"
    if "b-roll" in t or "broll" in t:
        return "talking_head_broll"
    return "talking_head"


def proven_formats(conn, account: str) -> dict[str, dict]:
    """Formats éprouvés : banque + formats test promus (format_status)."""
    bank = load_content_bank(account)
    out = {f["id"]: {**f, "origin": "bank"} for f in bank.get("proven_formats") or []}
    for r in conn.execute("SELECT * FROM format_status WHERE account=? AND status='proven'", (account,)):
        data = db.loads(r["data"], {}) or {}
        if r["format_id"] not in out and data:
            out[r["format_id"]] = {**data, "id": r["format_id"], "origin": r["origin"] or "promoted"}
    return out


def test_formats(account: str) -> dict[str, dict]:
    return {f["id"]: f for f in load_content_bank(account).get("test_formats") or []}


def render(text, ctx: dict):
    """Remplace {jour}, {objectif}... sans casser les autres accolades."""
    if isinstance(text, str):
        for k, v in ctx.items():
            text = text.replace("{" + k + "}", str(v))
        return text
    if isinstance(text, list):
        return [render(t, ctx) for t in text]
    if isinstance(text, dict):
        return {k: render(v, ctx) for k, v in text.items()}
    return text
