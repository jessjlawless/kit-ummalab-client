"""MCP local « hadith » (stdio) basé sur la hadith-api open source de fawazahmed0.

Outils :
  list_collections()                       — recueils disponibles
  get_hadith(collection, number, lang)     — texte + grade + liens (refuse d'approuver un grade non sahih/hasan)
  search_hadith(query, collections, lang)  — recherche plein texte, ne renvoie que sahih/hasan par défaut
  get_quran_verse(ref)                     — bonus : verset (arabe + fr Hamidullah) via api.alquran.cloud

Lancement : .venv/bin/python mcp/hadith/server.py   (déclaré dans .mcp.json pour Claude Code)
Option sunnah.com : SUNNAH_API_KEY dans .env (recoupement des grades).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from engine.sources import VERIFY_TAG, hadith, quran  # noqa: E402

mcp = FastMCP("hadith")


@mcp.tool()
def list_collections() -> dict:
    """Liste les recueils de hadiths disponibles (clé → nom)."""
    return hadith.COLLECTIONS


@mcp.tool()
def get_hadith(collection: str, number: int, lang: str = "fr") -> dict:
    """Récupère un hadith par recueil (bukhari, muslim, abudawud, tirmidhi, nasai, ibnmajah, malik, nawawi, qudsi)
    et numéro. `accepted` = True uniquement si le grade est sahih ou hasan. Toujours afficher la référence et le lien,
    et marquer la citation « À VÉRIFIER »."""
    h = hadith.get_hadith(collection, number, lang)
    h["status"] = VERIFY_TAG if h["accepted"] else "NE PAS UTILISER (grade non sahih/hasan ou indisponible)"
    return h


@mcp.tool()
def search_hadith(query: str, collections: list[str] | None = None, lang: str = "fr", limit: int = 10) -> list[dict]:
    """Recherche plein texte (mots séparés par des espaces, tous requis). Ne renvoie que des hadiths sahih/hasan."""
    return hadith.search(query, collections, lang, limit, only_accepted=True)


@mcp.tool()
def get_quran_verse(ref: str) -> dict:
    """Verset du Coran 'sourate:verset' (ex '65:3') : texte arabe + traduction française Hamidullah + lien quran.com."""
    v = quran.get_verse(ref)
    v["status"] = VERIFY_TAG
    return v


if __name__ == "__main__":
    mcp.run()
