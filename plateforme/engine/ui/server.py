"""Dashboard local, `engine ui` → http://127.0.0.1:8787 (n'écoute QUE sur ta machine).

Backend = le moteur Python ; Claude = Claude Code headless (ton abonnement) via engine.llm.
Les actions longues (pipeline, régénération, scout, stats) tournent en tâches de fond, suivies via /api/jobs."""
from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import db, log
from ..config import CONFIG_DIR, settings

logger = log.get("ui")
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Content Engine")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------------------------------------------------------------- tâches de fond (sous-processus arrêtables)
import subprocess  # noqa: E402
import sys  # noqa: E402

from .. import runs  # noqa: E402
from ..config import ROOT  # noqa: E402

JOBS: dict[str, dict] = {}
PROCS: dict[str, subprocess.Popen] = {}
_LOCK = threading.Lock()


def start_job(kind: str, label: str, argv: list[str]) -> dict:
    """Lance `python -m engine <argv>` dans son propre groupe de processus (→ bouton Stop fiable)."""
    with _LOCK:
        running = [j for j in JOBS.values() if j["kind"] == kind and j["status"] == "running"]
        if running:
            return _public(running[0])
        jid = uuid.uuid4().hex[:10]
        proc = subprocess.Popen([sys.executable, "-m", "engine", *argv], cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
        job = {"id": jid, "kind": kind, "label": label, "status": "running", "log": [], "result": None, "error": None,
               "started": dt.datetime.now().isoformat(timespec="seconds"), "finished": None, "external": False, "pid": proc.pid}
        JOBS[jid], PROCS[jid] = job, proc

    def pump():
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                job["log"].append(line[:300])
                del job["log"][:-80]
        rc = proc.wait()
        if job["status"] == "running":
            job["status"] = "done" if rc == 0 else "error"
            if rc != 0:
                job["error"] = next((l for l in reversed(job["log"]) if "ERROR" in l or "Error" in l or "✗" in l), f"code {rc}")[:400]
        job["finished"] = dt.datetime.now().isoformat(timespec="seconds")

    threading.Thread(target=pump, daemon=True).start()
    return _public(job)


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items()}


@app.get("/api/jobs")
def jobs():
    mine = {j["pid"] for j in JOBS.values() if j["status"] == "running"}
    ext = [{"id": f"ext-{r['pid']}", "kind": r["cmd"], "label": f"{r['label']} (terminal)", "status": "running", "log": [],
            "result": None, "error": None, "started": r["started"], "finished": None, "external": True, "pid": r["pid"]}
           for r in runs.running() if r["pid"] not in mine]
    return ext + sorted((_public(j) for j in JOBS.values()), key=lambda j: j["started"], reverse=True)[:30]


@app.get("/api/jobs/{jid}")
def job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404)
    return _public(JOBS[jid])


@app.post("/api/jobs/{jid}/stop")
def stop_job(jid: str):
    if jid.startswith("ext-"):
        pid = int(jid[4:])
        if not any(r["pid"] == pid for r in runs.running()):
            raise HTTPException(404)
        threading.Thread(target=runs.kill_tree, args=(pid,), daemon=True).start()
        return {"ok": True}
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404)
    if j["status"] == "running":
        j["status"] = "stopped"
        j["finished"] = dt.datetime.now().isoformat(timespec="seconds")
        threading.Thread(target=runs.kill_tree, args=(j["pid"],), daemon=True).start()
    return {"ok": True}


RUN_KINDS = {
    "weekly": ("Pipeline de la semaine", lambda p: ["weekly"] + (["--start", p["start"]] if p.get("start") else [])),
    "daily": ("Routine du jour", lambda p: ["daily", "--no-scout"] + (["--date", p["start"]] if p.get("start") else [])),
    "calendar": ("Régénérer le calendrier", lambda p: ["calendar"] + (["--start", p["start"]] if p.get("start") else [])
                 + (["--account", p["account"]] if p.get("account") else [])),
    "references": ("Chercher les références", lambda p: ["references"] + (["--start", p["start"]] if p.get("start") else [])),
    "scout": ("Scout des feeds", lambda p: ["scout"] + (["--platform", p["platform"]] if p.get("platform") else [])),
    "stats": ("Stats Instagram", lambda p: ["stats"]),
    "login": ("Connexion compte scout", lambda p: ["login", p["platform"]]),
    "broll": ("Liste B-roll", lambda p: ["broll"]),
    "analyze": ("Analyse des outliers", lambda p: ["analyze"]),
    "hooklab": ("Hook Lab", lambda p: ["hooklab"] + (["--creator", p["creator"]] if p.get("creator") else [])
                + (["--limit", str(int(p["limit"]))] if p.get("limit") else [])),
}


