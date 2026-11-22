"""CLI : engine weekly | daily | report (+ sous-commandes par module).

  engine weekly   scrape → outliers → analyse → synthèse → calendrier (+ exports + fiche du jour)
  engine daily    stats (Graph API) → fiche de tournage du jour → briefs ChatCut
  engine report   état du système → output/report.md
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
import sys
import traceback

from . import db, log

logger = log.get("cli")


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _step(name: str, fn, *args, **kwargs):
    """Exécute une étape ; en cas d'erreur on log et on continue (jamais bloqué)."""
    logger.info("▶ %s", name)
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error("✗ %s a échoué : %s, on continue avec les fallbacks", name, e)
        logger.debug(traceback.format_exc())
        with db.session() as conn:
            db.log_run(conn, "cli", name, "error", str(e))
        return None


# ---------------------------------------------------------------- modules
def cmd_monter(a):
    import time

    from . import montage

    mid = montage.start(a.rush, a.style, a.code)
    print(f"Montage lancé : data/montages/{mid}/  (suivi : progress.txt)")
    seen = 0
    while True:
        j = montage.get(mid)
        for line in j["progress"][seen:]:
            print("  " + line, flush=True)
        seen = len(j["progress"])
        if j["status"] != "en cours":
            break
        time.sleep(10)
    print(f"Statut : {j['status']}" + (f"  ->  {montage.video_path(mid)}" if j["has_video"] else ""))
    return 0 if j["status"] == "fini" else 1


