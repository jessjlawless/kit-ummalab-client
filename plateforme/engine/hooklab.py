"""Hook Lab, décortique le hook (≈ 3 premières secondes) des meilleures vidéos de créateurs choisis, sur 4 canaux :
  verbal   : ce qui est dit (Whisper, timestamps au mot)
  textuel  : le texte à l'écran (Claude vision sur les frames 0 → 4 s)
  visuel   : ce qu'on voit (frames + coupes mesurées par ffmpeg)
  auditif  : ce qu'on entend, MESURÉ (début de la voix, débit, volume, silences, pics sonores hors parole,
             son tonal pendant les vraies pauses = musique probable, spectre plat = ambiance) puis interprété ; Claude n'entend pas le son, il lit les mesures.
Sélection : par créateur, les vidéos au meilleur score outlier (vues / médiane de SON compte), jamais les vues brutes,
+ les vidéos de départ (seeds) importées de ton tableau avec tes annotations.
Config : config/hooklab.yaml (créateurs) + config/hooklab_seeds.yaml (généré : seeds + créateurs ajoutés au dashboard).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path

import yaml

from . import db, llm, log
from .config import CONFIG_DIR, DATA_DIR, OUTPUT_DIR, load_yaml
from .ethics import identity_block
from .principles import skill_text

logger = log.get("hooklab")

CFG_PATH = CONFIG_DIR / "hooklab.yaml"
EXTRA_PATH = CONFIG_DIR / "hooklab_seeds.yaml"
STATE_PATH = DATA_DIR / "hooklab_state.json"
FRAME_TIMES = [0, 0.5, 1, 1.5, 2, 2.5, 3, 4]
CHANNELS = ("verbal", "textuel", "visuel", "auditif")
_WHISPER = None


# ---------------------------------------------------------------- config
def cfg() -> dict:
    return load_yaml(CFG_PATH) if CFG_PATH.exists() else {}


def extra() -> dict:
    d = load_yaml(EXTRA_PATH) if EXTRA_PATH.exists() else None
    return d or {"creators": [], "seeds": []}


def _save_extra(d: dict) -> None:
    head = "# Généré par le Hook Lab (dashboard + import du tableau). Modifiable à la main.\n"
    EXTRA_PATH.write_text(head + yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")


def creators() -> list[dict]:
    """Créateurs de la config + ceux ajoutés depuis le dashboard (fusionnés par nom)."""
    out: dict[str, dict] = {}
    for c in (cfg().get("creators") or []) + (extra().get("creators") or []):
        cur = out.setdefault(c["name"], {"name": c["name"], "why": c.get("why", ""), "accounts": []})
        cur["why"] = cur["why"] or c.get("why", "")
        for a in c.get("accounts") or []:
            key = (a["platform"], a["handle"].lstrip("@").lower())
            if key not in {(x["platform"], x["handle"].lower()) for x in cur["accounts"]}:
                cur["accounts"].append({**a, "handle": a["handle"].lstrip("@")})
    return list(out.values())


def seeds() -> list[dict]:
    return (cfg().get("seeds") or []) + (extra().get("seeds") or [])


def add_creator(name: str, platform: str, handle: str, why: str = "") -> dict:
    if platform not in ("instagram", "tiktok", "youtube") or not handle.strip() or not name.strip():
        raise ValueError("nom, plateforme (instagram|tiktok|youtube) et handle requis")
    d = extra()
    d.setdefault("creators", [])
    for c in d["creators"]:
        if c["name"].lower() == name.strip().lower():
            c.setdefault("accounts", []).append({"platform": platform, "handle": handle.strip().lstrip("@"), "status": "à vérifier"})
            break
    else:
        d["creators"].append({"name": name.strip(), "why": why, "accounts": [
            {"platform": platform, "handle": handle.strip().lstrip("@"), "status": "à vérifier"}]})
    _save_extra(d)
    return {"ok": True}


def _state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(s: dict) -> None:
    STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- import d'un tableau de vidéos annotées
def import_xlsx(path: str) -> dict:
    """Colonnes : A créateur (reporté vers le bas) · B lien · C hook oral · D hook texte · E hook visuel · F hook auditif."""
    import openpyxl

    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    found: dict[str, dict] = {}
    creator = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        row = list(row) + [None] * 6
        if row[0] and str(row[0]).strip():
            creator = str(row[0]).strip().title()
        url = str(row[1] or "").strip()
        if not url.startswith("http"):
            continue
        url = url.split("?")[0]
        note = {k: str(v).strip() for k, v in zip(("oral", "texte", "visuel", "auditif"), row[2:6]) if v and str(v).strip()}
        if url in found:  # même lien deux fois dans le tableau : on fusionne les annotations
            for k, v in note.items():
                prev = found[url]["note"].get(k)
                found[url]["note"][k] = f"{prev} / {v}" if prev and v not in prev else v
            continue
        found[url] = {"creator": creator or "Inconnu", "url": url, "note": note}
    d = extra()
    known = {s["url"] for s in d.get("seeds") or []}
    new = [s for s in found.values() if s["url"] not in known]
    d["seeds"] = (d.get("seeds") or []) + new
    _save_extra(d)
    logger.info("tableau importé : %d liens (%d nouveaux)", len(found), len(new))
    return {"links": len(found), "new": len(new)}


# ---------------------------------------------------------------- collecte (meilleures vidéos par créateur)
def _account_ids(conn, platform: str, handle: str) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM accounts WHERE platform=? AND lower(handle)=lower(?)", (platform, handle))]


def collect(creator: str | None = None, force: bool = False) -> dict:
    from . import outliers
    from .scraper import BACKENDS, _backend_chain, _upsert_account, _upsert_videos

    c = cfg()
    lookback = dt.datetime.now() - dt.timedelta(days=int(c.get("lookback_days", 365)))
    limit = int(c.get("videos_per_account", 60))
    state = _state()
    stats = {"accounts": 0, "skipped": 0, "videos": 0, "missing": 0}
    with db.session() as conn:
        for cr in creators():
            if creator and cr["name"].lower() != creator.lower():
                continue
            for a in cr["accounts"]:
                key = f"{a['platform']}:{a['handle'].lower()}"
                st = state.get(key, {})
                if not force and st.get("scraped_at") and \
                        (dt.datetime.now() - dt.datetime.fromisoformat(st["scraped_at"])).days < 7 and st.get("videos"):
                    stats["skipped"] += 1
                    continue
                ids = _account_ids(conn, a["platform"], a["handle"])
                acc_id = ids[0] if ids else _upsert_account(conn, "hooklab", "creator", a["platform"], a["handle"], cr["name"])
                items, used = None, None
                chain = [b for b in _backend_chain(a["platform"], None) if b != "mock"]
                if a["platform"] == "tiktok" and "ytdlp" in chain:  # yt-dlp lit les profils TikTok sans compte, le navigateur en dernier recours
                    chain = ["ytdlp"] + [b for b in chain if b != "ytdlp"]
                for name in chain:
                    try:
                        logger.info("Hook Lab : récupère @%s (%s) via %s", a["handle"], a["platform"], name)
                        items = BACKENDS[name](a["platform"], a["handle"], since=lookback, limit=limit)
                        used = name
                        break
                    except Exception as e:
                        logger.warning("%s KO pour @%s : %s", name, a["handle"], str(e)[:160])
                raw = len(items or [])
                items = [i for i in (items or []) if not i.get("posted_at") or i["posted_at"] >= lookback.isoformat()]
                n = _upsert_videos(conn, acc_id, a["platform"], items, is_mock=False) if items else 0
                conn.execute("UPDATE accounts SET last_scraped_at=?, last_backend=? WHERE id=?",
                             (dt.datetime.now().isoformat(timespec="seconds"), used, acc_id))
                conn.commit()
                state[key] = {"status": "ok" if n else ("inactif (rien sur 12 mois)" if raw else "introuvable"), "videos": n, "backend": used,
                              "scraped_at": dt.datetime.now().isoformat(timespec="seconds")}
                _save_state(state)
                stats["accounts"] += 1
                stats["videos"] += n
                stats["missing"] += int(not n)
    outliers.run()
    return stats


# ---------------------------------------------------------------- seeds (liens précis)
def _parse_url(url: str) -> tuple[str, str | None, str] | None:
    """(platform, handle|None, external_id)."""
    if m := re.search(r"tiktok\.com/@([^/]+)/video/(\d+)", url):
        return "tiktok", m.group(1), m.group(2)
    if m := re.search(r"instagram\.com/(?:[^/]+/)?(?:reel|reels|p)/([A-Za-z0-9_-]+)", url):
        return "instagram", None, m.group(1)
    if m := re.search(r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})", url) or re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", url):
        return "youtube", None, m.group(1)
    return None


def _ytdlp_meta(url: str) -> dict:
    from .scraper.common import iso, to_int
    from .scraper.ytdlp_backend import YTDLP

    p = subprocess.run([YTDLP, "-J", "--no-warnings", "--socket-timeout", "30", "--no-playlist", url],
                       capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        return {}
    e = json.loads(p.stdout)
    return {"author": e.get("uploader_id") or e.get("channel_id") or e.get("uploader"), "caption": e.get("description") or e.get("title"),
            "posted_at": iso(e.get("timestamp")), "duration_s": e.get("duration"), "views": to_int(e.get("view_count")),
            "likes": to_int(e.get("like_count")), "comments": to_int(e.get("comment_count")),
            "shares": to_int(e.get("repost_count")), "thumb_url": e.get("thumbnail")}


def ensure_seed(conn, seed: dict) -> int | None:
    """Crée (si besoin) la ligne vidéo d'un lien du tableau ; télécharge les Reels via le navigateur du compte scout."""
    from .scraper import _upsert_account, _upsert_videos

    parsed = _parse_url(seed["url"])
    if not parsed:
        logger.warning("lien non reconnu : %s", seed["url"])
        return None
    platform, handle, ext = parsed
    row = conn.execute("SELECT id FROM videos WHERE platform=? AND external_id=?", (platform, ext)).fetchone()
    if row:
        return row["id"]
    media, meta = None, {}
    if platform == "instagram":
        from .browser.download import META, download

        target = DATA_DIR / "media" / "instagram" / f"{ext}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            media = str(target) if target.exists() and target.stat().st_size > 10_000 else \
                download("instagram", f"https://www.instagram.com/reel/{ext}/", ext, target)
        except Exception as e:
            logger.warning("Reel %s non téléchargé : %s", ext, e)
        meta = META.get(ext, {})
    else:
        meta = _ytdlp_meta(seed["url"])
    handle = (handle or meta.get("author") or "_seeds").lstrip("@")
    ids = _account_ids(conn, platform, handle)
    acc_id = ids[0] if ids else _upsert_account(conn, "hooklab", "creator", platform, handle, seed.get("creator"))
    item = {"external_id": ext, "url": seed["url"], **{k: meta.get(k) for k in (
        "video_url", "thumb_url", "caption", "posted_at", "duration_s", "views", "likes", "comments", "shares")}}
    _upsert_videos(conn, acc_id, platform, [item], is_mock=False)
    vid = conn.execute("SELECT id FROM videos WHERE account_id=? AND external_id=?", (acc_id, ext)).fetchone()["id"]
    if media:
        conn.execute("UPDATE videos SET media_path=? WHERE id=?", (media, vid))
    conn.commit()
    return vid


