"""Accès à la skill content-principles (.claude/skills/content-principles/SKILL.md).

Tous les modules de génération injectent ce texte dans leur prompt système et
référencent les IDs de principes (H-V1, R2, C2...)."""
from __future__ import annotations

import re
from functools import lru_cache

from .config import SKILL_PATH

ID_RE = re.compile(r"\*\*\[([A-Z]+(?:-[A-Z]+)?\d+)\]\s*([^*]+)\*\*")


@lru_cache(maxsize=1)
def skill_text() -> str:
    if not SKILL_PATH.exists():
        return ""
    text = SKILL_PATH.read_text(encoding="utf-8")
    # retire le frontmatter YAML
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2]
    return text.strip()


@lru_cache(maxsize=1)
def principle_index() -> dict[str, str]:
    """{ID: nom court} extrait de la skill."""
    return {m.group(1): m.group(2).strip(" --") for m in ID_RE.finditer(skill_text())}


def describe(ids: list[str]) -> list[str]:
    idx = principle_index()
    return [f"{i} {idx[i]}" if i in idx else i for i in ids]


def context_text(max_chars: int = 40000) -> str:  # 40k : tout le contexte du créateur (context/*.md)
    """Contexte personnel du créateur (dossier context/*.md, sauf README), lignes [À COMPLÉTER] ignorées."""
    from .config import ROOT

    parts = []
    for f in sorted((ROOT / "context").glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        lines = [l for l in f.read_text(encoding="utf-8").splitlines() if "[À COMPLÉTER" not in l]
        parts.append("\n".join(lines).strip())
    return "\n\n".join(p for p in parts if p)[:max_chars]


def language_rule() -> str:
    from .config import settings

    lang = settings().get("language", "fr")
    if lang == "en":
        return ("LANGUE DE SORTIE : tout le contenu des vidéos (sujets, hooks, texte à l'écran, scripts, CTA, plans) est en "
                "ANGLAIS parlé naturel (contractions, phrases courtes). Les règles de la skill sont en français : applique-les en anglais.")
    return "LANGUE DE SORTIE : français oral, tutoiement."


def system_prompt(role: str) -> str:
    """Prompt système commun : rôle + skill complète."""
    from .ethics import identity_block

    # les références [src: …] servent à la traçabilité, pas à la génération : retirées du prompt (≈ -35 % de tokens)
    skill = re.sub(r"\s*\[src:[^\]]*\]", "", skill_text()) or \
        "(skill content-principles introuvable, applique les bonnes pratiques Hormozi/Kallaway/Galloway)"
    return (
        f"{role}\n\n"
        f"{identity_block()}\n\n"
        f"=== CONTEXTE PERSONNEL DU CRÉATEUR ===\n{context_text()}\n=== FIN CONTEXTE ===\n\n"
        f"{language_rule()}\n\n"
        "Tu appliques STRICTEMENT la skill 'content-principles' ci-dessous. "
        "Quand on te demande un champ `principles`, cite les IDs exacts (ex: H-V1, R2, C2).\n\n"
        "=== SKILL content-principles ===\n"
        f"{skill}\n=== FIN SKILL ==="
    )
