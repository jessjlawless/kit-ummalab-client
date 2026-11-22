"""Exports : calendrier Markdown + JSON, fiche de tournage du jour, export Cockpit.
Schéma Cockpit documenté dans docs/COCKPIT_EXPORT.md."""
from __future__ import annotations

import datetime as dt
import json
from collections import OrderedDict
from pathlib import Path

from . import log, principles
from .config import OUTPUT_DIR, settings
from .formats import SETUP_LABELS
from .planner import WEEKDAYS_FR, load_entries

logger = log.get("exports")

COCKPIT_SCHEMA = "content-engine/calendar@1"
MIN_PER_VIDEO = 7      # A-roll (2 hooks + 2 prises) + B-roll
MIN_PER_SETUP = 5      # installation / lumière
SLOT_LABEL = {"proven": "éprouvé", "test": "TEST"}
ACC_SHORT = {"personal": "MON COMPTE"}

SETUP_GEAR = {
    "bureau": "téléphone sur trépied à hauteur des yeux, laptop ouvert (onglets Stripe/CRM prêts), micro-cravate",
    "chambre": "trépied, lumière douce (lampe + fenêtre), micro-cravate, lit/étagère rangés",
    "exterieur": "téléphone en main (stabilisation ON), micro sans fil, batterie chargée",
    "fac": "téléphone en main, mode silencieux, écouteurs pour discrétion",
    "cuisine": "trépied + 1 plan large, lumière plafond + fenêtre",
    "voiture": "support ventouse, moteur coupé (sécurité), micro-cravate",
    "salle_sport": "trépied compact, micro sans fil",
    "ecran": "enregistrement d'écran (QuickTime / iPhone), notifications coupées, comptes de démo prêts",
}


