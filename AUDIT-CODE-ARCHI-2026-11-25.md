# Audit code et architecture — OoT Remake Randomizer — 25/11/2026 (v0.8.4, branche `perf/audit-fixes`)

Complète [AUDIT-2026-11-25.md](AUDIT-2026-11-25.md) (performance). Ce qui y est déjà traité n'est pas répété ici :
découpage de `generate()` (§4.1), `ResourceStore` (§2.2), GUI monolithique (§4.4), `verify` géant (§4.5),
automatisation de la release (§5.2), tests logiques en CI sans le jeu (§3.4).

Périmètre : `src/oot_rando` (~33 600 lignes, 1 508 fonctions), `tests` (1 003 tests), CI/release, packaging.
Méthode : graphe d'imports calculé, lecture des modules sensibles (updater, parties, client AP, mémoire live,
règles logiques, solveur, verify), `ruff` sur tout `src`, suite de tests lancée (`run_parallel.py` sans NUP :
**1 003 tests, 320 ignorés, OK en 11 s**).

## 0. Mise en œuvre (25/11/2026, branche `perf/audit-fixes`)

| § | Point | État |
|---|---|---|
| 2.1 | Updater bloqué | **Fait** : `OSError` → `UpdateError`, workers `except Exception`, test |
| 2.2 | Fiche de partie corrompue | **Fait** : `list()` l'écarte (`unreadable`), carte « Unreadable party » dans la GUI, test |
| 2.3 | fsync du point de commit | **Fait** : fsync fichier (+ dossier sous Linux), test |
| 2.4 | Traces d'erreur | **Fait** : `WorkerError.trace` → `data/last-error.log` (ou `build/` depuis les sources) |
| 2.5 | Divers | **Fait** : nouvel essai d'ouverture de la bibliothèque, code mort, ligne fusionnée. Anti-rollback de l'updater : non fait (risque faible) |
| 3.1 | Couches | **Fait** : `catalog/`, `system.py`, `versions.py`, `formats/save_file.py`, `randomizer/save_patch.py`, `tests/test_layers.py` (0 violation). Imports différés : 470 → 316 (les restants sont dans `gui/`/`__main__`, dans la même couche, ou gardés par un `try`) |
| 3.2 | API privées | **Fait** : `formats/evfl_tools.py` (`parse_flow`, `params_by_event`…), ~20 autres helpers renommés publics |
| 3.3 | `verify` indépendant | **Fait** : docstring honnête + `output_invariants` (RESTBL, noms GameData des flows), testé sur seed réelle et en unitaire |
| 3.4 | `Settings` | **Fait** : test d'identité figé, `validate()`/`to_dict()` sans effet de bord (normalisation dans `__post_init__`). `FullOptions` typé : **non fait** (≈ 80 options lues comme dict partout, gain faible sans vérificateur de types) |
| 3.5 | Versions | **Fait** : version unique (`__init__.py`), `golden_seeds.py` signale une sortie changée sans bump de `GENERATOR_VERSION` |
| 3.6 | Dérive apworld | **Fait** : `tests/test_apworld_drift.py` (sources sans le jeu, catalogue avec, import sans zstd/evfl/ainb depuis les seuls fichiers embarqués). L'apworld commité était déjà en retard ; reconstruit |
| 3.7 | Modules fourre-tout | **Fait** : `randomizer_services` → `artifact.py`, `mods_folder.py`, `tracker/manual_tracker.py` ; `FillContext` documenté à la place du `SimpleNamespace` |
| 3.8 | Mode prudent | **À décider** (fonction visible dans la GUI : sa suppression est un choix produit) |
| 4.1 | Dépendances | **Fait** : `websockets` + extra `overlay` dans pyproject, `tests/test_dependencies.py` |
| 4.2 | ruff en CI | **Fait** |
| 4.3 | Typage | **Non fait** (mypy non installé ; à faire sur `formats/`, `logic/` si souhaité) |
| 4.4 | Couverture | **Non fait** (coverage non installé). Tests ajoutés : identité, couches, dérive apworld, dépendances, invariants |
| 4.5 | `CLAUDE.md` | **Fait** |

## 1. Synthèse

