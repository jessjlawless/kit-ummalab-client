# Content Engine — contexte pour Claude Code

Projet Python (venv `.venv`, Python 3.12) qui planifie et scripte 3 vidéos courtes/jour pour un créateur (2 formats éprouvés + 1 format test).
Guide utilisateur : GUIDE.md. Référence technique : README.md.

## Identité et ligne éditoriale (NON NÉGOCIABLE)
Source de vérité : `config/identity.yaml` (prénom `owner_name`, identité, règles), injecté dans tous les prompts via
`engine/principles.py` et appliqué par `engine/ethics.py`. Contexte personnel détaillé : `context/*.md`.
- Toujours : vente honnête, aucun chiffre inventé (sinon `[à compléter : ...]`), aucune promesse exagérée, aucune moquerie envers une personne.
- Si `islamic_rules: true` dans `config/identity.yaml` :
  - AUCUNE musique instrumentale dans aucune vidéo ni aucun brief de montage (voix, nasheed a cappella et bruitages autorisés).
  - Rien de contraire à l'éthique islamique (riba, jeux d'argent, mensonge/promesses exagérées, indécence, moqueries).
  - 1-2 rappels islamiques axés business / semaine, format documentaire, jamais des sermons.
  - Ne JAMAIS écrire un verset ou un hadith de mémoire : passer par `engine/sources/` ou le MCP `hadith` (`.mcp.json`).
    Hadiths sahih/hasan uniquement, marqués « À VÉRIFIER ».

## Règles de travail
- Toute génération (scripts, hooks, CTA, montage) applique la skill `.claude/skills/content-principles` et cite les IDs de principes.
- Langue des vidéos : `config/engine.yaml → language` (fr | en) ; dashboard, analyses et docs en français.
- Garder le système simple ; chaque module a un fallback sans clé API.
- Un seul compte, d'identifiant technique `personal` (nom affiché : `config/accounts/personal.yaml → name`).
- Tests : `.venv/bin/python -m pytest -q tests`.

## Aide à la configuration
Si l'utilisateur demande de l'aider à configurer le moteur (« configure-moi », « onboarding ») : pose-lui les questions
une par une, puis remplis `config/identity.yaml`, `context/01_moi.md` à `04_audience_langue.md`, `config/accounts/personal.yaml`
(niche, handles, 5-15 comptes de référence réels et vérifiés), `config/engine.yaml` (language, timezone, scout.keywords),
`config/hooklab.yaml` (créateurs de sa niche) et réécris `config/content_bank/personal.yaml` pour sa niche (même structure,
mêmes clés, scripts avec `[ ... ]` pour les faits qu'il doit compléter). N'invente aucun fait, chiffre ou résultat.
Termine par `./bin/engine doctor`.
