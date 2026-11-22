"""Test bout-en-bout en mock : .venv/bin/python -m pytest -q tests"""
import datetime as dt
from pathlib import Path

import pytest
import yaml

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from engine import config, formats, planner

    s = config.settings()
    monkeypatch.setitem(s.raw, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setitem(s.raw, "llm", {**s.raw.get("llm", {}), "provider": "none"})  # jamais d'appel réel en test
    monkeypatch.setitem(s.raw, "language", "fr")  # la fixture est en français
    monkeypatch.setitem(s.raw, "challenge", {**s.raw.get("challenge", {}), "start_date": None})  # défi pas lancé par défaut
    monkeypatch.setitem(s.raw, "scout", {**s.raw.get("scout", {}), "keywords": {"personal": ["ai", "dms"]}})
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "out")
    bank = yaml.safe_load((FIX / "bank_personal.yaml").read_text())
    loader = lambda acc: bank if acc == "personal" else {"proven_formats": [], "topics": [], "test_formats": []}  # noqa: E731
    monkeypatch.setattr(planner, "load_content_bank", loader)
    monkeypatch.setattr(formats, "load_content_bank", loader)
    monkeypatch.setattr(s, "accounts", {"personal": s.accounts["personal"]})
    return s


def test_outliers_and_analysis(env):
    from engine import analysis, db, outliers, scraper

    scraper.run(backend="mock", only_owner="personal")
    st = outliers.run()
    assert st["outliers"] > 0
    a = analysis.run(limit=5)
    assert a["analyzed"] == 5 and a["errors"] == 0
    with db.session() as c:
        r = c.execute("SELECT v.views, a.median_views, v.outlier_score FROM videos v JOIN accounts a ON a.id=v.account_id "
                      "WHERE v.is_outlier=1 LIMIT 1").fetchone()
        assert abs(r["views"] / r["median_views"] - r["outlier_score"]) < 0.01 and r["outlier_score"] >= 3


def _launch(s, monkeypatch, day: dt.date):
    monkeypatch.setitem(s.raw, "challenge", {**s.raw["challenge"], "start_date": day})


def test_calendar_rules(env, monkeypatch):
    from engine import ethics, planner

    start = dt.date(2026, 10, 19)  # lundi = Jour 1
    _launch(env, monkeypatch, start)
    entries = planner.plan_week(start, 7, use_llm=False, with_references=False)
    assert len(entries) == 7 * 3
    first = [e for e in entries if e["date"] == "2026-10-19"]
    assert first[0]["topic_id"] == "pb_001" and "Jour 1" in first[0]["subject"] and "jour 2" in first[0]["script"].lower()
    assert first[0]["episode_label"] == "Jour 1/90"
    assert [e["slot_type"] for e in first] == ["proven", "proven", "test"]
    # zéro musique partout
    assert all(e["edit_template"]["music"] == ethics.music_rule() for e in entries)
    # rappels : jeudi + dimanche, slot 2
    rappels = [e for e in entries if e["is_rappel"]]
    assert {e["weekday"] for e in rappels} == {"jeudi", "dimanche"} and all(e["slot_index"] == 2 for e in rappels)
    ok = next(e for e in rappels if e["topic_id"] == "rp_001")
    assert ok["citation"]["status"] == "À VÉRIFIER" and "65:3" in ok["citation"]["reference"]
    assert "confiance" in ok["script"]
    bad = next(e for e in rappels if e["topic_id"] == "rp_002")
    assert bad["citation"]["status"] == "citation à ajouter" and "citation à ajouter" in bad["script"]
    # garde-fou éthique
    assert not [e for e in entries if e["topic_id"] == "pb_003"]  # écarté par le garde-fou
    assert all(not e["ethics_flags"] for e in entries if e["slot_type"] == "proven")


