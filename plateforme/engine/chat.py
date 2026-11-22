"""Chat du dashboard : chaque conversation = une session Claude Code headless (ton abonnement), lancée dans le projet.

Elle charge donc CLAUDE.md, la skill content-principles, config/identity.yaml (et le MCP hadith si règles islamiques) : mêmes connaissances
et mêmes règles que Claude Code dans ce dossier. Une conversation reprend sa session (`--resume`), une nouvelle repart de zéro.
Historique dans SQLite (chat_conversations, chat_messages) ; le tour en cours vit en mémoire et se lit par polling."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import threading
import uuid

from . import db, log
from .config import ROOT, settings
from .llm import _claude_bin

logger = log.get("chat")

# Ce que la conversation peut faire sans demander : lire/écrire dans le projet, lancer le moteur, lire la base.
ALLOWED_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch", "mcp__hadith",
                 "Bash(.venv/bin/python -m engine:*)", "Bash(.venv/bin/python -m pytest:*)",
                 "Bash(ls:*)", "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)"]
DISALLOWED_TOOLS = ["Bash(git push:*)", "Bash(git commit:*)", "Bash(git reset:*)", "Bash(rm:*)"]

CHAT_PROMPT = """Tu es l'assistant intégré au dashboard local « Content Engine » de {owner}. Tu tournes dans le dossier du projet :
CLAUDE.md, config/identity.yaml et la skill content-principles s'appliquent à tout ce que tu génères ou modifies.
Réponds en français, court et concret. Le contenu des vidéos reste en anglais.

Ce que {owner} te demande le plus souvent :
- Voir le planning : .venv/bin/python -m engine plan --start AAAA-MM-JJ [--days N] [--full]
  (codes, statut, sujet ; --full ajoute format, décor, hook A). Codes : PB-AAAA-MM-JJ-N.
  Pour le détail complet d'une vidéo (script, plans, CTA) : output/calendar/<lundi>/calendar.json ou output/shooting/<date>.md.
- Régénérer UNE vidéo : .venv/bin/python -m engine regen <CODE> --instruction "<ce que {owner} veut changer>"
- Régénérer des jours : .venv/bin/python -m engine calendar --start AAAA-MM-JJ [--days N]
  Ça remplace les vidéos de ces jours : vérifie d'abord leur statut et préviens si certaines sont déjà filmées ou publiées.
  Une régénération prend plusieurs minutes : donne au Bash un timeout de 1 800 000 ms.
- Campagne (« cette semaine, que des objections / une semaine de lancement… ») : crée ou modifie config/campaigns/<id>.yaml
  (même structure que les fichiers existants : types, angle par slot, 3 slots par jour), puis régénère les jours concernés.
- « Cette semaine c'est X » (événement, lancement, examen, voyage…) : écris-le, daté, dans context/06_cette_semaine.md
  (injecté dans toutes les générations ; retire les semaines passées), puis propose de régénérer ce qui est concerné.
- Nouvelles connaissances (formations, livres, coaching) : note complète dans context/formations/<sujet>.md (non injectée),
  et l'essentiel actionnable, en quelques puces avec la source, dans context/05_formations.md (injecté).
  Le dossier context/ (hors formations/) doit rester sous 15 000 caractères au total : condense si besoin.
  N'invente rien : ne note que ce que {owner} t'a donné.