| | Verdict |
|---|---|
| Sécurité | **Bon.** Rien de critique. Mises à jour signées, `eval` verrouillé par AST, entrées AP validées, liens/jonctions refusés. |
| Robustesse des données joueur | **Bon**, avec 2 trous (fsync, une fiche corrompue bloque tout « My Games »). |
| Bugs trouvés | 3 réels, mineurs à moyens (§2). Les 11 alertes `B023` de ruff sont des faux positifs (vérifiés un par un). |
| Architecture | **Le point faible.** Couches inversées, 6 cycles entre paquets, 505 imports dans des fonctions pour les contourner, 76 imports de fonctions privées d'autres modules. |
| Outillage | Pas de linter ni de typage en CI, deux listes de dépendances divergentes, apworld binaire commité sans contrôle de dérive. |

Ce qui est déjà bien fait (à garder) :
- `logic/rules.py:139` : le code de règle généré passe une liste blanche de nœuds AST avant `eval` sans builtins. Propre.
- `updater.py` : `SHA256SUMS.txt` signé Ed25519, URL bornées au dépôt, tailles plafonnées, échange `.old`/`.new` réversible.
- `parties.py` : journal d'intention, point de commit unique (`library.json`), récupération au démarrage, verrou inter-processus, refus des liens symboliques et jonctions, vérification des copies par hash.
- `archipelago/bridge.py:394` `check_patch` : validation complète d'un `.aprmk` hostile. Client AP : pas de repli `ws://` après une erreur de certificat.
- GUI : les threads ne touchent jamais Tk, tout passe par `queue` + `poll()`. Génération dans un processus séparé.
- CI : actions épinglées par SHA, `permissions: contents: read`, selftest de l'exécutable construit.

---

## 2. Bugs

### 2.1 [P1] Mise à jour bloquée jusqu'au redémarrage si l'écriture échoue
`updater.py:257` : `new.write_bytes(data)` est **hors** du `try`. Une `OSError` (disque plein, dossier en lecture seule,
antivirus qui verrouille `.new`) remonte telle quelle. Le thread de `randomizer_gui.py:2283` n'attrape que `UpdateError` :
il meurt sans rien poster, `self.updating` reste à `'install'`, et chaque clic suivant répond « The update is being
downloaded » jusqu'à la fermeture. Même défaut dans le thread de vérification (`randomizer_gui.py:2247`) pour toute
exception autre que `UpdateError`.

Correctif : envelopper l'écriture de `.new` dans le `try` (→ `UpdateError`), et dans les deux workers
`except Exception as error` en plus de `UpdateError`.

### 2.2 [P2] Une seule fiche de partie corrompue rend « My Games » inutilisable
`parties.py:150` `list()` appelle `get()` sur chaque dossier ; `get()` lève sur un JSON invalide ou incohérent.
`_name()`, `recover()` (via `allowed`) et l'affichage passent tous par `list()` : un seul `party.json` abîmé bloque
création, renommage, activation **et la récupération d'une transaction interrompue**.

Correctif : `list()` ignore (et signale) les fiches illisibles ; `recover()` n'a besoin que des destinations du journal.

### 2.3 [P2] Le point de commit n'est pas durable
`parties.py:23` `_write` fait `write_text` puis `replace` sans `fsync`. Sur coupure de courant, NTFS/ext4 peuvent
laisser un `library.json` vide après le renommage → `index()` lève `JSONDecodeError` → bibliothèque bloquée.
C'est justement le fichier qui sert de point de commit des transactions.

Correctif : `os.fsync` du fichier temporaire avant `replace` (et du dossier sous Linux). 5 lignes.

### 2.4 [P3] Erreurs de génération sans trace
`gui/generation_worker.py:10` renvoie `str(error)` seul. Pour un rapport de bug joueur (« IndexError: list index
out of range »), il n'y a ni pile ni fichier de log. Envoyer `traceback.format_exc()` et l'écrire dans `data/last-error.log`.

### 2.5 [P3] Divers
- Démarrage avec une transaction en attente **et** le jeu ouvert : `PartyLibrary()` lève `GameRunning`, l'erreur est
  mise de côté (`parties_page.py:35`) et « My Games » reste désactivé pour toute la session, sans nouvel essai.
