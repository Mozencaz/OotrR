# Étude : saut des cinématiques et dialogues (OOTRR → notre projet)

Source : `github.com/ootrando/ootrr` @ 06cc58f (2026-11-20), Rust. Même jeu (remake Switch 1.1.1),
mêmes formats (bfevfl, RSDB, AINB). Fichiers clés : `randomizer/core/src/story_skip.rs` (2 588 l.),
`flow_extra/analyzed.rs`, `open_world/skips.rs`, `malon_song.rs`, `qol/skip.rs`, `short_get.rs`,
pipeline dans `slice/edit.rs` (≈ l. 395-450).

> **Licence** : OOTRR est en **GPL-3.0-or-later** (MIT seulement jusqu'à 0.4.0) ; nous sommes en MIT.
> Recopier/porter leur code = œuvre dérivée GPL, sauf accord écrit de relicence du propriétaire.
> Réimplémenter la *technique* (faits sur les fichiers du jeu, noms d'événements) est sans risque.

## 1. Le principe : ils ne « passent » pas la scène, ils la **suppriment**

Pas de fenêtre de saut (bouton +), pas de turbo A. Dans le flow *déclencheur*, l'appel à la scène
(`EventSystemActor.EventTransition` avec `EventName = Dm_…`) est **remplacé** par :

1. `GameDataActor.EventTriggerSetGameDataBool HavePlayedEvent.<scène> = true` (la scène compte
   comme jouée → les déclencheurs se retirent, les PNJ passent à l'état « après ») ;
2. les **écritures propres** de la scène, relues dans son fichier (`scene_writes`) : toutes les
   actions `GameDataActor` / `ChallengeSystemActor` sans sous-acteur (drapeaux, compteurs,
   étapes de quête) — **sauf** `IsGet.Item_Melody_*` (sinon chant vanilla donné en double) ;
3. les appels de sous-flows qui portent de l'état (`calls`, ex. `AllSage/MeetSheik_And_Gone`) ;
4. l'**item get standard** `Dm_SY_GetInEvent / GetInEvent_NotTurn_NotNpc` avec l'objet placé
   (`ActorName`) → Link brandit l'objet, fenêtre « Vous obtenez X », ajout à la poche ;
5. retrait du `SoundSystemActor.EventTriggerStopInGameBgm` en amont (`keep_music`) : la musique
   de zone continue.

Résultat Malon : `SubEvent_GetEponaSong` → au lieu de jouer `Dm_MelodyGet_Epona` (Malon chante,
Link rejoue), on écrit `HavePlayedEvent.Dm_MelodyGet_Epona`, ses écritures, et on lance l'item
get de ce que contient « Song from Malon ». C'est ce que montre la vidéo.

Table générique `SONG_TRIGGERS` (11 entrées) — `(check, flow déclencheur, scènes à couper, scène qui donne, checks en plus, appels)` :

| Check | Flow déclencheur | Scène donneuse |
|---|---|---|
| Song from Impa | DoorOfTime | Dm_MelodyGet_Zelda |
| Song from Malon | SubEvent_GetEponaSong | Dm_MelodyGet_Epona |
| Song from Saria | SacredForestMeadow | Dm_MelodyGet_Saria |
| Royal Family's Tomb | GimmickFlow_RoyalFamilyTomb | Dm_MelodyGet_Sun_03 (+ Sun, Sun_01, _04…_10 coupées) |
| Song from Ocarina of Time | DoorOfTime | Dm_MelodyGet_Time (+ « HF Ocarina of Time Item ») |
| Windmill | Npc_Hylia_009_Adult | Dm_MelodyGet_Storm |
| Sheik Forest / Crater / Ice | SageOfForest / SageOfFire / SageOfWater | Dm_MelodyGet_Forest / Fire / Water (+ appel AllSage/MeetSheik_And_Gone) |
| Sheik Kakariko | Dm_SY_BancChangeArrive | Dm_MelodyGet_Shadow |
| Sheik Temple | AllSage | Dm_MelodyGet_Shine |

Requiem (déclenché par la carte, pas par un flow) : la scène est gardée mais tronquée jusqu'au
grant (`patch_sheik` + `patch_requiem`).

## 2. Les trois pièges qu'ils ont résolus (et nous ?)

| Piège | OOTRR | Nous |
|---|---|---|
| **Préchargement RSDB** : un sous-flow externe absent de `GameAnalyzedEventInfo.SubFlowList` n'est jamais chargé → blocage / écran blanc | `flow_extra/analyzed.rs::cover` : recalcul transitif (`Reach::need`) pour toute ligne dont le flow a changé, aussi `ChildEventList` | **Déjà fait** : `patching/event_info.py` (`add_subflow_dependencies`, `add_child_events`) — même découverte (blanc après Gohma, 12/11) |
| **Préchargement interne au fichier** : chaque entry point bfevfl liste ses SubFlowEvents (`sub_flow_event_indices`). Un appel ajouté sans y figurer n'est pas préparé → **crash** (Bolero) | `item_get()` et `patch_song_trigger` ajoutent l'index du nouvel appel aux `subs` de **chaque entry qui l'atteint** (`entries_reaching`) | **Manquant dans `give_gift_after`** (qol_patches.py:1519) : n'actualise pas `_sub_flow_event_indices`. Fait seulement dans `ap_mailbox`/`chest_flags` pour leurs entrées neuves. Suspect plausible des échecs « cadeau après cinématique » |
| **Réglages d'événement** : la ligne `EventSetting` du déclencheur (caméra, NoPause, son) peut empêcher l'item get | `plain_row` : copie `EventBaseSetting`, `EventSettingComponentList`, `EventSoundSetting` depuis la ligne `KokiriForest_ArriveLostWood` (pont de Saria, validée) vers la ligne visée (fait pour Light Arrows, Requiem) | Rien d'équivalent |

Autres détails utiles :
- **Objets sans animation de brandissement** (ocarinas, chants) : `held()` remplace l'acteur par
  sa forme « pickup » puis ajoute l'objet à la poche après (`ocarina_hold`). Nous avons
  `item_forms.py` qui traite déjà ce cas pour 0155 / MelodyGet_Time.
- **Progressifs / clés** : l'item get est enveloppé par les tests de palier
  (`progressive::wrap_grant_as`) ou suivi du crédit de donjon (`gift_keys::credit`).
- **Malon adulte** : `malon_song.rs` patche l'AINB `LonLonRanch_Child_NoTerrain_Prefab_5286`
  (zone `Area_9a63`) pour que la zone de leçon soit pilotée par `HavePlayedEvent.Test_Npc_Hylia_049_Adult_D_N`
  (posé lors du don) plutôt que par l'étape `Get_Epona/ReadyForGetEponaSong` → enseignable
  quel que soit l'état de la quête, une seule fois.
- **Course d'Epona** (`open_world/skips.rs`) : nouvel événement `OOTRREponaOwn` (ligne RSDB copiée
  de `AppearPierre_ByScarecrowSong`, SubFlowList vidée) qui fait `EventCopyAndRegisterOwnedHorse`
  au 1er chant d'Epona adulte.
- **Bouton +** (`qol/skip.rs`) : `DisableSkip…SkipSetting.bgyml` `IsDisableSkip → false` (tout) ou
  retrait du composant dans les listes Dm_Kokiri_0000 / Dm_StaffCredit_0005. Nous avons déjà
  l'équivalent (`unlock_cutscene`, `LOCKED_CUTSCENES`).

## 3. Autres scènes qu'ils coupent (même boîte à outils)

- Pont de Saria (`Goto_HyruleCastle` / `KokiriForest_ArriveLostWood`) : 0150 + 0155 → drapeaux + item get, Link reste sur le pont.
- Arbre Mojo (forêt ouverte) : rencontre 0070/0075 + 1re entrée écrites au nouveau jeu (`deku()`).
- Temple du Temps enfant, 1re pioche de l'épée (→ `Market_Child_Field_ChildToAdult`), Rauru → item get.
- Fins de donjon (`Dm_SY_BancChange_EscapeDungeon`, 16 scènes `CUT_SCENES`) : pierre/médaillon donné **dans la salle du boss avant la téléportation**, arrêt à la Chambre des Sages sauté.
- Médaillons des sages : écran blanc + répliques coupés (`cut_white_screen`).
- Darunia (rubis, bracelet, danse), Light Arrows (6 timelines), fuite de Zelda (`Dm_HrlField_0060`), hiboux (champ, rivière, bois perdus), Grandes Fées (montée/descente coupées).

## 4. Transcription chez nous — plan proposé

Briques existantes réutilisables : `event_patch._flow/_snapshot`, `qol_patches._predecessors`,
`give_gift_after`, `event_info.add_subflow_dependencies`, `song_adapter.SONG_EVENTS`,
`item_forms` (formes pickup), `progressive`, `key_adapter`.

1. **Corriger `give_gift_after`** : après insertion, ajouter l'index du `RandoGiftGet` à
   `_sub_flow_event_indices` de toutes les entry points qui l'atteignent (parcours depuis
   `main_event`). Petit, testable hors jeu, probablement utile tout de suite.
2. **Nouveau module `patching/scene_drop.py`** :
   - `scene_writes(read_flow, scene)` → actions GameData/Challenge de la scène (hors `IsGet.Item_Melody_*`) ;
   - `drop_scene(raw, scene, gives, extra_writes, calls)` → remplace chaque `EventTransition`
     vers `scene` par la chaîne *HavePlayed → écritures → appels → item get(s)*, met à jour
     les `sub_flow_event_indices`, retire les `StopInGameBgm` en amont, vérifie par `_snapshot` ;
   - table `SONG_TRIGGERS` (§1) — **pilote : Malon seule** (`SubEvent_GetEponaSong`).
3. **Brancher sur `song_adapter`** : aujourd'hui on garde `Dm_MelodyGet_*` et on remplace son
   grant. Avec l'option, le contenu du check part dans l'item get du déclencheur ; le patch du
   grant dans la scène devient inutile pour ces checks (la scène n'est plus jouée).
4. **RSDB** : passer les flows modifiés à `event_info.add_subflow_dependencies` (Dm_SY_GetInEvent
   + ses dépendances) ; option `plain_row` si l'item get ne s'affiche pas.
5. **Logique / AP** : aucune règle ne change (même check, même lieu). Le check AP reste détecté
   via le drapeau de collecte posé après l'item get (`add_collection_markers`).
6. **Option** `drop_story_scenes` (GUI + Settings), ajouter progressivement : Malon → Saria
   (Bosquet) → Impa → Tempête → Soleil → Sheik ×5 → Saria pont → fins de donjon.

Risques connus : flows déclencheurs différents de ceux d'OOTRR si notre build modifie déjà
le flow (`story_fixes.second_malon_after_talon` touche `SubEvent_GetEponaSong` → appliquer
dans le même passage) ; Malon adulte (zone AINB) ; rien de tout ça n'est validé en jeu chez
eux non plus pour plusieurs entrées (« experimental, untested » dans leur README).

## 4 bis. Implémenté (branche feature/song-lesson-skip, 2026-11-20, non validé en jeu)

**Leçons de chant** — option `skip_song_lessons` (GUI, carte « Cutscenes and dialogues »),
`patching/song_lessons.py`, générique sur 10 leçons : Impa (`DoorOfTime`), Malon
(`SubEvent_GetEponaSong`), Saria (`SacredForestMeadow`), tombeau royal
(`GimmickFlow_RoyalFamilyTomb`), moulin (`Npc_Hylia_009_Adult`), Sheik forêt / cratère / caverne
de glace (`SageOfForest/Fire/Water`), Kakariko (`Dm_SY_BancChangeArrive`), temple (`AllSage`).
Chaque transition vers la leçon devient `HavePlayedEvent.<leçon>` → (attente de fin de
chargement si arrivée) → `Dm_SY_GetInEvent/GetInEvent_NotTurn_NotNpc` (objet lu dans la scène
patchée) → marqueur RandoCheck → état de la leçon relu dans la scène vanilla (`scene_state` :
écritures GameData / quête sauf `IsGet.Item_Melody_*`, appel `AllSage/MeetSheik_And_Gone`).
`StopInGameBgm` juste avant : contourné (la musique continue). Tombeau : la leçon `Dm_MelodyGet_Sun`
et les vidéos `Sun_01…_10` réduites à leur `HavePlayedEvent`. Appels listés dans chaque entry
qui les atteint ; RSDB complété par `complete_event_info`. Non faits : Chant du temps (donne
aussi l'ocarina, sans pose), Requiem (lancé par la carte).

**Timelines** — option `skip_story_timelines`, `patching/timeline_skip.py`. Recensement exact :
90 lignes `EventSetting` à `TimelineFileName` lancées par un flow (le « 125 » du §5 venait d'un
comptage plus large : fichiers sans flowchart, vidéos, entrées d'autres flows). Aucune n'écrit dans la sauvegarde.
86 sites / 75 scènes coupés dans 21 flows (table `SITES`, reconstruite par `scan`, test de
cohérence) ; transition → `HavePlayedEvent.<scène>` (+ `EventEventFadeIn` si un fondu au noir la
précède, 3 cas). Gardées : titre / générique / fin et ce qui y mène, intros de boss (présentation
de combat, musique), warps d'acteurs, équipement, heure ; scènes en tout début d'événement
(intro du nouveau jeu sous l'écran de chargement) ; noir avant sans retour de fondu (2 sites).
Appliqué en dernier, juste avant `complete_event_info` ; rejoué en fin de boucle par verify.
Heure du jour (20/11) : les timelines qui règlent l'heure sont coupées aussi ; le flow règle la même
heure à la place (`EventWorldManagerController.EventTrigger_SetTime`, action des flows du chant du
soleil et des sorties de donjon ; table `REPLAYS`, reconstruite par `scene_replays`) : Kaepora dans la
plaine 7 h 30 (déjà contourné en mode complet par `owl_advice` : site laissé tel quel), fuite de
Zelda 12 h, Cocorico en feu 0 h, Cocorico de nuit 22 h, fontaine Zora 12 h.
Équipement (20/11) : dans les timelines, `EventTriggerEquipmentUserRequestChangeState` est toujours
`DynamicEquipmentSlot 0, EquipmentState 1` (épée en main), en **clip** qui finit au plus tard avec la
scène (comme les bottes temporaires) : ni poche ni équipement sauvegardé ne changent. Pas rejoué (il
sortirait l'épée en jeu, même non possédée) ; la scène n'est plus gardée pour ça (`scene_only`). Idem
pour les warps des acteurs de la scène (`Dm_Locator`). Aussi coupés : `Dm_TimeTemple_0135`,
`Dm_DeathMtTrail_0020`. Restent gardés : épouvantails du lac (vrais acteurs), `Dm_TimeTemple_0050`
(début d'événement), titre / générique / fin.
Intros de boss (20/11) : coupées aussi (11 : Gohma, Dodongo, Barinade, Ganon spectral, Volvagia,
Morpha, Bongo Bongo, Nabooru Iron Knuckle, Kotake & Koume, Twinrova, Ganondorf). Leurs actions sur
le monde sont rejouées à la place, dans l'ordre de la timeline (`REPLAYED` / `REPLAYS`, comme l'heure) :
`EventDungeonBossSetConsiderBattlePresentation` sur le boss (le boss rush la lance ainsi sans
timeline, `DreamBossStage/Rematch_*`), `EventTriggerSoundStartBossBgm` (et `StopBGM` pour Twinrova).
Gardée : Ganon (`Dm_FinalBattle_BossIn`, warps des gravats de la tour).
Requête « scène passée ? » (20/11) : `EventQueryIsEventSkipedMostRecent` posée après une scène coupée
n'a plus de réponse sur elle (« la plus récente » = une autre scène). Elle prend le cas « passée » (0),
prévu par le jeu pour une scène écourtée : intros de boss → musique + `Get_StoneOfForest/BossAppearSkip_*`
(caméra), autres → fondu ou remise de caméra. 7 sites (dont 3 déjà coupés avant : `Dm_Kokiri_0150`,
`Dm_Kokiri_0030`, `Dm_SpiritTemple_0020`). Site gardé si la requête est aussi atteinte par un autre chemin
(aucun aujourd'hui).

**Saut automatique du +** — option `auto_skip_cutscenes`, `patching/skip_auto.py`. Chaque fenêtre
`SkipAcceptStart … SkipEnd` n'est jamais ouverte : ce qui menait au début va directement à la suite
de `SkipEnd`, sur le cas « sauté » (0) de `EventQueryIsEventSkipedMostRecent` (aussi les requêtes
posées plus loin, si seul un passage par une fenêtre y mène). `SkipEnd` en tête d'une entrée locale
appelée (fontaines) : l'appel est gardé, l'entrée démarre après. Fondu d'entrée ajouté si la fenêtre
en contenait un ou si `SkipEnd` avait `FadeInType ≠ 0` ; attente de fin de chargement si la fenêtre
ouvrait une entrée. Couvre les fenêtres du randomizer (`skip_locked_cutscenes`, construites aussi
avec l'option : 99 fenêtres / 65 flows, écritures rejouées) et 5 fontaines vanilla (`NATIVE_FLOWS`,
`scan`). Gardés avec leur + : fontaine de Din (requêtes de saut atteintes sans fenêtre), temple de
l'Eau 0020/0021/0022 (deux `SkipEnd` selon le niveau d'eau ou `SkipEnd` hors fenêtre). Pas les
timelines (le moteur les saute sur +, aucun réglage « saut auto » : seul `DisableSkip` existe),
ni les dialogues. Appliqué juste avant les timelines ; rejoué juste avant elles par verify.

**Dialogues PNJ sans choix** — option `skip_npc_dialogues`, `patching/npc_dialogue_skip.py`, liste
blanche par zone (`ZONES`). Pilote : forêt Kokiri, 30 flows (tous les Kokiri enfant/adulte, Mido,
Saria, Fado, pousse Mojo ; pas la boutique). Retirées : les répliques `EventTalk` /
`EventTalkIgnoreSameTalkAS` à `ChoiceNumber` = 0 (entier ; un `ChoiceNumber` lié à un argument
d'entrée compte comme un choix) qui ne suivent ni une réplique à choix ni un `EventQueryTalkChoice*`
(la réponse à ce que le joueur a demandé reste). Aussi retirés : `EventCloseMessageDialog` qu'aucune
réplique gardée n'atteint, `EventTriggerBecomeSpeaker` qui ne mène à aucune réplique gardée. Une réplique
gardée qui laissait sa boîte ouverte (`IsCloseDialog` false) pour une réplique retirée la ferme. Gardée
aussi : une réplique (ou un de ces événements) sans suite qui commence une entrée ou une branche de fork
(sinon vide ; 4 cas). Parcours avec retour des sous-flows locaux. 657 répliques sur 30 flows ; item gets,
écritures, animations inchangés ; aucun sous-flow neuf (rien pour le RSDB). Appliqué juste avant
`auto_skip_cutscenes` ; rejoué au même point par verify (seed de test + verify OK, 20/11).
Prochaines zones à ajouter après essai en jeu de Kokiri.

## 5. Généralisation à TOUT (recensement du jeu, 2026-11-20)

Script : scratchpad `census/census.py` (lit le .nup, 914 flows, 2 380 lignes EventSetting).

**Cinématiques** (265 scènes `Dm_*` distinctes lancées par `EventTransition`) :

| Type | Nombre | Faisabilité de la suppression générique |
|---|---|---|
| Timelines pures (pas de flowchart, donc aucune écriture) | 125 | **Facile** : transition → `HavePlayedEvent.<scène>`. Seul risque : position de Link / acteurs que la timeline déplaçait. 36 flows les lancent (Defeat_Ganon 18, EscapeDungeon 14, TitleEvent 13…) |
| Flowcharts `Dm_*` sans mécanisme ni équipement ni zone | 179 / 202 | **Automatisable** : drapeau joué + écritures relues + item get si objet + rejouer la dernière téléportation du joueur (165 en ont une) |
| Flowcharts avec mécanisme (`EventRequestActor.SetEventBool`), équipement ou changement de zone | 23 / 202 | **Au cas par cas** (vanne de l'Arbre Mojo, épées, âge, fins de donjon…) |

**Dialogues** : 404 flows parlent, 10 374 répliques dont 1 268 à choix (12 %).
- Côté PNJ (`Npc_*`, 240 flows) : 209 contiennent au moins un choix quelque part, mais par
  entrée/réplique la majorité est linéaire → supprimer réplique par réplique, pas flow par flow.
- Règle : retirer un `EventTalk` si `ChoiceNumber == 0` ET aucun Switch sur la réponse en aval ;
  enlever aussi les `CloseMessageDialog` / `BecomeSpeaker` orphelins (crash `MessageDialogStyle`
  `NoActor` déjà vu le 11/11 avec les fenêtres de saut).
- À garder (liste d'exclusion) : indices (pierres à potins, PNJ indices), prix des boutiques,
  règles des mini-jeux, messages d'objet (`GetPouchContent`, `Dm_SY_*`), Navi, panneaux.
- Ce qui reste après : animations / caméra sans texte → à tronquer aussi sinon PNJ muet qui gesticule.

**Ordre conseillé** : (1) Malon pilote ; (2) timelines génériques ; (3) Dm_* « sans monde »
automatiques avec rapport de couverture ; (4) dialogues PNJ sans choix par liste blanche de
flows, testés zone par zone ; (5) les 23 cas durs.