# ---------------------------------------------------------------- sélection
def _creator_of(conn) -> dict[tuple[str, str], str]:
    return {(a["platform"], a["handle"].lower()): cr["name"] for cr in creators() for a in cr["accounts"]}


def pick(conn, creator: str | None = None, reanalyze: bool = False) -> list[tuple[int, str, dict | None]]:
    """[(video_id, créateur, annotation|None)] : seeds d'abord, puis les meilleurs outliers de chaque créateur."""
    c = cfg()
    per, min_score, max_dur = int(c.get("per_creator", 10)), float(c.get("min_score", 2.0)), float(c.get("max_duration_s", 120))
    done = set() if reanalyze else {r["video_id"] for r in conn.execute("SELECT video_id FROM hook_breakdowns")}
    out: list[tuple[int, str, dict | None]] = []
    for s in seeds():
        if creator and (s.get("creator") or "").lower() != creator.lower():
            continue
        vid = ensure_seed(conn, s)
        if vid and vid not in done:
            out.append((vid, s.get("creator") or "Inconnu", s.get("note") or None))
            done.add(vid)
    for cr in creators():
        if creator and cr["name"].lower() != creator.lower():
            continue
        ids = [i for a in cr["accounts"] for i in _account_ids(conn, a["platform"], a["handle"])]
        if not ids:
            continue
        q = f"""SELECT id FROM videos WHERE account_id IN ({','.join('?' * len(ids))}) AND is_mock=0
                AND outlier_score >= ? AND (duration_s IS NULL OR duration_s <= ?)
                ORDER BY CASE platform WHEN 'instagram' THEN 0 WHEN 'tiktok' THEN 0 ELSE 1 END, outlier_score DESC"""
        n = (0 if reanalyze else conn.execute("SELECT COUNT(*) FROM hook_breakdowns WHERE creator=?", (cr["name"],)).fetchone()[0]) \
            + sum(1 for _, name, _ in out if name == cr["name"])
        for r in conn.execute(q, (*ids, min_score, max_dur)):
            if n >= per:
                break
            if r["id"] in done:
                continue
            out.append((r["id"], cr["name"], None))
            done.add(r["id"])
            n += 1
    return out


