"""Module 3, Analyse des outliers (transcription + visuel + classification).

Pipeline par vidéo :
  1. téléchargement (seulement les outliers)
  2. Whisper avec timestamps (OpenAI API ou faster-whisper local)
  3. hook = 3 premières secondes + texte à l'écran (via vision)
  4. ffmpeg : frames à 0/1/3/5 s puis toutes les 10 s
  5. Claude vision → cadrage, plans, split-screen, texte, sous-titres, B-roll, rythme, décor, CTA
  6. classification (hook, format visuel, structure, CTA, principes de la skill)
Sortie : data/analyses/<platform>_<id>.json + table analyses.
Fallbacks : sans clé LLM → heuristiques ; vidéo mock → analyse mock (method=mock).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import db, llm, log, principles
from .config import DATA_DIR, env, settings
from .scraper import download
from .scraper.mock_backend import MOCK_HOOKS

logger = log.get("analysis")

HOOK_TYPES = ["curiosity_gap", "contrarian", "result_proof", "callout", "stakes_challenge", "story", "question", "list", "pov", "other"]
VISUAL_FORMATS = ["talking_head", "talking_head_broll", "green_screen", "split_screen", "pov_vlog", "screen_record",
                  "text_over_broll", "skit", "interview", "other"]
STRUCTURES = ["list_steps", "story", "tutorial", "before_after", "myth_reality", "rant_opinion", "day_in_life",
              "case_study", "reaction", "other"]
CTA_TYPES = ["comment_keyword", "follow", "follow_series", "save", "share", "link_bio", "dm", "none"]
SUCCESS_DRIVERS = ["technique", "celebrity", "brand_ip", "animal_cute", "trend_audio", "news_event", "giveaway", "shock", "other"]
CONVERSIONS = ["comment_keyword", "lead_magnet", "link_bio", "dm", "offer", "none"]


def _engagement_text(v) -> str:
    keys = v.keys() if hasattr(v, "keys") else []
    parts = []
    for k, label in (("eng_comment_rel", "taux de commentaires"), ("eng_share_rel", "taux de partages")):
        if k in keys and v[k]:
            parts.append(f"{label} x{v[k]:.1f} vs médiane du compte")
    return ", ".join(parts) or "non disponible"

HOOK_TO_PRINCIPLE = {"curiosity_gap": "H-V1", "contrarian": "H-V2", "result_proof": "H-V3", "callout": "H-V4",
                     "stakes_challenge": "H-V5", "question": "H-V1", "list": "F6", "story": "S3", "pov": "F5"}
FORMAT_TO_PRINCIPLE = {"talking_head_broll": "F1", "green_screen": "F2", "split_screen": "F3", "pov_vlog": "F5",
                       "screen_record": "H-VIS3"}
CTA_TO_PRINCIPLE = {"comment_keyword": "C2", "follow_series": "C3", "follow": "C4", "save": "C4", "share": "C4"}

ANALYSES_DIR = DATA_DIR / "analyses"


# ---------------------------------------------------------------- transcription
def transcribe(path: str) -> dict:
    """{'text', 'segments': [{start, end, text}], 'backend'}, vide si aucun backend."""
    mode = settings().get("analysis.transcription", "auto")
    if mode in ("auto", "openai") and env("OPENAI_API_KEY"):
        try:
            return _transcribe_openai(path)
        except Exception as e:
            logger.warning("Whisper API KO : %s", e)
    if mode in ("auto", "faster_whisper"):
        try:
            return _transcribe_local(path)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("faster-whisper KO : %s", e)
    return {"text": "", "segments": [], "backend": "none"}


def _transcribe_openai(path: str) -> dict:
    import requests

    audio = _extract_audio(path)
    with open(audio, "rb") as f:
        r = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}"},
            files={"file": f},
            data={"model": "whisper-1", "response_format": "verbose_json", "timestamp_granularities[]": "segment"},
            timeout=300,
        )
    r.raise_for_status()
    d = r.json()
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in d.get("segments", [])]
    return {"text": d.get("text", ""), "segments": segs, "backend": "openai", "language": d.get("language")}


def _transcribe_local(path: str) -> dict:
    from faster_whisper import WhisperModel  # import paresseux (optionnel)

    import numpy as np

    model = WhisperModel(settings().get("analysis.faster_whisper_model", "small"), device="auto", compute_type="int8")
    # décodage via ffmpeg (évite la dépendance PyAV de faster-whisper, souvent incompatible)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    segments, info = model.transcribe(audio, vad_filter=True)
    segs = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
    return {"text": " ".join(s["text"] for s in segs), "segments": segs, "backend": "faster_whisper", "language": info.language}


def _extract_audio(path: str) -> str:
    out = Path(path).with_suffix(".m4a")
    if not out.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-b:a", "64k", str(out)], check=True)
    return str(out)


def hook_from_transcript(tr: dict, window: float) -> str:
    return " ".join(s["text"] for s in tr.get("segments", []) if s["start"] < window).strip()


# ---------------------------------------------------------------- frames
def probe_duration(path: str) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def frame_times(duration: float) -> list[float]:
    s = settings()
    times = [t for t in s.get("analysis.frames_at_s", [0, 1, 3, 5]) if t < duration]
    step = float(s.get("analysis.frame_every_s", 10))
    t = step
    while t < duration:
        times.append(t)
        t += step
    if duration > 2:
        times.append(max(duration - 1.5, 0))  # dernière frame : CTA
    return sorted(set(round(x, 1) for x in times))


def extract_frames(path: str, key: str) -> list[tuple[float, Path]]:
    if not shutil.which("ffmpeg"):
        return []
    out_dir = DATA_DIR / "frames" / key
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for t in frame_times(probe_duration(path)):
        f = out_dir / f"t{t:06.1f}.jpg"
        if not f.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", path, "-frames:v", "1",
                            "-vf", "scale=512:-2", "-q:v", "4", str(f)], check=False)
        if f.exists():
            frames.append((t, f))
    return frames


# ---------------------------------------------------------------- classification
def classify_heuristic(text: str, caption: str) -> dict:
    t = (text or caption or "").lower()
    first = t.split("\n")[0]
    if re.search(r"\b(jour|day)\s*\d+", first):
        hook = "stakes_challenge"
    elif re.search(r"\d[\d,.\s]*\s?(k|€|\$|%|calls|appels|clients|jours|days)", first) or re.search(r"[$€]\s?\d", first):
        hook = "result_proof"
    elif re.search(r"\b(si t'es|si tu es|if you're|if you are|coachs?\b|pour les)", first):
        hook = "callout"
    elif re.search(r"\b(stop|arrête|never|jamais|nobody|personne|terrible|wrong|faux|mensonge)", first):
        hook = "contrarian"
    elif first.strip().endswith("?"):
        hook = "question"
    elif re.search(r"^(\d+)\s", first):
        hook = "list"
    elif first.startswith("pov"):
        hook = "pov"
    elif re.search(r"(here's|voici|exactly|exactement|watch me|regarde)", first):
        hook = "curiosity_gap"
    else:
        hook = "other"
    if re.search(r"comment[e]?\s+['\"«]?[A-Z]{3,}", caption or "") or re.search(r"commente", t):
        cta = "comment_keyword"
    elif re.search(r"(part ?\d|day \d|jour \d|follow for|abonne)", t):
        cta = "follow_series"
    elif re.search(r"(save|enregistre)", t):
        cta = "save"
    elif re.search(r"(link in bio|lien en bio)", t):
        cta = "link_bio"
    else:
        cta = "none"
    return {"hook_type": hook, "visual_format": "other", "script_structure": "other", "cta_type": cta}


def _mock_analysis(v) -> dict:
    first = (v["caption"] or "").split("\n")[0]
    for hook, fmt, struct, cta in MOCK_HOOKS:
        if hook == first:
            h = classify_heuristic(hook, v["caption"])["hook_type"]
            return {"hook_text": hook, "hook_type": h, "visual_format": fmt, "script_structure": struct, "cta_type": cta,
                    "visual": {"framing": "mock", "notes": "analyse simulée (données mock)"}, "cta_text": "", "transcript": "",
                    "relies_on_music": fmt in ("text_over_broll", "pov_vlog") and len(hook) % 3 == 0}
    return {"hook_text": first, **classify_heuristic(first, v["caption"])}


VISION_PROMPT = """Analyse cette vidéo courte (Reel/TikTok/Short) qui a surperformé (score outlier x{score:.1f} vs médiane du compte @{handle}).
Engagement relatif au compte : {engagement}. Sois exigeant : une vidéo n'est un bon modèle que si elle a marché GRÂCE À SA TECHNIQUE
(hook, structure, rétention, CTA), pas grâce au nom de l'auteur, à un animal, à une actu ou à un son tendance.