- `updater` : la signature couvre les sommes mais pas la version. Rejouer une ancienne release signée reste possible
  pour qui contrôle la réponse de l'API GitHub. Risque faible (TLS + GitHub), noté pour mémoire.
- Code mort : `patching/lost_dog.py:2` (`CHALLENGES`), `randomizer/verify.py:406` (`add_skip_window`), 7 `noqa` inutiles.
- `archipelago/bridge.py:419` : un retour à la ligne a été fusionné en 17 espaces au milieu d'une condition.

---

## 3. Architecture

### 3.1 [P1] Couches inversées et cycles entre paquets

Graphe réel des imports entre paquets (nombre d'imports) :

```
formats  ←  tout le monde                                    (OK : couche basse)
game     →  patching  12   ✗  le « modèle » dépend des adaptateurs
patching →  game      16      …et réciproquement : cycle
logic    →  archipelago 1, randomizer 1   ✗
patching →  logic      2   ✗  (story_fixes, world_openings → rando_options)
randomizer ↔ archipelago   7 / 4   cycle
randomizer ↔ tracker       1 / 6   cycle  (save_patch importe randomizer_core)
```

Conséquence directe : **505 imports à l'intérieur de fonctions**, la plupart pour casser un cycle. Ils masquent
les dépendances réelles, retardent les `ImportError` à l'exécution (le test `test_compile_all` ne les voit pas) et
rendent l'ordre d'import fragile.

Cause racine : les **noms du jeu** (acteurs d'âmes, de clés, de jetons, `murmur3`, préfixes de drapeaux, `CHESTS`)
sont définis dans les adaptateurs `patching/*` alors qu'ils sont du domaine. `game/tracking_metadata.py` importe
`murmur3, soul_actor, soul_item, soul_label` depuis `patching/soul_adapter.py` ; `game/remake_world.py` va chercher
5 fonctions de nommage dans 4 adaptateurs.

Cible (DAG strict, chaque couche n'importe que les précédentes) :

```
formats → catalog (noms, hashs, constantes du jeu) → game → logic → patching → randomizer
        → {archipelago, tracker, parties} → gui / __main__
```

Étapes :
1. Créer `oot_rando/catalog/` et y déplacer les fonctions pures de nommage (`soul_actor`, `key_actor_item`,
   `token_family`, `ap_actor`, `murmur3`, `CHESTS`, préfixes). Les adaptateurs les réimportent.
2. `logic/rando_options.py:581` et `logic/audit_rules.py:325` : l'export YAML AP et `ap_settings` vont dans
   `archipelago/` ; la logique ne connaît pas Archipelago.
3. `tracker/save_patch.py` : `running_game`/`GameRunning`/`process_images` (utilisés par `parties`, `services`)
   vont dans un module système (`pc_port.py` ou `system.py`) ; `save_marker`/`SEED_MARKER_PREFIX` dans `catalog`.
4. Verrouiller : un test de 30 lignes (ast) qui échoue si un import viole l'ordre des couches. Sans ce garde-fou,
   le code assisté par IA recrée les cycles en une session.

### 3.2 [P1] API privées utilisées partout
76 imports de noms `_privés` d'un autre module : `_flow` (31), `_snapshot` (23), `_params` (11), `_predecessors` (8),
`_pack_path`, `_module_edit`… Ce sont de fait les primitives evfl/ainb du projet. Les promouvoir dans
`formats/evfl_tools.py` (ou `patching/flow.py`) avec un nom public. Sans changement de comportement ; ça rend visible
ce qui est stable.

### 3.3 [P1] `verify` n'est pas indépendant
La docstring (`verify.py:1`) promet une vérification indépendante « le plan du générateur n'est pas réutilisé ».
En pratique, `verify` reconstruit les fichiers attendus en **rappelant les mêmes fonctions de patch** (`qol_patches`,
`progressive`, `story_fixes`, `soul_adapter`… une vingtaine) et refait le balayage avec la **même** classe `Logic`.
Un bug dans un patcher ou dans les règles se retrouve à l'identique des deux côtés : `verify` le valide.

C'est un très bon test de **reproductibilité** et de **périmètre des diffs**, pas une preuve indépendante. Deux options :
- l'assumer : renommer le point 6 et la docstring, pour ne pas surestimer la garantie ;
- ou ajouter des **invariants** lus uniquement dans la sortie (chaque coffre a exactement une récompense existante,
  chaque drapeau d'âme est déclaré dans GameData, aucun acteur référencé n'est absent de RSDB/RESTBL, etc.) qui
  n'appellent aucun patcher.

### 3.4 [P1] `Settings` : deux produits dans une classe, identité fragile
`randomizer_core.py:91` :
- mélange le mode « prudent » historique (4 coffres Kokiri, `pool`, `excluded_checks`, `categories`) et le mode
  complet (`full: dict | None`, non typé, validé par `rando_options`). Le défaut `randomize_chests=True` est
  **refusé** dès que `full` est défini ;
- `validate()` **mute** `self.full` ; `to_dict()` rappelle `validate()` (effet de bord + coût à chaque identité) ;
- l'identité de seed (`settings_identity`) est le sha256 de `to_dict()`, avec des règles d'omission pour la
  rétrocompatibilité (`OPTIONAL_SKIPS` omis quand faux, `full` omis quand `None`, `spiritual_stones` injecté dans
  `from_dict`…). Changer un défaut ou l'ordre d'un champ change silencieusement l'identité de toutes les seeds.

Correctif progressif :
1. Test d'identité figé, **sans NUP** (tourne en CI) : 5–6 `Settings` représentatifs → hash attendu en dur.
   Coût : 20 lignes. Protège tout le reste.
2. `FullOptions` typé (dataclass ou `TypedDict`) à la place du `dict`.
3. `validate()` pur (retourne une copie normalisée) ; `identity_dict()` explicite et versionné, séparé de `to_dict()`.

### 3.5 [P2] Trois numéros de version, bumpés à la main
- version de l'application en double : `pyproject.toml` **et** `src/oot_rando/__init__.py` ;
- `GENERATOR_VERSION = '0.12.18'` (changelog dans le commentaire) ;
- `ADAPTER_VERSION = 'ap-glitchless-v5'`.

Oublier `GENERATOR_VERSION` après un changement de sortie = deux seeds différentes avec la même identité, et `verify`
qui accepte une seed qu'il ne sait plus reproduire. `tools/golden_seeds.py` existe mais ne tourne qu'en local avec le NUP.

Correctif : version unique via `[tool.setuptools.dynamic] version = {attr = "oot_rando.__version__"}` ; dans
`golden_seeds.py`, échouer si les empreintes changent **et** que `GENERATOR_VERSION` n'a pas bougé.

### 3.6 [P2] apworld binaire commité sans contrôle de dérive
`apworld/oot_remake.apworld` est reconstruit à la main avant chaque merge. Aucun test ne vérifie qu'il correspond
aux sources (`test_archipelago` construit un apworld temporaire, mais ne le compare pas au fichier commité).
Ajouter un test CI : reconstruire et comparer le contenu (liste + hash des membres, pas le zip brut), ou le produire
dans `release.yml` et arrêter de le commiter.

### 3.7 [P2] Modules fourre-tout
- `randomizer/randomizer_services.py` : lecture d'artefact, opérations sur le dossier mods, archivage, conflits,
  migration de sauvegardes **et** `ManualTracker`. `parties` et `tracker` en dépendent pour des raisons différentes.
  Séparer `artifact.py` (lecture/validation du manifest) et `mods_folder.py` ; `ManualTracker` va dans `tracker/`.
- `full_randomizer.prepare()` (406 lignes) renvoie un objet de ~20 champs que `plan()` dépaquette ligne 677-681 :
  c'est un contexte de génération qui mérite une vraie classe (`FillContext`) avec ses méthodes `sweep`, `allowed`.
- 23 fonctions de plus de 100 lignes, 81 de plus de 50. Les 4 premières sont déjà dans l'audit perf.

### 3.8 [P3] Mode prudent historique
`CHECKS`, `PRUDENT_POOL`, `placements_for`, `patch_map`, `categories` et la branche `active or open_forest` de
`generate()` servent un mode « première release prudente ». S'il n'est plus proposé dans la GUI, le retirer
simplifie `Settings` (§3.4) et `generate()`. À trancher avant le découpage de §4.1 de l'audit perf.

---

## 4. Outillage et qualité

### 4.1 [P1] Dépendances : deux sources de vérité, divergentes
`pyproject.toml` déclare `zstandard, evfl, ainb, certifi`. `requirements.txt` ajoute `websockets, Pillow,
texture2ddecoder`. Un `pip install .` donne un `oot-rando` dont le client AP et l'overlay plantent à l'import
différé. Déclarer `websockets` dans `dependencies`, `Pillow`/`texture2ddecoder` en extra `overlay`, et faire
de `requirements.txt` un simple `-e .[overlay,yaml]` (ou le supprimer). `certifi>=2026.11.20` (daté d'il y a 5 jours)
est inutilement strict : `>=2024.2` suffit, la date n'apporte pas de sécurité ici.

### 4.2 [P1] Pas de linter en CI
`ruff` est installé localement mais pas dans la CI. Jeu de règles minimal proposé (zéro bruit sur la base actuelle
après 3 corrections) :

```toml
[tool.ruff.lint]
select = ["F", "E9", "B", "PLW0603", "RUF100"]
ignore = ["B023", "B905", "B007"]   # fermetures synchrones, zip sans strict : choix assumés ici
```

Ajouter `ruff check src tools tests` comme première étape du job `tests`.

### 4.3 [P2] Aucune annotation de type
0 fonction annotée sur 1 508. Pas la peine de tout typer. Typer les **frontières** suffit : `Settings`,
manifest d'artefact, `.aprmk`, placement, `Logic.sweep` (via `TypedDict`/dataclasses), puis `mypy` sur
`formats/` et `logic/` seulement. C'est là qu'un dict mal formé coûte cher.

### 4.4 [P2] Tests
- 1 003 tests, **320 ignorés sans NUP (32 %)** : la CI ne fait jamais tourner la génération de bout en bout
  (cf. audit perf §3.4 pour les fixtures synthétiques).
- Pas de mesure de couverture. `coverage run tests/run_parallel.py` une fois en local suffit pour repérer les
  modules sans test (ex. `updater.replace_executable`, chemins d'erreur de `parties._install`).
- Manquent : test d'identité de seed (§3.4), test de couches (§3.1), test de dérive apworld (§3.6).

### 4.5 [P2] Pas de `CLAUDE.md` dans le dépôt
Le README annonce un code écrit principalement avec Claude Code. Les règles qui comptent (ordre des couches,
quand bumper `GENERATOR_VERSION`, interdiction d'importer un `_privé`, rebuild de l'apworld, flux main/dev) ne
sont écrites nulle part dans le dépôt. Un `CLAUDE.md` de 40 lignes rendrait ces règles visibles à chaque session,
et le test de §3.1 les ferait respecter.

---

## 5. Plan d'action conseillé

| Ordre | Action | Effort | Gain |
|---|---|---|---|
| 1 | §2.1 updater bloqué, §2.3 fsync, §2.2 fiche corrompue | 1 h | bugs joueurs |
| 2 | §4.1 dépendances, §4.2 ruff en CI, code mort §2.5 | 1 h | install correcte, garde-fou |
| 3 | §3.4.1 test d'identité de seed sans NUP | 30 min | protège toutes les refactos suivantes |
| 4 | §3.6 test de dérive apworld | 1 h | release plus sûre |
| 5 | §3.1 `catalog/` + test de couches, puis §3.2 API evfl publique | 1–2 j | supprime la plupart des 505 imports différés |
| 6 | §3.8 décider du sort du mode prudent, puis §3.4.2-3 `Settings` typé | 1 j | simplifie `generate()` avant le découpage perf §4.1 |
| 7 | §3.3 invariants de sortie dans `verify` | 1 j | vraie vérification indépendante |
| 8 | §4.5 `CLAUDE.md`, §3.5 version unique, §2.4 traces | 2 h | flux de travail |

L'ordre compte : les points 3 et 4 sont des filets de sécurité à poser **avant** les gros déplacements (5 et 6).