@app.post("/api/run/{kind}")
def run_kind(kind: str, payload: dict = Body(default={})):
    if kind not in RUN_KINDS:
        raise HTTPException(400, f"tâche inconnue : {kind}")
    label, argv = RUN_KINDS[kind]
    if kind == "login" and payload.get("platform") not in ("instagram", "tiktok", "youtube"):
        raise HTTPException(400)
    return start_job(kind, label + (f" {payload['platform']}" if kind in ("login", "scout") and payload.get("platform") else ""), argv(payload))


# ---------------------------------------------------------------- défi
@app.post("/api/challenge/start")
def challenge_start(payload: dict = Body(...)):
    from .. import challenge

    try:
        d = dt.date.fromisoformat(payload["date"])
    except (KeyError, ValueError):
        raise HTTPException(400, "date invalide (AAAA-MM-JJ)")
    if payload.get("regenerate", True):
        return start_job("challenge", f"Lancement du défi (Jour 1 = {d.strftime('%d/%m')})", ["challenge", "--date", d.isoformat()])
    challenge.set_start(d)
    return {"ok": True}


@app.post("/api/challenge/reset")
def challenge_reset():
    from .. import challenge

    challenge.set_start(None)
    return {"ok": True}


@app.get("/api/challenge-map")
def challenge_map():
    from .. import challenge

    return challenge.challenge_map()


# ---------------------------------------------------------------- B-roll
# ---------------------------------------------------------------- Hook Lab
@app.get("/api/hooklab")
def hooklab_get():
    from .. import hooklab

    return hooklab.overview()


@app.post("/api/hooklab/creators")
def hooklab_add(payload: dict = Body(...)):
    from .. import hooklab

    try:
        return hooklab.add_creator(payload.get("name", ""), payload.get("platform", ""), payload.get("handle", ""), payload.get("why", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/hooklab/export")
def hooklab_export():
    from .. import hooklab

    path = hooklab.export_xlsx()
    return FileResponse(path, filename="hooklab.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/broll")
def broll_list():
    from .. import broll

    return broll.load()


@app.post("/api/broll/{item_id}")
def broll_done(item_id: int, payload: dict = Body(...)):
    from .. import broll

    broll.set_done(item_id, bool(payload.get("done")))
    return {"ok": True}


# ---------------------------------------------------------------- miniatures + vidéos
THUMBS = Path(ROOT) / "data" / "thumbs"


@app.get("/api/thumb/{video_id}")
def thumb(video_id: int):
    from fastapi.responses import Response

    from ..thumbs import thumbnail

    path = thumbnail(video_id)
    if not path:
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/media/{video_id}")
def media(video_id: int):
    with db.session() as conn:
        r = conn.execute("SELECT media_path FROM videos WHERE id=?", (video_id,)).fetchone()
    if not r or not r["media_path"] or not Path(r["media_path"]).exists():
        raise HTTPException(404)
    return FileResponse(r["media_path"], media_type="video/mp4")


# ---------------------------------------------------------------- vue d'ensemble
@app.get("/api/overview")
def overview():
    from .. import llm
    from ..browser import PLATFORMS, has_session
    from ..config import env
    from ..principles import context_text

    s = settings()
    today = dt.date.today()
    with db.session() as conn:
        counts = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) n FROM calendar WHERE date BETWEEN ? AND ? GROUP BY 1",
            (today.isoformat(), (today + dt.timedelta(days=6)).isoformat()))}
        last_runs = [dict(r) for r in conn.execute("SELECT at, step, status, substr(detail,1,140) detail FROM runs ORDER BY id DESC LIMIT 8")]
        data = conn.execute("SELECT COUNT(*) n, SUM(is_mock) m, SUM(is_outlier) o FROM videos").fetchone()
        planned = conn.execute("SELECT MIN(date) a, MAX(date) b FROM calendar").fetchone()
    from .. import challenge

    ch = challenge.status()
    return {
        "challenge": ch,
        "week_start": __import__("engine.planner", fromlist=["x"]).default_week_start(today).isoformat(),
        "today": today.isoformat(), "day_number": ch["day_number"], "challenge_length": ch["length"],
        "challenge_start": ch["start_date"], "objectif": s.get("challenge.objectif"),
        "language": s.get("language"), "islamic": __import__("engine.ethics", fromlist=["x"]).islamic(), "week_counts": counts, "calendar_range": dict(planned),
        "videos": {"total": data["n"], "mock": data["m"] or 0, "outliers": data["o"] or 0},
        "llm": {"provider": llm.provider()},
        "sessions": {p: has_session(p) for p in PLATFORMS},
        "ig_stats": {a: bool(env(f"IG_{a.upper()}_TOKEN")) for a in s.accounts},
        "context_chars": len(context_text()),
        "accounts": {k: v.get("name") for k, v in s.accounts.items()},
        "last_runs": last_runs,
    }


