"""Module 5, Calendrier : 7 jours × 2 comptes × 3 vidéos (2 éprouvées + 1 test).

Deux sources :
  - llm  : Claude génère sujet, 2 hooks, script ~150 mots, CTA, plans, en appliquant la skill
           + la synthèse hebdo (module 4) + la banque comme exemples de style.
  - bank : fallback sans clé API, assemblage depuis config/content_bank/<compte>.yaml
           (sujets non encore utilisés, arc narratif "Jour X" pour le personal brand quand le défi est lancé).

Défi 90 jours (personal) : seulement si config/engine.yaml → challenge.start_date est renseigné et que le jour est dans
les 90 jours. Sinon (null), aucun contenu ne parle du défi : consigne NO_CHALLENGE_RULE au LLM, formats neutres
(`no_challenge` de la banque), sujets de banque liés au défi écartés, et garde-fou `challenge_flags` qui rejette la sortie.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from . import campaigns, challenge, db, ethics, llm, log, principles, quality
from .config import load_content_bank, settings
from .sources import citations
from .formats import SETUP_LABELS, infer_visual_format, proven_formats, render, test_formats

logger = log.get("calendar")

WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
PREFIX = {"personal": "PB"}


def default_week_start(today: dt.date | None = None) -> dt.date:
    """Le week-end on planifie la semaine suivante (lundi) ; en semaine on part d'aujourd'hui."""
    today = today or dt.date.today()
    if today.weekday() >= 5:
        return today + dt.timedelta(days=7 - today.weekday())
    return today


def _ctx(account: str, day: dt.date) -> dict:
    """Variables de rendu. {jour}/{objectif}/{episode_intro} n'existent que les jours où le défi est actif (personal)."""
    s = settings()
    ctx = {"date": day.strftime("%d/%m"), "episode_intro": ""}
    n = s.challenge_day(day) if account == "personal" else None
    if n:
        total = int(s.get("challenge.length_days", 90))
        ctx.update(objectif=s.get("challenge.objectif", "5 500 €/mois"), jour=n, jour_suivant=min(n + 1, total), total=total,
                   episode_intro=f"Day {n} of {total}. " if s.get("language") == "en" else f"Jour {n} sur {total}. ")
    return ctx


def _no_challenge(account: str, day: dt.date) -> bool:
    """Compte perso un jour hors défi : rien ne doit évoquer le défi."""
    return account == "personal" and not settings().challenge_day(day)


def _fmt_for(account: str, day: dt.date, fmt: dict) -> dict:
    return challenge.neutral(fmt) if _no_challenge(account, day) else fmt


def _latest_synthesis(conn, account: str) -> dict:
    r = conn.execute("SELECT data FROM syntheses WHERE account=? ORDER BY week_start DESC, id DESC LIMIT 1", (account,)).fetchone()
    return db.loads(r["data"], {}) if r else {}


def _used_topics(conn, account: str, exclude_from: str) -> dict[str, str]:
    rows = conn.execute("SELECT topic_id, MAX(date) d FROM calendar WHERE account=? AND date < ? AND topic_id IS NOT NULL "
                        "GROUP BY topic_id", (account, exclude_from)).fetchall()
    return {r["topic_id"]: r["d"] for r in rows}


def _edit_template(fmt: dict, synthesis: dict) -> dict:
    et = dict(fmt.get("edit_template") or {})
    vf = infer_visual_format(fmt)
    urls = list(fmt.get("inspiration_urls") or [])
    urls += [u for u in (synthesis.get("inspiration_by_visual_format") or {}).get(vf, []) if u not in urls]
    et["visual_format"] = vf
    et["inspiration_urls"] = urls[:5]
    return et


