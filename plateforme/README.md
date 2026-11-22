# Content Engine

Système de production de vidéos courtes (Reels, TikTok, Shorts) piloté par IA, pour un créateur.
Objectif : 3 vidéos/jour (2 formats éprouvés + 1 format test emprunté à une autre niche). Le système dit **exactement quoi filmer**.

> **Première fois ?** Lis [GUIDE.md](GUIDE.md) : installation, connexions et utilisation pas à pas. Ce README est la référence technique.

## Démarrage rapide

**Dashboard** (recommandé) : `./bin/engine ui` → http://127.0.0.1:8787 — fiche du jour (plans à cocher, prompteur, brief ChatCut),
semaine, régénérer une vidéo avec Claude, stats, découvertes, ton contexte, comptes scout. N'écoute que sur ta machine.

```bash
./setup.sh                   # installation (une seule fois)
./bin/engine doctor          # vérifie clés, skill, banque, sources
./bin/engine daily --print   # fiche de tournage du jour (génère le calendrier s'il manque)
./bin/engine weekly          # pipeline complet de la semaine
./bin/engine report          # état du système
```

(ou `source .venv/bin/activate` puis `engine …` — installer avec `uv pip install -e .` si besoin.)

## Commandes

| Commande | Ce qu'elle fait |
|---|---|
| `engine weekly [--start AAAA-MM-JJ] [--mock] [--force] [--no-llm]` | scrape → outliers → analyse → synthèse → calendrier 7 j → exports → fiche du jour → briefs ChatCut |
| `engine daily [--date] [--mock] [--print]` | stats Graph API → lien vidéos/calendrier → fiche de tournage → briefs ChatCut |
| `engine ui [--port 8787]` | **dashboard local** (backend = ce moteur + Claude Code) |
| `engine ig-auth [--flow facebook]` | connecte ton compte Instagram (OAuth de ton app Meta) pour les stats |
| `engine report` | `output/report.md` |
| `engine doctor` | diagnostic |
| `engine scrape / outliers / analyze / synthesize / calendar / shooting / stats / edit` | modules individuels |
| `engine plan [--start AAAA-MM-JJ] [--days N] [--account] [--full]` | planning en lecture seule (codes, statut, sujet, hook A) |
| `engine link <media> <code>` | lier manuellement une publication (ex. TikTok `--platform tiktok --views 1234`) |
| `engine login instagram\|tiktok\|youtube` | ouvre Chrome : tu connectes ton compte **scout** dédié (une fois) |
| `engine scout [--platform] [--minutes]` | scrolle les feeds avec les comptes scout : entraîne l'algo + découvre des outliers → `output/discovery/` |
| `engine hooklab [--creator NOM] [--limit N] [--import tableau.xlsx] [--add NOM PLATEFORME HANDLE]` | **Hook Lab** : décortique les hooks des meilleurs créateurs sur 4 canaux (verbal, texte, visuel, auditif) → dashboard + `output/hooklab/hooklab.xlsx` |
| `engine reset-mock` | supprime les données mock |

## Sorties

- `output/shooting/<date>.md` — **fiche de tournage** (vidéos regroupées par décor, hooks A/B, plans à filmer, script, CTA)
- `output/calendar/<lundi>/calendar.md|json` — calendrier de la semaine
- `output/cockpit/latest.json` — export pour l'app Cockpit (schéma : [docs/COCKPIT_EXPORT.md](docs/COCKPIT_EXPORT.md))
- `output/editing/<date>/<code>.md` — brief à coller dans ChatCut (toujours sans musique)
- `output/synthesis/<lundi>/<compte>.md|json` — synthèse hebdo
- `data/analyses/*.json` — analyse par vidéo outlier

## Architecture

