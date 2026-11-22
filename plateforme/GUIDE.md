# Content Engine — guide complet

Ton directeur de contenu personnel. Chaque jour, il te dit **exactement quoi filmer** : 3 vidéos courtes
(Reels, TikTok, Shorts) avec 2 hooks, le script, les plans à tourner, le texte à l'écran, le CTA et un brief de montage.
Il apprend de ce qui marche dans ta niche (vidéos qui font 3x la moyenne de leur créateur) et de tes propres stats.

Tout tourne **sur ton ordinateur**. L'intelligence vient de **Claude Code** (ton abonnement Claude) : pas de clé API obligatoire.

---

## Sommaire

1. [Ce qu'il te faut](#1-ce-quil-te-faut)
2. [Installation (15 min)](#2-installation-15-min)
3. [Configuration : ton identité (20 min)](#3-configuration--ton-identité-20-min)
4. [Premier lancement](#4-premier-lancement)
5. [Les connexions (optionnelles)](#5-les-connexions-optionnelles)
6. [Utilisation au quotidien](#6-utilisation-au-quotidien)
7. [Fonctions avancées](#7-fonctions-avancées)
8. [Automatiser](#8-automatiser)
9. [Commandes utiles](#9-commandes-utiles)
10. [Dépannage](#10-dépannage)
11. [Sauvegarde, mise à jour, confidentialité](#11-sauvegarde-mise-à-jour-confidentialité)

---

## 1. Ce qu'il te faut

| | Obligatoire ? | Coût |
|---|---|---|
| Un Mac (ou Linux). Windows : via WSL | oui | — |
| Un abonnement **Claude** (Pro ou Max) + **Claude Code** installé | oui, pour des scripts de qualité | inclus dans l'abonnement |
| **Google Chrome** | conseillé (comptes scout) | gratuit |
| **ffmpeg** | conseillé (analyse vidéo, Hook Lab) | gratuit |
| Un compte Instagram **professionnel** (créateur ou entreprise) | pour les stats | gratuit |
| Apify, OpenAI (Whisper) | non, options | à l'usage |

Sans Claude Code, le moteur tourne quand même en « mode dégradé » : il assemble les vidéos depuis la banque de contenu
(`config/content_bank/personal.yaml`), sans personnalisation fine.

---

## 2. Installation (15 min)

### 2.1 Dézipper le dossier
Dézippe `content-engine.zip` où tu veux, par exemple dans `Documents/`. **Évite** un dossier synchronisé en continu
(iCloud Drive « Optimiser le stockage », Dropbox) : la base de données n'aime pas ça.

### 2.2 Ouvrir un Terminal dans le dossier
Finder → clic droit sur le dossier `content-engine` → **Services → Nouveau terminal au dossier**
(ou ouvre Terminal, tape `cd ` puis glisse le dossier dans la fenêtre, puis Entrée).

### 2.3 Installer les outils de base (une fois par ordinateur)
Si tu n'as pas **Homebrew** (le gestionnaire de paquets du Mac) :
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Puis :
```bash
brew install uv ffmpeg
```
(`uv` installe Python tout seul, tu n'as rien d'autre à faire pour Python.)

### 2.4 Installer et connecter Claude Code
Suis l'installation officielle : https://docs.claude.com/en/docs/claude-code/setup — par exemple :
```bash
curl -fsSL https://claude.ai/install.sh | bash
```
Puis lance-le **une fois** pour te connecter avec ton compte Claude (Pro ou Max) :
```bash
claude
```
Choisis la connexion par abonnement Claude, valide dans le navigateur, puis quitte avec `/exit`.
C'est cette session que le moteur utilise ensuite en arrière-plan.

### 2.5 Lancer l'installation du moteur
Dans le Terminal ouvert dans le dossier :
```bash
./setup.sh
```
Le script crée l'environnement Python (`.venv`), installe les dépendances, crée ton fichier de clés `.env`,
vérifie ffmpeg / Claude Code / Chrome, lance les tests puis un diagnostic. Tu peux le relancer sans risque.

À la fin, `engine doctor` affiche une liste de lignes `OK` / `--`. Les `--` sont normaux tant que tu n'as pas tout configuré.

---

## 3. Configuration : ton identité (20 min)

C'est l'étape qui fait toute la différence : le moteur écrit **pour toi** seulement s'il te connaît.

### Option A — laisse Claude Code te configurer (recommandé)
Dans le Terminal, dans le dossier du moteur :
```bash
claude
```
Puis colle ce message :

> Configure-moi le Content Engine. Pose-moi les questions une par une (qui je suis, ma niche, mon offre, mon audience,
> ma langue de tournage, les créateurs que je regarde), puis remplis config/identity.yaml, les fichiers de context/,
> config/accounts/personal.yaml, config/engine.yaml, config/hooklab.yaml et réécris config/content_bank/personal.yaml
> pour ma niche. N'invente aucun fait ni chiffre. Termine par ./bin/engine doctor.

Claude Code connaît le projet (fichier `CLAUDE.md`) et sait quoi remplir. Relis ensuite les fichiers qu'il a modifiés.

### Option B — à la main
Ouvre les fichiers avec n'importe quel éditeur de texte (TextEdit en mode texte brut, VS Code…). Remplace tous les `À_REMPLIR`
et `[À COMPLÉTER …]`. Les lignes qui contiennent encore `[À COMPLÉTER` sont ignorées par le moteur.

| Fichier | Ce que tu y mets |
|---|---|
| `config/identity.yaml` | `owner_name` (ton prénom), `identity` (qui tu es en 3-5 lignes), les règles éditoriales, `islamic_rules` (voir § 5.7) |
| `context/01_moi.md` | ton histoire, ta crédibilité, tes convictions, ce que tu refuses de dire |
| `context/02_expertise.md` | ton sujet, tes méthodes, les questions qu'on te pose |
| `context/03_offre.md` | ce que tu vends, à qui, ton mot-clé de CTA (ex. « GUIDE ») |
| `context/04_audience_langue.md` | ta cible, ses mots, ton ton |
| `config/accounts/personal.yaml` | `name`, tes @ (`my_handles`), ta `niche`, **5 à 15 comptes de référence** de ta niche |
| `config/engine.yaml` | `language` (`fr` ou `en`), `timezone`, `scout.keywords` (mots-clés de ta niche, en anglais) |
| `config/hooklab.yaml` | les créateurs dont tu veux décortiquer les hooks (ajoute ceux de ta niche) |
| `config/content_bank/personal.yaml` | formats et sujets d'exemple (déjà génériques ; à adapter à ta niche) |

Tu peux ajouter d'autres fichiers dans `context/` (`05_histoires.md`, `06_clients.md`…) : tout est injecté dans les prompts
(maximum ~15 000 caractères au total).

**Les comptes de référence** : choisis des créateurs qui réussissent **avec un public proche du tien**, pas les plus gros.
Format : `- {platform: instagram, handle: nom_du_compte, status: "À VALIDER", note: "pourquoi"}` (`platform` = instagram, tiktok ou youtube).
Les comptes YouTube (Shorts) se récupèrent sans aucune connexion ; Instagram et TikTok demandent un compte scout (§ 5.2) ou Apify (§ 5.5).

Vérifie : `./bin/engine doctor`.

---

## 4. Premier lancement

### 4.1 Le dashboard
```bash
./bin/engine ui
```
Ça ouvre http://127.0.0.1:8787 dans ton navigateur (le dashboard n'écoute que sur ton ordinateur).
Laisse le Terminal ouvert tant que tu l'utilises ; `Ctrl + C` pour l'arrêter.

| Onglet | À quoi il sert |
|---|---|
| **Aujourd'hui** | la fiche du jour : vidéos regroupées par décor, plans à cocher, prompteur, brief de montage |
| **Calendrier** | la semaine ; clic sur une vidéo → détail, statut, « Régénérer avec Claude » |
| **B-roll** | la liste des plans de coupe à tourner en une session, réutilisables dans plusieurs vidéos |
| **Stats** | tes vues, ce qui surperforme, formats test promus |
| **Découvertes** | vidéos qui explosent dans ta niche (trouvées par le scout et le scraping) |
| **Hook Lab** | les meilleurs hooks de tes créateurs décortiqués sur 4 canaux (oral, texte, visuel, son) + adaptation pour toi |
| **Mon contexte** | éditer ton contexte sans ouvrir les fichiers |
| **Chat** | parler à Claude Code depuis le dashboard (« régénère mercredi », « cette semaine je suis malade »…) |
| **Système** | état des connexions, lancer les tâches, boutons Instagram |

### 4.2 Générer ta première semaine
Dans un second Terminal (ou depuis l'onglet Système) :
```bash
./bin/engine weekly
```
Ça enchaîne : récupération des vidéos de tes comptes de référence → détection des outliers → analyse → synthèse →
calendrier de 7 jours → fiche de tournage du jour. La première fois, compte 10 à 30 min (Claude écrit 21 scripts).

Tu veux juste tester vite, sans rien récupérer en ligne ?
```bash
./bin/engine weekly --mock
```
(Données simulées ; nettoie ensuite avec `./bin/engine reset-mock`.)

### 4.3 Lire la fiche du jour
```bash
./bin/engine daily --print
```
ou l'onglet **Aujourd'hui**. Fichiers produits : `output/shooting/<date>.md` (fiche de tournage),
`output/calendar/<lundi>/calendar.md` (semaine), `output/editing/<date>/<code>.md` (briefs de montage).

---

## 5. Les connexions (optionnelles)

Chaque connexion active la version « réelle » d'un module. Rien n'est obligatoire à part Claude Code.

| Connexion | Active | Où |
|---|---|---|
| Claude Code (§ 2.4) | scripts, hooks, analyse, Chat | `claude` une fois |
| Comptes scout (§ 5.2) | scraping Instagram/TikTok réel + découvertes | `./bin/engine login …` |
| Instagram Graph API (§ 5.3) | tes stats → le moteur apprend de tes vidéos | `.env` + `engine ig-auth` |
| Transcription (§ 5.4) | analyse de ce qui est dit dans les vidéos | automatique (local) ou `OPENAI_API_KEY` |
| Apify (§ 5.5) | scraping de secours très fiable | `APIFY_TOKEN` |
| Règles islamiques (§ 5.7) | zéro musique, rappels, citations sourcées | `config/identity.yaml` |

Le fichier `.env` (à la racine) contient tes clés. Il n'est **jamais** à partager.
Ouvre-le avec : `open -e .env` (Mac). Après chaque modification : `./bin/engine doctor`.

### 5.1 Claude Code — vérifier
`./bin/engine doctor` doit afficher `OK  Claude (backend : claude_cli)`. Sinon : relance `claude` et reconnecte-toi.
Pour que les tâches automatiques (§ 8) marchent même quand tu n'es pas connecté au Terminal :
```bash
claude setup-token
```
puis colle le token obtenu dans `.env` sur une nouvelle ligne : `CLAUDE_CODE_OAUTH_TOKEN=...`

Modèle utilisé : `config/engine.yaml → llm.cli_model` (`sonnet` par défaut ; `opus` = meilleur mais consomme plus de quota).

### 5.2 Comptes scout (Instagram, TikTok, YouTube)
Un compte « scout » est un compte **secondaire dédié** (jamais ton compte principal) que le moteur utilise pour
regarder les feeds de ta niche et récupérer les vidéos de tes comptes de référence.

1. Crée un compte secondaire sur chaque plateforme (une adresse mail dédiée suffit).
2. Connecte-le — c'est **toi** qui tapes tes identifiants dans la fenêtre Chrome qui s'ouvre, puis tu la fermes :
   ```bash
   ./bin/engine login instagram
   ./bin/engine login tiktok
   ./bin/engine login youtube
   ```
3. Premier passage (fenêtre visible, ~8 min par plateforme) :
   ```bash
   ./bin/engine scout
   ```
Ensuite `engine daily` relance le scout tout seul (plafond 30 min/jour, réglable dans `config/engine.yaml → scout`).
Le scout ne like, ne commente et ne publie jamais. Si une plateforme demande une vérification (captcha, code),
il s'arrête : refais `engine login <plateforme>` et règle-la à la main.
Les vidéos repérées arrivent dans l'onglet **Découvertes** et `output/discovery/`.

### 5.3 Instagram Graph API — tes statistiques
Le moteur lit les vues, la portée, les partages de **tes** Reels pour savoir quels formats marchent pour toi
(un format test qui bat ta médiane de 20 % sur 3 vidéos devient un format « éprouvé »).

Pré-requis : un compte Instagram **professionnel** (Paramètres → Type de compte → Créateur ou Entreprise).

**Créer l'app Meta (une fois, ~15 min)** — l'interface Meta change souvent, les noms peuvent varier :
1. Va sur https://developers.facebook.com → **Mes apps** → **Créer une app**.
2. Cas d'usage : **« Gérer les messages et le contenu sur Instagram »** (API Instagram avec connexion Instagram).
3. Dans l'app : **Cas d'usage → Personnaliser → Configuration de l'API avec connexion Instagram**.
   - Ajoute les autorisations `instagram_business_basic` et `instagram_business_manage_insights`.
   - **Rôles de l'app → Testeurs Instagram** : ajoute ton compte Instagram, puis accepte l'invitation dans
     Instagram (Paramètres → Apps et sites web → Invitations de testeur).
   - Section **Configurer la connexion professionnelle Instagram** → URL de redirection OAuth : `https://localhost:8765/callback`
4. Récupère **l'ID de l'app Instagram** et la **clé secrète de l'app Instagram** (même page).

**Connecter** :
1. Dans `.env` : `IG_APP_ID=` (ID de l'app Instagram), `IG_APP_SECRET=` (clé secrète),
   `IG_REDIRECT_URI=https://localhost:8765/callback` (exactement la même URL que dans l'app Meta).
2. Lance :
   ```bash
   ./bin/engine ig-auth
   ```
   Un lien s'ouvre : connecte-toi avec ton compte Instagram et accepte. Le navigateur affiche ensuite une **erreur de
   connexion sur localhost : c'est normal**. Copie l'URL complète de la barre d'adresse et colle-la dans le Terminal.
   (Même chose possible depuis l'onglet **Système** du dashboard, bouton Instagram.)
3. Le token et l'ID s'écrivent tout seuls dans `.env` (`IG_PERSONAL_TOKEN`, `IG_PERSONAL_USER_ID`) et sont rafraîchis
   automatiquement avant expiration (60 jours).
4. Test : `./bin/engine stats`

Variante si ton Instagram est lié à une Page Facebook et que ton app est de type « Facebook Login » :
`./bin/engine ig-auth --flow facebook` et `IG_GRAPH_HOST=graph.facebook.com` dans `.env`.

**Lier une vidéo publiée au calendrier** : c'est automatique (le moteur rapproche la publication de la vidéo prévue à ± 2 jours).
À la main : `./bin/engine link <id_media> <CODE>` ; pour TikTok : `./bin/engine link <id> <CODE> --platform tiktok --views 1234`.

### 5.4 Transcription (ce qui est dit dans les vidéos analysées)
- Par défaut : **faster-whisper en local** (gratuit, déjà installé ; le premier lancement télécharge le modèle, ~500 Mo).
- Plus rapide : une clé OpenAI dans `.env` → `OPENAI_API_KEY=` (quelques centimes par semaine).

### 5.5 Apify (scraping de secours)
Si les comptes scout posent problème : crée un compte sur https://apify.com, copie ton token
(Settings → API & Integrations) dans `.env` → `APIFY_TOKEN=`. Payant à l'usage (quelques $/mois à ce volume).

### 5.6 TikTok via cookies (alternative)
`YTDLP_COOKIES_BROWSER=chrome` dans `.env` : yt-dlp lit les cookies TikTok de ton Chrome (connecte-toi d'abord à TikTok dans Chrome).

### 5.7 Règles islamiques (optionnel)
Dans `config/identity.yaml` : `islamic_rules: true` active, pour toutes les vidéos :
- **zéro musique instrumentale** (voix, nasheed a cappella, bruitages) dans les scripts et les briefs de montage ;
- garde-fous **riba / jeux d'argent** en plus des garde-fous de base (promesses exagérées, indécence, moqueries) ;
- **1 à 2 rappels business par semaine** (intention, barakah, honnêteté, tawakkul, temps, argent), jeudi et dimanche par défaut,
  au format documentaire, jamais des sermons ;
- versets et hadiths **jamais écrits de mémoire** : le texte est récupéré depuis une API (Coran : alquran.cloud ;
  hadiths : hadith-api, sahih/hasan uniquement) et marqué **« À VÉRIFIER »**. Vérifie toi-même chaque citation via le lien
  fourni avant de filmer ; en cas de doute, filme sans.
- Option : clé sunnah.com (https://github.com/sunnah-com/api) → `SUNNAH_API_KEY=` pour recouper le grade.
- Claude Code peut aussi chercher une source via le serveur MCP local `hadith` (déclaré dans `.mcp.json`, à approuver au premier lancement de `claude`).

À `false` (défaut) : musique permise (basse sous la voix, libre de droits), pas de rappels.

### 5.8 Clé API Anthropic (alternative à l'abonnement)
`ANTHROPIC_API_KEY=` dans `.env` : le moteur utilise alors l'API (facturée à l'usage) au lieu de Claude Code.
Laisse vide pour utiliser ton abonnement.

### 5.9 Montage avec ChatCut
Les briefs de montage (`output/editing/<date>/<code>.md`, bouton « Brief » du dashboard) sont écrits pour être collés
tels quels dans ChatCut (ou n'importe quel monteur) : nettoyage, hook, texte à l'écran, sous-titres, rythme, B-roll, son.

---

## 6. Utilisation au quotidien

### La routine (≈ 2 h par jour pour 3 vidéos)
1. **Matin** — onglet **Aujourd'hui** : les 3 vidéos sont regroupées par décor pour filmer vite. Pour chacune : hook A et
   hook B (filme les deux), script (prompteur intégré), plans à tourner (coche au fur et à mesure), texte à l'écran, CTA.
2. **Les `[à compléter : …]`** : ce sont les vrais chiffres et faits que toi seul connais. Le moteur n'invente jamais
   de résultat : remplis-les à voix haute en filmant.
3. **Tournage** : fais 2-3 prises du hook, une prise pour le corps.
4. **Montage** : colle le brief de montage dans ChatCut (ou suis-le à la main).
5. **Publication** : publie, puis passe la vidéo en « publiée » dans le Calendrier (la liaison avec tes stats est automatique
   si Instagram est connecté).
6. **Le dimanche** : `./bin/engine weekly` (ou laisse l'automatisation le faire) prépare la semaine suivante à partir
   de ce qui a marché.

### Changer une vidéo qui ne te plaît pas
- Dashboard → Calendrier → clic sur la vidéo → **Régénérer** (avec une consigne : « hook plus contrarian », « plus court »…).
- Ou : `./bin/engine regen PB-2026-11-03-2 --instruction "plus personnel, raconte mon premier client"`
- Régénérer des jours entiers : `./bin/engine calendar --start 2026-11-05 --days 2`

Le code d'une vidéo : `PB-<date>-<slot>` (slots 1 et 2 = formats éprouvés, 3 = format test).

### Le Chat du dashboard
Chaque conversation est une vraie session Claude Code dans le dossier du moteur. Exemples :
- « Qu'est-ce qui est prévu demain ? »
- « Régénère mercredi, plus axé objections »
- « Cette semaine je suis en déplacement, je n'ai que mon téléphone : adapte les tournages » (noté dans `context/06_cette_semaine.md`)
- « Ajoute à mes connaissances ce que j'ai appris en formation : … » (noté dans `context/formations/` + l'essentiel dans `context/05_formations.md`)
- « Crée une campagne de lancement du 3 au 5 novembre pour mon offre X »

Le Chat peut lire et modifier les fichiers du projet et lancer le moteur. Il ne fait jamais de commit, push ni suppression.

---

## 7. Fonctions avancées

### Campagnes (lancement, semaine thématique)
Une campagne impose, sur une période, le **type et l'angle de chaque vidéo** (présentation, témoignage, objection,
fonctionnalité…) à la place de la rotation habituelle. Exemple commenté : `config/campaigns/exemple-lancement.yaml.exemple`.
Copie-le en `config/campaigns/mon-lancement.yaml`, adapte-le, puis : `./bin/engine calendar --start <première date>`.

### Défi public « 90 jours »
Format série documentaire (« Jour X/90 », objectif chiffré public, compteur, cliffhanger). Désactivé par défaut.
- Renseigne l'objectif : `config/engine.yaml → challenge.objectif` (ex. « 5 000 €/mois »).
- Lance-le : `./bin/engine challenge --date 2026-11-01` (Jour 1) ou bouton « Lancer le défi » du dashboard.
- Arrête-le : `./bin/engine challenge --reset`.
Tant qu'il n'est pas lancé, aucune vidéo ne parle de défi.

### Hook Lab
Décortique les meilleurs hooks de tes créateurs (`config/hooklab.yaml`) sur 4 canaux et les réinjecte dans la génération.
```bash
./bin/engine hooklab --limit 5                      # analyse 5 vidéos par créateur
./bin/engine hooklab --add "Nom" tiktok handle      # ajoute un créateur
./bin/engine hooklab --import tableau.xlsx          # importe des vidéos annotées
```
Export : `output/hooklab/hooklab.xlsx`. Nécessite ffmpeg.

### Banque de B-roll
`./bin/engine broll` (ou onglet B-roll) : regroupe tous les plans de coupe des 14 prochains jours par lieu, pour les tourner en une session.

### La skill de principes
`.claude/skills/content-principles/SKILL.md` : ~220 principes (hooks, structure, rétention, CTA, positionnement, production),
chacun tiré de vraies transcriptions de créateurs (Kallaway, Hormozi, Jenny Hoyos, Paddy Galloway, Mino Lee…).
Chaque vidéo générée cite les IDs des principes appliqués (ex. `H-V2`, `R3`). Les transcriptions et analyses sources sont dans
`data/transcripts/` et `data/analysis/` (base de recherche).
⚠ Ne relance pas `tools/assemble_skill.py` : il régénérerait la skill depuis les brouillons de recherche et écraserait la version adaptée.

### Réglages fins (`config/engine.yaml`)
- `outliers.threshold` : 3.0 = une vidéo doit faire 3x la médiane de son créateur pour compter.
- `calendar.proven_per_day` / `test_per_day` : 2 + 1 par défaut.
- `funnel.personal` : mix hebdo notoriété / confiance / conversion.
- `promotion` : quand un format test devient éprouvé.
- `scout` : durée, mots-clés, fenêtre visible ou non.

---

## 8. Automatiser

Pour que la semaine et la fiche du jour se préparent seules, ajoute deux tâches planifiées :
```bash
crontab -e
```
puis colle (en remplaçant le chemin par celui de ton dossier) :
```
0 6 * * 1 cd "/Users/TOI/Documents/content-engine" && ./bin/engine weekly >> data/logs/cron.log 2>&1
0 7 * * * cd "/Users/TOI/Documents/content-engine" && ./bin/engine daily >> data/logs/cron.log 2>&1
```
Pense au `CLAUDE_CODE_OAUTH_TOKEN` (§ 5.1). L'ordinateur doit être allumé (pas en veille) à ces heures-là.
Le scout ouvre une fenêtre Chrome : mets `scout.headless: true` dans `config/engine.yaml` pour qu'il tourne invisible.

---

## 9. Commandes utiles

Toutes se lancent depuis le dossier du moteur, avec `./bin/engine <commande>` :

| Commande | Ce qu'elle fait |
|---|---|
| `ui` | dashboard → http://127.0.0.1:8787 |
| `doctor` | diagnostic : ce qui est connecté ou pas |
| `weekly [--mock] [--force] [--no-llm]` | pipeline complet de la semaine |
| `daily [--print]` | stats + fiche du jour + briefs de montage |
| `plan --start AAAA-MM-JJ --days 7 [--full]` | planning en lecture seule |
| `regen <CODE> --instruction "..."` | régénère une vidéo |
| `calendar --start AAAA-MM-JJ [--days N]` | régénère des jours |
| `shooting --date AAAA-MM-JJ` | fiche de tournage d'un jour |
| `broll` | banque de B-roll |
| `hooklab` | Hook Lab |
| `login instagram\|tiktok\|youtube` / `scout` | comptes scout |
| `ig-auth` / `stats` / `link` | Instagram et stats |
| `challenge --date AAAA-MM-JJ` / `--reset` | défi 90 jours |
| `report` | état du système → `output/report.md` |
| `reset-mock` | supprime les données de test |

`./bin/engine <commande> --help` pour toutes les options.

---

## 10. Dépannage

**`./setup.sh: Permission denied`** → `chmod +x setup.sh bin/engine` puis relance.

**« Claude » en `--` dans doctor** → lance `claude` dans le Terminal et reconnecte-toi. Vérifie que `claude --version` répond.
Si Claude Code est installé ailleurs : `CLAUDE_BIN=/chemin/vers/claude` dans `.env`.

**Les vidéos sont génériques** → ton contexte est trop vide : `./bin/engine doctor` indique le nombre de caractères utiles.
Remplis `context/` (des faits, des histoires, des chiffres réels) et `config/identity.yaml`, puis régénère.

**« garde-fou éthique » dans les logs** → une vidéo générée contenait une promesse exagérée ou un terme interdit ; le moteur
la rejette et en régénère une autre. Normal. Ajuste `forbidden_patterns` dans `config/identity.yaml` si un mot est bloqué à tort.

**Scraping vide / 0 outlier** → vérifie tes comptes de référence (handles exacts, sans @), connecte un compte scout (§ 5.2)
ou ajoute des comptes YouTube (scrapables sans connexion). `--` sur une plateforme = pas de session : `engine login`.

**Le scout s'arrête (vérification humaine)** → `./bin/engine login <plateforme>`, règle le captcha toi-même, ferme la fenêtre.

**`ig-auth` : « redirect_uri mismatch »** → `IG_REDIRECT_URI` dans `.env` doit être **identique** à l'URL déclarée dans l'app Meta
(même https, même port, même `/callback`).

**`ffmpeg` introuvable** → `brew install ffmpeg`.

**Le dashboard ne s'ouvre pas** → le port est peut-être pris : `./bin/engine ui --port 8790`.

**Repartir de zéro sur le planning** → supprime `data/engine.db` (perds l'historique : calendrier, stats, analyses), puis `./bin/engine weekly`.

**Tout vérifier** → `.venv/bin/python -m pytest -q tests` (tout doit être vert).

Bloqué ? Lance `claude` dans le dossier et décris le problème : Claude Code connaît le projet.

---

## 11. Sauvegarde, mise à jour, confidentialité

- **Ce qui t'appartient** : `config/`, `context/`, `.env`, `data/engine.db` (historique), `output/`. Sauvegarde ces éléments
  (Time Machine suffit).
- **Ne partage jamais** `.env` (tes clés et tokens) ni `data/browser/` (sessions de tes comptes scout).
- **Confidentialité** : tout tourne en local. Ce qui part en ligne : les prompts envoyés à Claude (ton contexte inclus),
  les requêtes aux plateformes (scraping, API Instagram) et, si activé, à OpenAI (transcription) ou Apify.
- **Versionner tes réglages** (optionnel) : `git init` dans le dossier ; `.gitignore` exclut déjà `.env`, la base, les médias et les sessions.
- **Mise à jour du moteur** : remplace les dossiers `engine/`, `tests/`, `bin/` et le fichier `pyproject.toml` par ceux de la nouvelle
  version, garde tes `config/`, `context/`, `.env` et `data/`, puis relance `./setup.sh`.
