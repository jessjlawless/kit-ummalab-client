"""engine report, état du système (données, mocks, calendrier, perfs, formats) → output/report.md"""
from __future__ import annotations

import datetime as dt

from . import db
from .config import OUTPUT_DIR


def build() -> str:
    today = dt.date.today().isoformat()
    L = [f"# Content Engine, rapport du {dt.datetime.now():%d/%m/%Y %H:%M}", ""]
    with db.session() as conn:
        q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
        acc = q("SELECT owner, category, COUNT(*) n, SUM(last_backend='mock') mock FROM accounts GROUP BY 1,2")
        L += ["## Comptes de référence", ""] + [f"- {r['owner']} / {r['category']} : {r['n']} comptes ({r['mock'] or 0} en mock)" for r in acc]
        v = q("SELECT COUNT(*) n, SUM(is_mock) m, SUM(is_outlier) o FROM videos")[0]
        an = q("SELECT method, COUNT(*) n FROM analyses GROUP BY 1")
        L += ["", "## Données", "", f"- Vidéos scrapées : {v['n']} (mock : {v['m'] or 0}) · outliers : {v['o'] or 0}",
              "- Analyses : " + (", ".join(f"{r['method']} {r['n']}" for r in an) or "aucune")]
        top = q("""SELECT v.url, v.outlier_score, a.handle, a.owner, v.is_mock FROM videos v JOIN accounts a ON a.id=v.account_id
                   WHERE v.is_outlier=1 ORDER BY v.outlier_score DESC LIMIT 8""")
        L += ["", "## Top outliers", ""] + [f"- x{r['outlier_score']} @{r['handle']} ({r['owner']}){' [mock]' if r['is_mock'] else ''} {r['url']}" for r in top]
        cal = q("SELECT account, status, COUNT(*) n, MIN(date) d1, MAX(date) d2 FROM calendar GROUP BY 1,2")
        L += ["", "## Calendrier", ""] + [f"- {r['account']} · {r['status']} : {r['n']} vidéos ({r['d1']} → {r['d2']})" for r in cal]
        nxt = q("SELECT code, json_extract(data,'$.subject') s FROM calendar WHERE date=? ORDER BY account, slot_index", today)
        L += ["", f"### Aujourd'hui ({today})", ""] + ([f"- `{r['code']}` {r['s']}" for r in nxt] or ["- rien de planifié"])
        flags = q("SELECT code, json_extract(data,'$.ethics_flags') f FROM calendar WHERE json_array_length(json_extract(data,'$.ethics_flags'))>0")
        if flags:
            L += ["", "### ⚠ Garde-fous éthiques à relire", ""] + [f"- `{r['code']}` : {r['f']}" for r in flags]
        cits = q("SELECT code, json_extract(data,'$.citation.status') st, json_extract(data,'$.citation.reference') ref "
                 "FROM calendar WHERE json_extract(data,'$.is_rappel')=1 ORDER BY date")
        if cits:
            L += ["", "### Rappels et citations", ""] + [f"- `{r['code']}` : {r['st']} {r['ref'] or ''}" for r in cits]
        mv = q("SELECT account, COUNT(*) n, SUM(is_mock) m, SUM(calendar_id IS NOT NULL) l, AVG(views) av FROM my_videos GROUP BY 1")
        L += ["", "## Mes vidéos (Graph API)", ""] + ([f"- {r['account']} : {r['n']} vidéos (mock {r['m'] or 0}), {r['l']} liées au calendrier, "
                                                       f"{int(r['av'] or 0)} vues en moyenne" for r in mv] or ["- aucune (token Graph API manquant ?)"])
        fs = q("SELECT * FROM format_status")
        L += ["", "## Formats promus", ""] + ([f"- {r['account']} : {r['format_id']} → {r['status']} ({r['origin']})" for r in fs] or ["- aucun pour l'instant"])
        runs = q("SELECT at, command, step, status, substr(detail,1,120) d FROM runs ORDER BY id DESC LIMIT 12")
        L += ["", "## Derniers runs", ""] + [f"- {r['at']} {r['step']} {r['status']} {r['d']}" for r in runs]
    p = OUTPUT_DIR / "report.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L), encoding="utf-8")
    return str(p)