# ---------------------------------------------------------------- mesures (son, coupes, mots)
def _pcm(path: str, seconds: float | None = None):
    import numpy as np

    cmd = ["ffmpeg", "-loglevel", "error", "-i", path] + (["-t", str(seconds)] if seconds else []) + \
          ["-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def transcribe_words(path: str) -> dict:
    """Whisper local avec timestamps au mot : {'words': [{w, start, end}], 'text', 'language'}."""
    global _WHISPER
    try:
        from faster_whisper import WhisperModel

        from .config import settings
    except ImportError:
        return {"words": [], "text": "", "language": None}
    if _WHISPER is None:
        _WHISPER = WhisperModel(settings().get("analysis.faster_whisper_model", "small"), device="auto", compute_type="int8")
    segs, info = _WHISPER.transcribe(_pcm(path), vad_filter=True, word_timestamps=True)
    words, texts = [], []
    for s in segs:
        texts.append(s.text.strip())
        for w in s.words or []:
            words.append({"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)})
    return {"words": words, "text": " ".join(texts), "language": info.language}


def scene_cuts(path: str, until: float = 5.0) -> list[float]:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-t", str(until), "-i", path, "-vf", "select='gt(scene,0.3)',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True)
    return [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def loudness(path: str, until: float = 6.0) -> float | None:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-t", str(until), "-i", path, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    return float(m[-1]) if m else None


def audio_metrics(path: str, words: list[dict], hook_s: float = 3.0) -> dict:
    """Mesures objectives du canal auditif (Claude ne les invente pas : il les lit)."""
    import numpy as np

    try:
        x = _pcm(path, 90)
    except Exception:
        return {}
    if not len(x):
        return {"speech_start_s": None, "background_audio": "aucun son"}
    hop = 800  # 50 ms à 16 kHz
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-10)
    db_ = 20 * np.log10(rms + 1e-10)
    t = np.arange(n) * 0.05
    speech = np.zeros(n, bool)
    for w in words:
        speech[(t >= w["start"] - 0.05) & (t <= w["end"] + 0.05)] = True
    voiced = db_[speech]
    sp_med = float(np.median(voiced)) if len(voiced) else None
    bg_med, flat, gap_s = _gap_profile(x, words)
    if bg_med is None:
        background = "indéterminé (parole continue)"  # aucune vraie pause : impossible de mesurer le fond sous la voix
    elif bg_med < -50:
        background = "aucun"
    elif flat is not None and flat < 0.1:
        background = "tonal"  # son harmonique entre les phrases : musique probable
    else:
        background = "bruit/ambiance"  # souffle, pièce, ambiance réelle (spectre plat)
    # silences du hook (≥ 0,25 s sous -40 dBFS)
    silences, start, end_i = [], None, int(min(n, (hook_s + 0.5) / 0.05))
    for i in range(end_i + 1):
        quiet = i < end_i and db_[i] < -40
        if quiet and start is None:
            start = t[i]
        elif not quiet and start is not None:
            stop = t[min(i, n - 1)]
            if stop - start >= 0.25:
                silences.append([round(float(start), 2), round(float(stop), 2)])
            start = None
    # pics sonores hors parole dans les 6 premières secondes (bruitage probable : whoosh, impact, clic…)
    starts = [w["start"] for w in words]
    peaks = []
    for i in range(3, int(min(n, 6 / 0.05))):
        if db_[i] - float(np.mean(db_[i - 3:i])) >= 10 and db_[i] > -30 and not any(abs(t[i] - s) < 0.15 for s in starts):
            if not peaks or t[i] - peaks[-1] > 0.3:
                peaks.append(round(float(t[i]), 2))
    hook_words = [w for w in words if w["start"] < hook_s]
    spoken = (hook_words[-1]["end"] - hook_words[0]["start"]) if len(hook_words) > 1 else 0
    return {
        "speech_start_s": words[0]["start"] if words else None,
        "words_in_hook": len(hook_words),
        "words_per_s": round(len(hook_words) / spoken, 1) if spoken > 0.5 else None,
        "voice_level_db": round(sp_med, 1) if sp_med is not None else None,
        "voice_dynamics_db": round(float(np.std(voiced)), 1) if len(voiced) > 5 else None,
        "background_level_db": round(bg_med, 1) if bg_med is not None else None,
        "background_flatness": flat, "pauses_measured_s": gap_s,
        "background_audio": background,
        "silences": silences,
        "sfx_peaks_s": peaks,
        "loudness_lufs": loudness(path),
    }


def _gap_profile(x, words: list[dict], sr: int = 16000) -> tuple[float | None, float | None, float]:
    """Niveau (dBFS) et planéité spectrale du son PENDANT LES VRAIES PAUSES (≥ 0,25 s, à 0,15 s des mots).
    Planéité basse (< 0,1) = son tonal (musique) ; haute = bruit / ambiance."""
    import numpy as np

    if not words:
        spans = [(0.0, len(x) / sr)]
    else:
        spans = [(0.0, words[0]["start"])] + [(a["end"], b["start"]) for a, b in zip(words, words[1:])] + [(words[-1]["end"], len(x) / sr)]
    segs = [(s + 0.15, e - 0.15) for s, e in spans if e - s - 0.3 >= 0.25]
    lv, fl, tot = [], [], 0.0
    win = np.hanning(2048)
    for s, e in segs:
        y = x[int(s * sr):int(e * sr)]
        for i in range(0, len(y) - 2048, 1024):
            f = y[i:i + 2048] * win
            P = (np.abs(np.fft.rfft(f)) ** 2 + 1e-12)[5:400]  # ≈ 40 Hz, 3 kHz
            fl.append(float(np.exp(np.mean(np.log(P))) / np.mean(P)))
            lv.append(float(10 * np.log10(np.mean(f ** 2) + 1e-12)))
        tot += e - s
    if not lv:
        return None, None, round(tot, 1)
    return float(np.median(lv)), round(float(np.median(fl)), 3), round(tot, 1)


def hook_frames(path: str, key: str, duration: float) -> list[tuple[float, Path]]:
    out_dir = DATA_DIR / "frames" / f"hook_{key}"
    out_dir.mkdir(parents=True, exist_ok=True)
    times = [x for x in FRAME_TIMES if x < max(duration - 0.2, 0.5)]
    if duration > 8:
        times += [round(duration / 2, 1), round(max(duration - 1.5, 0), 1)]
    frames = []
    for x in times:
        f = out_dir / f"t{x:06.2f}.jpg"
        if not f.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(x), "-i", path, "-frames:v", "1",
                            "-vf", "scale=540:-2", "-q:v", "4", str(f)], check=False)
        if f.exists():
            frames.append((x, f))
    return frames


