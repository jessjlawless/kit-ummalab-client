# Ton contexte — à compléter librement

Tout fichier `.md` de ce dossier (sauf ce README) est injecté dans **tous** les prompts de génération
(calendrier, scripts, hooks, CTA, format test, analyse, montage). Plus c'est précis et vrai, meilleurs sont les scripts.

- Écris en français ou en anglais, peu importe : les vidéos sortent dans la langue choisie dans `config/engine.yaml` (`language: fr` ou `en`).
- Ajoute des faits, des histoires vraies, des chiffres réels, des opinions tranchées, ce que tu refuses de dire.
- Crée autant de fichiers que tu veux (ex. `05_histoires.md`, `06_clients.md`). Ordre = ordre alphabétique.
- Garde l'ensemble sous ~15 000 caractères (au-delà, c'est tronqué).
- Les lignes `[À COMPLÉTER ...]` sont ignorées tant que tu ne les remplaces pas.

## Fichiers tenus par le Chat du dashboard
- `05_formations.md` — l'essentiel actionnable de tes formations (détail complet dans `formations/`, non injecté).
- `06_cette_semaine.md` — le contexte de la semaine en cours (« cette semaine c'est X »), daté ; les semaines passées sont retirées.