def test_exports_and_feedback(env):
    from engine import config, editing, exports, feedback, planner, synthesis

    start = dt.date(2026, 10, 12)
    planner.plan_week(start, 7, use_llm=False, with_references=False)
    paths = exports.export_week(start, start + dt.timedelta(days=6))
    assert paths["markdown"].exists() and '"schema": "content-engine/calendar@1"' in paths["cockpit"].read_text()
    p = exports.export_shooting(start)
    txt = p.read_text()
    assert "Fiche de tournage" in txt and "Setup 1" in txt
    briefs = editing.run(start)
    assert briefs and "AUCUNE MUSIQUE" in Path(briefs[0]).read_text()
    st = feedback.run(mock=True)
    assert st["personal"]["videos"] > 0
    syn = synthesis.run(dt.date(2026, 10, 19))
    assert syn["personal"]["my_stats"]["n_videos"] > 0


def test_ethics_patterns():
    from engine import ethics

    assert ethics.check_text("Gagne de l'argent facile au casino")
    assert ethics.check_text("ajoute une musique tendance")
    assert not ethics.check_text("AUCUNE musique — voix + sound design neutre")
    assert not ethics.check_text("le levier le plus puissant de ton business")
    assert ethics.memory_citation("Le Prophète ﷺ a dit : « ... »")
    assert ethics.memory_citation('The Prophet (pbuh) said: "..."')
    assert ethics.check_text("This is guaranteed easy money") and ethics.check_text("add background music")
    assert not ethics.check_text("NO music — voice + neutral sound design without instruments (whoosh, clicks, text pops)")
    assert not ethics.check_text("leverage your skills with AI") and ethics.check_text("take a personal loan")
    assert ethics.memory_citation("Comme dit la sourate Al-Talaq verset 3")
    assert not ethics.memory_citation("Il y a un verset qui m'a marqué : {citation}. Depuis, je bosse autrement.")


def test_llm_path_with_fake_llm(env, monkeypatch):
    """Chemin LLM (sans réseau) : réponse simulée, garde-fou éthique, citations, zéro musique."""
    from engine import llm, planner

    calls = {"n": 0}

    def fake_complete_json(system, user, max_tokens=None, vision=False):
        calls["n"] += 1
        assert "AUCUNE musique" in system and "IDENTITÉ" in system
        base = {"hooks": ["Hook A", "Hook B"], "text_hook": "T", "visual_hook": "V", "script": "Jour {jour}. " * 20,
                "cta": "Abonne-toi", "cta_type": "follow_series", "setup": "bureau", "shots": ["A-roll"], "principles": ["D1"]}
        items = [dict(base, slot=1, format_id="episode_vlog", subject="S1"),
                 dict(base, slot=2, format_id="episode_vlog", subject="S2"),
                 dict(base, slot=3, subject="S3")]
        if "RAPPEL" in user:
            items[1].update(is_rappel=True, theme="tawakkul", script="Avant {citation} après",
                            citation_candidates=[{"type": "quran", "ref": "65:3", "expected_keywords": ["confiance"]}])
        if calls["n"] == 1:  # 1re réponse non conforme → doit être rejetée puis régénérée
            items[0]["subject"] = "Mets une musique tendance"
        return items

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    _launch(env, monkeypatch, dt.date(2026, 10, 19))
    entries = planner.plan_week(dt.date(2026, 10, 19), 7, use_llm=True, with_references=False)
    assert len(entries) == 21 and all(e["source"] == "llm" for e in entries)
    assert calls["n"] == 8  # 7 jours + 1 régénération
    assert not any(e["ethics_flags"] for e in entries)
    r = [e for e in entries if e["is_rappel"]]
    assert len(r) == 2 and r[0]["citation"]["status"] == "À VÉRIFIER"
    assert entries[0]["episode_label"] == "Jour 1/90" and "Jour 1." in entries[0]["script"]


def test_challenge_day_bounds(env, monkeypatch):
    """start_date null = pas de défi ; sinon actif seulement du Jour 1 au dernier jour."""
    assert env.challenge_start is None and env.challenge_day(dt.date(2026, 10, 19)) is None
    _launch(env, monkeypatch, dt.date(2026, 10, 19))
    assert env.challenge_day(dt.date(2026, 10, 18)) is None
    assert env.challenge_day(dt.date(2026, 10, 19)) == 1
    assert env.challenge_day(dt.date(2027, 1, 16)) == 90 and env.challenge_day(dt.date(2027, 1, 17)) is None