# ---------------------------------------------------------------- décorticage (Claude vision + mesures)
def _skill_sections() -> str:
    s = re.sub(r"\s*\[src:[^\]]*\]", "", skill_text())
    hooks = re.search(r"## 1\..*?(?=\n## 2\.)", s, re.S)
    adapt = re.search(r"## 8\..*", s, re.S)
    return "\n\n".join(m.group(0) for m in (hooks, adapt) if m)


SYSTEM = """Tu es l'analyste de hooks le plus exigeant du short form (Reels/TikTok/Shorts). Tu décortiques UNIQUEMENT le hook
(≈ 3 premières secondes) d'une vidéo qui a surperformé, sur 4 canaux : VERBAL (ce qui est dit), TEXTUEL (texte à l'écran),
VISUEL (ce qu'on voit), AUDITIF (ce qu'on entend). Tu ne devines rien : le verbal vient de la transcription horodatée, le
visuel et le texte des images jointes, l'auditif des MESURES fournies (tu n'entends pas le son : tu interprètes les mesures
et la transcription, et tu le dis quand c'est une estimation). Si un canal est vide (pas de texte, pas de voix), dis-le.

{identity}

Langue : analyse en français. Le `template` et les `adaptations` sont dans la langue des vidéos du créateur ({language}),
oraux, sans exagération ni promesse de gain{music}.

=== SKILL content-principles (sections hooks + adaptation au créateur) ===
{skill}
=== FIN SKILL ==="""

