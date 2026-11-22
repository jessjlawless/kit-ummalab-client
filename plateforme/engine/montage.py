"""Module 8, montage : une rush brute -> un reel 9:16 monté, dans le style choisi.

La plateforme ne refait pas un monteur : elle pilote le skill `supermonteur` (installé par le kit Claude)
avec `claude -p`, sur l'abonnement Claude de l'utilisateur. Un dossier par montage dans data/montages/<id>/ :
  rush.<ext>    la rush déposée
  job.json      style, statut, dates, fiche liée
  progress.txt  une ligne par étape (écrite par Claude), lue par le dashboard
  final.mp4     le reel monté
  resume.md     ce qui a été fait + la note /10
  claude.log    sortie brute de claude -p (debug)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from . import db, ethics, log
from .config import ROOT
from .llm import _claude_bin

logger = log.get(__name__)
DIR = ROOT / "data" / "montages"
SKILL = Path(os.path.expanduser("~/.claude/skills/supermonteur"))

STYLES = {
    "soustitres": {"desc": "Coupes serrées et sous-titres mot à mot. Le plus rapide, pour poster tous les jours.", "label": "Face cam sous-titrée", "file": "face-cam-soustitres.md",
                   "brief": "Face caméra, degré « sous-titres » : dérush serré + sous-titres mot à mot + mots forts. Rien d'autre."},
    "brolls": {"desc": "Sous-titres, chiffres en grand et plans de coupe. Pour tes vidéos phares.", "label": "Face cam + B-rolls", "file": "face-cam-high-prod.md",
               "brief": "Face caméra, degré « high prod », style Sobre : B-rolls seulement s'ils montrent ce que la tête ne peut pas "
                        "montrer (bibliothèque de B-rolls de l'utilisateur), chiffres géants, titre-question sur le hook."},
    "viral": {"desc": "Comparaison, mauvais / bien / excellent ou classement. La vidéo doit être écrite pour.", "label": "Format viral repris", "file": "montage-viral.md",
              "brief": "Montage viral (comparaison en T, mauvais / bien / excellent ou tier list) selon ce que la vidéo raconte. "
                       "Si la rush n'a pas été écrite pour ce format, fais un face cam high prod et dis-le dans resume.md."},
    "voixoff": {"desc": "Ta voix sur des images sans ton visage. Pour poster sans te montrer.", "label": "Voix off / faceless", "file": "voix-off.md",
                "brief": "Voix off : la voix de la rush sur des plans sans visage (B-rolls de l'utilisateur, captures, textes). "
                         "Jamais de visage généré par IA."},
}
STATUS = ("en cours", "fini", "erreur")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "reel"


def _job_path(mid: str) -> Path:
    p = (DIR / mid).resolve()
    if DIR.resolve() not in p.parents:
        raise ValueError("montage inconnu")
    return p


def _read(mid: str) -> dict:
    d = _job_path(mid)
    job = json.loads((d / "job.json").read_text()) if (d / "job.json").exists() else {}
    job["id"] = mid
    job["progress"] = (d / "progress.txt").read_text(errors="ignore").strip().splitlines() if (d / "progress.txt").exists() else []
    job["has_video"] = (d / "final.mp4").exists()
    job["resume"] = (d / "resume.md").read_text(errors="ignore") if (d / "resume.md").exists() else ""
    if job.get("status") == "en cours" and job.get("pid"):
        try:
            os.kill(job["pid"], 0)
        except OSError:  # process mort sans avoir écrit son statut (redémarrage, crash)
            job["status"] = "fini" if job["has_video"] else "erreur"
            _write(mid, job)
    return job


def _write(mid: str, job: dict) -> None:
    keep = {k: v for k, v in job.items() if k not in ("id", "progress", "has_video", "resume")}
    (_job_path(mid) / "job.json").write_text(json.dumps(keep, ensure_ascii=False, indent=2))


def list_jobs() -> list[dict]:
    if not DIR.exists():
        return []
    return [_read(p.name) for p in sorted(DIR.iterdir(), reverse=True) if (p / "job.json").exists()]


def get(mid: str) -> dict:
    return _read(mid)


def video_path(mid: str) -> Path:
    return _job_path(mid) / "final.mp4"


def _fiche(code: str | None) -> dict:
    if not code:
        return {}
    with db.session() as conn:
        row = conn.execute("SELECT data FROM calendar WHERE code=?", (code,)).fetchone()
    return db.loads(row["data"], {}) if row else {}


def _prompt(job: dict, rush: Path) -> str:
    st = STYLES[job["style"]]
    fiche = _fiche(job.get("code"))
    music = ("AUCUNE musique instrumentale (règle islamique de l'utilisateur) : pas de musique du tout, SFX très discrets "
             "seulement si le style en prévoit." if ethics.islamic() else
             "Musique : seulement un morceau libre de droits déjà présent dans les dossiers de l'utilisateur ; sinon, sans musique.")
    lines = [
        f"Tu es le monteur de la plateforme. Monte la rush {rush.name} (dossier courant) en reel 9:16 avec le skill supermonteur.",
        f"Lis d'abord {SKILL}/SKILL.md, puis le carnet ~/Documents/Brain/00-Moi/regles-agents/supermonteur.md s'il existe,",
        f"puis {SKILL}/lecons.md et UNIQUEMENT le style {SKILL}/styles/{st['file']}. Applique-les.",
        "",
        "MODE AUTOMATIQUE (personne ne peut répondre pendant le montage) :",
        f"- Le brief est déjà fait. Style : {st['label']}. {st['brief']}",
        f"- {music}",
        "- Pas de référence de style. Pas d'image générée par IA. Format 9:16 1080x1920 (rush horizontale : recadrage centré).",
        "- Ne pose aucune question et n'attends aucun OK de plan : décide comme un bon monteur, et note tes choix dans resume.md.",
        "- Ne publie rien, n'envoie rien, ne copie rien hors de ce dossier (pas de T9, pas de Drive).",
        "- Travaille et rends dans CE dossier (pas dans ~/Documents).",
        "",
        "AVANCEMENT : à chaque étape, ajoute UNE ligne courte en français à progress.txt (echo \"...\" >> progress.txt),",
        "ex. « 1/7 Cadre 1080x1920 », « 2/7 Transcription », « 3/7 Dérush », « 4/7 Plan », « 5/7 Rendu », « 6/7 Son », « 7/7 Vérification ».",
        "",
        "FIN : le reel monté s'appelle final.mp4 dans ce dossier, vérifié (étape 7 du skill : h264 1080x1920 yuv420p + aac,",
        "start_time 0, ~-14 LUFS, planche check.jpg regardée). Écris resume.md : 5 lignes max (ce qui a été coupé, mots forts,",
        "choix faits) + la note /10 du skill. Dernière ligne de progress.txt : « FINI » (ou « ERREUR : raison »).",
    ]
    if fiche:
        lines += ["", "FICHE DE TOURNAGE de cette vidéo (le script prévu, pour choisir les bonnes prises et les mots forts) :",
                  json.dumps({k: fiche.get(k) for k in ("subject", "hooks", "text_hook", "script", "cta")}, ensure_ascii=False)[:4000]]
    return "\n".join(lines)


def start(src: str | Path, style: str, code: str | None = None, move: bool = False) -> str:
    """Crée le dossier du montage et lance claude -p en arrière-plan. Renvoie l'id."""
    if style not in STYLES:
        raise ValueError(f"style inconnu : {style} (choix : {', '.join(STYLES)})")
    if not (SKILL / "SKILL.md").exists():
        raise RuntimeError("skill supermonteur absent : installe le kit Claude (il l'ajoute dans ~/.claude/skills/)")
    claude = _claude_bin()
    if not claude:
        raise RuntimeError("Claude Code introuvable (commande claude)")
    src = Path(src)
    mid = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{_slug(src.stem)}"
    d = DIR / mid
    d.mkdir(parents=True)
    rush = d / f"rush{src.suffix.lower()}"
    (shutil.move if move else shutil.copy2)(str(src), rush)
    job = {"style": style, "style_label": STYLES[style]["label"], "code": code, "source": src.name,
           "status": "en cours", "started": dt.datetime.now().isoformat(timespec="seconds")}
    _write(mid, job)
    (d / "progress.txt").write_text("0/7 Rush reçue, le monteur démarre\n")
    cmd = [claude, "-p", "--output-format", "text", "--no-session-persistence",
           "--model", os.environ.get("MONTAGE_MODEL", "opus"),
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
           "--add-dir", str(SKILL), "--add-dir", os.path.expanduser("~/Documents/Brain/00-Moi"),
           "--add-dir", os.path.expanduser("~/Documents/Contenu/medias"),
           "--max-turns", "200"]
    env = dict(os.environ, PATH=":".join([os.path.expanduser("~/.local/bin"), os.path.expanduser("~/.local/node/bin"),
                                          "/opt/homebrew/bin", "/usr/local/bin", os.environ.get("PATH", "")]))
    logf = open(d / "claude.log", "w")
    p = subprocess.Popen(cmd, cwd=d, stdin=subprocess.PIPE, stdout=logf, stderr=subprocess.STDOUT, text=True, env=env)
    p.stdin.write(_prompt(job, rush))
    p.stdin.close()
    job["pid"] = p.pid
    _write(mid, job)

    def wait():
        rc = p.wait()
        logf.close()
        j = _read(mid)
        ok = rc == 0 and (d / "final.mp4").exists()
        j.update(status="fini" if ok else "erreur", finished=dt.datetime.now().isoformat(timespec="seconds"), rc=rc)
        if not ok:
            with open(d / "progress.txt", "a") as f:
                f.write(f"ERREUR : le monteur s'est arrêté sans final.mp4 (code {rc}), voir claude.log\n")
        _write(mid, j)
        logger.info("montage %s : %s", mid, j["status"])

    threading.Thread(target=wait, daemon=True).start()
    logger.info("montage %s lancé (%s, pid %s)", mid, style, p.pid)
    return mid