def test_calendar_without_challenge(env):
    """Défi pas lancé : aucune mention du défi, sujets « Jour X » de la banque écartés, rappels toujours là."""
    from engine import challenge, ethics, planner

    entries = planner.plan_week(dt.date(2026, 10, 19), 7, use_llm=False, with_references=False)
    assert len(entries) == 7 * 3
    assert all(e["episode_label"] is None and e["day_number"] is None for e in entries)
    assert not [e for e in entries if e["topic_id"] == "pb_001"]  # sujet de lancement du défi
    assert all(not challenge.mentions(e) and not e["challenge_flags"] for e in entries)
    assert all(not set(e["principles"]) & challenge.CHALLENGE_PRINCIPLES for e in entries)
    assert all(e["format"]["name"] == "Épisode documentaire" for e in entries if e["format"]["id"] == "episode_vlog")
    assert all(e["edit_template"]["music"] == ethics.music_rule() for e in entries)
    rappels = [e for e in entries if e["is_rappel"]]
    assert {e["weekday"] for e in rappels} == {"jeudi", "dimanche"}
    assert any(e["citation"]["status"] == "À VÉRIFIER" for e in rappels)


def test_challenge_starting_mid_week(env, monkeypatch):
    from engine import planner

    _launch(env, monkeypatch, dt.date(2026, 10, 22))
    entries = planner.plan_week(dt.date(2026, 10, 19), 7, use_llm=False, with_references=False)
    before = [e for e in entries if e["date"] < "2026-10-22"]
    assert before and all(e["episode_label"] is None for e in before)
    assert next(e for e in entries if e["date"] == "2026-10-22")["episode_label"] == "Jour 1/90"


def test_mentions_detector():
    from engine import challenge

    assert challenge.mentions({"subject": "Day 3 mistake: I polished"})
    assert challenge.mentions({"script": "Day 4 of 90. Today..."}) and challenge.mentions({"cta": "Follow the challenge"})
    assert challenge.mentions({"hooks": ["Duel Day 2: hype or truth?"]}) and challenge.mentions({"x": "Jour {jour}/90"})
    assert not challenge.mentions({"script": "I review it on day one, day three, day seven."})
    assert not challenge.mentions({"reference_query": "90 day challenge", "principles": ["D1"]})
    # notes internes d'un format (« sans défi ni compte à rebours ») : pas une mention ; le texte à l'écran, si
    assert not challenge.format_mentions({"adaptation": "sans défi ni compte à rebours", "edit_template": {"on_screen_text": "timer"}})
    assert challenge.format_mentions({"edit_template": {"on_screen_text": "'Day {jour}/90' top left"}})
    assert not challenge.format_mentions({"edit_template": {"on_screen_text": "'Day {jour}/90' top left"},
                                          "no_challenge": {"edit_template": {"on_screen_text": "timer"}}})


def test_llm_without_challenge_rejects_day_counter(env, monkeypatch):
    """Défi pas lancé : consigne explicite au LLM, et une sortie « Day X/90 » est rejetée puis régénérée."""
    from engine import llm, planner

    prompts = []

    def fake_complete_json(system, user, max_tokens=None, vision=False):
        prompts.append(user)
        base = {"hooks": ["Hook A", "Hook B"], "text_hook": "T", "visual_hook": "V", "script": "Real day. " * 20,
                "cta": "Follow for the next one", "cta_type": "soft", "setup": "bureau", "shots": ["A-roll"],
                "principles": ["D1", "S3"]}
        items = [dict(base, slot=i, format_id="episode_vlog", subject=f"S{i}") for i in (1, 2, 3)]
        if "RAPPEL" in user:
            items[1].update(is_rappel=True, theme="tawakkul", script="Avant {citation} après",
                            citation_candidates=[{"type": "quran", "ref": "65:3", "expected_keywords": ["confiance"]}])
        if len(prompts) == 1:
            items[0]["subject"] = "Day 3/90: the first week of the challenge"
        return items

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    entries = planner.plan_week(dt.date(2026, 10, 19), 7, use_llm=True, with_references=False)
    assert len(entries) == 21 and all(e["source"] == "llm" for e in entries)
    assert len(prompts) == 8 and all("DÉFI 90 JOURS NON LANCÉ" in p for p in prompts)
    assert all(e["episode_label"] is None and not e["challenge_flags"] and "D1" not in e["principles"] for e in entries)