def _entry(account: str, day: dt.date, slot: int, slot_type: str, fmt: dict, item: dict, synthesis: dict,
           source: str, topic_id: str | None, stage: str | None = None) -> dict:
    ctx = _ctx(account, day)
    fmt = _fmt_for(account, day, fmt)
    memory_flags = ethics.memory_citation(item.get("script") or "")
    themes = set(((ethics.identity().get("islamic") or {}).get("rappels") or {}).get("themes") or []) if ethics.islamic() else set()
    is_rappel = item.get("is_rappel") is True or bool(item.get("citation_candidates")) or (item.get("theme") in themes)
    citation = citations.resolve(item.get("citation_candidates") or []) if is_rappel else None
    if is_rappel and citation is None:  # secours : candidats déjà vérifiés de la banque pour ce thème
        bank_cands = [c for r in load_content_bank(account).get("rappels") or [] if r.get("theme") == item.get("theme")
                      for c in r.get("citation_candidates") or []]
        citation = citations.resolve(bank_cands)
    if is_rappel or "{citation}" in (item.get("script") or ""):
        ctx = {**ctx, "citation": citations.spoken_text(citation) if citation
               else citations.missing_text(item.get("theme") or "rappel")}
    item = render(item, ctx)
    hooks = item.get("hooks") or []
    hooks = (hooks + hooks)[:2] if hooks else ["", ""]
    entry = {
        "code": f"{PREFIX[account]}-{day.isoformat()}-{slot}",
        "account": account,
        "account_name": settings().accounts.get(account, {}).get("name", account),
        "date": day.isoformat(),
        "weekday": WEEKDAYS_FR[day.weekday()],
        "slot_index": slot,
        "slot_type": slot_type,
        "day_number": ctx.get("jour"),
        "episode_label": (f"Day {ctx['jour']}/{ctx['total']}" if settings().get("language") == "en"
                          else f"Jour {ctx['jour']}/{ctx['total']}") if ctx.get("jour") else None,
        "reference_query": item.get("reference_query"),
        "format": {"id": fmt.get("id"), "name": fmt.get("name"), "source_niche": fmt.get("source_niche"),
                   "structure": fmt.get("script_structure")},
        "topic_id": topic_id,
        "subject": item.get("subject", ""),
        "hooks": [
            {"variant": v, "verbal": h, "text_on_screen": item.get("text_hook", ""), "visual": item.get("visual_hook", "")}
            for v, h in zip("AB", hooks)
        ],
        "script": (item.get("script") or "").strip(),
        "word_count": len((item.get("script") or "").split()),
        "cta": {"text": item.get("cta", ""), "type": item.get("cta_type", "soft")},
        "setup": item.get("setup") or "bureau",
        "setup_label": SETUP_LABELS.get(item.get("setup") or "bureau", item.get("setup")),
        "shots": item.get("shots") or [],
        "edit_template": ethics.enforce_no_music(render(_edit_template(fmt, synthesis), ctx)),
        "principles": item.get("principles") or fmt.get("principles") or [],
        "is_rappel": is_rappel,
        "funnel_stage": (item.get("funnel_stage") if item.get("funnel_stage") in quality.STAGES else None)
                        or ("mofu" if is_rappel else None) or stage or quality.infer_stage(item),
        "rappel_theme": item.get("theme"),
        "citation": citations.card(citation, item.get("theme") or "") if is_rappel else None,
        "source": source,
        "status": "planned",
    }
    if is_rappel and "I4" not in entry["principles"]:
        entry["principles"] = entry["principles"] + ["I4", "I5"]
    entry["ethics_flags"] = ethics.check(entry) + memory_flags
    if entry["ethics_flags"]:
        logger.warning("⚠ garde-fou éthique %s : %s", entry["code"], entry["ethics_flags"])
    entry["challenge_flags"] = []
    if _no_challenge(account, day):
        entry["principles"] = [p for p in entry["principles"] if p not in challenge.CHALLENGE_PRINCIPLES]
        entry["challenge_flags"] = challenge.mentions(entry)
        if entry["challenge_flags"]:
            logger.warning("⚠ défi non lancé, mention du défi dans %s : %s", entry["code"], entry["challenge_flags"])
    return entry


def _rejected(e: dict) -> list[str]:
    return e["ethics_flags"] + [f"défi non lancé : {m}" for m in e.get("challenge_flags") or []]


def _bank_ok(item: dict, account: str, day: dt.date) -> bool:
    """Hors défi, un sujet/rappel/variante de banque qui parle du défi est écarté (le reste est rendu sans {episode_intro})."""
    return not (_no_challenge(account, day) and challenge.mentions(item))


# ---------------------------------------------------------------- fallback banque
def _pick_bank_topic(topics: list[dict], used: dict, taken: set, day_n: int | None, formats_today: set,
                     ranking: list[str], today_ids: set | None = None, weekday: int | None = None,
                     want_stage: str | None = None) -> dict | None:
    today_ids = today_ids or set()
    avail = [t for t in topics if t["id"] not in used and t["id"] not in taken]
    rank = {f: i for i, f in enumerate(ranking)}

    def key(t):
        dh = t.get("day_hint")
        if day_n is not None and dh is not None:
            # jour exact > jours passés (rattrapage) > jours futurs (à garder pour plus tard)
            timing = 0 if dh == day_n else (1 if dh < day_n else 50 + dh)
        else:
            timing = 2 if day_n is not None else 0
        wrong_day = any(w in t.get("subject", "").lower() for w in WEEKDAYS_FR if w != WEEKDAYS_FR[weekday]) \
            if weekday is not None else False
        stage_miss = bool(want_stage) and quality.infer_stage(t) != want_stage
        return (wrong_day, timing, stage_miss, t.get("format") in formats_today, rank.get(t.get("format"), 99))

    if avail:
        return sorted(avail, key=key)[0]
    # banque épuisée : reprise des sujets les plus anciens (signalée)
    old = [t for t in topics if t["id"] not in today_ids]
    if not old:
        return None
    t = dict(sorted(old, key=lambda t: (t["id"] in taken, used.get(t["id"], "")))[0])
    t["subject"] = "[REPRISE, nouvel angle à trouver] " + t.get("subject", "")
    return t


def is_rappel_day(day: dt.date) -> bool:
    if not ethics.islamic():
        return False
    cfg = (ethics.identity().get("islamic") or {}).get("rappels") or {}
    days = list(cfg.get("weekdays", [3, 6]))[: int(cfg.get("per_week_per_account", 2))]
    return day.weekday() in days


def _pick_rappel(rappels: list[dict], used: dict, taken: set) -> dict | None:
    avail = [r for r in rappels if r["id"] not in used and r["id"] not in taken]
    if avail:
        return avail[0]
    old = [r for r in rappels if r["id"] not in taken]
    return sorted(old, key=lambda r: used.get(r["id"], ""))[0] if old else None


def _choose_test_format(account: str, synthesis: dict, week_start: dt.date) -> dict | None:
    no_ch = account == "personal" and not challenge.active_in(week_start)
    tf = synthesis.get("test_format")
    if tf and tf.get("variants"):
        if not (no_ch and challenge.format_mentions(tf)):
            return tf
        logger.warning("format test de la synthèse « %s » écrit pour le défi (non lancé) → banque", tf.get("name"))
    bank = list(test_formats(account).values())
    if no_ch:  # formats test intrinsèquement liés au défi (ex. check-in « Day X/90 ») écartés
        bank = [f for f in bank if not challenge.format_mentions(f)]
    if not bank:
        return None
    return bank[week_index(week_start) % len(bank)]


