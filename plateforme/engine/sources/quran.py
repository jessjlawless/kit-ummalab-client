"""Coran via l'API publique alquran.cloud (sans clé), texte arabe (uthmani) + traduction
française (Hamidullah) + référence sourate:verset. Fallback : API quran.com v4."""
from __future__ import annotations

import re

from .. import log
from . import VERIFY_TAG, cached_get_json, keywords_match

logger = log.get("quran")
ALQURAN = "https://api.alquran.cloud/v1"
QURANCOM = "https://api.quran.com/api/v4"
FR_EDITION = "fr.hamidullah"
EN_EDITION = "en.sahih"           # Saheeh International
QURANCOM_FR_TRANSLATION_ID = 31  # Muhammad Hamidullah sur quran.com
QURANCOM_EN_TRANSLATION_ID = 20  # Saheeh International sur quran.com
TRANSLATORS = {"fr": "Muhammad Hamidullah", "en": "Saheeh International"}


def _clean(t: str) -> str:
    return re.sub(r"<[^>]+>", "", t or "").strip()


def get_verse(ref: str, lang: str = "fr") -> dict:
    """ref = 'sourate:verset' (ex: '65:3'). Lève une exception si introuvable.
    Renvoie arabe + traduction (fr Hamidullah ou en Saheeh International) dans `translation_text`."""
    edition = EN_EDITION if lang == "en" else FR_EDITION
    if not re.fullmatch(r"\d{1,3}:\d{1,3}", ref):
        raise ValueError(f"référence invalide : {ref}")
    try:
        d = cached_get_json(f"{ALQURAN}/ayah/{ref}/editions/quran-uthmani,{edition}")
        ar, tr = d["data"][0], d["data"][1]
        surah = ar["surah"]
        return {
            "type": "quran", "ref": ref, "arabic": ar["text"], "translation_text": _clean(tr["text"]),
            "french": _clean(tr["text"]) if lang != "en" else None, "lang": lang,
            "surah_name": surah.get("englishName"), "surah_name_ar": surah.get("name"),
            "translation": TRANSLATORS["en" if lang == "en" else "fr"], "source": "api.alquran.cloud",
            "url": f"https://quran.com/{ref.replace(':', '/')}",
        }
    except Exception as e:
        logger.warning("alquran.cloud KO (%s), essai quran.com", e)
    tid = QURANCOM_EN_TRANSLATION_ID if lang == "en" else QURANCOM_FR_TRANSLATION_ID
    d = cached_get_json(f"{QURANCOM}/verses/by_key/{ref}?translations={tid}&fields=text_uthmani")
    v = d["verse"]
    t = _clean((v.get("translations") or [{}])[0].get("text", ""))
    return {
        "type": "quran", "ref": ref, "arabic": v.get("text_uthmani"), "translation_text": t,
        "french": t if lang != "en" else None, "lang": lang,
        "translation": TRANSLATORS["en" if lang == "en" else "fr"], "source": "api.quran.com",
        "url": f"https://quran.com/{ref.replace(':', '/')}",
    }


def search(query: str, limit: int = 10) -> list[dict]:
    d = cached_get_json(f"{ALQURAN}/search/{requests_quote(query)}/all/{FR_EDITION}")
    out = []
    for m in (d.get("data") or {}).get("matches", [])[:limit]:
        ref = f"{m['surah']['number']}:{m['numberInSurah']}"
        out.append({"ref": ref, "french": _clean(m["text"]), "url": f"https://quran.com/{ref.replace(':', '/')}"})
    return out


def requests_quote(s: str) -> str:
    from urllib.parse import quote

    return quote(s)


def verified_citation(ref: str, expected_keywords: list[str], lang: str = "fr") -> dict | None:
    """Récupère le verset et vérifie que la traduction contient les mots-clés attendus.
    Renvoie None si la source ne correspond pas (→ « citation à ajouter »)."""
    try:
        v = get_verse(ref, lang)
    except Exception as e:
        logger.warning("verset %s indisponible : %s", ref, e)
        return None
    if not keywords_match(v["translation_text"], expected_keywords):
        logger.warning("verset %s : mots-clés %s absents de la traduction → rejeté", ref, expected_keywords)
        return None
    v["reference_label"] = (f"Quran {ref} ({v.get('surah_name') or ''}), transl. {v['translation']}" if lang == "en"
                            else f"Coran {ref} ({v.get('surah_name') or ''}), trad. {v['translation']}")
    v["status"] = VERIFY_TAG
    return v