Règles :
{citations_rule}- Ne modifie pas config/identity.yaml ni la ligne éditoriale sans accord explicite.
- Pas de git commit, push ou suppression de fichiers : {owner} s'en occupe.
- Avant une action longue ou qui écrase du contenu, dis en une phrase ce que tu vas faire, sauf si {owner} l'a déjà demandé clairement.
- À la fin, résume ce qui a changé (codes des vidéos, fichiers)."""


def chat_prompt() -> str:
    from . import ethics

    cit = ("- Versets et hadiths : uniquement via le MCP hadith ou engine/sources/, sahih/hasan, marqués « À VÉRIFIER ».\n"
           if ethics.islamic() else "")
    name = ethics.owner() if ethics.owner() != "le créateur" else "l'utilisateur"
    return CHAT_PROMPT.format(owner=name, citations_rule=cit)


RUNS: dict[str, dict] = {}   # conv_id -> tour en cours {proc, text, tools, started}
_LOCK = threading.Lock()


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _row(r) -> dict:
    return dict(r) if r else {}


def list_conversations() -> list[dict]:
    with db.session() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT c.id, c.title, c.created_at, c.updated_at,
                      (SELECT COUNT(*) FROM chat_messages m WHERE m.conv_id=c.id) n_messages
               FROM chat_conversations c ORDER BY c.updated_at DESC""")]
    for r in rows:
        r["running"] = r["id"] in RUNS
    return rows


def create(title: str | None = None) -> dict:
    cid = uuid.uuid4().hex[:12]
    with db.session() as conn:
        conn.execute("INSERT INTO chat_conversations(id, title, created_at, updated_at) VALUES (?,?,?,?)",
                     (cid, (title or "Nouvelle conversation").strip()[:80], _now(), _now()))
    return get(cid)


def get(cid: str) -> dict:
    with db.session() as conn:
        conv = _row(conn.execute("SELECT * FROM chat_conversations WHERE id=?", (cid,)).fetchone())
        if not conv:
            raise KeyError(cid)
        msgs = [dict(r) for r in conn.execute(
            "SELECT id, role, content, tools, is_error, created_at FROM chat_messages WHERE conv_id=? ORDER BY id", (cid,))]
    for m in msgs:
        m["tools"] = db.loads(m["tools"], [])
    conv.pop("claude_session_id", None)
    run = RUNS.get(cid)
    live = {"text": run["text"], "tools": run["tools"], "started": run["started"]} if run else None
    return {**conv, "messages": msgs, "live": live}


def rename(cid: str, title: str) -> None:
    with db.session() as conn:
        conn.execute("UPDATE chat_conversations SET title=? WHERE id=?", (title.strip()[:80] or "Conversation", cid))


def delete(cid: str) -> None:
    stop(cid)
    with db.session() as conn:
        conn.execute("DELETE FROM chat_messages WHERE conv_id=?", (cid,))
        conn.execute("DELETE FROM chat_conversations WHERE id=?", (cid,))


def tool_label(name: str, inp: dict) -> str:
    """Résumé lisible d'un appel d'outil, affiché sous la réponse."""
    def rel(p: str) -> str:
        return os.path.relpath(p, ROOT) if p and os.path.isabs(p) else (p or "")

    if name == "Bash":
        return inp.get("description") or str(inp.get("command", ""))[:160]
    if name in ("Read", "Edit", "Write"):
        verb = {"Read": "Lit", "Edit": "Modifie", "Write": "Écrit"}[name]
        return f"{verb} {rel(inp.get('file_path', ''))}"
    if name in ("Glob", "Grep"):
        return f"Cherche « {inp.get('pattern', '')} »"
    if name.startswith("mcp__hadith"):
        return "Source islamique : " + name.split("__")[-1].replace("_", " ")
    if name in ("WebSearch", "WebFetch"):
        return f"Web : {inp.get('query') or inp.get('url', '')}"[:160]
    return name


def build_cmd(session_id: str | None) -> list[str]:
    cmd = [_claude_bin(), "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
           "--mcp-config", str(ROOT / ".mcp.json"), "--strict-mcp-config", "--permission-mode", "acceptEdits",
           "--allowedTools", *ALLOWED_TOOLS, "--disallowedTools", *DISALLOWED_TOOLS,
           "--append-system-prompt", chat_prompt()]
    if settings().get("chat.model"):
        cmd += ["--model", settings().get("chat.model")]
    if session_id:
        cmd += ["--resume", session_id]
    return cmd


