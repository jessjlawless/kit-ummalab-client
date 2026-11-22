"""Téléchargement d'une vidéo Instagram/TikTok via le navigateur du compte scout (comme un humain qui ouvre la vidéo) :
on ouvre la page de la vidéo, on lit l'URL mp4 progressive dans les réponses JSON de la plateforme
(Instagram `video_versions`, TikTok `playAddr`), puis on la télécharge avec le même navigateur.
Aucun appel direct avec les cookies hors navigateur (Instagram les signale)."""
from __future__ import annotations

import random
from pathlib import Path

from .. import log
from . import check_blocked, context, goto, has_session
from .extract import EXTRACTORS, walk

logger = log.get("browser.download")
META: dict[str, dict] = {}  # code/id → métadonnées vues dans la page (auteur, vues, caption), utilisé par le Hook Lab


def download(platform: str, url: str, code: str, target: Path) -> str | None:
    if platform not in ("instagram", "tiktok") or not has_session(platform):
        return None
    found: list[str] = []
    with context(platform, headless=True) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                if "json" not in (resp.headers.get("content-type") or "") and "graphql" not in resp.url:
                    return
                data = resp.json()
                for it in EXTRACTORS[platform](data):
                    if str(it["external_id"]) == str(code):
                        META[str(code)] = {**META.get(str(code), {}), **{k: v for k, v in it.items() if v is not None}}
                for d in walk(data):
                    if platform == "instagram" and d.get("code") == code and d.get("video_versions"):
                        found.append(d["video_versions"][0]["url"])
                    elif platform == "tiktok" and str(d.get("id")) == str(code) and isinstance(d.get("video"), dict):
                        u = d["video"].get("playAddr") or d["video"].get("downloadAddr")
                        if u:
                            found.append(u)
            except Exception:
                pass

        page.on("response", on_response)
        goto(page, url, platform)
        page.wait_for_timeout(random.uniform(3500, 6000))
        check_blocked(page, platform)
        if not found:  # dernier recours : la balise <video> de la page (souvent un blob → ignoré)
            src = page.evaluate("() => { const v = document.querySelector('video'); return v ? (v.currentSrc || v.src) : null; }")
            if src and src.startswith("http"):
                found.append(src)
        if not found:
            logger.warning("pas d'URL vidéo trouvée pour %s", url)
            return None
        r = ctx.request.get(found[0], timeout=120000)
        if not r.ok or len(r.body()) < 20000:
            logger.warning("téléchargement navigateur KO (%s) pour %s", r.status, url)
            return None
        target.write_bytes(r.body())
    return str(target)
