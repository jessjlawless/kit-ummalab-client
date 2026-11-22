import pytest


@pytest.fixture(autouse=True)
def islamic_rules(request, monkeypatch):
    """Les tests historiques couvrent le mode « règles islamiques » au complet ; test_islamic_off.py le désactive."""
    from engine import ethics

    ethics._patterns.cache_clear()
    monkeypatch.setitem(ethics.identity(), "islamic_rules", request.module.__name__ != "test_islamic_off")
    yield
    ethics._patterns.cache_clear()


@pytest.fixture(autouse=True)
def no_user_campaigns(request, monkeypatch, tmp_path):
    """Les vraies campagnes de config/campaigns ne doivent pas déborder sur les semaines fixes des tests.
    test_campaigns.py gère lui-même son dossier."""
    if request.module.__name__ == "test_campaigns":
        yield
        return
    from engine import campaigns

    monkeypatch.setattr(campaigns, "DIR", tmp_path / "campaigns")
    campaigns.reload()
    yield
    campaigns.reload()