def _out(*parts) -> Path:
    p = OUTPUT_DIR.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fr_date(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{WEEKDAYS_FR[x.weekday()]} {x.strftime('%d/%m')}"


def _video_md(e: dict, level: str = "###", with_script: bool = True) -> list[str]:
    acc = ACC_SHORT.get(e["account"], e["account"])
    ep = f" · {e['episode_label']}" if e.get("episode_label") else ""
    rp = " · RAPPEL" if e.get("is_rappel") else ""
    L = [f"{level} [{acc} · {SLOT_LABEL.get(e['slot_type'], e['slot_type'])}{rp}{ep}] {e['subject']}",
         f"`{e['code']}` · format **{e['format'].get('name') or e['format'].get('id')}**"
         + (f" (emprunté à : {e['format']['source_niche']})" if e['format'].get('source_niche') else "")
         + f" · source : {e.get('source')}", ""]
    for h in e["hooks"]:
        L.append(f"- **Hook {h['variant']}** (à dire) : « {h['verbal']} »")
    if e["hooks"]:
        L.append(f"- **Texte écran** : {e['hooks'][0].get('text_on_screen') or '-'}")
        L.append(f"- **1re seconde (visuel)** : {e['hooks'][0].get('visual') or '-'}")
    L.append(f"- **CTA** : {e['cta']['text']} _({e['cta']['type']})_")
    ref = e.get("reference")
    if ref:
        L.append(f"- **Vidéo de référence (a marché)** : {ref['url']}, « {ref.get('title') or ''} » · {ref.get('why')}")
    else:
        L.append("- **Vidéo de référence** : _aucune trouvée pour l'instant (scraping réel nécessaire)_")
    idea = e.get("big_idea")
    if idea:
        L.append(f"- **Grande idée reprise** : {idea['idea']} · vidéo longue {idea['url']}, « {idea.get('title') or ''} »"
                 f" ({idea.get('channel')}, x{idea.get('score')})")
    cit = e.get("citation")
    if cit:
        if cit.get("status") == "citation à ajouter":
            L.append(f"- **Citation** : _citation à ajouter_ (aucune source vérifiée trouvée, idée : {cit.get('idea')}). "
                     "Ne cite rien de mémoire.")
        else:
            L.append(f"- **Citation, {cit['status']}** : {cit.get('reference')} · source : {cit.get('url')}"
                     + (f" · JSON : {cit['source_url']}" if cit.get("source_url") else ""))
            if cit.get("arabic"):
                L.append(f"  - Arabe : {cit['arabic']}")
            L.append(f"  - Texte source : « {cit.get('translation') or cit.get('french') or cit.get('text')} »")
    if e.get("ethics_flags"):
        L.append(f"- **⚠ À relire (garde-fou éthique)** : {'; '.join(e['ethics_flags'])}")
    if e.get("shots"):
        L += ["", "**Plans à filmer**"] + [f"- [ ] {s}" for s in e["shots"]]
    if with_script and e.get("script"):
        L += ["", f"**Script** (~{e.get('word_count', 0)} mots, après le hook)", ""]
        _h = ((e.get("hooks") or [{}])[0] or {}).get("verbal")
        if _h:
            L += [f"> **{_h}**"]
        L += ["> " + line if line.strip() else ">" for line in e["script"].splitlines()]
    et = e.get("edit_template") or {}
    if et:
        L += ["", "<details><summary>Modèle de montage</summary>", ""]
        for k in ("format", "pacing", "subtitles", "on_screen_text", "music"):
            if et.get(k):
                L.append(f"- {k} : {et[k]}")
        if et.get("broll"):
            L.append("- B-roll : " + ", ".join(et["broll"]))
        if et.get("inspiration_urls"):
            L.append("- Inspiration : " + " ".join(et["inspiration_urls"]))
        L += ["", "</details>"]
    if e.get("principles"):
        shown = e["principles"][:8]
        more = f" (+{len(e['principles']) - 8})" if len(e["principles"]) > 8 else ""
        L.append(f"\n_Principes : {', '.join(principles.describe(shown))}{more}_")
    L.append("")
    return L


# ---------------------------------------------------------------- calendrier semaine
def calendar_md(entries: list[dict], start: dt.date, end: dt.date) -> str:
    L = [f"# Calendrier de contenu, {start.strftime('%d/%m')} → {end.strftime('%d/%m/%Y')}", "",
         f"{len(entries)} vidéos · généré le {dt.datetime.now():%d/%m %H:%M}", ""]
    test = {e["account"]: e["format"] for e in entries if e["slot_type"] == "test"}
    if test:
        L.append("**Formats test de la semaine** : " + " · ".join(
            f"{ACC_SHORT[a]} → {f.get('name')} ({f.get('source_niche')})" for a, f in test.items()))
        L.append("")
    L += ["## Vue d'ensemble", "", "| Jour | Compte | Slot | Sujet | Setup |", "|---|---|---|---|---|"]
    for e in entries:
        L.append(f"| {_fr_date(e['date'])} | {ACC_SHORT[e['account']]} | {SLOT_LABEL[e['slot_type']]} | "
                 f"{e['subject'].replace('|', '/')} | {e['setup']} |")
    L.append("")
    by_day: OrderedDict[str, list] = OrderedDict()
    for e in entries:
        by_day.setdefault(e["date"], []).append(e)
    for d, es in by_day.items():
        perso = next((e for e in es if e.get("episode_label")), None)
        L += [f"## {_fr_date(d).capitalize()}" + (f", {perso['episode_label']}" if perso else ""), ""]
        for e in es:
            L += _video_md(e)
    return "\n".join(L)


def cockpit_payload(entries: list[dict], start: dt.date, end: dt.date) -> dict:
    s = settings()
    return {
        "schema": COCKPIT_SCHEMA,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "timezone": s.get("timezone"),
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "challenge": {"start_date": s.challenge_start.isoformat() if s.challenge_start else None,
                      "length_days": s.get("challenge.length_days"),
                      "objectif": s.get("challenge.objectif")},
        "accounts": [{"id": k, "name": v.get("name"), "handles": v.get("my_handles")} for k, v in s.accounts.items()],
        "videos": [{k: v for k, v in e.items() if k != "calendar_id"} for e in entries],
    }


def export_week(start: dt.date, end: dt.date) -> dict[str, Path]:
    entries = load_entries(start, end)
    tag = start.isoformat()
    md = _out("calendar", tag, "calendar.md")
    md.write_text(calendar_md(entries, start, end), encoding="utf-8")
    payload = cockpit_payload(entries, start, end)
    js = _out("calendar", tag, "calendar.json")
    js.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    cockpit = _out("cockpit", "latest.json")
    cockpit.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("calendrier exporté : %s", md)
    return {"markdown": md, "json": js, "cockpit": cockpit}


# ---------------------------------------------------------------- fiche de tournage
def shooting_sheet(day: dt.date) -> tuple[str, dict]:
    entries = load_entries(day, day)
    groups: OrderedDict[str, list] = OrderedDict()
    for e in sorted(entries, key=lambda e: e["setup"]):
        groups.setdefault(e["setup"], []).append(e)
    # setups les plus chargés d'abord, écran à la fin (peut se faire n'importe où)
    order = sorted(groups, key=lambda s: (s == "ecran", -len(groups[s])))
    minutes = len(entries) * MIN_PER_VIDEO + len(groups) * MIN_PER_SETUP
    ep = next((e["episode_label"] for e in entries if e.get("episode_label")), None)

    L = [f"# Fiche de tournage, {_fr_date(day.isoformat())}" + (f", {ep}" if ep else ""), "",
         f"**{len(entries)} vidéos · {len(groups)} setups · ~{minutes} min estimées**", ""]
    if not entries:
        L.append("_Aucune vidéo planifiée ce jour-là. Lance `engine weekly` (ou `engine calendar --start AAAA-MM-JJ`)._")
        return "\n".join(L), {"date": day.isoformat(), "videos": []}
    L += ["## Ordre de tournage", ""]
    for i, s in enumerate(order, 1):
        L.append(f"{i}. **{SETUP_LABELS.get(s, s)}**, {len(groups[s])} vidéo(s), ~{len(groups[s]) * MIN_PER_VIDEO + MIN_PER_SETUP} min")
    L += ["", "**Règles de tournage** : filme les 2 hooks (A et B) à la suite pour chaque vidéo · 1re seconde = déjà en "
          "mouvement · regarde l'objectif · si tu bafouilles, reprends la phrase entière (le montage coupe) · "
          "garde 1 s de silence avant/après chaque prise · AUCUNE musique (ni en fond pendant le tournage) · "
          "citations religieuses : lis uniquement le texte vérifié affiché, après l'avoir vérifié toi-même.", ""]
    for i, s in enumerate(order, 1):
        es = groups[s]
        L += [f"## Setup {i}, {SETUP_LABELS.get(s, s)}", "", f"Matériel : {SETUP_GEAR.get(s, '-')}", ""]
        for j, e in enumerate(es, 1):
            L += _video_md(e, level=f"### {i}.{j}")
        broll = [(e["code"], sh) for e in es for sh in e.get("shots", []) if "b-roll" in sh.lower()]
        if broll:
            L += ["### B-roll à enchaîner dans ce setup", ""] + [f"- [ ] {sh} _({c})_" for c, sh in broll] + [""]
    L += ["---", "Après le tournage : `engine edit --date " + day.isoformat() + "` → instructions ChatCut par vidéo."]
    data = {"schema": "content-engine/shooting@1", "date": day.isoformat(), "episode_label": ep,
            "estimated_minutes": minutes,
            "setups": [{"setup": s, "label": SETUP_LABELS.get(s, s), "gear": SETUP_GEAR.get(s),
                        "videos": [e["code"] for e in groups[s]]} for s in order],
            "videos": entries}
    return "\n".join(L), data


def export_shooting(day: dt.date) -> Path:
    md, data = shooting_sheet(day)
    p = _out("shooting", f"{day.isoformat()}.md")
    p.write_text(md, encoding="utf-8")
    _out("shooting", f"{day.isoformat()}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _out("shooting", "today.md").write_text(md, encoding="utf-8") if day == dt.date.today() else None
    logger.info("fiche de tournage : %s", p)
    return p