PROMPT = """Créateur : {creator} (@{handle}, {platform}). Score outlier : {score} (vues / médiane de son compte). Vues : {views}.
Durée : {duration}s. Caption : {caption}

TRANSCRIPTION HORODATÉE AU MOT (3,5 premières secondes) :
{hook_words}
Suite de la transcription (contexte, pour comprendre le payoff promis) : {rest}

MESURES AUDIO (ffmpeg + Whisper) : {audio}
COUPES DE PLAN détectées (s, 5 premières secondes) : {cuts}
IMAGES JOINTES : frames aux instants {times} s (dans l'ordre).

Renvoie un JSON avec exactement ces clés :
{{
 "archetype": "nom court + ID de l'archétype principal de la skill, 4 mots max (ex. 'Investigator (H-A5)')",
 "funnel_stage": "tofu|mofu|bofu",
 "strong_channel": "verbal|textuel|visuel|auditif, le canal qui porte le plus le hook",
 "verbal": {{"text": "mots EXACTS dits pendant les 3 premières secondes (copie la transcription, '' si personne ne parle)",
            "technique": "mécanisme précis (boucle ouverte, chiffre, interpellation, contradiction…) en 1 phrase",
            "formula": "structure abstraite de la phrase (ex. 'résultat surprenant + délai + 'voilà comment'')"}},
 "textuel": {{"text": "texte EXACT à l'écran pendant le hook ('' si aucun ; sous-titres seuls = 'sous-titres uniquement')",
             "appears_s": 0.0, "position": "où (haut, centre, bas…)", "style": "police, taille, couleur, fond, animation",
             "relation": "identique|complément|contraste|aucun (par rapport au verbal)"}},
 "visuel": {{"first_frame": "ce qu'on voit à 0 s, précisément", "motion": "mouvement/action dans les 2 premières secondes",
            "framing": "cadrage, décor, lumière", "proof": "preuve montrée à l'écran ('' si aucune)",
            "pattern_interrupt": "ce qui casse le scroll visuellement ('' si rien)"}},
 "auditif": {{"first_sound": "voix|bruitage|musique|silence|ambiance", "voice": "énergie, débit, ton (d'après les mesures)",
             "sound_design": "bruitages/silences/pics et leur rôle (d'après les mesures)",
             "music": "aucune|probable|oui", "halal_adaptation": "comment obtenir le même effet SANS musique instrumentale (voix, silence, bruitage{nasheed}), '' si la musique n'y est pour rien"}},
 "synergy": "comment les 4 canaux se renforcent ou se contredisent (1-2 phrases)",
 "why_it_works": "pourquoi CE hook arrête le scroll, en termes de technique (2 phrases max)",
 "template": "hook réutilisable en anglais avec des [trous] à remplir",
 "adaptations": {{"personal": "hook prêt à tourner pour le compte du créateur, dans la langue de ses vidéos, adapté à son identité et à sa niche (+ texte écran + visuel entre parenthèses)"}},
 "hook_strength": 0-10, "replicability": 0-10 (un créateur inconnu ferait-il des vues avec la même technique ?),
 "success_driver": "technique|celebrity|brand_ip|animal_cute|trend_audio|news_event|giveaway|shock|other",
 "principles": ["IDs exacts de la skill illustrés par ce hook (H-V…, H-VIS…, H-TXT…, H-A…)"]
}}"""