```
.claude/skills/content-principles/SKILL.md   Module 0 — principes (hooks, rétention, CTA, identité…) injectés dans tous les prompts
tools/build_principles.py                    récupère/condense les transcriptions YouTube (Hormozi, Kallaway, Galloway, Brock Johnson, Mino Lee)
config/engine.yaml                           seuils, défi, LLM, promotion
config/accounts/personal.yaml                ton compte + comptes de référence (niche + autres niches)
config/content_bank/personal.yaml            banque de contenu (fallback sans Claude) : formats, sujets, formats test, rappels
config/identity.yaml                         identité + règles (honnêteté ; règles islamiques activables : zéro musique, rappels, citations)
engine/scraper/                              Module 1 — apify | browser (compte scout) | instaloader | yt-dlp (TikTok, YouTube Shorts) | mock
engine/browser/                              comptes scout : login manuel, profils en connecté, scout des feeds (Playwright + Chrome)
engine/ui/                                   dashboard local (FastAPI + page unique en JS vanilla, sans build)
config/campaigns/ + engine/campaigns.py      campagnes : type et angle imposés par slot sur une période
engine/chat.py                               Chat du dashboard : conversations = sessions Claude Code headless (ton abonnement)
engine/hooklab.py + config/hooklab.yaml       Hook Lab — meilleurs hooks des créateurs, 4 canaux (Whisper au mot, frames, coupes et mesures audio ffmpeg, Claude vision), réinjectés dans le planner
engine/references.py                         vidéo de référence réelle (qui a marché) pour chaque vidéo planifiée
context/                                     TON contexte (à compléter) injecté dans tous les prompts
engine/outliers.py                           Module 2 — score = vues / médiane du compte, seuil x3
engine/analysis.py                           Module 3 — Whisper (API ou local), frames ffmpeg, Claude vision, classification
engine/synthesis.py                          Module 4 — tendances niche, format test hebdo, promotion test → éprouvé
engine/planner.py + exports.py               Module 5 — calendrier, fiche de tournage, export Cockpit
engine/feedback.py                           Module 6 — Instagram Graph API, liaison publication ↔ calendrier
engine/editing.py                            Module 7 — briefs ChatCut
engine/ethics.py                             garde-fous (riba, jeux d'argent, exagération, musique, indécence, moquerie)
engine/sources/                              Coran (alquran.cloud / quran.com) + hadiths (fawazahmed0 hadith-api, sunnah.com en option)
mcp/hadith/                                  MCP local « hadith » (déclaré dans .mcp.json)
data/engine.db                               SQLite : accounts, videos, analyses, my_videos, calendar (+ syntheses, format_status, hook_breakdowns, chat_*, runs)
```

Claude : appelé via **Claude Code en headless** (`claude -p`, ton abonnement) — aucune clé API nécessaire.
Ton contexte (histoire, expertise, offre, audience…) : dossier **`context/`**, injecté dans tous les prompts.
Langue des vidéos : `config/engine.yaml → language` (fr par défaut, en possible).

Mode dégradé : sans aucune clé, tout tourne (scraping mock, analyse mock/heuristique, calendrier depuis la banque).
Chaque clé ajoutée dans `.env` active la version « réelle » du module concerné — voir `GUIDE.md`.

## Campagnes

`config/campaigns/*.yaml` impose, pour un compte et une période, le **type et l'angle de chaque slot** (présentation motion design,
présentation face cam, témoignage, objection, fonctionnalité, rappel…) à la place de la rotation formats éprouvés + format test.
Le planner génère chaque slot selon son type (Claude, avec la skill et la Hook Library) ; sans Claude, il crée une fiche à compléter.
Chaque vidéo garde `campaign` (type, angle, notes « À préparer ») et la régénération d'une vidéo conserve son type et son angle.
Exemple commenté : `config/campaigns/exemple-lancement.yaml.exemple` (copie-le en `.yaml` pour l'activer). Après modification :
`engine calendar --start AAAA-MM-JJ`.

## Chat (dashboard)

Onglet **Chat** : plusieurs conversations, chacune est une vraie session Claude Code (`claude -p`, ton abonnement) lancée dans ce dossier.
Elle a donc les mêmes connaissances que Claude Code ici (CLAUDE.md, `config/identity.yaml`, skill content-principles, MCP hadith si règles islamiques)
et peut lancer le moteur : « régénère mercredi, plus axé objections », « refais PB-2026-10-21-2 plus court », « cette semaine c'est X »,
« ajoute à mes connaissances : … ». « Nouvelle conversation » repart de zéro ; une conversation existante reprend sa session (`--resume`).
- Ce qu'elle peut faire sans demander : lire/écrire dans le projet, `python -m engine …` (dont `engine plan`, le planning en lecture seule). Jamais de commit, push ni suppression.
- Contexte de la semaine → `context/06_cette_semaine.md` ; formations → `context/formations/<sujet>.md` (complet) + `context/05_formations.md` (essentiel, injecté).
- Code : `engine/chat.py` (consignes `CHAT_PROMPT`, outils autorisés), historique dans les tables `chat_conversations` / `chat_messages`.
  Modèle : celui par défaut de ton Claude Code, ou `chat.model` dans `config/engine.yaml`.

## Défi 90 jours (optionnel)

`config/engine.yaml → challenge.start_date` pilote tout : `null` = défi pas lancé → **aucun** contenu « Day X/90 », compteur, compte à rebours
ni objectif du défi (consigne au LLM, formats `no_challenge` de la banque, sujets liés au défi écartés, garde-fou `challenge_flags`).
Une date = défi actif du Jour 1 au Jour 90 seulement. `engine challenge --date AAAA-MM-JJ` (ou le bouton « Lancer le défi » du dashboard) le lance,
`engine challenge --reset` le remet à `null`.

## Tests

```bash
.venv/bin/python -m pytest -q tests
```