# ---------------------------------------------------------------- vidéos
def _entries(start: dt.date, end: dt.date):
    from ..planner import load_entries

    return load_entries(start, end)


@app.get("/api/day/{day}")
def day(day: str):
    from ..exports import MIN_PER_SETUP, MIN_PER_VIDEO, SETUP_GEAR
    from ..formats import SETUP_LABELS

    d = dt.date.fromisoformat(day)
    entries = _entries(d, d)
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(e["setup"], []).append(e)
    order = sorted(groups, key=lambda s: (s == "ecran", -len(groups[s])))
    return {"date": day, "day_number": settings().challenge_day(d),
            "minutes": len(entries) * MIN_PER_VIDEO + len(groups) * MIN_PER_SETUP,
            "setups": [{"setup": s, "label": SETUP_LABELS.get(s, s), "gear": SETUP_GEAR.get(s), "videos": groups[s]} for s in order]}


@app.get("/api/week")
def week(start: str | None = None):
    d = dt.date.fromisoformat(start) if start else dt.date.today()
    return {"start": d.isoformat(), "days": [(d + dt.timedelta(days=i)).isoformat() for i in range(7)],
            "videos": _entries(d, d + dt.timedelta(days=6))}


def _get(code: str) -> dict:
    with db.session() as conn:
        r = conn.execute("SELECT data, status, id FROM calendar WHERE code=?", (code,)).fetchone()
    if not r:
        raise HTTPException(404)
    e = db.loads(r["data"], {})
    e["status"], e["calendar_id"] = r["status"], r["id"]
    return e


@app.get("/api/video/{code}")
def video(code: str):
    from ..editing import brief

    e = _get(code)
    e["chatcut"] = brief(e)["chatcut_prompt"]
    return e


@app.post("/api/video/{code}")
def update_video(code: str, payload: dict = Body(...)):
    from ..planner import update_entry

    allowed = {k: v for k, v in payload.items() if k in ("status", "shots_done", "citation_verified", "notes", "hook_used")}
    if "status" in allowed and allowed["status"] not in ("planned", "filmed", "published"):
        raise HTTPException(400)
    return update_entry(code, **allowed)


@app.post("/api/video/{code}/script")
def edit_script(code: str, payload: dict = Body(...)):
    """Le créateur corrige le hook / le script / le CTA à la main : on enregistre sa version et l'avant/après
    dans le carnet de corrections, relu par toutes les générations suivantes (context/00_corrections.md)."""
    from ..corrections import record
    from ..planner import update_entry

    e = _get(code)
    hooks = [dict(h) for h in (e.get("hooks") or [{}])] or [{}]
    before = {"hook": hooks[0].get("verbal", ""), "script": e.get("script", ""),
              "cta": (e.get("cta") or {}).get("text", "") if isinstance(e.get("cta"), dict) else (e.get("cta") or "")}
    after = {k: str(payload.get(k, before[k])).strip() for k in before}
    if after == before:
        return e
    hooks[0]["verbal"] = after["hook"]
    cta = dict(e["cta"]) if isinstance(e.get("cta"), dict) else {"type": "dm"}
    cta["text"] = after["cta"]
    out = update_entry(code, hooks=hooks, script=after["script"], cta=cta, word_count=len(after["script"].split()),
                       edited_by_owner=True)
    record(e, before, after)
    return out


@app.post("/api/video/{code}/regenerate")
def regenerate(code: str, payload: dict = Body(default={})):
    _get(code)
    return start_job(f"regen:{code}", f"Régénérer {code}", ["regen", code, "--instruction", (payload.get("instruction") or "").strip()])