def _system() -> str:
    from . import ethics
    from .config import settings

    return SYSTEM.format(identity=identity_block(), skill=_skill_sections(),
                         language="anglais" if settings().get("language") == "en" else "français",
                         music=", sans musique instrumentale" if ethics.islamic() else "")


def breakdown(conn, video_id: int, creator: str, note: dict | None = None) -> dict | None:
    from .analysis import probe_duration
    from .scraper import download

    v = conn.execute("""SELECT v.*, a.handle, a.owner, a.category, a.niche_label FROM videos v
                        JOIN accounts a ON a.id=v.account_id WHERE v.id=?""", (video_id,)).fetchone()
    if not v:
        return None
    path = v["media_path"] if v["media_path"] and Path(v["media_path"]).exists() else download(v)
    if not path:
        logger.warning("vidéo non téléchargeable : %s", v["url"])
        return None
    if path != v["media_path"]:
        conn.execute("UPDATE videos SET media_path=? WHERE id=?", (path, video_id))
        conn.commit()  # pas de verrou d'écriture pendant Whisper / Claude
    key = f"{v['platform']}_{v['external_id']}"
    duration = probe_duration(path) or float(v["duration_s"] or 0)
    tr = transcribe_words(path)
    words = tr["words"]
    audio = audio_metrics(path, words)
    cuts = scene_cuts(path)
    frames = hook_frames(path, key, duration)
    hook_words = " ".join(f"[{w['start']:.2f}] {w['w']}" for w in words if w["start"] < 3.5) or "(personne ne parle)"
    rest = " ".join(w["w"] for w in words if w["start"] >= 3.5)[:1500] or "(rien)"
    from . import ethics

    prompt = PROMPT.format(nasheed=", nasheed a cappella" if ethics.islamic() else "",
        creator=creator, handle=v["handle"], platform=v["platform"], score=f"x{v['outlier_score']:.1f}" if v["outlier_score"] else "non calculé",
        views=v["views"] or "?", duration=round(duration, 1), caption=(v["caption"] or "")[:600].replace("\n", " "),
        hook_words=hook_words, rest=rest, audio=json.dumps(audio, ensure_ascii=False), cuts=cuts or "aucune",
        times=", ".join(str(x) for x, _ in frames),
    )
    a, method = None, "measures"
    if llm.available():
        try:
            a = llm.complete_json(_system(), [{"type": "text", "text": prompt}] + [llm.image_block(f) for _, f in frames],
                                  max_tokens=3000, vision=bool(frames))
            method = "llm"
        except Exception as e:
            logger.warning("décorticage LLM KO pour %s : %s", key, e)
    if not isinstance(a, dict):
        a = {"verbal": {"text": " ".join(w["w"] for w in words if w["start"] < 3)}, "textuel": {}, "visuel": {}, "auditif": {}}
    # les mesures priment sur l'interprétation
    a.setdefault("verbal", {}).update({"words_per_s": audio.get("words_per_s"), "first_word_s": audio.get("speech_start_s")})
    a.setdefault("visuel", {})["cuts_3s"] = sum(1 for c in cuts if c <= 3)
    a["visuel"]["cuts_s"] = cuts
    a.setdefault("auditif", {})["metrics"] = audio
    a["auditif"]["music"] = music_verdict(audio, a["auditif"].get("music"))
    a.setdefault("textuel", {})
    a["transcript"] = tr["text"]
    a["words"] = words[:400]
    a["language"] = tr["language"]
    a["frames"] = [str(f) for _, f in frames]
    a["duration_s"] = round(duration, 1)
    strong = a.get("strong_channel") if a.get("strong_channel") in CHANNELS else None
    conn.execute(
        """INSERT INTO hook_breakdowns(video_id, creator, strong_channel, hook_strength, replicability, success_driver, data, creator_note, method)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(video_id) DO UPDATE SET creator=excluded.creator, strong_channel=excluded.strong_channel,
             hook_strength=excluded.hook_strength, replicability=excluded.replicability, success_driver=excluded.success_driver,
             data=excluded.data, creator_note=COALESCE(excluded.creator_note, hook_breakdowns.creator_note), method=excluded.method,
             created_at=datetime('now','localtime')""",
        (video_id, creator, strong, _num(a.get("hook_strength")), _num(a.get("replicability")), a.get("success_driver"),
         db.dumps(a), db.dumps(note) if note else None, method),
    )
    conn.commit()
    return a


