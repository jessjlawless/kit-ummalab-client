from __future__ import annotations

import datetime as dt
import random
import time
from typing import Callable, TypeVar

from .. import log
from ..config import settings

logger = log.get("scraper")
T = TypeVar("T")


def polite_sleep(scale: float = 1.0) -> None:
    s = settings()
    time.sleep(random.uniform(float(s.get("scraper.min_delay_s", 4)), float(s.get("scraper.max_delay_s", 12))) * scale)


def with_retries(fn: Callable[[], T], what: str) -> T:
    retries = int(settings().get("scraper.max_retries", 3))
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            wait = (2 ** attempt) * 5 + random.uniform(0, 5)
            logger.warning("%s : échec %d/%d (%s), retry dans %.0fs", what, attempt, retries, str(e)[:150], wait)
            if attempt < retries:
                time.sleep(wait)
    raise RuntimeError(f"{what} : abandon après {retries} essais : {last}")


def iso(ts) -> str | None:
    """Normalise timestamp unix / ISO en ISO local naïf."""
    if ts in (None, ""):
        return None
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    if isinstance(ts, dt.datetime):
        return ts.replace(tzinfo=None).isoformat(timespec="seconds")
    s = str(ts).replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(s).replace(tzinfo=None).isoformat(timespec="seconds")
    except ValueError:
        return None


def to_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