def week_index(week_start: dt.date) -> int:
    """N° de semaine depuis le début du défi (0 = 1re semaine), sinon n° de semaine absolu → rotation des formats test."""
    start = settings().challenge_start
    return max((week_start - start).days // 7, 0) if start else week_start.toordinal() // 7


def _plan_day_bank(conn, account, day, used, taken, synthesis, test_fmt, day_idx, stages=None) -> list[dict]:
    stages = stages or [None, None, None]
    bank = load_content_bank(account)
    fmts = proven_formats(conn, account)
    ranking = synthesis.get("format_ranking") or list(fmts)
    day_n = settings().challenge_day(day) if account == "personal" else None
    topics = [t for t in bank.get("topics") or [] if _bank_ok(t, account, day)]
    rappels = [r for r in bank.get("rappels") or [] if _bank_ok(r, account, day)]
    out, formats_today, today_ids = [], set(), set()
    n_proven = int(settings().get("calendar.proven_per_day", 2))
    rappel_slot = n_proven if is_rappel_day(day) and rappels else None
    for slot in range(1, n_proven + 1):
        if slot == rappel_slot:
            r = _pick_rappel(rappels, used, taken)
            if r:
                taken.add(r["id"])
                fmt = fmts.get(r.get("format"), {"id": r.get("format"), "name": r.get("format")})
                out.append(_entry(account, day, slot, "proven", fmt, {**r, "is_rappel": True}, synthesis, "bank", r["id"], "mofu"))
                continue
        for _ in range(8):  # saute les sujets bloqués par le garde-fou éthique
            t = _pick_bank_topic(topics, used, taken, day_n, formats_today, ranking, today_ids, day.weekday(),
                                 stages[slot - 1] if slot - 1 < len(stages) else None)
            if not t:
                break
            taken.add(t["id"])
            today_ids.add(t["id"])
            fmt = fmts.get(t.get("format"), {"id": t.get("format"), "name": t.get("format")})
            e = _entry(account, day, slot, "proven", fmt, t, synthesis, "bank", t["id"], quality.infer_stage(t))
            if _rejected(e):
                logger.warning("sujet %s écarté (%s)", t["id"], "; ".join(_rejected(e)))
                continue
            formats_today.add(t.get("format"))
            out.append(e)
            break
    variants = [(k, v) for k, v in enumerate((test_fmt or {}).get("variants") or []) if _bank_ok(v, account, day)]
    if variants:
        k, v = variants[day_idx % len(variants)]
        out.append(_entry(account, day, n_proven + 1, "test", test_fmt, v, synthesis, "bank", f"{test_fmt['id']}#v{k + 1}"))
    return out


# ---------------------------------------------------------------- génération LLM
LLM_INSTRUCTIONS = """Génère les 3 vidéos du {weekday} {date} pour le compte « {account_name} ».
{challenge_line}
Contexte du compte : {niche}
Langue : {language}, phrases courtes, ton naturel du créateur (voir identité et contexte), zéro jargon corporate.

Étapes de funnel imposées pour ce jour : {funnel_line}
Définitions : {funnel_defs}
Slots :
 1 et 2 = formats ÉPROUVÉS (choisis parmi : {proven_ids})
 3 = FORMAT TEST de la semaine « {test_name} » (emprunté à la niche {test_niche}) : {test_adaptation}
     Brief de la variante du jour (à améliorer, garder l'esprit, hooks DIFFÉRENTS des autres jours) : {test_variant}

{rappel_line}
Synthèse hebdo de ce qui surperforme (applique-la) :
{synthesis}

Sujets déjà traités (ne pas répéter) : {used}

Exemples de style (banque) :
{examples}

{hook_library}

Renvoie un tableau JSON de {n_videos} objets, chacun :
{{"slot": 1|2|3, "format_id": "...", "subject": "...", "hooks": ["hook verbal A (<3 s)", "hook verbal B (<3 s)"],
 "text_hook": "texte écran ≤ 7 mots", "visual_hook": "action visible en 1re seconde",
 "script": "130-160 mots, oral, commence après le hook, re-hook au milieu, finit sur le CTA",
 "cta": "...", "cta_type": "follow_series|comment_keyword|save|share|dm|soft",
 "setup": one of {setups}, "shots": ["liste de plans concrets à filmer (4-7)"], "principles": ["IDs skill"],
 "funnel_stage": "tofu|mofu|bofu (celle imposée pour ce slot)",
 "is_rappel": true|false, "theme": "(rappel seulement) intention|barakah|honnetete|tawakkul|temps|argent",
 "citation_candidates": [(rappel seulement) {{"type":"quran","ref":"65:3","expected_keywords":["confiance"]}} ou
                         {{"type":"hadith","collection":"bukhari","number":1,"expected_keywords":["intention"]}}]}}
{abs_rules}
Regroupe si possible les vidéos du jour sur 1-2 setups pour filmer vite. Pour les chiffres réels que seul le créateur connaît, écris [à compléter : ...].
Ajoute aussi "reference_query" : une requête YouTube (4-8 mots, anglais) pour trouver une VRAIE vidéo courte qui a marché avec ce format/angle."""
OUTPUT_SPEC = LLM_INSTRUCTIONS[LLM_INSTRUCTIONS.index("Renvoie un tableau JSON"):]  # schéma + règles, partagés avec les campagnes

AI_TICS = [  # tournures qui sonnent IA (règle anti-ia)
    r"\b(ce|c')\s*n'est pas [^.!?]{1,90}[,;:]\s*(c'est|mais)\b",
    r"\bn'est pas (seulement|juste|qu'?un) [^.!?]{1,60}[,;:]\s*c'est\b",
    r"\bce n'est pas [^.!?]{1,60}\. c'est\b",
    r"[\u2014\u2013]",
]
TEXT_FIELDS = ("subject", "text_hook", "script", "cta", "visual_hook")


def _ai_tics(text: str) -> bool:
    return any(re.search(p, text or "", re.I) for p in AI_TICS)


def _clean_items(items: list[dict], src_reels: dict, src_ideas: dict) -> None:
    """Après génération : codes internes Rn/In remplacés, tournures IA réécrites, une seule idée par vidéo longue."""
    names = {k: f"le reel de @{v['handle']}" for k, v in src_reels.items()}
    names.update({k: f"« {v['title']} »" for k, v in src_ideas.items()})

    def sub(x):
        if isinstance(x, str):
            return re.sub(r"\b([RI]\d{1,2})\b", lambda m: names.get(m.group(1), m.group(1)), x)
        if isinstance(x, list):
            return [sub(v) for v in x]
        if isinstance(x, dict):
            return {k: (v if k in ("source_reel", "source_idea") else sub(v)) for k, v in x.items()}
        return x

    for n, it in enumerate(items):
        items[n] = it = sub(it)
        fields = [(f, None) for f in TEXT_FIELDS if _ai_tics(it.get(f) or "")]
        fields += [("hooks", i) for i, h in enumerate(it.get("hooks") or []) if _ai_tics(h)]
        for f, i in fields:
            text = it[f] if i is None else it[f][i]
            fixed = llm.complete(
                "Tu enlèves le ton IA d'un texte parlé en français, sans changer ce qu'il dit ni sa longueur. Interdit : "
                "« ce n'est pas X, c'est Y », « pas X mais Y » en antithèse, tirets longs, formules. Phrases plates et directes, "
                "tutoiement, mots simples. Garde la dernière phrase (CTA) mot pour mot si c'est un script. Réponds uniquement par le texte.",
                text, max_tokens=1200).strip()
            if fixed and not _ai_tics(fixed):
                if i is None:
                    it[f] = fixed
                else:
                    it[f][i] = fixed
    if src_ideas:
        titles = [src_ideas.get(str(it.get("source_idea") or ""), {}).get("url") for it in items]
        dup = {t for t in titles if t and titles.count(t) > 1}
        if dup:
            raise ValueError(f"deux vidéos de la journée partent de la même vidéo longue : {dup}")


MAX_WORDS, MIN_WORDS = 200, 110


def _fit_length(items: list[dict]) -> None:
    """Verrou de longueur : un script hors 110-200 mots est réécrit à ~150 mots, sens, exemples et CTA gardés."""
    for it in items:
        script = (it.get("script") or "").strip()
        n = len(script.split())
        if MIN_WORDS <= n <= MAX_WORDS or not script:
            continue
        for _ in range(2):
            fixed = llm.complete(
                "Tu raccourcis ou rallonges un script de vidéo courte parlée. Tu gardes la voix, le tutoiement, l'idée, "
                "l'exemple concret et la dernière phrase (le CTA) mot pour mot. Aucun fait nouveau. Réponds uniquement par le script.",
                f"Réécris ce script en 140 à 170 mots (il en fait {n}) :\n\n{script}", max_tokens=1200).strip()
            if MIN_WORDS <= len(fixed.split()) <= MAX_WORDS:
                it["script"] = fixed
                break
            script, n = fixed, len(fixed.split())


CAMPAIGN_INSTRUCTIONS = """Génère les {n_videos} vidéos du {weekday} {date} pour le compte « {account_name} »,
dans la campagne « {title} ». Le type et l'angle de chaque slot sont IMPOSÉS par la campagne (ne les change pas).
Brief de la campagne :
{brief}
Contexte du compte : {niche}
Langue : {language}, phrases courtes, ton naturel du créateur (voir identité et contexte), zéro jargon corporate.

Slots :
{slot_lines}

Hooks : c'est la priorité de la campagne. 2 hooks verbaux VRAIMENT différents par vidéo (angle, mécanisme), < 3 s,
qui arrêtent la cible du compte en plein scroll ; texte écran et hook visuel cohérents avec le hook A.
Déjà écrit dans cette campagne (ne répète ni les sujets ni les hooks) : {used}

{rappel_line}

{hook_library}

{sources}
PREUVES : n'utilise QUE les preuves listées dans « Mes preuves » (contexte, fichier 05_preuves.md). S'il n'y en a aucune,
la vidéo BOFU/MOFU convainc par une démonstration (méthode montrée à l'écran, calcul simple, avant/après d'un process)
et ne contient AUCUN résultat client, aucune capture client, aucun « [à compléter] » à ce sujet.

Champ supplémentaire "notes" (string, français) : ce que le créateur doit préparer ou vérifier pour cette vidéo
(faits à compléter, autorisation client, éléments à capturer à l'écran, animations à générer).

""" + OUTPUT_SPEC


def _hook_library(account: str) -> str:
    try:
        from . import hooklab

        return hooklab.library_text(account)[:6000]
    except Exception as e:  # le Hook Lab est un bonus : jamais bloquant
        logger.warning("bibliothèque Hook Lab indisponible : %s", e)
        return ""


def _plan_day_llm(conn, account, day, used_subjects, synthesis, test_fmt, day_idx, rappel_themes_used=None, stages=None) -> list[dict]:
    stages = stages or ["tofu", "mofu", "tofu"]
    cfg = settings().accounts.get(account, {})
    bank = load_content_bank(account)
    fmts = {k: _fmt_for(account, day, f) for k, f in proven_formats(conn, account).items()}
    ctx = _ctx(account, day)
    test_fmt = _fmt_for(account, day, test_fmt) if test_fmt else test_fmt
    variant = (test_fmt.get("variants") or [{}])[day_idx % max(len(test_fmt.get("variants") or [1]), 1)] if test_fmt else {}
    examples = [{k: t.get(k) for k in ("format", "subject", "hooks", "script", "cta")}
                for t in (bank.get("topics") or []) if _bank_ok(t, account, day)][:3]
    syn_short = {k: synthesis.get(k) for k in ("niche", "my_stats", "promotions") if synthesis.get(k)}
    prompt = LLM_INSTRUCTIONS.format(
        language="ANGLAIS parlé naturel (contractions)" if settings().get("language") == "en" else "français oral, tutoiement",
        funnel_line=", ".join(f"slot {i + 1} = {s.upper()}" for i, s in enumerate(stages))
                    + (" (le rappel du slot 2 reste MOFU)" if is_rappel_day(day) else ""),
        funnel_defs=" | ".join(quality.STAGE_DEF.values()),
        weekday=WEEKDAYS_FR[day.weekday()], date=day.isoformat(), account_name=cfg.get("name", account),
        challenge_line=_challenge_line(account, day, ctx, series=True),
        niche=cfg.get("niche", ""), proven_ids=json.dumps({k: v.get("name") for k, v in fmts.items()}, ensure_ascii=False),
        test_name=(test_fmt or {}).get("name", "-"), test_niche=(test_fmt or {}).get("source_niche", "-"),
        test_adaptation=(test_fmt or {}).get("adaptation", ""),
        test_variant=json.dumps(render(variant, ctx) if _bank_ok(variant, account, day) else
                                {k: variant.get(k) for k in ("subject",)} | {"note": "réécris cette variante sans aucune référence au défi"},
                                ensure_ascii=False)[:1500],
        synthesis=json.dumps(syn_short, ensure_ascii=False, default=str)[:5000], used=json.dumps(used_subjects[-40:], ensure_ascii=False),
        examples=json.dumps(render(examples, ctx), ensure_ascii=False)[:4000], setups=list(SETUP_LABELS),
        hook_library=_hook_library(account), n_videos=3, abs_rules=ethics.absolute_rules(),
        rappel_line=("ATTENTION : le slot 2 de ce jour est un RAPPEL islamique axé business (is_rappel=true), intégré au "
                     "format documentaire, jamais un sermon ; thèmes déjà traités : " + ", ".join(rappel_themes_used or []) + ". "
                     "Pour citation_candidates, choisis UNIQUEMENT parmi ces candidats déjà vérifiés (copie-les tels quels) : "
                     + json.dumps({r.get("theme"): r.get("citation_candidates") for r in bank.get("rappels") or []}, ensure_ascii=False))
        if is_rappel_day(day) else "Aucun rappel ce jour (is_rappel=false partout).",
    )
    items = llm.complete_json(principles.system_prompt(f"Tu es le directeur de contenu {ethics.of_owner()}."), prompt, max_tokens=6000)
    out = []
    for it in items:
        slot = int(it.get("slot", len(out) + 1))
        if slot == 3 and test_fmt:
            fmt, stype, tid = test_fmt, "test", f"{test_fmt['id']}#v{day_idx + 1}"
        else:
            fmt = fmts.get(it.get("format_id"), {"id": it.get("format_id"), "name": it.get("format_id")})
            stype, tid = "proven", None
        st = stages[slot - 1] if 0 < slot <= len(stages) else None
        out.append(_entry(account, day, slot, stype, fmt, it, synthesis, "llm", tid, st))
    if len(out) < 3:
        raise ValueError(f"LLM a renvoyé {len(out)} vidéos au lieu de 3")
    bad = [e["code"] + " " + "; ".join(_rejected(e)) for e in out if _rejected(e)]
    if bad:
        raise ValueError(f"garde-fou : {bad}")
    return out


def _challenge_line(account: str, day: dt.date, ctx: dict, series: bool = False) -> str:
    if account != "personal":
        return ""
    if not ctx.get("jour"):
        return challenge.NO_CHALLENGE_RULE
    line = (f"Épisode du défi : Jour {ctx['jour']}/{ctx['total']} (« Day {ctx['jour']}/{ctx['total']} » en anglais ; "
            f"objectif : dépasser {ctx['objectif']}).")
    return line + (" Chaque vidéo affiche le compteur et s'inscrit dans la continuité de la série." if series else "")


# ---------------------------------------------------------------- campagnes (config/campaigns/*.yaml)
def _campaign_rappel_candidates(account: str, theme: str | None) -> list[dict]:
    return [c for r in load_content_bank(account).get("rappels") or [] if r.get("theme") == theme
            for c in r.get("citation_candidates") or []]


def _campaign_entries(account, day, camp, slots, items, synthesis, source, indexes=None) -> list[dict]:
    out = []
    for i, slot, it in zip(indexes or range(1, len(slots) + 1), slots, items):
        it = {**it, "funnel_stage": slot.get("funnel") or it.get("funnel_stage"), "setup": it.get("setup") or slot.get("setup")}
        if slot["is_rappel"]:
            it.update(is_rappel=True, theme=slot.get("theme") or it.get("theme"))
            it["citation_candidates"] = it.get("citation_candidates") or _campaign_rappel_candidates(account, it["theme"])
        fmt = {"id": f"campaign:{slot['type']}", "name": slot["name"], "script_structure": slot["instructions"]}
        e = _entry(account, day, i, "proven", fmt, it, synthesis, source, f"{camp['id']}#{day.isoformat()}-{i}", slot.get("funnel"))
        e["campaign"] = campaigns.tag(camp, slot, it)
        out.append(e)
    return out


def _plan_day_campaign_llm(account, day, camp, slots, used_subjects, synthesis, indexes=None, extra="", conn=None) -> list[dict]:
    cfg = settings().accounts.get(account, {})
    lines = [f" {i} = {s['name'].upper()}, angle imposé : {s['angle']}\n     {s['instructions']} (funnel : {s.get('funnel') or 'libre'})"
             for i, s in enumerate(slots, start=1)]
    rappel = next((s for s in slots if s["is_rappel"]), None)
    from . import veille
    src_text, src_reels, src_ideas = veille.sources(account)
    prompt = CAMPAIGN_INSTRUCTIONS.format(
        n_videos=len(slots), weekday=WEEKDAYS_FR[day.weekday()], date=day.isoformat(), account_name=cfg.get("name", account),
        title=camp.get("title", camp["id"]), brief=str(camp.get("brief", "")).strip(), niche=cfg.get("niche", ""),
        language="ANGLAIS parlé naturel (contractions)" if settings().get("language") == "en" else "français oral, tutoiement",
        slot_lines="\n".join(lines), used=json.dumps(used_subjects[-40:], ensure_ascii=False), setups=list(SETUP_LABELS),
        hook_library=_hook_library(account), abs_rules=ethics.absolute_rules(), sources=src_text,
        rappel_line=(f"Le slot {slots.index(rappel) + 1} est un RAPPEL islamique (is_rappel=true, theme « {rappel['theme']} »). "
                     "Pour citation_candidates, choisis UNIQUEMENT parmi ces candidats déjà vérifiés (copie-les tels quels) : "
                     + json.dumps(_campaign_rappel_candidates(account, rappel["theme"]), ensure_ascii=False))
        if rappel else "Aucun rappel ce jour (is_rappel=false partout).") + extra
    items = llm.complete_json(principles.system_prompt(f"Tu es le directeur de contenu {ethics.of_owner()}."), prompt, max_tokens=8000)
    items = items if isinstance(items, list) else [items]
    if len(items) < len(slots):
        raise ValueError(f"LLM a renvoyé {len(items)} vidéos au lieu de {len(slots)}")
    items = sorted(items, key=lambda it: int(it.get("slot") or 99))[: len(slots)]
    _fit_length(items)
    _clean_items(items, src_reels, src_ideas)
    out = _campaign_entries(account, day, camp, slots, items, synthesis, "llm", indexes)
    if src_reels or src_ideas:  # veille obligatoire : chaque vidéo part d'un reel gagnant + d'une grande idée
        missing = []
        for e, it in zip(out, items):
            r, i = src_reels.get(str(it.get("source_reel") or "")), src_ideas.get(str(it.get("source_idea") or ""))
            if src_reels and not r or src_ideas and not i:
                missing.append(e["code"])
                continue
            if r:
                e["reference"] = {"url": r["url"], "video_id": r["video_id"], "title": r["hook_text"], "channel": r["handle"],
                                  "platform": r["platform"], "views": r["views"], "source": "veille",
                                  "funnel_stage": r["funnel_stage"], "hook_model": r["hook_text"],
                                  "why": f"x{r['score']} la médiane de @{r['handle']} · hook repris en modèle, format {r['visual_format']}"}
            if i:
                e["big_idea"] = {k: i[k] for k in ("url", "title", "channel", "views", "score", "idea")}
        if missing:
            raise ValueError(f"vidéos sans source de veille : {missing}")
        veille.mark_used([src_ideas[str(it.get('source_idea'))]["id"] for it in items if str(it.get("source_idea")) in src_ideas], conn)
    bad = [e["code"] + " " + "; ".join(_rejected(e)) for e in out if _rejected(e)]
    if bad:
        raise ValueError(f"garde-fou : {bad}")
    return out


def _plan_day_campaign_bank(conn, account, day, camp, slots, used, taken, synthesis, indexes=None) -> list[dict]:
    items = []
    for s in slots:
        if s["is_rappel"]:
            rappels = [r for r in load_content_bank(account).get("rappels") or [] if r.get("theme") == s.get("theme")]
            r = _pick_rappel(rappels, used, taken)
            if r:
                taken.add(r["id"])
                items.append({k: v for k, v in r.items() if k != "id"})
                continue
        items.append(campaigns.fallback_item(camp, s))
    return _campaign_entries(account, day, camp, slots, items, synthesis, "bank", indexes)


# ---------------------------------------------------------------- orchestration
def plan_week(start: dt.date | None = None, days: int | None = None, use_llm: bool | None = None,
              accounts: list[str] | None = None, with_references: bool = True) -> list[dict]:
    start = start or default_week_start()
    days = days or int(settings().get("calendar.days", 7))
    use_llm = llm.available() if use_llm is None else use_llm
    accounts = accounts or list(settings().accounts)
    end = start + dt.timedelta(days=days - 1)
    all_entries: list[dict] = []
    with db.session() as conn:
        for account in accounts:
            synthesis = _latest_synthesis(conn, account)
            test_fmt = _choose_test_format(account, synthesis, start)
            conn.execute("DELETE FROM calendar WHERE account=? AND date BETWEEN ? AND ? AND status='planned'",
                         (account, start.isoformat(), end.isoformat()))
            used = _used_topics(conn, account, start.isoformat())
            used_subjects = [r["s"] for r in conn.execute(
                "SELECT json_extract(data,'$.subject') s FROM calendar WHERE account=? ORDER BY date", (account,))]
            taken: set = set()
            rappel_themes: list = []
            funnel = quality.week_plan(account, days, 3, start.isoformat())
            for i in range(days):
                day = start + dt.timedelta(days=i)
                if conn.execute("SELECT 1 FROM calendar WHERE account=? AND date=?", (account, day.isoformat())).fetchone():
                    logger.info("%s %s déjà filmé/publié → conservé", account, day)
                    continue
                entries = None
                camp = campaigns.for_day(account, day)
                if camp:
                    if use_llm:
                        for attempt in range(2):
                            try:
                                entries = _plan_day_campaign_llm(account, day, *camp, used_subjects, synthesis, conn=conn)
                                break
                            except Exception as e:
                                logger.warning("campagne %s : génération LLM KO (%s, essai %d) : %s", camp[0]["id"], day, attempt + 1, e)
                    if entries is None:
                        entries = _plan_day_campaign_bank(conn, account, day, *camp, used, taken, synthesis)
                elif use_llm:
                    for attempt in range(2):
                        try:
                            entries = _plan_day_llm(conn, account, day, used_subjects, synthesis, test_fmt, i, rappel_themes, funnel[i])
                            break
                        except Exception as e:
                            logger.warning("génération LLM KO (%s %s, essai %d) : %s", account, day, attempt + 1, e)
                    if entries is None:
                        logger.warning("→ fallback banque pour %s %s", account, day)
                if entries is None:
                    entries = _plan_day_bank(conn, account, day, used, taken, synthesis, test_fmt, i, funnel[i])
                for e in entries:
                    used_subjects.append(e["subject"])
                    if e.get("rappel_theme"):
                        rappel_themes.append(e["rappel_theme"])
                    conn.execute(
                        """INSERT INTO calendar(code, week_start, date, account, slot_index, slot_type, format_id, topic_id,
                               day_number, setup, data, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(date, account, slot_index) DO UPDATE SET code=excluded.code, data=excluded.data,
                               slot_type=excluded.slot_type, format_id=excluded.format_id, topic_id=excluded.topic_id,
                               setup=excluded.setup, source=excluded.source, week_start=excluded.week_start""",
                        (e["code"], start.isoformat(), e["date"], account, e["slot_index"], e["slot_type"], e["format"]["id"],
                         e["topic_id"], e["day_number"], e["setup"], db.dumps(e), e["source"]),
                    )
                all_entries.extend(entries)
        db.log_run(conn, "calendar", "plan_week", "ok", f"{start}→{end} : {len(all_entries)} vidéos")
    logger.info("calendrier %s → %s : %d vidéos planifiées", start, end, len(all_entries))
    if with_references:
        try:
            from .references import attach

            attach(all_entries)
        except Exception as e:
            logger.warning("références KO : %s", e)
    return all_entries


def load_entries(start: dt.date, end: dt.date, account: str | None = None) -> list[dict]:
    with db.session() as conn:
        q = "SELECT data, status, id FROM calendar WHERE date BETWEEN ? AND ?"
        args: list = [start.isoformat(), end.isoformat()]
        if account:
            q += " AND account=?"
            args.append(account)
        rows = conn.execute(q + " ORDER BY date, account, slot_index", args).fetchall()
    out = []
    for r in rows:
        e = db.loads(r["data"], {})
        e["status"] = r["status"]
        e["calendar_id"] = r["id"]
        out.append(e)
    return out


# ---------------------------------------------------------------- régénération d'une vidéo (dashboard)
REGEN_PROMPT = """Réécris UNE vidéo du calendrier du créateur ({account_name}, {weekday} {date}, slot {slot} = {slot_type}).
{challenge_line}
Vidéo actuelle :
{current}

Consigne du créateur : {instruction}

Contraintes : garde le même slot{fmt_rule} et l'étape de funnel {stage} ({stage_def}). {rappel_rule}
Sujets déjà au calendrier (ne pas dupliquer) : {used}
Format disponible(s) : {formats}

Renvoie UN objet JSON : {{"format_id": "...", "subject": "...", "hooks": ["A (<3 s)", "B (<3 s)"], "text_hook": "≤ 7 mots",
 "visual_hook": "...", "script": "130-160 mots, oral, commence après le hook, re-hook au milieu, finit sur le CTA",
 "cta": "...", "cta_type": "follow_series|comment_keyword|save|share|dm|soft", "setup": one of {setups},
 "shots": ["4-7 plans concrets"], "principles": ["IDs skill"], "reference_query": "requête YouTube 4-8 mots (anglais)",
 "funnel_stage": "tofu|mofu|bofu",
 "is_rappel": bool, "theme": "...", "citation_candidates": [...]}}
{abs_rules}"""


def regenerate(code: str, instruction: str = "") -> dict:
    """Régénère une seule vidéo (Claude si dispo, sinon prochain sujet/variante de la banque) et la sauvegarde."""
    with db.session() as conn:
        row = conn.execute("SELECT * FROM calendar WHERE code=?", (code,)).fetchone()
        if not row:
            raise KeyError(code)
        account, day, slot, slot_type = row["account"], dt.date.fromisoformat(row["date"]), row["slot_index"], row["slot_type"]
        week_start = dt.date.fromisoformat(row["week_start"])
        day_idx = max((day - week_start).days, 0)
        old = db.loads(row["data"], {})
        synthesis = _latest_synthesis(conn, account)
        test_fmt = _choose_test_format(account, synthesis, week_start)
        fmts = proven_formats(conn, account)
        bank = load_content_bank(account)
        used_subjects = [r["s"] for r in conn.execute(
            "SELECT json_extract(data,'$.subject') s FROM calendar WHERE account=? AND code<>?", (account, code))]
        entry = None
        camp = campaigns.for_day(account, day) if old.get("campaign") else None
        if camp and 0 < slot <= len(camp[1]):  # vidéo de campagne : même type, même angle
            c, one = camp[0], [camp[1][slot - 1]]
            if llm.available():
                extra = ("\n\nC'est une RÉÉCRITURE de ce slot. Vidéo actuelle : "
                         + json.dumps({k: old.get(k) for k in ("subject", "hooks", "script", "cta", "setup", "shots")}, ensure_ascii=False)[:4000]
                         + "\nConsigne du créateur : " + (instruction or "propose une meilleure version (hook plus fort, angle plus spécifique)"))
                for attempt in range(2):
                    try:
                        entry = _plan_day_campaign_llm(account, day, c, one, used_subjects, synthesis, [slot], extra, conn=conn)[0]
                        break
                    except Exception as ex:
                        logger.warning("régénération campagne %s KO (essai %d) : %s", code, attempt + 1, ex)
            if entry is None:
                entry = _plan_day_campaign_bank(conn, account, day, c, one, _used_topics(conn, account, "9999-12-31"), set(),
                                                synthesis, [slot])[0]
        elif llm.available():
            ctx = _ctx(account, day)
            rappel = bool(old.get("is_rappel"))
            prompt = REGEN_PROMPT.format(
                account_name=settings().accounts.get(account, {}).get("name", account), weekday=WEEKDAYS_FR[day.weekday()],
                date=day.isoformat(), slot=slot, slot_type=slot_type,
                challenge_line=_challenge_line(account, day, ctx),
                current=json.dumps({k: old.get(k) for k in ("subject", "hooks", "script", "cta", "format", "setup", "shots")},
                                   ensure_ascii=False)[:4000],
                instruction=instruction or "propose une meilleure version (hook plus fort, angle plus spécifique)",
                fmt_rule=f" et le format test « {(test_fmt or {}).get('name')} »" if slot_type == "test" else "",
                stage=(old.get("funnel_stage") or "tofu").upper(), stage_def=quality.STAGE_DEF.get(old.get("funnel_stage") or "tofu"),
                rappel_rule=("C'est un RAPPEL islamique axé business (is_rappel=true) ; citation_candidates UNIQUEMENT parmi : "
                             + json.dumps({r.get("theme"): r.get("citation_candidates") for r in bank.get("rappels") or []},
                                          ensure_ascii=False)) if rappel else "Ce n'est pas un rappel (is_rappel=false).",
                used=json.dumps(used_subjects[-40:], ensure_ascii=False),
                formats=json.dumps({k: v.get("name") for k, v in fmts.items()} if slot_type == "proven"
                                   else {(test_fmt or {}).get("id"): (test_fmt or {}).get("name")}, ensure_ascii=False),
                setups=list(SETUP_LABELS), abs_rules=ethics.absolute_rules(),
            )
            for attempt in range(2):
                try:
                    it = llm.complete_json(principles.system_prompt(f"Tu es le directeur de contenu {ethics.of_owner()}."), prompt, max_tokens=4000)
                    it = it[0] if isinstance(it, list) else it
                    if slot_type == "test" and test_fmt:
                        fmt, tid = test_fmt, old.get("topic_id")
                    else:
                        fmt = fmts.get(it.get("format_id")) or fmts.get((old.get("format") or {}).get("id")) or {"id": it.get("format_id")}
                        tid = None
                    e = _entry(account, day, slot, slot_type, fmt, it, synthesis, "llm", tid, old.get("funnel_stage"))
                    if _rejected(e):
                        raise ValueError(f"garde-fou : {_rejected(e)}")
                    entry = e
                    break
                except Exception as ex:
                    logger.warning("régénération LLM %s KO (essai %d) : %s", code, attempt + 1, ex)
        if entry is None:  # fallback banque
            used = _used_topics(conn, account, "9999-12-31")
            variants = [(k, v) for k, v in enumerate((test_fmt or {}).get("variants") or []) if _bank_ok(v, account, day)]
            if slot_type == "test" and variants:
                k, v = variants[(day_idx + 1 + int(old.get("regen_count", 0))) % len(variants)]
                entry = _entry(account, day, slot, "test", test_fmt, v, synthesis, "bank", f"{test_fmt['id']}#v{k + 1}")
            else:
                pool = [t for t in (bank.get("rappels") if old.get("is_rappel") else bank.get("topics")) or [] if _bank_ok(t, account, day)]
                t = _pick_bank_topic(pool, used, {old.get("topic_id")}, settings().challenge_day(day) if account == "personal" else None,
                                     set(), synthesis.get("format_ranking") or [], {old.get("topic_id")}, day.weekday())
                if not t:
                    raise RuntimeError("banque épuisée, ajoute une clé/Claude ou des sujets")
                fmt = fmts.get(t.get("format"), {"id": t.get("format"), "name": t.get("format")})
                entry = _entry(account, day, slot, slot_type, fmt, {**t, "is_rappel": bool(old.get("is_rappel"))}, synthesis, "bank", t["id"])
        entry["regen_count"] = int(old.get("regen_count", 0)) + 1
        entry["regen_instruction"] = instruction
        conn.execute("UPDATE calendar SET data=?, format_id=?, topic_id=?, setup=?, source=?, status='planned' WHERE code=?",
                     (db.dumps(entry), entry["format"]["id"], entry["topic_id"], entry["setup"], entry["source"], code))
    try:
        from .references import attach

        attach([entry])
    except Exception as ex:
        logger.warning("référence KO : %s", ex)
    return entry


def update_entry(code: str, **fields) -> dict:
    """Met à jour des champs du JSON d'une vidéo (statut, plans cochés, citation vérifiée…)."""
    with db.session() as conn:
        row = conn.execute("SELECT data FROM calendar WHERE code=?", (code,)).fetchone()
        if not row:
            raise KeyError(code)
        e = db.loads(row["data"], {})
        status = fields.pop("status", None)
        e.update(fields)
        if status:
            e["status"] = status
            conn.execute("UPDATE calendar SET status=? WHERE code=?", (status, code))
        conn.execute("UPDATE calendar SET data=? WHERE code=?", (db.dumps(e), code))
    return e
