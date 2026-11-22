"""Hadiths via la hadith-api open source de fawazahmed0 (CDN jsDelivr, gratuite, sans clé).
Option : API sunnah.com (SUNNAH_API_KEY dans .env) pour recouper le grade.

Règle : uniquement sahih ou hasan, avec recueil + numéro. Grade absent → hadith refusé,
SAUF Sahih al-Bukhari et Sahih Muslim dont le recueil entier est classé sahih
(décision documentée dans DECISIONS.md, désactivable : SAHIHAYN_IMPLICIT = False)."""
from __future__ import annotations

import re

from .. import log
from ..config import env
from . import VERIFY_TAG, cached_get_json, keywords_match, normalize

logger = log.get("hadith")
CDN = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
CDN_FALLBACK = "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1"
SUNNAH_API = "https://api.sunnah.com/v1"

COLLECTIONS = {
    "bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim", "abudawud": "Sunan Abi Dawud",
    "tirmidhi": "Jami' at-Tirmidhi", "nasai": "Sunan an-Nasa'i", "ibnmajah": "Sunan Ibn Majah",
    "malik": "Muwatta Malik", "nawawi": "40 Hadiths an-Nawawi", "qudsi": "40 Hadiths Qudsi",
}
SAHIHAYN = {"bukhari", "muslim"}
SAHIHAYN_IMPLICIT = True
ACCEPT = re.compile(r"\b(sahih|hasan)\b", re.I)
REJECT = re.compile(r"(da.?if|daif|weak|maudu|mawdu|fabricated|munkar|shadh|batil)", re.I)


def _get(path: str) -> dict:
    try:
        return cached_get_json(f"{CDN}/{path}")
    except Exception:
        return cached_get_json(f"{CDN_FALLBACK}/{path}")


def _edition(collection: str, lang: str) -> str:
    if lang == "fr" and collection == "tirmidhi":  # pas d'édition française de Tirmidhi
        return "eng-tirmidhi"
    return f"{'fra' if lang == 'fr' else 'eng'}-{collection}"


def evaluate_grade(collection: str, grades: list[dict]) -> tuple[bool, str]:
    """(accepté, libellé du grade)."""
    if not grades:
        if collection in SAHIHAYN and SAHIHAYN_IMPLICIT:
            return True, f"Sahih (recueil {COLLECTIONS[collection]})"
        return False, "grade indisponible"
    labels = [f"{g.get('grade')} ({g.get('name')})" for g in grades]
    albani = [g for g in grades if "albani" in (g.get("name") or "").lower()]
    ref = albani or grades
    if any(REJECT.search(g.get("grade") or "") for g in ref):
        return False, "; ".join(labels)
    ok = all(ACCEPT.search(g.get("grade") or "") for g in ref)
    return ok, "; ".join(labels)


def _sunnah_grade(collection: str, number: int) -> list[dict] | None:
    key = env("SUNNAH_API_KEY")
    if not key:
        return None
    try:
        d = cached_get_json(f"{SUNNAH_API}/collections/{collection}/hadiths/{number}", headers={"X-API-Key": key})
        for h in d.get("hadith", []):
            if h.get("lang") == "en" and h.get("grades"):
                return [{"name": g.get("graded_by") or "sunnah.com", "grade": g.get("grade")} for g in h["grades"]]
    except Exception as e:
        logger.warning("sunnah.com KO : %s", e)
    return None


def get_hadith(collection: str, number: int, lang: str = "fr") -> dict:
    collection = collection.lower()
    if collection not in COLLECTIONS:
        raise ValueError(f"recueil inconnu : {collection} (choix : {', '.join(COLLECTIONS)})")
    ed = _edition(collection, lang)
    d = _get(f"editions/{ed}/{int(number)}.json")
    h = (d.get("hadiths") or [None])[0]
    if not h:
        raise LookupError(f"{collection} {number} introuvable")
    grades = h.get("grades") or []
    if not grades and lang == "fr" and collection not in SAHIHAYN:  # grades parfois seulement en anglais
        try:
            grades = (_get(f"editions/eng-{collection}/{int(number)}.json")["hadiths"][0].get("grades")) or []
        except Exception:
            pass
    sunnah = _sunnah_grade(collection, int(number))
    if sunnah:
        grades = grades + sunnah
    accepted, grade_label = evaluate_grade(collection, grades)
    return {
        "type": "hadith", "collection": collection, "collection_name": COLLECTIONS[collection],
        "number": int(number), "text": (h.get("text") or "").strip(), "lang": "fr" if ed.startswith("fra") else "en",
        "grades": grades, "grade": grade_label, "accepted": accepted,
        "reference": h.get("reference"), "source": "fawazahmed0/hadith-api",
        "source_url": f"{CDN}/editions/{ed}/{int(number)}.json",
        "url": f"https://sunnah.com/{collection}:{int(number)}",
    }


def search(query: str, collections: list[str] | None = None, lang: str = "fr", limit: int = 10,
           only_accepted: bool = True) -> list[dict]:
    """Recherche plein texte (télécharge et met en cache l'édition complète, quelques Mo)."""
    q = normalize(query).split()
    out = []
    for c in collections or ["bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah"]:
        ed = _edition(c, lang)
        try:
            d = _get(f"editions/{ed}.min.json")
        except Exception as e:
            logger.warning("édition %s indisponible : %s", ed, e)
            continue
        for h in d.get("hadiths", []):
            t = normalize(h.get("text") or "")
            if t and all(w in t for w in q):
                ok, label = evaluate_grade(c, h.get("grades") or [])
                if only_accepted and not ok:
                    continue
                out.append({"collection": c, "number": h["hadithnumber"], "grade": label, "accepted": ok,
                            "text": h["text"][:600], "url": f"https://sunnah.com/{c}:{h['hadithnumber']}"})
                if len(out) >= limit:
                    return out
    return out


def verified_citation(collection: str, number: int, expected_keywords: list[str], lang: str = "fr") -> dict | None:
    try:
        h = get_hadith(collection, number, lang)
    except Exception as e:
        logger.warning("hadith %s %s indisponible : %s", collection, number, e)
        return None
    if not h["accepted"]:
        logger.warning("hadith %s %s refusé (grade : %s)", collection, number, h["grade"])
        return None
    if not keywords_match(h["text"], expected_keywords):
        logger.warning("hadith %s %s : mots-clés %s absents → rejeté", collection, number, expected_keywords)
        return None
    h["reference_label"] = f"{h['collection_name']} {'no.' if lang == 'en' else 'n°'} {h['number']}, {h['grade']}"
    h["status"] = VERIFY_TAG
    return h
