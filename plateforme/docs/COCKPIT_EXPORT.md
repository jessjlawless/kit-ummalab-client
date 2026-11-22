# Export Cockpit — format JSON

Fichiers produits :

| Fichier | Contenu |
|---|---|
| `output/cockpit/latest.json` | dernier calendrier généré (schéma `content-engine/calendar@1`) — c'est celui que Cockpit doit lire |
| `output/calendar/<lundi>/calendar.json` | même contenu, archivé par semaine |
| `output/shooting/<date>.json` | fiche de tournage du jour (schéma `content-engine/shooting@1`) |
| `output/editing/<date>/briefs.json` | briefs de montage ChatCut du jour |

Encodage UTF-8, dates ISO `AAAA-MM-JJ`, heures locales `Europe/Berlin`.

## `content-engine/calendar@1`

```jsonc
{
  "schema": "content-engine/calendar@1",
  "generated_at": "2026-10-19T07:00:00",
  "timezone": "Europe/Berlin",
  "week_start": "2026-10-19",
  "week_end": "2026-10-25",
  "challenge": { "start_date": "2026-10-19", "length_days": 90, "objectif": "5 500 €/mois" },
  "accounts": [ { "id": "personal", "name": "...", "handles": { "instagram": "...", "tiktok": "..." } } ],
  "videos": [ Video, ... ]          // triées par date, compte, slot
}
```

### `Video`

| Champ | Type | Description |
|---|---|---|
| `code` | string | identifiant stable, ex. `PB-2026-10-19-1` (PB, puis date, puis slot) |
| `account` | `"personal"` | |
| `account_name` | string | |
| `date` / `weekday` | string | `2026-10-19` / `lundi` |
| `slot_index` | int | 1, 2 = éprouvés ; 3 = test |
| `slot_type` | `"proven"` \| `"test"` | |
| `day_number` | int \| null | jour du défi (personal uniquement) |
| `episode_label` | string \| null | `"Jour 1/90"` |
| `format` | object | `{id, name, source_niche (test), structure}` |
| `topic_id` | string \| null | id dans la banque (`pb_001`, `tf_x#v3`, `rp_002`…) |
| `subject` | string | sujet en une ligne |
| `hooks` | array | 2 variantes : `{variant: "A"\|"B", verbal, text_on_screen, visual}` |
| `script` | string | ~150 mots, à dire après le hook |
| `word_count` | int | |
| `cta` | object | `{text, type}` — type ∈ `follow_series, comment_keyword, save, share, dm, soft` |
| `setup` / `setup_label` | string | décor : `bureau, chambre, exterieur, fac, cuisine, voiture, salle_sport, ecran` |
| `shots` | string[] | liste de plans à filmer |
| `edit_template` | object | `{format, pacing, subtitles, broll[], on_screen_text, music, visual_format, inspiration_urls[]}` — `music` vaut toujours « AUCUNE musique … » |
| `principles` | string[] | IDs de la skill content-principles (`H-V1`, `R2`, `I4`…) |
| `is_rappel` | bool | rappel islamique axé business |
| `rappel_theme` | string \| null | `intention, barakah, honnetete, tawakkul, temps, argent` |
| `citation` | object \| null | voir ci-dessous |
| `ethics_flags` | string[] | garde-fous déclenchés (vide = OK) |
| `reference` | object \| null | vraie vidéo qui a marché à prendre en modèle : `{url, title, channel, platform, source ("outlier+llm" \| "outlier" \| "youtube_search"), why}` |
| `reference_query` | string \| null | requête utilisée pour chercher une référence |
| `source` | `"llm"` \| `"bank"` | origine du contenu |
| `status` | `"planned"` \| `"filmed"` \| `"published"` | |

### `citation`

- Sans source vérifiée : `{"status": "citation à ajouter", "idea": "tawakkul"}`
- Coran : `{"status": "À VÉRIFIER PAR LE CRÉATEUR", "type": "quran", "reference": "Coran 65:3 (At-Talaaq), trad. Muhammad Hamidullah", "url": "https://quran.com/65/3", "source": "api.alquran.cloud", "arabic": "...", "french": "..."}`
- Hadith : `{"status": "À VÉRIFIER PAR LE CRÉATEUR", "type": "hadith", "reference": "Sahih al-Bukhari n°1 — Sahih (...)", "url": "https://sunnah.com/bukhari:1", "source_url": "https://cdn.jsdelivr.net/...json", "text": "...", "grade": "..."}`

## `content-engine/shooting@1`

```jsonc
{
  "schema": "content-engine/shooting@1",
  "date": "2026-10-19",
  "episode_label": "Jour 1/90",
  "estimated_minutes": 57,
  "setups": [ { "setup": "bureau", "label": "...", "gear": "...", "videos": ["PB-2026-10-19-1", "PB-2026-10-19-2"] } ],
  "videos": [ Video, ... ]   // + calendar_id
}
```

Ordre de tournage = ordre de `setups`.

## Lier une publication

Quand une vidéo est publiée, `engine daily` la lie automatiquement (Graph API, date ± 2 j + similarité caption/hook).
Manuel : `engine link <media_id|url> <code> [--views N --platform tiktok]`.
