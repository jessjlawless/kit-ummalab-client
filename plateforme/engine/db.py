"""SQLite : schéma et helpers. Tables : accounts, videos, analyses, my_videos, calendar
(+ syntheses, format_status, hook_breakdowns, chat_conversations, chat_messages, runs)."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY,
    platform        TEXT NOT NULL,              -- instagram | tiktok
    handle          TEXT NOT NULL,
    owner           TEXT NOT NULL,              -- personal (pour quel compte on l'observe)
    category        TEXT NOT NULL,              -- niche | other
    niche_label     TEXT,
    followers       INTEGER,
    median_views    REAL,
    last_scraped_at TEXT,
    last_backend    TEXT,
    UNIQUE(platform, handle, owner)
);

CREATE TABLE IF NOT EXISTS videos (
    id            INTEGER PRIMARY KEY,
    account_id    INTEGER NOT NULL REFERENCES accounts(id),
    platform      TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    url           TEXT,
    video_url     TEXT,                         -- URL directe du mp4 si fournie par le backend
    caption       TEXT,
    posted_at     TEXT,
    duration_s    REAL,
    views         INTEGER,
    likes         INTEGER,
    comments      INTEGER,
    shares        INTEGER,
    saves         INTEGER,
    scraped_at    TEXT,
    outlier_score REAL,
    is_outlier    INTEGER DEFAULT 0,
    media_path    TEXT,
    is_mock       INTEGER DEFAULT 0,
    UNIQUE(account_id, external_id)
);

CREATE TABLE IF NOT EXISTS analyses (
    id               INTEGER PRIMARY KEY,
    video_id         INTEGER NOT NULL UNIQUE REFERENCES videos(id),
    hook_text        TEXT,
    hook_type        TEXT,
    visual_format    TEXT,
    script_structure TEXT,
    cta_type         TEXT,
    principles       TEXT,                      -- JSON list d'IDs de la skill
    data             TEXT NOT NULL,             -- JSON complet
    method           TEXT,                      -- llm | heuristic | mock
    created_at       TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS my_videos (
    id                INTEGER PRIMARY KEY,
    account           TEXT NOT NULL,            -- personal
    platform          TEXT NOT NULL DEFAULT 'instagram',
    external_id       TEXT NOT NULL,
    url               TEXT,
    caption           TEXT,
    posted_at         TEXT,
    calendar_id       INTEGER REFERENCES calendar(id),
    format_id         TEXT,
    views             INTEGER,
    reach             INTEGER,
    likes             INTEGER,
    comments          INTEGER,
    shares            INTEGER,
    saves             INTEGER,
    avg_watch_time_s  REAL,
    total_watch_time_s REAL,
    raw               TEXT,
    is_mock           INTEGER DEFAULT 0,
    updated_at        TEXT,
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS calendar (
    id          INTEGER PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,           -- ex: PB-2026-10-19-1
    week_start  TEXT NOT NULL,
    date        TEXT NOT NULL,
    account     TEXT NOT NULL,
    slot_index  INTEGER NOT NULL,
    slot_type   TEXT NOT NULL,                  -- proven | test
    format_id   TEXT,
    topic_id    TEXT,
    day_number  INTEGER,
    setup       TEXT,
    data        TEXT NOT NULL,                  -- JSON complet de la vidéo planifiée
    source      TEXT,                           -- llm | bank
    status      TEXT DEFAULT 'planned',         -- planned | filmed | published
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(date, account, slot_index)
);

CREATE TABLE IF NOT EXISTS syntheses (
    id          INTEGER PRIMARY KEY,
    week_start  TEXT NOT NULL,
    account     TEXT NOT NULL,
    data        TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(week_start, account)
);

CREATE TABLE IF NOT EXISTS format_status (
    account     TEXT NOT NULL,
    format_id   TEXT NOT NULL,
    status      TEXT NOT NULL,                  -- proven | test | retired
    origin      TEXT,                           -- bank | promoted | llm
    data        TEXT,                           -- JSON du format (pour les formats promus)
    updated_at  TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (account, format_id)
);

CREATE TABLE IF NOT EXISTS hook_breakdowns (   -- Hook Lab : hook décortiqué sur 4 canaux
    id             INTEGER PRIMARY KEY,
    video_id       INTEGER NOT NULL UNIQUE REFERENCES videos(id),
    creator        TEXT,
    strong_channel TEXT,                        -- verbal | textuel | visuel | auditif
    hook_strength  REAL,
    replicability  REAL,
    success_driver TEXT,
    data           TEXT NOT NULL,               -- JSON complet (4 canaux, mesures audio, template, adaptations)
    creator_note    TEXT,                        -- JSON : annotation du créateur (tableau importé)
    method         TEXT,                        -- llm | measures
    created_at     TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS chat_conversations (   -- chat du dashboard : 1 conversation = 1 session Claude Code
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    claude_session_id TEXT,                     -- pour `claude -p --resume`
    created_at        TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY,
    conv_id     TEXT NOT NULL REFERENCES chat_conversations(id),
    role        TEXT NOT NULL,                  -- user | assistant
    content     TEXT NOT NULL,
    tools       TEXT,                           -- JSON : actions faites pendant la réponse
    is_error    INTEGER DEFAULT 0,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    command     TEXT,
    step        TEXT,
    status      TEXT,
    detail      TEXT,
    at          TEXT DEFAULT (datetime('now','localtime'))
);
"""


def connect() -> sqlite3.Connection:
    path = settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # lectures/écritures concurrentes (dashboard + pipeline)
    conn.executescript(SCHEMA)
    for col in ("eng_comment_rel REAL", "eng_share_rel REAL", "thumb_url TEXT"):  # migrations légères
        try:
            conn.execute(f"ALTER TABLE videos ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def dumps(obj: Any) -> str:
    # jamais de tiret long stocké (« a — b » → « a, b ») : tout ce qui est affiché ou exporté sort d'ici
    return re.sub(r"\s*[\u2014\u2013]\s*", ", ", json.dumps(obj, ensure_ascii=False, default=str))


def loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return default


def log_run(conn: sqlite3.Connection, command: str, step: str, status: str, detail: str = "") -> None:
    conn.execute("INSERT INTO runs(command, step, status, detail) VALUES (?,?,?,?)", (command, step, status, detail[:2000]))
