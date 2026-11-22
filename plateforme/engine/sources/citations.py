"""Résolution des citations des rappels : la banque/le LLM proposent des candidats
(référence + mots-clés attendus), on récupère le VRAI texte depuis la source et on vérifie.
Aucun texte religieux n'est jamais écrit de mémoire."""
from __future__ import annotations

import re

from .. import log
from . import VERIFY_TAG, hadith, quran

logger = log.get("citations")
MISSING = "[citation à ajouter]"


def _lang() -> str:
    from ..config import settings

    return settings().get("language", "fr")


def missing_text(theme: str) -> str:
    return f"[citation to add, idea: {theme}]" if _lang() == "en" else f"[citation à ajouter, idée : {theme}]"


def resolve(candidates: list[dict]) -> dict | None:
    lang = _lang()
    for c in candidates or []:
        try:
            if c.get("type") == "quran" and c.get("ref"):
                v = quran.verified_citation(str(c["ref"]), c.get("expected_keywords") or [], lang)
            elif c.get("type") == "hadith" and c.get("collection") and c.get("number"):
                v = hadith.verified_citation(c["collection"], int(c["number"]), c.get("expected_keywords") or [], lang)
            else:
                continue
        except Exception as e:
            logger.warning("candidat %s KO : %s", c, e)
            v = None
        if v:
            return v
    return None


def spoken_text(cit: dict | None) -> str:
    """Ce que le créateur dit dans la vidéo (traduction française + référence orale)."""
    if not cit:
        return MISSING
    en = cit.get("lang", "fr") == "en"
    if cit["type"] == "quran":
        if en:
            return f"\"{cit['translation_text']}\" (Quran, Surah {cit.get('surah_name') or ''} {cit['ref']})"
        return f"« {cit['translation_text']} » (Coran, sourate {cit.get('surah_name') or ''} {cit['ref']})"
    text = cit["text"]
    # à l'oral : uniquement la parole rapportée (extraite telle quelle de la source), sans la chaîne « Rapporté par… / Narrated… »
    spoken = None
    for o, c in (("«", "»"), ("\u201c", "\u201d"), ('"', '"')):
        if o in text and c in text[text.index(o) + 1:]:
            spoken = text[text.index(o): text.rindex(c) + 1]
            break
    if spoken is None:
        m = re.search(r"\b(a dit|dire|disait|said|saying)\s*[:,]\s*", text)
        body = text[m.end():].strip() if m else text
        spoken = f"\"{body}\"" if en else f"« {body} »"
    return f"{spoken} ({cit['collection_name']}, {'no.' if en else 'n°'} {cit['number']})"


def card(cit: dict | None, idea: str = "") -> dict:
    """Bloc affiché dans la fiche de tournage / l'export."""
    if not cit:
        return {"status": "citation à ajouter", "idea": idea}
    base = {"status": VERIFY_TAG, "type": cit["type"], "reference": cit.get("reference_label"), "url": cit.get("url"),
            "source": cit.get("source")}
    if cit["type"] == "quran":
        base.update(arabic=cit.get("arabic"), translation=cit.get("translation_text"), french=cit.get("translation_text"))
    else:
        base.update(text=cit.get("text"), grade=cit.get("grade"), source_url=cit.get("source_url"))
    return base
