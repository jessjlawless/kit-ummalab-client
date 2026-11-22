"""Vérifie que les sources répondent : .venv/bin/python mcp/hadith/selftest.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.sources import hadith, quran  # noqa: E402

v = quran.get_verse("65:3")
print("Coran 65:3 :", v["french"][:120], "|", v["url"])
h = hadith.get_hadith("bukhari", 1)
print("Bukhari 1 :", h["grade"], "| accepted =", h["accepted"], "|", h["text"][:100])
h = hadith.get_hadith("tirmidhi", 2344)
print("Tirmidhi 2344 :", h["grade"][:80], "| accepted =", h["accepted"])
print("verified :", bool(quran.verified_citation("65:3", ["confiance", "suffit"])))