def test_real_video_analysis_path(env, monkeypatch, tmp_path):
    """Vidéo locale (non mock) : frames ffmpeg + classification LLM simulée + JSON de sortie."""
    import shutil
    import subprocess

    from engine import analysis, db, llm

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg absent")
    vid = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=24:size=320x568:rate=15",
                    "-f", "lavfi", "-i", "anullsrc", "-t", "24", "-shortest", str(vid)], check=True)
    monkeypatch.setattr(analysis, "transcribe", lambda p: {"text": "Stop", "segments": [{"start": 0, "end": 1, "text": "Stop doing this."}], "backend": "fake"})
    monkeypatch.setattr(analysis, "ANALYSES_DIR", tmp_path / "an")
    monkeypatch.setattr(analysis, "DATA_DIR", tmp_path)
    monkeypatch.setattr(llm, "available", lambda: True)
    seen = {}

    def fake(system, content, max_tokens=None, vision=False):
        seen["images"] = sum(1 for c in content if c["type"] == "image")
        return {"hook_text": "Stop doing this.", "hook_type": "contrarian", "visual_format": "talking_head", "script_structure": "myth_reality",
                "cta_type": "follow", "relies_on_music": False, "principles": ["H-V2"]}

    monkeypatch.setattr(llm, "complete_json", fake)
    with db.session() as c:
        c.execute("INSERT INTO accounts(platform, handle, owner, category) VALUES ('instagram','x','personal','niche')")
        c.execute("INSERT INTO videos(account_id, platform, external_id, url, views, outlier_score, is_outlier, media_path, is_mock) "
                  "VALUES (1,'instagram','real1','https://x',1000,5,1,?,0)", (str(vid),))
        v = c.execute("SELECT v.*, a.handle, a.owner, a.category, a.niche_label FROM videos v JOIN accounts a ON a.id=v.account_id").fetchone()
        a = analysis.analyze_video(c, v)
    assert a["method"] == "llm" and a["hook_type"] == "contrarian"
    assert seen["images"] == len(analysis.frame_times(24.0)) == 7  # 0,1,3,5,10,20 + fin
    assert (tmp_path / "an" / "instagram_real1.json").exists()


def test_english_citations(monkeypatch):
    from engine import config
    from engine.sources import citations

    monkeypatch.setitem(config.settings().raw, "language", "en")
    c = citations.resolve([{"type": "quran", "ref": "65:3", "expected_keywords": ["relies", "sufficient"]}])
    assert c and c["lang"] == "en" and "Saheeh" in c["reference_label"]
    h = citations.resolve([{"type": "hadith", "collection": "bukhari", "number": 1, "expected_keywords": ["intention"]}])
    spoken = citations.spoken_text(h)
    assert spoken.startswith('"') and "Narrated" not in spoken and "no. 1" in spoken
    assert citations.missing_text("tawakkul").startswith("[citation to add")


def test_browser_extractors():
    """Formats JSON connus (web) d'Instagram et TikTok → items normalisés."""
    from engine.browser.extract import instagram_items, tiktok_items

    ig = {"data": {"xdt_api__v1__clips__user__connection_v2": {"edges": [{"node": {"media": {
        "code": "C1abc", "play_count": 120000, "like_count": 5000, "comment_count": 80, "taken_at": 1760000000,
        "video_duration": 41.2, "caption": {"text": "Day 3 of 90 #medschool"}, "user": {"username": "someone"},
        "video_versions": [{"url": "https://cdn/x.mp4"}]}}}]}}}
    it = instagram_items(ig)[0]
    assert it["external_id"] == "C1abc" and it["views"] == 120000 and it["author"] == "someone"
    assert it["url"] == "https://www.instagram.com/reel/C1abc/" and it["caption"].startswith("Day 3")
    tt = {"itemList": [{"id": "7300000000000000001", "desc": "How I book calls from DMs", "createTime": 1760000000,
                        "author": {"uniqueId": "coachx"}, "authorStats": {"followerCount": 20000},
                        "stats": {"playCount": 450000, "diggCount": 20000, "commentCount": 300, "shareCount": 900, "collectCount": 1200},
                        "video": {"duration": 38, "playAddr": "https://v/x"}}]}
    t = tiktok_items(tt)[0]
    assert t["views"] == 450000 and t["author_followers"] == 20000 and "/@coachx/video/" in t["url"]