def send(cid: str, text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("message vide")
    if not _claude_bin():
        raise RuntimeError("Claude Code introuvable sur ce Mac (commande `claude`).")
    with _LOCK:
        if cid in RUNS:
            raise RuntimeError("Claude répond déjà dans cette conversation.")
        with db.session() as conn:
            conv = _row(conn.execute("SELECT * FROM chat_conversations WHERE id=?", (cid,)).fetchone())
            if not conv:
                raise KeyError(cid)
            n = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE conv_id=?", (cid,)).fetchone()[0]
            conn.execute("INSERT INTO chat_messages(conv_id, role, content, created_at) VALUES (?,?,?,?)", (cid, "user", text, _now()))
            if n == 0 and conv["title"] == "Nouvelle conversation":
                conn.execute("UPDATE chat_conversations SET title=? WHERE id=?", (text.splitlines()[0][:60], cid))
            conn.execute("UPDATE chat_conversations SET updated_at=? WHERE id=?", (_now(), cid))
        run_env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        run_env.update(BASH_DEFAULT_TIMEOUT_MS="600000", BASH_MAX_TIMEOUT_MS="1800000")
        proc = subprocess.Popen(build_cmd(conv.get("claude_session_id")), cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1, env=run_env, start_new_session=True)
        RUNS[cid] = {"proc": proc, "text": "", "tools": [], "started": _now(), "stopped": False}
    proc.stdin.write(text)
    proc.stdin.close()
    threading.Thread(target=_pump, args=(cid, proc), daemon=True).start()
    return get(cid)


def _pump(cid: str, proc: subprocess.Popen) -> None:
    run = RUNS[cid]
    done_text, session_id, error = [], None, None
    try:
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if ev.get("session_id"):
                session_id = ev["session_id"]
            if kind == "stream_event":
                e = ev.get("event") or {}
                if e.get("type") == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
                    run["text"] += e["delta"]["text"]
                elif e.get("type") == "message_start" and run["text"] and not run["text"].endswith("\n\n"):
                    run["text"] += "\n\n"
            elif kind == "assistant":
                for b in (ev.get("message") or {}).get("content", []):
                    if b.get("type") == "text":
                        done_text.append(b["text"])
                    elif b.get("type") == "tool_use":
                        run["tools"].append({"id": b.get("id"), "label": tool_label(b.get("name", ""), b.get("input") or {}), "ok": None})
            elif kind == "user":
                for b in (ev.get("message") or {}).get("content", []):
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        for t in run["tools"]:
                            if t["id"] == b.get("tool_use_id"):
                                t["ok"] = not b.get("is_error")
            elif kind == "result" and ev.get("is_error"):
                error = str(ev.get("result") or ev.get("subtype") or "erreur")[:500]
        proc.wait()
        if proc.returncode and not error and not run["stopped"]:
            error = (proc.stderr.read() or f"code {proc.returncode}").strip()[-500:]
    except Exception as e:  # pragma: no cover - filet de sécurité
        error = str(e)[:500]
    finally:
        text = "\n\n".join(t.strip() for t in done_text if t.strip()) or run["text"].strip()
        if run["stopped"]:
            text = (text + "\n\n_(arrêté)_").strip()
        elif error and not text:
            text = f"Erreur : {error}"
        with db.session() as conn:
            conn.execute("INSERT INTO chat_messages(conv_id, role, content, tools, is_error, created_at) VALUES (?,?,?,?,?,?)",
                         (cid, "assistant", text, db.dumps([{"label": t["label"], "ok": t["ok"]} for t in run["tools"]]),
                          int(bool(error) and not run["stopped"]), _now()))
            sets, args = "updated_at=?", [_now()]
            if session_id:
                sets, args = sets + ", claude_session_id=?", args + [session_id]
            conn.execute(f"UPDATE chat_conversations SET {sets} WHERE id=?", (*args, cid))
        RUNS.pop(cid, None)
        if error:
            logger.warning("chat %s : %s", cid, error)


def stop(cid: str) -> None:
    run = RUNS.get(cid)
    if not run:
        return
    run["stopped"] = True
    from . import runs

    threading.Thread(target=runs.kill_tree, args=(run["proc"].pid,), daemon=True).start()
