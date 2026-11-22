"""Carnet des corrections du créateur : chaque script qu'il réécrit à la main dans le dashboard devient un exemple
avant / après. data/corrections.jsonl garde tout ; context/00_corrections.md (injecté dans TOUS les prompts
via principles.context_text) montre les plus récentes pour que les générations suivantes écrivent comme lui."""
from __future__ import annotations

import datetime as dt
import json

from .config import ROOT

LOG = ROOT / "data" / "corrections.jsonl"
CTX = ROOT / "context" / "00_corrections.md"
KEEP = 6           # exemples montrés au modèle
MAX_CHARS = 6000   # budget dans le contexte (context_text coupe à 40 000)


def record(entry: dict, before: dict, after: dict) -> None:
    camp = entry.get("campaign") or {}
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "code": entry.get("code"),
           "stage": entry.get("funnel_stage"), "type": camp.get("label") or entry.get("format"),
           "subject": entry.get("subject"), "before": before, "after": after}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    rebuild()


def load() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def rebuild() -> None:
    rows = load()
    latest = {}
    for r in rows:  # une seule version par vidéo : la dernière
        latest[r["code"]] = r
    rows = sorted(latest.values(), key=lambda r: r["ts"], reverse=True)[:KEEP]
    from .ethics import owner
    name = owner()
    head = (f"# Corrections de {name} (exemples à imiter)\n\n"
            f"{name} a réécrit ces scripts à la main. Sa version (APRÈS) est la référence de ton, de longueur, de vocabulaire "
            "et de structure : écris comme l'APRÈS, jamais comme l'AVANT. Repère ce qu'il supprime (formules abstraites, "
            "précautions, exemples hors sujet) et ce qu'il ajoute.\n")
    blocks = []
    for r in rows:
        b, a = r["before"], r["after"]
        parts = [f"## {r.get('stage', '').upper()} · {r.get('type') or ''} · {r.get('subject') or ''}"]
        for k, label in (("hook", "Hook"), ("script", "Script"), ("cta", "CTA")):
            if (b.get(k) or "") != (a.get(k) or ""):
                parts += [f"AVANT ({label}) : {b.get(k, '')}", f"APRÈS ({label}) : {a.get(k, '')}"]
        blocks.append("\n".join(parts))
    text = head
    for blk in blocks:
        if len(text) + len(blk) > MAX_CHARS:
            break
        text += "\n" + blk + "\n"
    CTX.write_text(text if blocks else "", encoding="utf-8")
