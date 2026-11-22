---
name: plateforme
description: La Plateforme de contenu. Installe, configure sur la niche de l'utilisateur et ouvre sa plateforme locale blanc et bleu (veille concurrentielle, hooks, scripts TOFU/MOFU/BOFU, calendrier, prompteur, montage). Use when "plateforme", "ouvre ma plateforme", "lance ma plateforme", "configure ma plateforme", "mes hooks", "mes scripts", "change ma niche".
---

# La Plateforme de contenu

Dossier : `~/Documents/Plateforme-contenu`. Tout tourne sur l'ordinateur et l'abonnement Claude de l'utilisateur.
Parle en français, court, tutoiement. Questions avec boutons quand c'est possible. Ne publie rien, n'envoie rien.

## 1. Déjà configurée ?
Si `config/accounts/personal.yaml` ne contient plus `À_REMPLIR` à la ligne `niche` : va à l'étape 5.

## 2. Installation technique
Mac ou Linux seulement (sur Windows : dis-le et arrête-toi). Annonce 5 à 10 minutes.
- Vérifie `ffmpeg`, `yt-dlp`, `uv`. S'il en manque un, propose de l'installer avec Homebrew et attends son accord.
- Lance `./setup.sh`. S'il échoue : trouve la cause, corrige, relance.

## 3. Questionnaire (une question à la fois)
1. Prénom et nom affiché.
2. Sa niche, en une phrase : « J'aide [qui] à [résultat] grâce à [moyen] ».
3. Son offre : ce qu'il vend, son prix, comment on l'achète. Pas encore d'offre : note-le.
4. Sa cible : âge, situation, problème, ce qu'elle a déjà essayé, ses mots exacts.
5. Son histoire et ce qui le rend crédible (faits réels).
6. Ses preuves : résultats réels, avec accord de la personne. Aucune : laisse vide.
7. Ses comptes Instagram, TikTok, YouTube.
8. 3 à 10 créateurs qu'il admire dans sa niche (facultatif).
9. Langue des vidéos (fr ou en) et fuseau horaire.
10. « Veux-tu activer les règles islamiques ? (pas de musique instrumentale, pas de riba ni de jeux d'argent, citations seulement depuis une source) » Oui / Non.

## 4. Remplissage
N'invente aucun fait, chiffre, résultat ni témoignage. Inconnu = `[à compléter : ...]`.
- `config/identity.yaml` : `owner_name`, `identity`, `islamic_rules` (true seulement si Oui).
- `context/01_moi.md` à `05_preuves.md`.
- `config/accounts/personal.yaml` : `name`, `my_handles`, `niche`, puis 5 à 15 `reference_accounts` réels de sa niche, vérifiés un par un avec yt-dlp ou une recherche web. Jamais de compte deviné.
- `config/engine.yaml` : `language`, `timezone`, `scout.keywords.personal`.
- `config/hooklab.yaml` : ajoute ses créateurs.
- `config/content_bank/personal.yaml` : garde les formats, écris 10 `topics` pour sa niche avec la même structure que décrite dans `CLAUDE.md`.
- Termine par `./bin/engine doctor`.

Ne lis jamais les cookies ou le trousseau du navigateur. Ne demande jamais de mot de passe dans le chat.

## 5. Premières idées et ouverture
Lance dans cet ordre, en arrière-plan, et préviens quand c'est fini (20 à 40 minutes la première fois) :
```bash
./bin/engine veille
./bin/engine calendar --start <prochain lundi AAAA-MM-JJ> --days 7
```
Ouvre ensuite la plateforme : `./bin/engine ui` (http://127.0.0.1:8787).
Si la veille échoue sur un compte, continue avec les autres et dis-le. Ne présente jamais une idée sans source comme issue de la veille.

## Bêta
Le montage automatique est en bêta. Si un montage échoue, lis `data/montages/<id>/claude.log`, explique la cause en une ligne et propose de relancer.