def cmd_veille(a):
    from . import veille

    if a.ideas_only:
        print(json.dumps({"grandes_idees": veille.youtube_long()}, ensure_ascii=False))
        return 0
    print(json.dumps(_step("veille", veille.run, rediscover=a.rediscover), ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_scrape(a):
    from . import scraper

    return scraper.run(force=a.force, backend=a.backend, only_owner=getattr(a, "account", None))


def cmd_outliers(a):
    from . import outliers

    return outliers.run()


def cmd_analyze(a):
    from . import analysis

    return analysis.run(limit=a.limit, reanalyze=a.reanalyze, upgrade=a.upgrade)


def cmd_synthesize(a):
    from . import synthesis

    return synthesis.run(a.start, include_mock=not a.no_mock)


def cmd_calendar(a):
    from . import exports, planner

    start = a.start or planner.default_week_start()
    days = a.days
    planner.plan_week(start, days, use_llm=False if a.no_llm else None, accounts=[a.account] if a.account else None)
    end = start + dt.timedelta(days=(days or 7) - 1)
    paths = exports.export_week(start, end)
    print(f"\nCalendrier : {paths['markdown']}\nJSON (Cockpit) : {paths['cockpit']}")
    return paths


def cmd_references(a):
    from . import exports, references
    from .planner import load_entries

    start = a.start or dt.date.today()
    end = start + dt.timedelta(days=6)
    n = references.attach(load_entries(start, end))
    exports.export_week(start, end)
    exports.export_shooting(start)
    print(f"{n} références attachées ({start} → {end})")


def cmd_regen(a):
    from .planner import regenerate

    e = regenerate(a.code, a.instruction or "")
    print(f"✓ {a.code} régénérée : {e['subject']}")
    return True


def cmd_hooklab(a):
    from . import hooklab

    if a.import_file:
        print("✓ tableau importé :", hooklab.import_xlsx(a.import_file))
    if a.add:
        name, platform, handle = a.add
        hooklab.add_creator(name, platform, handle)
        print(f"✓ créateur ajouté : {name} ({platform} @{handle})")
    if not a.export_only and not a.import_file and not a.add:
        res = hooklab.run(creator=a.creator, limit=a.limit, collect_first=not a.no_collect, reanalyze=a.reanalyze)
        print(f"✓ Hook Lab : {res['done']} hooks décortiqués, {res['failed']} échecs ({res['picked']} sélectionnés)")
    out = hooklab.export_xlsx()
    print(f"Export Excel : {out}")
    return True


def cmd_broll(a):
    from . import broll

    res = broll.generate(days=a.days)
    print(f"✓ {res['count']} plans B-roll ({res['source']})")
    return True


def cmd_challenge(a):
    from . import challenge

    if a.reset:
        challenge.set_start(None)
        print("Défi remis à « pas encore lancé ».")
        return True
    d = a.date or dt.date.today()
    challenge.set_start(d)
    print(f"Défi lancé : Jour 1 = {d}")
    if not a.no_regen:
        from . import exports, planner

        planner.plan_week(d, 7, accounts=["personal"])
        exports.export_week(d, d + dt.timedelta(days=6))
        exports.export_shooting(d)
    return True


def cmd_shooting(a):
    from . import exports

    p = exports.export_shooting(a.date or dt.date.today())
    print(f"\nFiche de tournage : {p}")
    return p


def cmd_plan(a):
    """Lecture seule : le planning d'une période (codes, statut, sujet, hook A), utilisé par le Chat du dashboard."""
    from .planner import load_entries

    start = a.start or dt.date.today()
    entries = load_entries(start, start + dt.timedelta(days=max(a.days, 1) - 1), a.account)
    if not entries:
        print("Aucune vidéo planifiée sur cette période.")
    for e in entries:
        kind = "rappel" if e.get("is_rappel") else e.get("slot_type", "")
        hook = next((h.get("verbal") for h in e.get("hooks") or [] if isinstance(h, dict) and h.get("verbal")), "")
        print(f"{e['code']}  [{e.get('status', 'planned')}] {kind:<6}  {e.get('subject', '')}")
        if a.full:
            print(f"    format : {(e.get('format') or {}).get('name', '')} · décor : {e.get('setup', '')}\n    hook A : {hook}")
    return True


def cmd_edit(a):
    from . import editing

    return editing.run(a.date or dt.date.today())


def cmd_stats(a):
    from . import feedback

    return feedback.run(mock=a.mock)


def cmd_link(a):
    from . import feedback

    print(feedback.manual_link(a.media, a.code, a.views, a.platform))


def cmd_ig_auth(a):
    from . import ig_auth
    from .config import settings

    accounts = list(settings().accounts) if a.account == "all" else [a.account]
    if a.refresh:
        for acc in accounts:
            print(acc, "rafraîchi" if ig_auth.refresh_if_needed(acc, force=True) else "non rafraîchi (voir logs)")
        return True
    if a.links:
        for acc in accounts:
            print(f"{acc} : {ig_auth.auth_url(a.flow, acc)}")
        return True
    ok = [ig_auth.connect(acc, a.flow) for acc in accounts]
    if all(ok):
        print("\nTest : ./bin/engine stats")
    return all(ok)


def cmd_login(a):
    from . import browser

    return browser.login(a.platform)


def cmd_scout(a):
    from .browser import scout

    if a.headless:
        from .config import settings

        settings().raw.setdefault("scout", {})["headless"] = True
    res = scout.run([a.platform] if a.platform else None, a.minutes)
    print(f"\nDécouvertes : {res.get('report')}")
    return res


def cmd_ui(a):
    from .ui.server import serve

    serve(a.port, open_browser=not a.no_open)


def cmd_reset_mock(a):
    with db.session() as conn:
        conn.execute("DELETE FROM analyses WHERE video_id IN (SELECT id FROM videos WHERE is_mock=1)")
        n = conn.execute("DELETE FROM videos WHERE is_mock=1").rowcount
        m = conn.execute("DELETE FROM my_videos WHERE is_mock=1").rowcount
        conn.execute("UPDATE accounts SET last_scraped_at=NULL WHERE last_backend='mock'")
    print(f"{n} vidéos mock et {m} stats mock supprimées.")


# ---------------------------------------------------------------- orchestrations
def cmd_weekly(a):
    from . import analysis, exports, outliers, planner, scraper, synthesis

    start = a.start or planner.default_week_start()
    _step("1. scrape", scraper.run, force=a.force, backend="mock" if a.mock else None)
    _step("2. outliers", outliers.run)
    _step("3. analyse", analysis.run)
    _step("4. synthèse", synthesis.run, start)
    _step("5. calendrier", planner.plan_week, start, use_llm=False if a.no_llm else None)
    end = start + dt.timedelta(days=6)
    paths = _step("export calendrier", exports.export_week, start, end) or {}
    today = dt.date.today()
    sheet_day = today if start <= today <= end else start
    sheet = _step("fiche de tournage", exports.export_shooting, sheet_day)
    from . import editing

    _step("briefs ChatCut", editing.run, sheet_day)
    print("\n=== engine weekly terminé ===")
    if paths:
        print(f"Calendrier      : {paths.get('markdown')}")
        print(f"Export Cockpit  : {paths.get('cockpit')}")
    print(f"Fiche du {sheet_day} : {sheet}")
    return True


def cmd_daily(a):
    from . import editing, exports, feedback, planner

    day = a.date or dt.date.today()
    _step("stats (Graph API)", feedback.run, mock=a.mock)
    from .config import settings

    if settings().get("scout.auto_in_daily", True) and not a.no_scout:
        from .browser import PLATFORMS, has_session, scout

        logged = [p for p in PLATFORMS if p != "youtube" and has_session(p)] + (["youtube"] if has_session("youtube") else [])
        if logged:
            _step("scout (feeds)", scout.run, logged)
    with db.session() as conn:
        has = conn.execute("SELECT 1 FROM calendar WHERE date=?", (day.isoformat(),)).fetchone()
    if not has:
        logger.info("aucune vidéo planifiée le %s → génération du calendrier à partir de ce jour", day)
        _step("calendrier", planner.plan_week, day, use_llm=False if a.no_llm else None)
        _step("export calendrier", exports.export_week, day, day + dt.timedelta(days=6))
    p = _step("fiche de tournage", exports.export_shooting, day)
    _step("briefs ChatCut", editing.run, day)
    print(f"\n=== Fiche de tournage du {day} : {p} ===")
    if p and a.print:
        print(open(p, encoding="utf-8").read())
    return True


def cmd_report(a):
    from .report import build

    p = build()
    print(f"Rapport : {p}")
    return p


def cmd_doctor(a):
    from . import llm, principles
    from .config import SKILL_PATH, env, load_content_bank, settings

    def ok(b):
        return "OK " if b else "-- "

    print(ok(SKILL_PATH.exists()), "skill content-principles", f"({len(principles.principle_index())} principes)")
    for acc in settings().accounts:
        b = load_content_bank(acc)
        print(ok(bool(b.get("topics"))), f"banque {acc} : {len(b.get('topics') or [])} sujets, "
              f"{len(b.get('test_formats') or [])} formats test, {len(b.get('rappels') or [])} rappels")
    print(ok(llm.available()), f"Claude (backend : {llm.provider()}), génération + vision")
    from .browser import PLATFORMS, has_session

    for p in PLATFORMS:
        print(ok(has_session(p)), f"session scout {p} (engine login {p})")
    from .principles import context_text

    print(ok(len(context_text()) > 800), f"contexte perso (context/*.md) : {len(context_text())} caractères utiles")
    print(ok(bool(env("OPENAI_API_KEY"))), "OPENAI_API_KEY (Whisper API)")
    print(ok(bool(env("APIFY_TOKEN"))), "APIFY_TOKEN (scraping fiable)")
    print(ok(bool(env("IG_SCRAPER_USERNAME"))), "IG_SCRAPER_USERNAME (session instaloader)")
    for acc in settings().accounts:
        print(ok(bool(env(f"IG_{acc.upper()}_TOKEN"))), f"IG_{acc.upper()}_TOKEN (stats Graph API)")
    import shutil

    print(ok(bool(shutil.which("ffmpeg"))), "ffmpeg")
    from . import ethics

    print(ok(ethics.owner() != "le créateur"), f"identité : {ethics.owner()} (config/identity.yaml → owner_name)")
    print(f"OK  règles islamiques : {'activées' if ethics.islamic() else 'désactivées'} (identity.yaml → islamic_rules)")
    if ethics.islamic():
        try:
            from .sources import quran

            quran.get_verse("1:1")
            print("OK  API Coran (alquran.cloud)")
        except Exception as e:
            print("--  API Coran :", e)


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="engine", description="Content Engine, production de vidéos courtes pilotée par IA")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("weekly", help="scrape → outliers → analyse → synthèse → calendrier")
    s.add_argument("--start", type=_date, help="1er jour du calendrier (défaut : lundi prochain le week-end, sinon aujourd'hui)")
    s.add_argument("--force", action="store_true", help="ignore le cache de scraping")
    s.add_argument("--mock", action="store_true", help="force les données de scraping mock")
    s.add_argument("--no-llm", action="store_true", help="n'utilise pas Claude même si la clé est présente")
    s.set_defaults(fn=cmd_weekly)

    s = sub.add_parser("daily", help="stats + fiche de tournage du jour + briefs ChatCut")
    s.add_argument("--date", type=_date)
    s.add_argument("--mock", action="store_true", help="stats simulées (test de la boucle)")
    s.add_argument("--no-llm", action="store_true")
    s.add_argument("--print", action="store_true", help="affiche la fiche dans le terminal")
    s.add_argument("--no-scout", action="store_true", help="ne lance pas le scout des feeds")
    s.set_defaults(fn=cmd_daily)

    s = sub.add_parser("report", help="état du système → output/report.md")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("doctor", help="vérifie clés, skill, banque, sources")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("monter", help="Module 8, monte une rush brute en reel 9:16 (skill supermonteur)")
    s.add_argument("rush")
    s.add_argument("--style", default="soustitres", choices=["soustitres", "brolls", "viral", "voixoff"])
    s.add_argument("--code", help="code de la fiche de tournage liée (ex. PB-2026-11-23-1)")
    s.set_defaults(fn=cmd_monter)

    s = sub.add_parser("veille", help="veille de la niche : comptes, reels gagnants, grandes idées YouTube")
    s.add_argument("--rediscover", action="store_true", help="recherche à nouveau les comptes de la niche")
    s.add_argument("--ideas-only", action="store_true", help="seulement les grandes idées des vidéos longues")
    s.set_defaults(fn=cmd_veille)

    s = sub.add_parser("scrape", help="Module 1, scrape les comptes de référence")
    s.add_argument("--force", action="store_true")
    s.add_argument("--backend", choices=["auto", "apify", "instaloader", "ytdlp", "mock"])
    s.add_argument("--account", choices=["personal"])
    s.set_defaults(fn=cmd_scrape)

    s = sub.add_parser("outliers", help="Module 2, scores outliers")
    s.set_defaults(fn=cmd_outliers)

    s = sub.add_parser("analyze", help="Module 3, analyse des outliers")
    s.add_argument("--limit", type=int)
    s.add_argument("--reanalyze", action="store_true")
    s.add_argument("--upgrade", action="store_true", help="analyse aussi les anciennes analyses sans critères de qualité")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("synthesize", help="Module 4, synthèse hebdo")
    s.add_argument("--start", type=_date)
    s.add_argument("--no-mock", action="store_true", help="ignore les données mock")
    s.set_defaults(fn=cmd_synthesize)

    s = sub.add_parser("calendar", help="Module 5, calendrier 7 jours + exports")
    s.add_argument("--start", type=_date)
    s.add_argument("--account", choices=["personal"])
    s.add_argument("--days", type=int)
    s.add_argument("--no-llm", action="store_true")
    s.set_defaults(fn=cmd_calendar)

    s = sub.add_parser("references", help="(re)cherche la vidéo de référence de chaque vidéo planifiée")
    s.add_argument("--start", type=_date)
    s.set_defaults(fn=cmd_references)

    s = sub.add_parser("plan", help="affiche le planning (lecture seule) : codes, statut, sujet")
    s.add_argument("--start", type=_date, help="1er jour (défaut : aujourd'hui)")
    s.add_argument("--days", type=int, default=1)
    s.add_argument("--account", choices=["personal"])
    s.add_argument("--full", action="store_true", help="ajoute format, décor et hook A")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("shooting", help="fiche de tournage d'un jour")
    s.add_argument("--date", type=_date)
    s.set_defaults(fn=cmd_shooting)

    s = sub.add_parser("stats", help="Module 6, stats Instagram Graph API")
    s.add_argument("--mock", action="store_true")
    s.set_defaults(fn=cmd_stats)

    s = sub.add_parser("link", help="lie une vidéo publiée à une entrée du calendrier")
    s.add_argument("media", help="media id Instagram, URL, ou id TikTok")
    s.add_argument("code", help="code calendrier, ex PB-2026-10-19-1")
    s.add_argument("--views", type=int, help="vues (saisie manuelle, ex. TikTok)")
    s.add_argument("--platform", default="instagram", choices=["instagram", "tiktok"])
    s.set_defaults(fn=cmd_link)

    s = sub.add_parser("edit", help="Module 7, briefs de montage ChatCut d'un jour")
    s.add_argument("--date", type=_date)
    s.set_defaults(fn=cmd_edit)

    s = sub.add_parser("ig-auth", help="connecte tes comptes Instagram (OAuth de ton app Meta) pour les stats")
    s.add_argument("account", nargs="?", default="all", choices=["all", "personal"])
    s.add_argument("--flow", default="instagram", choices=["instagram", "facebook"],
                   help="instagram = Instagram Login (défaut) ; facebook = Facebook Login (IG lié à une Page)")
    s.add_argument("--links", action="store_true", help="affiche seulement les liens de connexion")
    s.add_argument("--refresh", action="store_true", help="rafraîchit les tokens (Instagram Login, 60 j)")
    s.set_defaults(fn=cmd_ig_auth)

    s = sub.add_parser("login", help="connecte un compte scout (TU tapes tes identifiants dans Chrome)")
    s.add_argument("platform", choices=["instagram", "tiktok", "youtube"])
    s.set_defaults(fn=cmd_login)

    s = sub.add_parser("scout", help="scrolle les feeds : entraîne l'algo + découvre des outliers")
    s.add_argument("--platform", choices=["instagram", "tiktok", "youtube"])
    s.add_argument("--minutes", type=float)
    s.add_argument("--headless", action="store_true")
    s.set_defaults(fn=cmd_scout)

    s = sub.add_parser("regen", help="régénère une vidéo du calendrier (Claude)")
    s.add_argument("code")
    s.add_argument("--instruction", default="")
    s.set_defaults(fn=cmd_regen)

    s = sub.add_parser("broll", help="liste des B-rolls à tourner (Claude)")
    s.add_argument("--days", type=int, default=14)
    s.set_defaults(fn=cmd_broll)

    s = sub.add_parser("hooklab", help="Hook Lab : décortique les hooks des créateurs (verbal, texte, visuel, auditif)")
    s.add_argument("--creator", help="un seul créateur (nom dans config/hooklab.yaml)")
    s.add_argument("--limit", type=int, help="nombre max de hooks à décortiquer")
    s.add_argument("--no-collect", action="store_true", help="ne re-scrape pas les comptes")
    s.add_argument("--reanalyze", action="store_true", help="refait aussi les hooks déjà décortiqués")
    s.add_argument("--import", dest="import_file", help="importe un tableau .xlsx (créateur, lien, hook oral/texte/visuel/auditif)")
    s.add_argument("--add", nargs=3, metavar=("NOM", "PLATEFORME", "HANDLE"), help="ajoute un créateur")
    s.add_argument("--export-only", action="store_true", help="exporte seulement l'Excel")
    s.set_defaults(fn=cmd_hooklab)

    s = sub.add_parser("challenge", help="lance le défi 90 jours (Jour 1 = date) ou le réinitialise")
    s.add_argument("--date", type=_date)
    s.add_argument("--reset", action="store_true")
    s.add_argument("--no-regen", action="store_true")
    s.set_defaults(fn=cmd_challenge)

    s = sub.add_parser("ui", help="dashboard local → http://127.0.0.1:8787")
    s.add_argument("--port", type=int, default=8787)
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(fn=cmd_ui)

    s = sub.add_parser("reset-mock", help="supprime toutes les données mock de la base")
    s.set_defaults(fn=cmd_reset_mock)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    a = parser.parse_args(argv)
    log.setup(a.verbose)
    from . import runs

    runs.register(a.cmd, list(argv if argv is not None else sys.argv[1:]))
    result = a.fn(a)
    return 0 if result is not False else 1


if __name__ == "__main__":
    sys.exit(main())
