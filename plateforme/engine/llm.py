"""Wrapper Claude (texte + vision), deux backends :

  api, SDK Anthropic (ANTHROPIC_API_KEY)
  claude_cli, Claude Code en mode headless (`claude -p`), avec TON abonnement : login de Claude Code
               sur ce Mac, ou token long-lived `claude setup-token` → CLAUDE_CODE_OAUTH_TOKEN dans .env.
               Aucune clé API nécessaire.
llm.provider (engine.yaml) : auto (api si clé, sinon claude_cli) | api | claude_cli | none.
Si aucun backend : available() == False et chaque module bascule sur son fallback."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from . import log
from .config import env, settings

logger = log.get("llm")
_client = None


_cli_ok: bool | None = None


def _claude_bin() -> str | None:
    return env("CLAUDE_BIN") or shutil.which("claude") or (
        os.path.expanduser("~/.local/bin/claude") if os.path.exists(os.path.expanduser("~/.local/bin/claude")) else None)


def _cli_logged_in() -> bool:
    """Ping minimal (≈700 tokens) une fois par process."""
    global _cli_ok
    if _cli_ok is None:
        try:
            out = _cli_run("You are a JSON API.", 'Reply with exactly: {"ok": true}', timeout=90)
            _cli_ok = '"ok"' in out
        except Exception as e:
            logger.warning("Claude Code CLI indisponible : %s", str(e)[:200])
            _cli_ok = False
    return _cli_ok


def provider() -> str:
    p = settings().get("llm.provider", "auto")
    if p != "auto":
        return p
    if env("ANTHROPIC_API_KEY"):
        return "api"
    if _claude_bin():
        return "claude_cli"
    return "none"


def available() -> bool:
    p = provider()
    if p == "api":
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return bool(env("ANTHROPIC_API_KEY"))
    if p == "claude_cli":
        return bool(_claude_bin()) and _cli_logged_in()
    return False


def _cli_run(system: str, prompt: str, images: list[str] | None = None, timeout: int = 900, web: bool = False) -> str:
    cmd = [_claude_bin(), "-p", "--output-format", "json", "--no-session-persistence", "--strict-mcp-config",
           "--model", settings().get("llm.cli_model", "sonnet"), "--system-prompt", system]
    if images:
        dirs = sorted({os.path.dirname(i) for i in images})
        cmd += ["--tools", "Read", "--allowedTools", "Read", "--max-turns", str(len(images) + 4)]
        for d in dirs:
            cmd += ["--add-dir", d]
        prompt += ("\n\nCommence par lire (outil Read) ces images, dans l'ordre (frames de la vidéo) :\n"
                   + "\n".join(images) + "\nPuis réponds.")
    elif web:  # veille : Claude peut chercher sur le web (comptes de la niche)
        cmd += ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch,WebFetch", "--max-turns", "30"]
    else:
        cmd += ["--tools", ""]
    run_env = dict(os.environ)
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=run_env)
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude -p : sortie illisible ({(p.stderr or p.stdout)[:300]})")
    if d.get("is_error"):
        raise RuntimeError(f"claude -p : {str(d.get('result'))[:300]}")
    return d.get("result") or ""


def _get_client():
    global _client
    if _client is None:
        import anthropic

        # URL explicite : on ignore un éventuel ANTHROPIC_BASE_URL hérité d'un autre outil.
        base_url = env("ENGINE_ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        _client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"), base_url=base_url, max_retries=3)
    return _client


def _model(vision: bool = False) -> str:
    if env("CLAUDE_MODEL"):
        return env("CLAUDE_MODEL")  # type: ignore[return-value]
    return settings().get("llm.vision_model" if vision else "llm.model", "claude-sonnet-5-5")


def no_dash(text: str) -> str:
    """Jamais de tiret long dans ce qui sort du modèle : « a — b » devient « a, b »."""
    return re.sub(r"\s*[—–]\s*", ", ", text) if text else text


def complete(system: str, user: str | list, max_tokens: int | None = None, vision: bool = False) -> str:
    return no_dash(_complete(system, user, max_tokens, vision))


def _complete(system: str, user: str | list, max_tokens: int | None = None, vision: bool = False) -> str:
    content = user if isinstance(user, list) else [{"type": "text", "text": user}]
    if provider() == "claude_cli":
        text = "\n\n".join(c["text"] for c in content if c.get("type") == "text")
        images = [c["_path"] for c in content if c.get("type") == "image" and c.get("_path")]
        last: Exception | None = None
        for attempt in range(2):
            try:
                return _cli_run(system, text, images)
            except Exception as e:
                last = e
                logger.warning("claude -p échoué (essai %d/2) : %s", attempt + 1, str(e)[:200])
                time.sleep(10)
        raise RuntimeError(f"Claude Code indisponible : {last}")
    client = _get_client()
    content = [{k: v for k, v in c.items() if k != "_path"} for c in content]
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=_model(vision),
                max_tokens=max_tokens or int(settings().get("llm.max_tokens", 8000)),
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        except Exception as e:  # réseau, quota, etc.
            last_err = e
            logger.warning("Appel Claude échoué (essai %d/3) : %s", attempt + 1, e)
            time.sleep(2 ** attempt * 3)
    raise RuntimeError(f"Claude indisponible : {last_err}")


def web_json(system: str, prompt: str, timeout: int = 1200) -> Any:
    """Réponse JSON après recherche web (Claude Code CLI seulement : c'est l'abonnement du créateur qui paie)."""
    if provider() != "claude_cli":
        raise RuntimeError("la recherche web passe par Claude Code (claude -p) : connecte-toi avec « claude »")
    return extract_json(no_dash(_cli_run(system, prompt, timeout=timeout, web=True)))


def extract_json(text: str) -> Any:
    """Récupère le premier objet/tableau JSON d'une réponse (tolère ```json ... ```)."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("Pas de JSON dans la réponse")
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    end = text.rfind(closer)
    return json.loads(text[start : end + 1])


def complete_json(system: str, user: str | list, max_tokens: int | None = None, vision: bool = False) -> Any:
    text = complete(system + "\n\nRéponds UNIQUEMENT avec du JSON valide.", user, max_tokens, vision)
    try:
        return extract_json(text)
    except (ValueError, json.JSONDecodeError):
        logger.warning("JSON invalide, nouvelle tentative de réparation")
        fixed = complete("Tu répares du JSON. Renvoie uniquement le JSON valide corrigé.", text[:60000], max_tokens)
        return extract_json(fixed)


def image_block(path: Path) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
            "_path": str(Path(path).resolve())}
