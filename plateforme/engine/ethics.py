"""Identité + garde-fous (config/identity.yaml), appliqués à TOUT contenu généré.

- owner() : prénom du créateur (identity.yaml → owner_name)
- islamic() : règles islamiques activées ? (identity.yaml → islamic_rules: true|false)
- identity_block() : texte injecté dans tous les prompts (via principles.system_prompt)
- absolute_rules() : règles absolues rappelées dans les prompts de génération
- enforce_no_music(edit_template) : force « AUCUNE musique » dans chaque modèle de montage (règles islamiques seulement)
- check(entry) : liste des violations (exagération, indécence, moquerie + riba, jeux d'argent, musique si règles islamiques)
"""
from __future__ import annotations

import re
from functools import lru_cache

from .config import CONFIG_DIR, load_yaml

NEGATED_MUSIC = re.compile(
    r"\b(aucune|sans|pas de|z[ée]ro|no|without|zero)\s+(de\s+)?(musiques?|music)(\s+instrumentale?s?)?\b"
    r"|\b(sans|without|ni|no)\s+(d.)?(instruments?|percussions?)\b|\binstrument-free\b"
    r"|\b(no|without|zero)\s+instrumental\s+music\b"
    r"|\b(nasheeds?|a cappella|acapella|vocal[- ]only|voix seule)\b", re.I)  # sons halal autorisés


@lru_cache(maxsize=1)
def identity() -> dict:
    p = CONFIG_DIR / "identity.yaml"
    return load_yaml(p) if p.exists() else {}


def owner() -> str:
    """Prénom du créateur (identity.yaml → owner_name), « le créateur » par défaut."""
    name = str(identity().get("owner_name") or "").strip()
    return name if name and "À_REMPLIR" not in name else "le créateur"


def of_owner() -> str:
    """« de Marie » ou « du créateur » (prénom non renseigné)."""
    return f"de {owner()}" if owner() != "le créateur" else "du créateur"


def islamic() -> bool:
    """Règles islamiques activées (zéro musique instrumentale, riba, rappels hebdo, citations sourcées) ?"""
    return bool(identity().get("islamic_rules"))


def absolute_rules() -> str:
    """Règles absolues rappelées dans les prompts de génération (selon islamic_rules)."""
    if islamic():
        return ("RÈGLES ABSOLUES : aucune musique (montage = voix + sound design neutre) ; rien de contraire à l'éthique islamique "
                "(riba, jeux d'argent, promesses exagérées, indécence, moquerie) ; ne JAMAIS écrire le texte d'un verset ou d'un hadith : "
                "mets le placeholder {citation} dans le script, le moteur insère le texte vérifié depuis la source.")
    return ("RÈGLES ABSOLUES : vente honnête, aucune promesse exagérée, aucun chiffre inventé, aucune fausse urgence ; "
            "pas d'indécence ni de moquerie envers une personne. is_rappel=false partout.")


def music_rule() -> str:
    from .config import settings

    if not islamic():
        if settings().get("language") == "en":
            return identity().get("music_rule_free_en", "Music allowed, low under the voice (royalty-free), or voice + sound design only")
        return identity().get("music_rule_free", "Musique autorisée, basse sous la voix (libre de droits), ou voix + sound design seuls")
    if settings().get("language") == "en":
        return identity().get("music_rule_en", "NO music, voice + neutral sound design without instruments")
    return identity().get("music_rule", "AUCUNE musique, voix + sound design neutre sans instruments")


def identity_block() -> str:
    idt = identity()
    if not idt:
        return ""
    rules = list(idt.get("rules") or []) + (list((idt.get("islamic") or {}).get("rules") or []) if islamic() else [])
    rules = "\n".join(f"- {r}" for r in rules)
    head = f"Créateur : {owner()}\n" if owner() != "le créateur" else ""
    return f"=== IDENTITÉ ET LIGNE ÉDITORIALE (NON NÉGOCIABLE) ===\n{head}{idt.get('identity', '').strip()}\n{rules}\n=== FIN IDENTITÉ ==="


@lru_cache(maxsize=1)
def _patterns() -> dict[str, list[re.Pattern]]:
    pats = dict(identity().get("forbidden_patterns") or {})
    if islamic():
        pats.update((identity().get("islamic") or {}).get("forbidden_patterns") or {})
    return {cat: [re.compile(p, re.I) for p in ps] for cat, ps in pats.items()}


