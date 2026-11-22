"""Module 7, Instructions de montage pour ChatCut, générées depuis le modèle de montage de chaque vidéo.
Toujours : AUCUNE musique. Sortie : output/editing/<date>/<code>.md (+ .json)."""
from __future__ import annotations

import datetime as dt
import json
import re

from . import ethics, log, principles
from .config import OUTPUT_DIR
from .planner import load_entries

logger = log.get("editing")


def _keywords(script: str, n: int = 6) -> list[str]:
    """Mots à mettre en emphase (zoom punch-in / couleur) : chiffres, montants, mots en MAJUSCULES."""
    found = re.findall(r"\b\d[\d\s.,]*\s?(?:€|%|k|euros?|jours?|clients?|appels?|DM|messages?)?", script)
    found += re.findall(r"\b[A-ZÉÈÀ]{3,}\b", script)
    out = []
    for f in found:
        f = f.strip(" .,")
        if len(f) > 1 and f not in out:
            out.append(f)
    return out[:n]


def brief(e: dict) -> dict:
    et = ethics.enforce_no_music(e.get("edit_template"))
    hooks = e.get("hooks") or []
    text_hook = hooks[0].get("text_on_screen") if hooks else ""
    broll = [s for s in e.get("shots", []) if "b-roll" in s.lower()] or et.get("broll") or []
    kw = _keywords(e.get("script", ""))
    steps = [
        "Projet 9:16 (1080×1920), 30 fps, durée cible 45-60 s."
        + (" AUCUNE MUSIQUE INSTRUMENTALE dans tout le montage (voix, nasheed a cappella et bruitages autorisés)." if ethics.islamic() else ""),
        "Nettoyage : supprime silences > 250 ms, « euh », faux départs et prises ratées ; garde la meilleure prise de chaque phrase (coupe sèche, zéro temps mort).",
        f"Hook : la vidéo commence directement sur le hook A « {hooks[0]['verbal'] if hooks else ''} », aucune intro, aucun logo.",
        f"Texte à l'écran 0-3 s : « {text_hook} », gros, tiers supérieur, hors zones UI Instagram, apparition en pop." if text_hook else None,
        f"Overlay permanent : {et['on_screen_text']}" if et.get("on_screen_text") else None,
        f"Sous-titres : {et.get('subtitles') or 'mot-à-mot, 2-3 mots par ligne, centre-bas, mots clés en couleur'}.",
        f"Rythme : {et.get('pacing') or 'un changement visuel toutes les 2-4 s (cut, zoom, B-roll, texte)'}.",
        f"Emphase (zoom punch-in + couleur) sur : {', '.join(kw)}." if kw else None,
        ("B-roll à placer quand le script en parle : " + " | ".join(broll)) if broll else None,
        f"Son : {ethics.music_rule()}. Voix normalisée ~-14 LUFS, débruitage léger.",
    ]
    cit = e.get("citation") or {}
    if cit.get("reference"):
        steps.append(f"Citation : afficher en bas « {cit['reference']} » pendant la citation. ⚠ {cit.get('status')} avant export.")
    elif cit:
        steps.append("Citation : AUCUNE citation religieuse à l'écran tant que la source n'est pas vérifiée (citation à ajouter).")
    steps.append(f"Fin : CTA « {e['cta']['text']} » + texte écran court du CTA sur les 2 dernières secondes.")
    if len(hooks) > 1:
        steps.append(f"Exporter 2 versions : V-A (hook A) et V-B (remplacer les 0-3 s par le hook B « {hooks[1]['verbal']} »).")
    rules = principles.describe([i for i in ("R1", "R3", "R14", "R18", "F4", "H-VIS1", "H-TXT1", "I2") if i in principles.principle_index()])
    if rules:
        steps.append("Règles de montage (skill content-principles) : " + " · ".join(rules) + ".")
    steps = [s for s in steps if s]
    prompt = (f"Monte cette vidéo pour Instagram Reels ({e['account_name']}, {e['subject']}).\n"
              + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
    return {"code": e["code"], "date": e["date"], "account": e["account"], "subject": e["subject"],
            "format": e["format"], "visual_format": et.get("visual_format"), "steps": steps, "chatcut_prompt": prompt,
            "no_music": True, "inspiration_urls": et.get("inspiration_urls", [])}


def run(day: dt.date) -> list[str]:
    entries = load_entries(day, day)
    out_dir = OUTPUT_DIR / "editing" / day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, all_briefs = [], []
    for e in entries:
        b = brief(e)
        all_briefs.append(b)
        md = [f"# Montage ChatCut, {b['code']}", "", f"**{b['subject']}** · format {b['format'].get('name')}", "",
              "Importe les rushes (A-roll + B-roll) dans ChatCut puis colle ce brief :", "", "```", b["chatcut_prompt"], "```", ""]
        if b["inspiration_urls"]:
            md += ["Inspiration : " + " ".join(b["inspiration_urls"]), ""]
        p = out_dir / f"{b['code']}.md"
        p.write_text("\n".join(md), encoding="utf-8")
        paths.append(str(p))
    (out_dir / "briefs.json").write_text(json.dumps(all_briefs, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("%d briefs ChatCut → %s", len(paths), out_dir)
    return paths
