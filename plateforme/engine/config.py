"""Chargement de la configuration (YAML + .env) et chemins du projet."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
SKILL_PATH = ROOT / ".claude" / "skills" / "content-principles" / "SKILL.md"

ACCOUNT_IDS = ("personal",)


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env, override=False)
    except ImportError:  # parsing minimal si python-dotenv absent
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str | None = None) -> str | None:
    """Variable d'environnement ; chaîne vide = absente."""
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Settings:
    raw: dict
    accounts: dict[str, dict] = field(default_factory=dict)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def db_path(self) -> Path:
        return ROOT / self.get("db_path", "data/engine.db")

    @property
    def challenge_start(self) -> dt.date | None:
        """Date du Jour 1 du défi. None = pas encore lancé (start_date: null) → aucun contenu « Day X »."""
        v = self.get("challenge.start_date")
        if isinstance(v, dt.date):
            return v
        if v in (None, "", "null", "None"):
            return None
        return dt.date.fromisoformat(str(v))

    def challenge_day(self, day: dt.date) -> int | None:
        """N° du jour du défi pour `day`, ou None hors défi (pas lancé, avant le Jour 1, après le dernier jour)."""
        start = self.challenge_start
        if start is None:
            return None
        n = (day - start).days + 1
        return n if 1 <= n <= int(self.get("challenge.length_days", 90)) else None


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        raw = load_yaml(CONFIG_DIR / "engine.yaml") or {}
        accounts = {}
        for acc_id in ACCOUNT_IDS:
            p = CONFIG_DIR / "accounts" / f"{acc_id}.yaml"
            if p.exists():
                accounts[acc_id] = load_yaml(p) or {}
        _settings = Settings(raw=raw, accounts=accounts)
    return _settings


def load_content_bank(account: str) -> dict:
    p = CONFIG_DIR / "content_bank" / f"{account}.yaml"
    if not p.exists():
        return {"account": account, "proven_formats": [], "topics": [], "test_formats": []}
    return load_yaml(p) or {}