def _texts(entry: dict) -> str:
    parts = [entry.get("subject", ""), entry.get("script", ""), (entry.get("cta") or {}).get("text", "") if isinstance(entry.get("cta"), dict) else entry.get("cta", "")]
    for h in entry.get("hooks") or []:
        parts += [h.get("verbal", ""), h.get("text_on_screen", ""), h.get("visual", "")] if isinstance(h, dict) else [h]
    parts += [entry.get("text_hook", ""), entry.get("visual_hook", "")]
    parts += [str(s) for s in entry.get("shots") or []]
    return "\n".join(str(p) for p in parts if p)


# Une promesse niée est une phrase honnête : « pas de résultats garantis », « ce n'est pas de l'argent facile ».
NEGATED_PROMISE = re.compile(r"\b(nobody|no one|can.?t|cannot|won.?t|don.?t|doesn.?t|isn.?t|never|not|no|personne ne|ne|n'|pas|jamais|aucun|aucune|rien|ni)\s*"
                             r"(\S+\s+){0,3}(?:\w['’])?(guarantee[sd]?|garanti\w*|r[eé]sultats? garanti\w*|argent facile|easy money|"
                             r"devenir riche (vite|rapidement)|get rich (quick|fast)|effortless(ly)?|sans (aucun )?effort)\b", re.I)
NEGATED_AFTER = re.compile(r"(?:\w['’])?(r[eé]sultats? garanti\w*|argent facile|sans (aucun )?effort|easy money)\b[^.!?\n]{0,25}?"
                           r"\b(n'existe pas|n'existe plus|c'est faux|un mensonge|une arnaque|doesn.?t exist|is a lie|is a myth)", re.I)


def check_text(text: str) -> list[str]:
    text = NEGATED_MUSIC.sub(" ", text or "")
    text = NEGATED_PROMISE.sub(" ", text)
    text = NEGATED_AFTER.sub(" ", text)  # « je ne peux rien garantir » = honnête, pas une promesse
    out = []
    for cat, pats in _patterns().items():
        for p in pats:
            m = p.search(text)
            if m:
                out.append(f"{cat}: « {m.group(0)} »")
                break
    return out


def check(entry: dict) -> list[str]:
    """Violations sur le contenu (sujet, hooks, script, CTA, plans). Le modèle de montage est
    normalisé séparément par enforce_no_music."""
    return check_text(_texts(entry))


def enforce_no_music(et: dict | None) -> dict:
    et = dict(et or {})
    et["music"] = music_rule()
    if not islamic():
        return et
    # retire toute mention de musique/son tendance dans les autres champs
    for k, v in list(et.items()):
        if k != "music" and isinstance(v, str) and check_text(v) and any(c.startswith("music") for c in check_text(v)):
            et[k] = re.sub(r"[^.;,]*(musique|son tendance|trending sound|beat|song)[^.;,]*[.;,]?", "", v, flags=re.I).strip() or v
    if isinstance(et.get("broll"), list):
        et["broll"] = [b for b in et["broll"] if not any(c.startswith("music") for c in check_text(str(b)))]
    return et


MEMORY_CITATION = re.compile(
    r"(proph[eè]te|messager d.allah|rasul|ﷺ|\(saw\)|sws).{0,60}(a dit|disait|dit\s*:|«)"
    r"|(allah|dieu) (dit|a dit) dans"
    r"|\bsourate\s+[\wé'-]+\s*,?\s*(verset|v\.)?\s*\d+"
    r"|\b\d{1,3}\s*:\s*\d{1,3}\b.{0,20}(coran|sourate)"
    r"|\bhadith\b.{0,40}[«\"“]"
    r"|(prophet|messenger of allah|ﷺ|\(pbuh\)|pbuh).{0,60}(said|says|used to say)\s*[:,]?\s*[\"“]"
    r"|allah says in"
    r"|\bsurah\s+[\w'-]+\s*,?\s*(verse|ayah|v\.)?\s*\d+",
    re.I,
)


def memory_citation(raw_script: str) -> list[str]:
    """Signale un verset/hadith qui semble écrit de mémoire (hors placeholder {citation})."""
    m = MEMORY_CITATION.search((raw_script or "").replace("{citation}", ""))
    return [f"citation de mémoire ? « {m.group(0)[:60]} », utiliser {{citation}}"] if m else []