# ---------------------------------------------------------------- stats
@app.get("/api/stats")
def stats():
    from ..synthesis import my_stats

    out = {}
    with db.session() as conn:
        for acc in settings().accounts:
            vids = [dict(r) for r in conn.execute(
                """SELECT m.external_id, m.url, m.caption, m.posted_at, m.views, m.reach, m.likes, m.comments, m.shares, m.saves,
                          m.avg_watch_time_s, m.is_mock, c.code, json_extract(c.data,'$.subject') subject,
                          json_extract(c.data,'$.format.name') format_name, c.slot_type
                   FROM my_videos m LEFT JOIN calendar c ON c.id=m.calendar_id WHERE m.account=?
                   ORDER BY m.posted_at DESC LIMIT 60""", (acc,))]
            fs = [dict(r) for r in conn.execute("SELECT format_id, status, origin, updated_at FROM format_status WHERE account=?", (acc,))]
            out[acc] = {"summary": my_stats(conn, acc, include_mock=True), "videos": vids, "formats": fs}
    return out


@app.get("/api/synthesis/{account}")
def synthesis(account: str):
    with db.session() as conn:
        r = conn.execute("SELECT data FROM syntheses WHERE account=? ORDER BY week_start DESC, id DESC LIMIT 1", (account,)).fetchone()
    return db.loads(r["data"], {}) if r else {}


