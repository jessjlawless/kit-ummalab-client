"""Module 2, Outliers. score = vues / médiane des vues du compte (jamais de vues brutes).
On garde si score >= outliers.threshold (défaut 3)."""
from __future__ import annotations

import statistics

from . import db, log
from .config import settings

logger = log.get("outliers")


def run() -> dict:
    s = settings()
    threshold = float(s.get("outliers.threshold", 3.0))
    min_n = int(s.get("outliers.min_videos_per_account", 5))
    stats = {"accounts": 0, "scored": 0, "outliers": 0, "skipped_small": 0}
    with db.session() as conn:
        for acc in conn.execute("SELECT id, handle FROM accounts").fetchall():
            rows = conn.execute(
                "SELECT id, views FROM videos WHERE account_id=? AND views IS NOT NULL AND views > 0", (acc["id"],)
            ).fetchall()
            if len(rows) < min_n:
                stats["skipped_small"] += 1
                continue
            med = statistics.median(r["views"] for r in rows)
            conn.execute("UPDATE accounts SET median_views=? WHERE id=?", (med, acc["id"]))
            for r in rows:
                score = r["views"] / med if med else 0
                conn.execute(
                    "UPDATE videos SET outlier_score=?, is_outlier=? WHERE id=?",
                    (round(score, 3), int(score >= threshold), r["id"]),
                )
                stats["scored"] += 1
                stats["outliers"] += int(score >= threshold)
            # engagement relatif (signal de conversion) : taux de commentaires / partages vs médiane du compte
            for col, field in (("comments", "eng_comment_rel"), ("shares", "eng_share_rel")):
                rates = {r["id"]: r[col] / r["views"] for r in conn.execute(
                    f"SELECT id, views, {col} FROM videos WHERE account_id=? AND views>0 AND {col} IS NOT NULL", (acc["id"],))}
                if len(rates) >= min_n:
                    m = statistics.median(rates.values()) or None
                    for vid, rate in rates.items():
                        conn.execute(f"UPDATE videos SET {field}=? WHERE id=?", (round(rate / m, 2) if m else None, vid))
            stats["accounts"] += 1
        db.log_run(conn, "outliers", "outliers", "ok", db.dumps(stats))
    logger.info("outliers (seuil x%.1f) : %s", threshold, stats)
    return stats


def top(conn, owner: str, category: str, limit: int = 50):
    return conn.execute(
        """SELECT v.*, a.handle, a.owner, a.category, a.niche_label FROM videos v
           JOIN accounts a ON a.id = v.account_id
           WHERE a.owner=? AND a.category=? AND v.is_outlier=1
           ORDER BY v.outlier_score DESC LIMIT ?""",
        (owner, category, limit),
    ).fetchall()
