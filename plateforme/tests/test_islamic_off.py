"""Règles islamiques désactivées (défaut de la version vierge) : pas de rappels, musique libre, garde-fous de base."""
import datetime as dt

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    import yaml
    from pathlib import Path
    from engine import config, formats, planner

    bank = yaml.safe_load((Path(__file__).parent / "fixtures" / "bank_personal.yaml").read_text())
    loader = lambda acc: bank
    monkeypatch.setattr(planner, "load_content_bank", loader)
    monkeypatch.setattr(formats, "load_content_bank", loader)
    s = config.settings()
    monkeypatch.setitem(s.raw, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setitem(s.raw, "llm", {**s.raw.get("llm", {}), "provider": "none"})
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "out")
    yield s


def test_guards_without_islamic_rules():
    from engine import ethics

    assert not ethics.islamic()
    assert ethics.check_text("I took a loan and some background music") == []          # riba / musique : hors périmètre
    assert ethics.check_text("I guarantee results")                                      # exagération : toujours active
    assert "{citation}" not in ethics.absolute_rules() and "honnête" in ethics.absolute_rules()
    assert ethics.enforce_no_music({"music": "lo-fi", "pacing": "on the beat"})["pacing"] == "on the beat"


def test_week_without_rappels(env):
    from engine import ethics, planner

    entries = planner.plan_week(dt.date(2026, 10, 19), 7, use_llm=False, with_references=False)
    assert len(entries) == 7 * 3
    assert not [e for e in entries if e["is_rappel"]]
    assert all(e["edit_template"]["music"] == ethics.music_rule() for e in entries)
    assert not [e for e in entries if e["ethics_flags"]]
