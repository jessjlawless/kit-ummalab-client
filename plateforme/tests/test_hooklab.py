"""Hook Lab : import du tableau, parsing des liens, mesures audio, sélection par score outlier (sans réseau ni LLM)."""
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    from engine import config, hooklab

    s = config.settings()
    monkeypatch.setitem(s.raw, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setitem(s.raw, "llm", {**s.raw.get("llm", {}), "provider": "none"})
    monkeypatch.setattr(hooklab, "EXTRA_PATH", tmp_path / "hooklab_seeds.yaml")
    monkeypatch.setattr(hooklab, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(hooklab, "OUTPUT_DIR", tmp_path / "out")
    return hooklab


def test_parse_url(lab):
    assert lab._parse_url("https://www.tiktok.com/@jun_yuh/video/7467426008015047982") == ("tiktok", "jun_yuh", "7467426008015047982")
    assert lab._parse_url("https://www.instagram.com/reel/DbLqaO8Bgt2/") == ("instagram", None, "DbLqaO8Bgt2")
    assert lab._parse_url("https://www.youtube.com/shorts/abcdEFG1234") == ("youtube", None, "abcdEFG1234")
    assert lab._parse_url("https://example.com/x") is None


def test_import_xlsx_merges_duplicates(lab, tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, "Lien", "Hook oral", "Hook texte", "Hook visuel", "Hook auditif"])
    ws.append(["MINO LEE", "https://www.instagram.com/reel/AAA/", "oral 1", "texte", None, None])
    ws.append([None, "https://www.instagram.com/reel/AAA/", "oral 2", None, None, None])
    ws.append([None, "https://www.tiktok.com/@x/video/123?q=1", None, None, "visuel", "voix grave"])
    ws.append(["Jun yuh", "pas un lien", None, None, None, None])
    p = tmp_path / "t.xlsx"
    wb.save(p)
    assert lab.import_xlsx(str(p)) == {"links": 2, "new": 2}
    s = {x["url"]: x for x in lab.seeds()}
    assert s["https://www.instagram.com/reel/AAA/"]["note"]["oral"] == "oral 1 / oral 2"
    assert s["https://www.tiktok.com/@x/video/123"]["creator"] == "Mino Lee"
    assert s["https://www.tiktok.com/@x/video/123"]["note"]["auditif"] == "voix grave"
    assert lab.import_xlsx(str(p))["new"] == 0  # idempotent


def test_audio_metrics_detects_speech_start_and_silence(lab, tmp_path):
    # 0-0,5 s silence, 0,5-2 s « voix » (bruit modulé), 2-2,6 s silence, puis ton continu
    f = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "aevalsrc='if(between(t,0.5,2),0.5*sin(2*PI*220*t)*sin(2*PI*3*t),if(gt(t,2.6),0.3*sin(2*PI*440*t),0))':s=16000:d=5",
                    str(f)], check=True)
    words = [{"w": "hello", "start": 0.5, "end": 1.0}, {"w": "world", "start": 1.1, "end": 1.9}]
    m = lab.audio_metrics(str(f), words)
    assert m["speech_start_s"] == 0.5 and m["words_in_hook"] == 2
    assert any(a <= 2.1 and b >= 2.5 for a, b in m["silences"])
    assert m["background_audio"] == "tonal"  # son harmonique pendant les pauses = musique probable
    assert lab.music_verdict(m, "aucune") == "probable"


def test_audio_metrics_noise_is_not_music(lab, tmp_path):
    f = tmp_path / "n.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:a=0.05:r=16000", str(f)], check=True)
    m = lab.audio_metrics(str(f), [{"w": "hi", "start": 0.5, "end": 1.0}])
    assert m["background_audio"] == "bruit/ambiance" and lab.music_verdict(m, "probable") == "aucune"
    assert lab.music_verdict({"background_audio": "indéterminé (parole continue)"}, "aucune") == "indéterminée"


def test_pick_uses_outlier_score_per_creator(lab, monkeypatch):
    from engine import db

    monkeypatch.setattr(lab, "cfg", lambda: {"per_creator": 2, "min_score": 2.0, "max_duration_s": 120, "creators": [
        {"name": "Test", "accounts": [{"platform": "tiktok", "handle": "t1"}]}], "seeds": []})
    with db.session() as c:
        c.execute("INSERT INTO accounts(platform, handle, owner, category) VALUES ('tiktok','t1','hooklab','creator')")
        aid = c.execute("SELECT id FROM accounts").fetchone()[0]
        for i, (score, dur) in enumerate([(5, 30), (1, 30), (9, 400), (3, 20), (2.5, 50)]):
            c.execute("INSERT INTO videos(account_id, platform, external_id, views, outlier_score, duration_s, is_mock) "
                      "VALUES (?,?,?,?,?,?,0)", (aid, "tiktok", f"v{i}", 100, score, dur))
        c.commit()
        picked = lab.pick(c)
        ext = [c.execute("SELECT external_id FROM videos WHERE id=?", (v,)).fetchone()[0] for v, *_ in picked]
    assert ext == ["v0", "v3"]  # score ≥ 2, durée ≤ 120 s, triés par score, 2 max


def test_library_and_export(lab, monkeypatch):
    from engine import db

    with db.session() as c:
        c.execute("INSERT INTO accounts(platform, handle, owner, category) VALUES ('tiktok','t1','hooklab','creator')")
        c.execute("INSERT INTO videos(account_id, platform, external_id, url, views, outlier_score, is_mock) VALUES (1,'tiktok','v1','u',100,4,0)")
        data = {"verbal": {"text": "I only got 100 views"}, "textuel": {"text": "100 views"}, "visuel": {"first_frame": "kitchen"},
                "auditif": {"first_sound": "voix", "music": "aucune"}, "template": "I only got [n] views",
                "adaptations": {"personal": "Day 3/90: I only got 40 views"}}
        c.execute("INSERT INTO hook_breakdowns(video_id, creator, strong_channel, hook_strength, replicability, success_driver, data, method) "
                  "VALUES (1,'Test','textuel',8,9,'technique',?,'llm')", (json.dumps(data),))
        c.commit()
    from engine.config import settings

    s = settings()
    monkeypatch.setitem(s.raw, "challenge", {**s.raw.get("challenge", {}), "start_date": None})
    txt = lab.library_text("personal")
    assert "I only got [n] views" in txt and "Day 3/90" not in txt  # défi pas lancé : adaptation « Day X » retirée
    monkeypatch.setitem(s.raw, "challenge", {**s.raw["challenge"], "start_date": "2026-10-19"})
    assert "Day 3/90" in lab.library_text("personal")
    out = lab.export_xlsx()
    assert Path(out).exists()
