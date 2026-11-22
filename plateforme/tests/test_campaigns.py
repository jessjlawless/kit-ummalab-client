"""Campagnes : la semaine suit le type/l'angle imposés par config/campaigns/*.yaml (fallback sans LLM)."""
import datetime as dt

import pytest

CAMP = """
id: test-camp
account: personal
start: 2026-10-19
end: 2026-10-20
title: "Test"
brief: "Présentation"
types:
  objection: {name: "Objection", funnel: bofu, setup: bureau, instructions: "court"}
  rappel: {name: "Rappel", funnel: mofu, setup: bureau, theme: honnetete, instructions: "doc"}
  temoignage: {name: "Témoignage client", funnel: bofu, instructions: "n'invente rien"}
features: {booking: "Booke les appels"}
days:
  2026-10-19:
    - {type: temoignage, angle: "Cas client n°1"}
    - {type: rappel}
    - {type: objection, angle: "« C'est trop cher »"}
"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from engine import campaigns, config

    s = config.settings()
    monkeypatch.setitem(s.raw, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setitem(s.raw, "llm", {**s.raw.get("llm", {}), "provider": "none"})
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "out")
    d = tmp_path / "campaigns"
    d.mkdir()
    (d / "test.yaml").write_text(CAMP, encoding="utf-8")
    monkeypatch.setattr(campaigns, "DIR", d)
    campaigns.reload()
    yield s
    campaigns.reload()


def test_campaign_days_follow_the_lineup(env):
    from engine import campaigns, planner

    assert campaigns.for_day("personal", dt.date(2026, 10, 21)) is None
    entries = planner.plan_week(dt.date(2026, 10, 19), days=1, use_llm=False, accounts=["personal"], with_references=False)
    assert [e["format"]["id"] for e in entries] == ["campaign:temoignage", "campaign:rappel", "campaign:objection"]
    assert [e["slot_index"] for e in entries] == [1, 2, 3]
    temo, rappel, obj = entries
    assert temo["campaign"]["angle"] == "Cas client n°1" and temo["funnel_stage"] == "bofu"
    assert "[à écrire" in temo["script"]                       # sans LLM : fiche à compléter, rien d'inventé
    assert rappel["is_rappel"] and rappel["rappel_theme"] == "honnetete" and rappel["citation"]
    assert obj["hooks"][0]["verbal"] == "C'est trop cher"


def test_regen_keeps_campaign_slot(env):
    from engine import planner

    planner.plan_week(dt.date(2026, 10, 19), days=1, use_llm=False, accounts=["personal"], with_references=False)
    e = planner.regenerate("PB-2026-10-19-3", "plus court")
    assert e["code"] == "PB-2026-10-19-3" and e["format"]["id"] == "campaign:objection"
    assert e["campaign"]["angle"] == "« C'est trop cher »" and e["regen_count"] == 1