def test_scout_save_discovery(env):
    from engine import db
    from engine.browser import scout

    st = scout.save([
        {"platform": "tiktok", "external_id": "1", "url": "u1", "caption": "AI agent that books calls from DMs for coaches",
         "views": 400000, "author": "coachx", "author_followers": 20000},
        {"platform": "tiktok", "external_id": "2", "url": "u2", "caption": "funny cat", "views": 9e6, "author": "cats",
         "author_followers": 1000},
    ])
    assert st == {"saved": 1, "relevant": 1, "outliers": 1}
    with db.session() as c:
        r = c.execute("SELECT a.owner, a.category, v.outlier_score FROM videos v JOIN accounts a ON a.id=v.account_id").fetchone()
    assert r["owner"] == "personal" and r["category"] == "discovery" and r["outlier_score"] == 20.0


def test_ig_auth_flow(tmp_path, monkeypatch):
    """OAuth Instagram Login : capture locale du code, échanges (simulés), enregistrement dans .env."""
    import threading
    import urllib.parse
    import urllib.request

    from engine import ig_auth

    monkeypatch.setattr(ig_auth, "ENV_PATH", tmp_path / ".env")
    for k, v in {"IG_APP_ID": "1", "IG_APP_SECRET": "s", "IG_REDIRECT_URI": "http://localhost:8799/cb"}.items():
        monkeypatch.setenv(k, v)

    def fake_open(url):
        state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
        threading.Timer(0.3, lambda: urllib.request.urlopen(f"http://localhost:8799/cb?code=ABC&state={state}")).start()

    monkeypatch.setattr(ig_auth.webbrowser, "open", fake_open)

    class R:
        def __init__(self, d):
            self.d, self.status_code = d, 200

        def json(self):
            return self.d

        def raise_for_status(self):
            pass

    monkeypatch.setattr(ig_auth.requests, "post", lambda *a, **k: R({"access_token": "short", "user_id": 42}))
    monkeypatch.setattr(ig_auth.requests, "get", lambda url, **k: R(
        {"access_token": "LONGLIVEDTOKEN123", "expires_in": 5184000} if "access_token" in url else {"user_id": "1789", "username": "createur"}))
    assert ig_auth.connect("personal")
    env_txt = (tmp_path / ".env").read_text()
    assert "IG_PERSONAL_USER_ID=1789" in env_txt and "IG_PERSONAL_TOKEN=LONGLIVEDTOKEN123" in env_txt
    assert "IG_GRAPH_HOST=graph.instagram.com" in env_txt


def test_ig_auth_dashboard_flow(tmp_path, monkeypatch):
    from engine import ig_auth

    monkeypatch.setattr(ig_auth, "ENV_PATH", tmp_path / ".env")
    for k, v in {"IG_APP_ID": "1", "IG_APP_SECRET": "s", "IG_REDIRECT_URI": "https://localhost:8765/callback"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(ig_auth, "_instagram_tokens", lambda code: {"token": "TOK" + code, "user_id": "9", "username": "yns", "expires": "2026-12-17"})
    b = ig_auth.begin("personal")
    assert "instagram.com/oauth/authorize" in b["url"] and "client_id=1" in b["url"]
    r = ig_auth.complete(f"https://localhost:8765/callback?code=XYZ&state={b['state']}#_")
    assert r["ok"] and "IG_PERSONAL_TOKEN=TOKXYZ" in (tmp_path / ".env").read_text()
    with pytest.raises(ValueError):
        ig_auth.complete(f"https://localhost:8765/callback?code=XYZ&state={b['state']}")  # state consommé


def test_negated_promises_are_honest():
    from engine import ethics
    assert not ethics.check_text("Il n'y a pas de résultats garantis.")
    assert not ethics.check_text("Ce n'est pas de l'argent facile.")
    assert ethics.check_text("Je te garantis 10k en 30 jours.")
    assert ethics.check_text("C'est de l'argent facile.")