def music_verdict(audio: dict, llm_value: str | None) -> str:
    """La mesure tranche quand elle peut ; sinon on garde l'avis du LLM (transcription/caption), marqué incertain."""
    bg = audio.get("background_audio") or ""
    if bg == "tonal":
        return "probable" if llm_value != "oui" else "oui"
    if bg in ("aucun", "bruit/ambiance"):
        return "aucune"
    return llm_value if llm_value in ("oui", "probable") else "indéterminée"


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def run(creator: str | None = None, limit: int | None = None, collect_first: bool = True, reanalyze: bool = False) -> dict:
    stats = {"collected": None, "picked": 0, "done": 0, "failed": 0}
    if collect_first:
        stats["collected"] = collect(creator)
    with db.session() as conn:
        todo = pick(conn, creator, reanalyze)
        if limit:
            todo = todo[:limit]
        stats["picked"] = len(todo)
        logger.info("Hook Lab : %d hooks à décortiquer", len(todo))
        for i, (vid, name, note) in enumerate(todo, 1):
            try:
                a = breakdown(conn, vid, name, note)
                stats["done" if a else "failed"] += 1
                if a:
                    logger.info("[%d/%d] %s, %s", i, len(todo), name, (a.get("verbal") or {}).get("text", "")[:80])
            except Exception as e:
                stats["failed"] += 1
                logger.warning("[%d/%d] %s : échec %s", i, len(todo), name, str(e)[:200])
        db.log_run(conn, "hooklab", "hooklab", "ok", db.dumps(stats))
    return stats


# ---------------------------------------------------------------- lecture (dashboard, planner, export)
def items(conn=None) -> list[dict]:
    own = conn is None
    conn = conn or db.connect()
    try:
        rows = conn.execute("""SELECT h.*, v.platform, v.url, v.views, v.outlier_score, v.posted_at, v.duration_s, v.caption,
                                      a.handle FROM hook_breakdowns h JOIN videos v ON v.id=h.video_id
                               JOIN accounts a ON a.id=v.account_id ORDER BY COALESCE(h.hook_strength,0) DESC, v.outlier_score DESC""").fetchall()
    finally:
        if own:
            conn.close()
    out = []
    for r in rows:
        d = json.loads(r["data"])
        out.append({
            "id": r["id"], "video_id": r["video_id"], "creator": r["creator"], "platform": r["platform"], "handle": r["handle"],
            "url": r["url"], "views": r["views"], "outlier_score": r["outlier_score"], "posted_at": (r["posted_at"] or "")[:10],
            "duration_s": d.get("duration_s") or r["duration_s"], "hook_strength": r["hook_strength"], "replicability": r["replicability"],
            "success_driver": r["success_driver"], "strong_channel": r["strong_channel"], "archetype": d.get("archetype"),
            "funnel_stage": d.get("funnel_stage"), **{ch: d.get(ch) or {} for ch in CHANNELS},
            "synergy": d.get("synergy"), "why_it_works": d.get("why_it_works"), "template": d.get("template"),
            "adaptations": d.get("adaptations") or {}, "principles": d.get("principles") or [],
            "creator_note": json.loads(r["creator_note"]) if r["creator_note"] else None, "method": r["method"],
        })
    return out


def overview() -> dict:
    st = _state()
    with db.session() as conn:
        its = items(conn)
        count = {}
        for it in its:
            count[it["creator"]] = count.get(it["creator"], 0) + 1
        crs = []
        for cr in creators():
            accs = []
            for a in cr["accounts"]:
                s = st.get(f"{a['platform']}:{a['handle'].lower()}", {})
                ids = _account_ids(conn, a["platform"], a["handle"])
                n = conn.execute(f"SELECT COUNT(*) FROM videos WHERE account_id IN ({','.join('?' * len(ids)) or 'NULL'})",
                                 ids).fetchone()[0] if ids else 0
                status = s.get("status") or ("ok" if n else ("à récupérer" if a.get("status") == "vérifié" else "à vérifier"))
                accs.append({"platform": a["platform"], "handle": a["handle"], "status": status, "videos": n})
            crs.append({"name": cr["name"], "why": cr["why"], "accounts": accs, "analyzed": count.get(cr["name"], 0)})
        for name in count:  # créateurs venus du tableau sans compte configuré
            if name not in {c["name"] for c in crs}:
                crs.append({"name": name, "why": "vidéos de ton tableau", "accounts": [], "analyzed": count[name]})
        pending = len(pick_preview(conn))
    return {"stats": {"creators": len(crs), "videos": len(its) + pending, "analyzed": len(its), "pending": pending},
            "creators": crs, "items": its}