Caption : {caption}
Transcription (timestamps) : {transcript}
Hook verbal (3 premières secondes) : {hook}
Frames jointes (timestamps en secondes) : {times}

Renvoie un JSON avec exactement ces clés :
{{
 "hook_text": "hook verbal exact (3 premières s)",
 "text_hook": "texte à l'écran pendant le hook ('' si aucun)",
 "visual_hook": "ce qu'on voit dans la 1re seconde",
 "hook_type": one of {hook_types},
 "visual_format": one of {formats},
 "script_structure": one of {structures},
 "cta_type": one of {ctas},
 "cta_text": "CTA exact (fin de vidéo + caption)",
 "visual": {{"framing": "...", "shots": "types de plans", "split_screen": bool, "on_screen_text": "style/position",
            "subtitles": "style des sous-titres", "broll": "usage du B-roll", "cut_pace": "rythme estimé des coupes",
            "setting": "décor"}},
 "success_driver": one of {drivers}, POURQUOI elle a marché : "technique" = grâce au hook / à la structure / au montage
     (reproductible) ; sinon ce qui l'explique surtout (célébrité de l'auteur, marque/IP, animal mignon, son tendance, actu, giveaway, choc),
 "replicability": 0-10, un créateur INCONNU (0 abonné) dans la niche du créateur ferait-il des vues avec la même technique ?
     (10 = pure technique ; ≤ 4 = marche surtout grâce à la notoriété / au sujet / au hasard),
 "hook_strength": 0-10, force des 3 premières secondes (verbal + visuel + texte). Une vidéo sans vrai hook = ≤ 4,
 "retention_devices": ["boucles ouvertes, re-hooks, payoff, rythme… réellement présents"],
 "funnel_stage": "tofu" (notoriété : large, partageable) | "mofu" (confiance : expertise, preuve, coulisses) | "bofu" (conversion : offre, objection, CTA mot-clé → DM, lead magnet),
 "conversion_mechanism": one of {conversions},
 "reference_verdict": "oui" | "non", à proposer au créateur comme modèle ? (oui seulement si replicability ≥ 7, hook_strength ≥ 6, success_driver = technique),
 "relies_on_music": bool (le format repose-t-il sur une musique / un son tendance ?),
 "music_free_adaptation": "comment reproduire l'effet SANS musique (voix, rythme des coupes, texte, sound design neutre)",
 "why_it_works": "2 phrases max",
 "adaptable_idea": "comment le créateur pourrait adapter ce format (1-2 phrases)",
 "principles": ["IDs de la skill appliqués"]
}}"""


def select_frames(frames: list, n: int) -> list:
    """Garde toutes les frames du hook (≤ 5 s), la dernière (CTA) et un échantillon régulier du milieu."""
    if len(frames) <= n:
        return frames
    head = [f for f in frames if f[0] <= 5]
    rest = [f for f in frames if f[0] > 5]
    k = max(n - len(head) - 1, 0)
    mid = [rest[int(i * (len(rest) - 1) / max(k, 1))] for i in range(k)] if k and len(rest) > 1 else []
    return sorted(set(head + mid + [frames[-1]]), key=lambda f: f[0])


def classify_llm(v, tr: dict, hook: str, frames: list[tuple[float, Path]]) -> dict:
    transcript = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in tr.get("segments", []))[:6000]
    prompt = VISION_PROMPT.format(
        score=v["outlier_score"] or 0, handle=v["handle"], caption=(v["caption"] or "")[:1500],
        transcript=transcript or "(indisponible)", hook=hook or "(indisponible)",
        times=", ".join(f"{t}s" for t, _ in frames) or "(aucune)",
        hook_types=HOOK_TYPES, formats=VISUAL_FORMATS, structures=STRUCTURES, ctas=CTA_TYPES,
        drivers=SUCCESS_DRIVERS, conversions=CONVERSIONS, engagement=_engagement_text(v),
    )
    content = [{"type": "text", "text": prompt}] + [llm.image_block(f) for _, f in select_frames(frames, 12)]
    return llm.complete_json(principles.system_prompt("Tu es analyste de contenu court (Reels/TikTok)."), content,
                             max_tokens=2500, vision=bool(frames))


def _principles_for(a: dict) -> list[str]:
    ids = [HOOK_TO_PRINCIPLE.get(a.get("hook_type")), FORMAT_TO_PRINCIPLE.get(a.get("visual_format")),
           CTA_TO_PRINCIPLE.get(a.get("cta_type"))]
    return [i for i in ids if i]


def analyze_video(conn, v) -> dict:
    key = f"{v['platform']}_{v['external_id']}"
    window = float(settings().get("analysis.hook_window_s", 3))
    if v["is_mock"]:
        a = _mock_analysis(v)
        method = "mock"
    else:
        path = v["media_path"] or download(v)
        if path and not v["media_path"]:
            conn.execute("UPDATE videos SET media_path=? WHERE id=?", (path, v["id"]))
            conn.commit()  # ne pas garder le verrou d'écriture pendant la transcription / l'appel Claude
        tr = transcribe(path) if path else {"text": "", "segments": [], "backend": "none"}
        hook = hook_from_transcript(tr, window)
        frames = extract_frames(path, key) if path else []
        a, method = None, "heuristic"
        if llm.available():
            try:
                a = classify_llm(v, tr, hook, frames)
                method = "llm"
            except Exception as e:
                logger.warning("classification LLM KO pour %s : %s", key, e)
        if a is None:
            a = {"hook_text": hook or (v["caption"] or "").split("\n")[0][:200],
                 **classify_heuristic(hook, v["caption"])}
        a["transcript"] = tr.get("text", "")
        a["transcript_segments"] = tr.get("segments", [])
        a["transcription_backend"] = tr.get("backend")
        a["frames"] = [str(f) for _, f in frames]
    a.setdefault("principles", _principles_for(a))
    a["video"] = {"url": v["url"], "handle": v["handle"], "platform": v["platform"], "views": v["views"],
                  "outlier_score": v["outlier_score"], "posted_at": v["posted_at"], "caption": v["caption"],
                  "owner": v["owner"], "category": v["category"], "niche": v["niche_label"], "is_mock": bool(v["is_mock"])}
    a["method"] = method

    ANALYSES_DIR.mkdir(parents=True, exist_ok=True)
    (ANALYSES_DIR / f"{key}.json").write_text(json.dumps(a, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    conn.execute(
        """INSERT INTO analyses(video_id, hook_text, hook_type, visual_format, script_structure, cta_type, principles, data, method)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(video_id) DO UPDATE SET hook_text=excluded.hook_text, hook_type=excluded.hook_type,
             visual_format=excluded.visual_format, script_structure=excluded.script_structure, cta_type=excluded.cta_type,
             principles=excluded.principles, data=excluded.data, method=excluded.method, created_at=datetime('now')""",
        (v["id"], a.get("hook_text"), a.get("hook_type"), a.get("visual_format"), a.get("script_structure"),
         a.get("cta_type"), db.dumps(a.get("principles", [])), db.dumps(a), method),
    )
    return a


def run(limit: int | None = None, reanalyze: bool = False, upgrade: bool = False) -> dict:
    limit = limit or int(settings().get("analysis.max_videos_per_run", 30))
    stats = {"analyzed": 0, "llm": 0, "heuristic": 0, "mock": 0, "errors": 0}
    with db.session() as conn:
        q = """SELECT v.*, a.handle, a.owner, a.category, a.niche_label FROM videos v
               JOIN accounts a ON a.id=v.account_id
               WHERE v.is_outlier=1 {cond}
               ORDER BY v.is_mock ASC, CASE v.platform WHEN 'instagram' THEN 0 WHEN 'tiktok' THEN 1 ELSE 2 END,
                        v.outlier_score DESC LIMIT ?"""
        cond = "" if reanalyze else "AND v.id NOT IN (SELECT video_id FROM analyses)"
        if upgrade:  # nouvelles analyses + anciennes sans les critères de qualité (réplicabilité, funnel…)
            cond = ("AND (v.id NOT IN (SELECT video_id FROM analyses) OR v.id IN (SELECT video_id FROM analyses "
                    "WHERE json_extract(data,'$.replicability') IS NULL))")
        rows = conn.execute(q.format(cond=cond), (limit,)).fetchall()
        for v in rows:
            try:
                a = analyze_video(conn, v)
                stats["analyzed"] += 1
                stats[a["method"]] += 1
                conn.commit()
            except Exception as e:
                stats["errors"] += 1
                logger.exception("analyse KO pour %s : %s", v["url"], e)
        db.log_run(conn, "analyze", "analyze", "ok", db.dumps(stats))
    logger.info("analyse : %s", stats)
    return stats
