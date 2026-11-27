# Audit UX/UI — OoT Remake Randomizer — 25/11/2026 (v0.8.4, branche `feature/audits-2026-11-25`)

Complète [AUDIT-2026-11-25.md](AUDIT-2026-11-25.md) (performance) et
[AUDIT-CODE-ARCHI-2026-11-25.md](AUDIT-CODE-ARCHI-2026-11-25.md) (code et architecture).

Périmètre : `src/oot_rando/gui` (Tkinter/ttk, thème « clam », formes arrondies en PNG nine-slice).
Méthode : application lancée sur une vraie configuration (turbo, raccourcis globaux, mises à jour et écriture
d'état coupés), captures des 8 pages à 1220×860 et à la taille minimale 1040×720, lecture du code de `gui/`,
contrastes calculés selon WCAG 2.1. Chaque changement a d'abord été montré en maquette interactive (M1–M7) et
validé avant d'être codé.

## 1. Constats

| # | Prio | Page | Constat | Maquette |
|---|---|---|---|---|
| U1 | P1 | Accueil | La tuile Save affiche « Linked » en vert alors que le tracker dit que la sauvegarde n'est pas liée à la seed. | M1 |
| U2 | P1 | Tracker | Sauvegarde non liée : les 1 088 lieux sont « Unknown » sans explication ; « Not yet » mélange bloqué et inconnu. | M3 |
| U3 | P2 | Accueil | Le titre est le hash hexadécimal (chiffres elzéviriens de Georgia) ; la puce seed est dupliquée et déborde. | M1 |
| U4 | P2 | Accueil | « Regenerate » apparaît sans dire pourquoi. | M1 |
| U5 | P1 | Nouvelle seed | « Generate and install » se trouve sous ~45 réglages, sans résumé. | M2 |
| U6 | P2 | Nouvelle seed | Aucun écart au preset visible, pas de remise à zéro par réglage. | M2 |
| U7 | P2 | Nouvelle seed | L'aide n'existe qu'au survol (ni clavier, ni tactile Steam Deck). | M2 |
| U8 | P2 | Nouvelle seed | Inventaire de départ et key rings en texte libre, erreur signalée seulement à la génération. | M2 |
| U9 | P3 | Nouvelle seed | Combobox tronquées, spinbox carrée, interrupteurs décalés de 10 px. | M6 |
| U10 | P3 | Nouvelle seed | Cartes preset utilisables à la souris seulement. | M2 |
| U11 | P2 | Tracker | Marquer un lieu demande un double-clic caché. | M3 |
| U12 | P2 | Tracker | La colonne State affiche des compteurs pour les zones ; Keys/Souls mêlés aux filtres. | M3 |
| U13 | P3 | Toutes | Le libellé « Search » change de place selon la page. | M6 |
| U14 | P2 | Spoiler | Colonnes qui débordent à 1 040 px, onglets mal alignés. | M4 |
| U15 | P3 | Tracker, Spoiler | Cartes 22 px plus larges que sur les autres pages. | M6 |
| U16 | P2 | Multiworld | Étape 3 entièrement affichée alors qu'inactive ; étape 1 validée par un drapeau global. | M5 |
| U17 | P2 | Setup | Libellé de 90 caractères, aucune validation sur place. | M7 |
| U18 | P3 | Setup, Aide | Réglages de mise à jour répartis sur deux pages. | M7 |
| U19 | P3 | My Games | Page presque vide quand l'option est désactivée. | M7 |
| U20 | P1 | Toutes | Chaque erreur et chaque succès ouvre une fenêtre modale. | M6 |
| U21 | P3 | Toutes | Barre d'état au texte périmé, contraste 4,07:1. | M6 |
| U22 | P2 | Toutes | Trois couleurs sous 4,5:1 : Done `#9aa197` (2,61:1), Partial `#9a7412` (4,23:1), texte atténué sur la page (4,07:1). | M3, M6 |
| U23 | P2 | Menu | Menu latéral inaccessible au clavier. | M6 |
| U24 | P3 | Menu | Icônes du menu absentes sous Linux (police Segoe Fluent Icons). | M6 |

## 2. Décisions

| Maquette | Verdict | Mise en œuvre |
|---|---|---|
| M1 Accueil fiable | Validée | Faite |
| M2 Nouvelle seed | À revoir → v2 (un onglet par groupe, le premier sélectionné), validée | Faite |
| M3 Tracker | Validée | Faite |
| M4 Spoiler | Validée | Faite |
| M5 Multiworld | Validée | Faite |
| M6 Retours, clavier, finitions | Validée | Faite |
| M7 Setup | Validée | Faite |

## 3. Mise en œuvre

- **Couleurs** (`theme.py`) : Done `#6b7368` (4,83:1), Partial `#86691a` (5,10:1), texte atténué `#5f6960`
  (4,93:1 sur la page). Chaque état porte aussi une forme et un mot (● ◆ ◐ ? ✓).
- **Retours** : erreurs et avertissements en bandeaux dans la page (avec « Open Setup », « Copy the details »,
  « Open the error log » quand il est récent) ; succès en toasts de 6 s ; décisions (mise à jour, sauvegardes,
  suppression, version de seed string) en bandeaux avec leurs boutons. Seule la fermeture pendant que Turbo A
  joue pour le jeu garde une fenêtre : la fenêtre se ferme, il n'y a plus de page où afficher un bandeau.
  La barre d'état n'apparaît que pendant un travail long (génération, téléchargement d'une mise à jour).
- **Clavier** : entrées du menu focalisables (Tab, Entrée, Espace, flèches), Ctrl+1 à Ctrl+9, anneau de focus
  or sur les boutons et interrupteurs.
- **Accueil** : nom de partie ou « Game of 24 Nov », hash en chasse fixe groupé par 4 ; tuile Save alignée sur
  le tracker (`TrackerSession.link`) ; bandeau de régénération avec la version d'origine et « Not now » ;
  aventure courante en bas du menu.
- **Tracker** : bandeau quand la sauvegarde n'est pas celle de la seed ; compteurs Available / Blocked /
  Unknown / Done / All ; sélecteur Locations / Keys / Souls ; barre de progression dessinée devant chaque zone ;
  case à cocher en tête de ligne (grisée quand la sauvegarde confirme le lieu) ; colonnes à la taille minimale,
  texte coupé avec « … ».
- **Spoiler** : tableau masqué par des barres grises et confirmation dans la page ; colonnes à la taille
  minimale, texte coupé avec « … » ; sélecteur segmenté.
- **Multiworld** : étape 3 verrouillée tant qu'aucune seed Archipelago n'est ouverte ; journal et chat une fois
  connecté ; étape 1 valide tant que les réglages exportés n'ont pas changé (un export d'une version
  précédente, sans trace de ses réglages, est signalé : il faut l'exporter à nouveau).
- **Nouvelle seed** : barre d'action toujours visible (preset, nombre de changements, « Reset to … »,
  « Copy seed string », « Generate and install », puis l'étape et la progression pendant la génération) ;
  groupes en onglets verticaux, un seul affiché, le premier à l'ouverture (flèches haut/bas) ; recherche (`/`)
  dans tous les groupes avec le nombre de résultats par onglet ; mention « changed » et ↺ par réglage, nombre
  de changements par onglet ; le ⓘ déplie l'aide sous la ligne (clic, Entrée, Espace) ; inventaire de départ
  en étiquettes avec suggestions, nom inconnu signalé tout de suite (key rings vérifiés en quittant le champ) ;
  presets en groupe radio au clavier ; après génération, un toast « Open the tracker ». Les libellés passent à
  la ligne selon la place laissée par les contrôles (rien n'est coupé à 1 040 px). Les deux réglages
  généraux du groupe Open world (forêt ouverte, skulltulas de nuit) ne font pas partie des presets : ils ne
  portent pas la mention « changed ».
- **Setup** : chemins vérifiés sous leur champ, émulateurs supplémentaires dans « Advanced », une seule carte
  Updates, interrupteur My Games (l'entrée de menu n'apparaît que s'il est activé).

## 4. Limites

- Vérifié sur captures et par script (Windows, 1220×860 et 1040×720). Rien n'est validé en jeu.
- Les icônes Canvas du menu ont été vérifiées en simulant l'absence de la police d'icônes, pas sous Linux.
- Le contenu des seeds ne change pas : `GENERATOR_VERSION` est inchangé.
