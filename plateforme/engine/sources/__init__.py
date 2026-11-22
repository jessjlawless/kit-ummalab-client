"""Sources religieuses vérifiables (Coran, hadiths). Aucune citation de mémoire :
tout texte affiché vient d'une API, avec référence + lien, marqué « À VÉRIFIER »."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests

from ..config import DATA_DIR

CACHE = DATA_DIR / "cache" / "sources"
VERIFY_TAG = "À VÉRIFIER"


def cached_get_json(url: str, headers: dict | None = None, timeout: int = 30) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    r = requests.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def normalize(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def keywords_match(text: str, keywords: list[str]) -> bool:
    """Toutes les racines de mots-clés attendus doivent apparaître dans le texte source."""
    t = normalize(text)
    return all(normalize(k)[:6] in t for k in keywords or [])


def path_exists(p: Path) -> bool:
    return p.exists()