# ---------------------------------------------------------------- découvertes
@app.get("/api/discoveries")
def discoveries():
    known = {(a.get("platform"), str(a.get("handle", "")).lower()) for cfg in settings().accounts.values()
             for a in (cfg.get("reference_accounts") or []) + (cfg.get("other_niche_accounts") or [])}
    with db.session() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT v.id video_id, v.media_path, v.url, v.views, v.outlier_score, v.caption, v.platform, v.external_id, v.eng_comment_rel, a.handle, a.owner,
                      a.category, a.followers, an.hook_type, an.visual_format, an.method, an.data,
                      json_extract(an.data,'$.why_it_works') why
               FROM videos v JOIN accounts a ON a.id=v.account_id LEFT JOIN analyses an ON an.video_id=v.id
               WHERE v.is_mock=0 AND v.is_outlier=1 ORDER BY (an.id IS NOT NULL) DESC, (a.category='discovery') DESC,
                     v.outlier_score DESC LIMIT 200""")]
    from ..quality import eligibility

    for r in rows:
        an = {**(db.loads(r.pop("data"), {}) or {}), "method": r.get("method")} if r.get("method") else None
        slot = "test" if r["category"] == "other" else "proven"
        r["eligible"], r["eligibility_reason"] = eligibility(an, r["platform"], slot, r.get("eng_comment_rel"))
        for k in ("replicability", "hook_strength", "success_driver", "funnel_stage", "conversion_mechanism"):
            r[k] = (an or {}).get(k)
        r["known"] = (r["platform"], (r["handle"] or "").lower()) in known
        mp = r.pop("media_path", None)
        r["thumb_url"] = f"/api/thumb/{r['video_id']}"
        r["media_url"] = f"/api/media/{r['video_id']}" if mp and Path(mp).exists() else None
        r["title"] = (r["caption"] or "").split("\n")[0][:140]
    return rows


@app.post("/api/accounts/add")
def add_account(payload: dict = Body(...)):
    owner, platform, handle = payload.get("owner"), payload.get("platform"), str(payload.get("handle", "")).lstrip("@")
    category = payload.get("category", "reference_accounts")
    if owner not in settings().accounts or platform not in ("instagram", "tiktok", "youtube") or not re.fullmatch(r"[\w.\-]+", handle):
        raise HTTPException(400, "paramètres invalides")
    p = CONFIG_DIR / "accounts" / f"{owner}.yaml"
    lines = p.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith(f"{category}:"))
    except StopIteration:
        raise HTTPException(400, "section introuvable")
    end = start + 1
    while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, f'  - {{platform: {platform}, handle: {handle}, status: "À VALIDER", note: "ajouté depuis le dashboard"}}')
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    settings().accounts[owner].setdefault(category, []).append({"platform": platform, "handle": handle})
    return {"ok": True}


# ---------------------------------------------------------------- Instagram (stats), OAuth sans terminal
def _reload_env():
    from ..config import ROOT

    try:
        from dotenv import dotenv_values

        for k, v in dotenv_values(ROOT / ".env").items():
            if v is not None:
                __import__("os").environ[k] = v
    except Exception:
        pass


@app.get("/api/ig/status")
def ig_status():
    from .. import ig_auth

    _reload_env()
    return ig_auth.config_status()


@app.post("/api/ig/begin")
def ig_begin(payload: dict = Body(...)):
    from .. import ig_auth

    _reload_env()
    try:
        return ig_auth.begin(payload["account"], payload.get("flow", "instagram"))
    except SystemExit as e:
        raise HTTPException(400, str(e))


@app.post("/api/ig/complete")
def ig_complete(payload: dict = Body(...)):
    from .. import ig_auth

    try:
        return ig_auth.complete(payload.get("url", ""), payload.get("state"), payload.get("choice"))
    except (ValueError, SystemExit) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Échange refusé par Meta : {str(e)[:300]}")


# ---------------------------------------------------------------- chat (sessions Claude Code, ton abonnement)
@app.get("/api/chat")
def chat_list():
    from .. import chat

    return chat.list_conversations()


@app.post("/api/chat")
def chat_create(payload: dict = Body(default={})):
    from .. import chat

    return chat.create(payload.get("title"))


@app.get("/api/chat/{cid}")
def chat_get(cid: str):
    from .. import chat

    try:
        return chat.get(cid)
    except KeyError:
        raise HTTPException(404)


@app.post("/api/chat/{cid}/message")
def chat_send(cid: str, payload: dict = Body(...)):
    from .. import chat

    try:
        return chat.send(cid, payload.get("text", ""))
    except KeyError:
        raise HTTPException(404)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/chat/{cid}/stop")
def chat_stop(cid: str):
    from .. import chat

    chat.stop(cid)
    return {"ok": True}


@app.post("/api/chat/{cid}/rename")
def chat_rename(cid: str, payload: dict = Body(...)):
    from .. import chat

    chat.rename(cid, payload.get("title", ""))
    return {"ok": True}


@app.delete("/api/chat/{cid}")
def chat_delete(cid: str):
    from .. import chat

    chat.delete(cid)
    return {"ok": True}


# ---------------------------------------------------------------- contexte
@app.get("/api/context")
def get_context():
    d = CONFIG_DIR.parent / "context"
    return [{"name": f.name, "content": f.read_text(encoding="utf-8")} for f in sorted(d.glob("*.md"))]


@app.post("/api/context/{name}")
def save_context(name: str, payload: dict = Body(...)):
    if not re.fullmatch(r"[\w\-]+\.md", name):
        raise HTTPException(400)
    (CONFIG_DIR.parent / "context" / name).write_text(payload.get("content", ""), encoding="utf-8")
    return {"ok": True}


# ---------------------------------------------------------------- montage (Module 8)
from fastapi import File, Form, UploadFile  # noqa: E402

from .. import montage  # noqa: E402

UPLOADS = ROOT / "data" / "uploads"


@app.get("/api/montages")
def montages():
    today = dt.date.today()
    with db.session() as conn:
        rows = conn.execute("SELECT code, date, json_extract(data,'$.subject') s FROM calendar WHERE date BETWEEN ? AND ? "
                            "ORDER BY date, code", ((today - dt.timedelta(days=7)).isoformat(),
                                                    (today + dt.timedelta(days=14)).isoformat())).fetchall()
    return {"styles": [{"id": k, **{x: v[x] for x in ("label", "desc", "brief")}} for k, v in montage.STYLES.items()],
            "fiches": [{"code": r["code"], "date": r["date"], "subject": r["s"]} for r in rows],
            "jobs": montage.list_jobs()}


@app.get("/api/montages/{mid}")
def montage_get(mid: str):
    try:
        return montage.get(mid)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404)


@app.post("/api/montages")
async def montage_new(file: UploadFile = File(...), style: str = Form(...), code: str = Form("")):
    if style not in montage.STYLES:
        raise HTTPException(400, "style inconnu")
    ext = Path(file.filename or "rush.mp4").suffix.lower()
    if ext not in (".mp4", ".mov", ".m4v", ".mkv", ".webm"):
        raise HTTPException(400, "format vidéo non pris en charge (mp4, mov)")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    tmp = UPLOADS / f"{uuid.uuid4().hex}{ext}"
    with open(tmp, "wb") as f:
        while chunk := await file.read(8 << 20):
            f.write(chunk)
    named = tmp.with_name(re.sub(r"[^\w.\-]+", "-", Path(file.filename or "rush").stem)[:40] + ext)
    tmp.rename(named)
    try:
        mid = montage.start(named, style, code or None, move=True)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"id": mid}


@app.get("/api/montages/{mid}/video")
def montage_video(mid: str):
    try:
        p = montage.video_path(mid)
    except ValueError:
        raise HTTPException(404)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4", filename=f"{mid}.mp4")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


def serve(port: int = 8787, open_browser: bool = True) -> None:
    import webbrowser

    import uvicorn

    url = f"http://127.0.0.1:{port}"
    print(f"\n  Content Engine → {url}   (Ctrl+C pour arrêter)\n")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