def pick_preview(conn) -> list[int]:
    """Comme pick() mais sans rien télécharger (pour compter ce qui reste à faire)."""
    c = cfg()
    per, min_score, max_dur = int(c.get("per_creator", 10)), float(c.get("min_score", 2.0)), float(c.get("max_duration_s", 120))
    done = {r["video_id"] for r in conn.execute("SELECT video_id FROM hook_breakdowns")}
    known = {(r["platform"], r["external_id"]): r["id"] for r in conn.execute("SELECT id, platform, external_id FROM videos")}
    out = []
    for s in seeds():
        p = _parse_url(s["url"])
        vid = known.get((p[0], p[2])) if p else None
        if not vid or vid not in done:
            out.append(vid or -1)
    for cr in creators():
        ids = [i for a in cr["accounts"] for i in _account_ids(conn, a["platform"], a["handle"])]
        if not ids:
            continue
        rows = conn.execute(f"""SELECT id FROM videos WHERE account_id IN ({','.join('?' * len(ids))}) AND is_mock=0
                AND outlier_score >= ? AND (duration_s IS NULL OR duration_s <= ?) ORDER BY outlier_score DESC LIMIT ?""",
                            (*ids, min_score, max_dur, per)).fetchall()
        out += [r["id"] for r in rows if r["id"] not in done]
    return out


def library_text(account: str, n: int = 12) -> str:
    """Bibliothèque de hooks décortiqués injectée dans le planner : techniques réplicables seulement."""
    its = [i for i in items() if (i["replicability"] or 0) >= 7 and (i["hook_strength"] or 0) >= 7
           and i["success_driver"] in (None, "technique")]
    if not its:
        return ""
    from . import challenge
    from .config import settings

    lines = []
    for i in its[:n]:
        v, t, vi, au = i["verbal"], i["textuel"], i["visuel"], i["auditif"]
        adapt = (i.get("adaptations") or {}).get(account, "")
        if account == "personal" and settings().challenge_start is None and challenge.mentions(adapt):
            adapt = ""  # anciennes adaptations « Day X/90 » : pas tant que le défi n'est pas lancé
        lines.append(f"- {i['creator']} ({i.get('archetype') or '?'}), dit : « {v.get('text', '')[:140]} » | écran : « {t.get('text', '')[:80]} » "
                     f"| visuel : {vi.get('first_frame', '')[:120]} | son : {au.get('first_sound', '')} → template : {i.get('template', '')} "
                     f"| adaptation : {adapt[:200]}")
    return ("HOOKS DÉCORTIQUÉS (Hook Lab, vraies vidéos qui ont surperformé grâce à la technique ; inspire-toi des MÉCANISMES, "
            "ne copie pas les phrases) :\n" + "\n".join(lines))


def export_xlsx() -> Path:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hook Lab"
    head = ["Créateur", "Plateforme", "Lien", "Score outlier", "Vues", "Hook oral", "Hook texte", "Hook visuel", "Hook auditif",
            "Musique", "Canal fort", "Archétype", "Force", "Réplicabilité", "Pourquoi ça marche", "Template",
            "Adaptation", "Principes", "Ton annotation"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1D1D1F")
    for i in items():
        v, t, vi, au = i["verbal"], i["textuel"], i["visuel"], i["auditif"]
        note = i["creator_note"] or {}
        ws.append([
            i["creator"], i["platform"], i["url"], i["outlier_score"], i["views"], v.get("text"),
            t.get("text"), " · ".join(x for x in (vi.get("first_frame"), vi.get("motion")) if x),
            " · ".join(x for x in (au.get("first_sound"), au.get("voice"), au.get("sound_design")) if x),
            au.get("music"), i["strong_channel"], i.get("archetype"), i["hook_strength"], i["replicability"], i.get("why_it_works"),
            i.get("template"), i["adaptations"].get("personal"), ", ".join(i["principles"]),
            " | ".join(f"{k} : {val}" for k, val in note.items()),
        ])
    widths = [16, 10, 40, 8, 10, 50, 35, 50, 50, 10, 10, 22, 7, 7, 50, 45, 55, 22, 45]
    for col, w in zip("ABCDEFGHIJKLMNOPQRS", widths):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"
    out = OUTPUT_DIR / "hooklab" / "hooklab.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
