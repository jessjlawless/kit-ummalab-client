"""Données mock réalistes (distribution log-normale des vues + quelques outliers).
Déterministe par handle pour des tests reproductibles. Marquées is_mock=1 en base."""
from __future__ import annotations

import datetime as dt
import hashlib
import random

# (hook, format visuel, structure, cta), sert aussi à l'analyse mock
MOCK_HOOKS = [
    ("I made $10,000 in 30 days as a full-time student. Here's exactly how.", "talking_head_broll", "case_study", "follow"),
    ("Stop sending this DM to your leads.", "green_screen", "myth_reality", "comment_keyword"),
    ("If you're a coach with under 10k followers, watch this.", "talking_head", "list_steps", "comment_keyword"),
    ("Day 12 of trying to make more than a doctor.", "pov_vlog", "day_in_life", "follow_series"),
    ("Nobody talks about this part of running a business at 21.", "talking_head_broll", "story", "follow"),
    ("3 messages that booked 40 calls last month.", "screen_record", "list_steps", "comment_keyword"),
    ("This is what $0 to $5k looks like. No filter.", "pov_vlog", "before_after", "follow_series"),
    ("I asked 100 coaches why they don't follow up. Here's what they said.", "talking_head", "case_study", "save"),
    ("You're losing 80% of your leads in the first message.", "split_screen", "myth_reality", "comment_keyword"),
    ("Rating my subscribers' sales DMs.", "screen_record", "list_steps", "comment_keyword"),
    ("What I eat in a day as a med student building a business.", "pov_vlog", "day_in_life", "follow"),
    ("The 2-line message that closes more than any sales call.", "text_over_broll", "tutorial", "comment_keyword"),
    ("Watch me try to get my first client in 24 hours.", "pov_vlog", "story", "follow_series"),
    ("Everyone says post more. That's terrible advice.", "talking_head", "rant_opinion", "share"),
    ("POV: you hired an AI setter and woke up to 6 booked calls.", "text_over_broll", "before_after", "dm"),
    ("Week 3 progress check: here are the real numbers.", "talking_head_broll", "case_study", "follow_series"),
    ("I tried the 5am routine for 30 days. Honest results.", "pov_vlog", "before_after", "follow"),
    ("Recipe for a DM that converts: 4 ingredients.", "talking_head_broll", "tutorial", "comment_keyword"),
]


def _rng(handle: str, platform: str) -> random.Random:
    seed = int(hashlib.sha1(f"{platform}:{handle}".encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def fetch(platform: str, handle: str, since: dt.datetime, limit: int) -> list[dict]:
    rng = _rng(handle, platform)
    base = rng.lognormvariate(10.5, 1.0)  # médiane ~36k vues, large dispersion entre comptes
    n = min(limit, rng.randint(18, 40))
    now = dt.datetime.now().replace(microsecond=0)
    out = []
    for i in range(n):
        posted = now - dt.timedelta(days=rng.uniform(0.5, 29.5))
        views = base * rng.lognormvariate(0, 0.55)
        if rng.random() < 0.10:  # ~10 % d'outliers
            views *= rng.uniform(3.2, 12)
        hook, *_ = rng.choice(MOCK_HOOKS)
        views = int(views)
        out.append({
            "external_id": f"mock_{platform}_{handle}_{i:03d}",
            "url": f"https://www.{platform}.com/{handle}/mock{i:03d}",
            "video_url": None,
            "caption": f"{hook}\n\n#business #entrepreneur",
            "posted_at": posted.isoformat(),
            "duration_s": round(rng.uniform(22, 75), 1),
            "views": views,
            "likes": int(views * rng.uniform(0.02, 0.08)),
            "comments": int(views * rng.uniform(0.001, 0.01)),
            "shares": int(views * rng.uniform(0.001, 0.02)),
            "saves": int(views * rng.uniform(0.002, 0.02)),
        })
    return out
