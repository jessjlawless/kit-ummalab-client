# MCP local « hadith »

Serveur MCP (stdio) basé sur la [hadith-api de fawazahmed0](https://github.com/fawazahmed0/hadith-api) (CDN jsDelivr, gratuit, sans clé).
Bonus : `get_quran_verse` via api.alquran.cloud (traduction française Hamidullah).

- Déclaré dans `.mcp.json` à la racine → disponible automatiquement dans Claude Code ouvert dans ce dossier.
- Test manuel : `.venv/bin/python mcp/hadith/selftest.py`
- Règles : seuls les hadiths **sahih / hasan** sont `accepted`. Grade absent → refusé, sauf Sahih al-Bukhari / Sahih Muslim (recueils entièrement sahih — voir DECISIONS.md).
- Option : `SUNNAH_API_KEY` dans `.env` (API sunnah.com, sur demande sur leur GitHub) pour recouper les grades.
- Cache : `data/cache/sources/`.
