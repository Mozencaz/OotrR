# Full randomizer — design notes

Every ticked category is shuffled together: a hookshot can come out of a bush, a
skulltula token out of a pot or a shop, a heart piece out of a skulltula. Generation
and logic are checked statically (`python -m oot_rando verify`); items marked
"experimental" in the settings still wait for the in-game pilots listed at the end.

## Sources (Items tab)

| Option | Source | Write into the game |
|---|---|---|
| **Chests** (`shuffle_chests`) | every chest, major items included | `Dynamic.Drop__DropActor` of the chest |
| **Gold Skulltulas** (`tokensanity`: dungeons / overworld / all) | 100 skulltulas = the 100 AP locations | `Drop__DropActor` added to the enemy (native instance parameter); every item but the token is dropped by a pickup built on the token (see below) |
| **Shops** (`shopsanity`: 1 to 8 items per shop, random 1–4, or Whole shops) | 64 stalls across 8 shops, masks excluded | stall `Gyaml`; fixed price of 10 rupees; bought once |
| **Freestanding items** (`shuffle_freestanding_items`) | non-respawning heart pieces, rupees and hearts | item `Gyaml` |
| **NPC gifts and minigames** (`shuffle_npc_gifts`) | 29 gifts (`extra_sources.NPC_GIFTS`) | item parameter of the event (`ActorName`, `ReveiveItem`…) via `evfl` |
| **Bosses and dungeon rewards** (`shuffle_boss_rewards`) | 3 stones, 6 medallions (Rauru's included), 8 boss heart containers | hand-over event (`GetPouchContentByActorName`); placed heart container `Gyaml` |
| **Great Fairies** (`shuffle_great_fairies`) | Din, Farore, Nayru, magic, double magic, double defense | `ActorName` of the fairy cutscene |
| **Quest rewards** (`shuffle_quest_rewards`) | Saria's ocarina, Ocarina of Time, Zelda's Letter (only with a shuffled child trade quest: it takes the Weird Egg's slot), Light Arrows, Biggoron Sword, Ruto's Letter (the bottle in Lake Hylia) | `ActorName` of the cutscene; ocarinas: also the silent pouch add; Ruto's Letter: `Gyaml` of the bottle pickup |
| **Pots, crates, beehives, bushes, rocks** | explicit-drop objects (rupee, heart); empty rocks (≈ 195, no drop table) | existing `Drop__DropActor`, or added on rocks whose pack declares it as an instance parameter |
| **Trees** (`shuffle_trees`) | 52 `Obj_Tree_*` (Hyrule Field 39, Kokiri Forest 8, castle, Kakariko, market); trees with an explicit `None` drop table and Colossus palms stay vanilla | `Drop__DropActor` added (instance parameter of the tree pack); falls when Link rolls into the tree |
| **Business Scrubs** (`shuffle_scrubs`) | single-sale remake scrubs only: stick upgrade (`LW Deku Scrub Near Bridge`), nut upgrade (`LW Deku Scrub Grotto Front`), field and crater heart pieces | `ActorName` and `Price` of each `SimpleShopSub_Scrub_Business_OneTime` call in `Enemy_Scrub_Business_Common` |

| **Songs** (`shuffle_song_items`) | the 12 song cutscenes (`Dm_MelodyGet_*`) | silent add of the cutscene (`GetPouchContentByActorName`); see *Songs* below |

Never changed: the whole adult trade quest up to the Biggoron Sword, the
child trade (egg, letter, masks), cows, the Gerudo card, beans, the lake Fire
Arrows. Repeatable sources (pots, crates, beehives, bushes, rocks, trees) give their
shuffled reward only once (`repeatable_adapter.py`), then go back to their vanilla loot.

## Starting inventory, item pool, removed keys

* **Starting inventory** (`start_inventory_from_pool`, AP name): items held from the
  start, given silently at the end of the opening (`event_patch.add_pouch_items`). A
  copy found in the item pool is replaced by rupees; progressive copies take the
  lowest levels of their family. Songs are given the same way (`Item_Melody_*`);
  tunics and trade items have no pouch actor yet. In a multiworld, the apworld's own `start_inventory_from_pool` is used.
* **Item pool** (`item_pool_value`): plentiful (one extra copy of each major
  non-progressive item, replacing filler), scarce (at most 3 bottles, half the
  hearts), minimal (one bottle, no hearts, double defense or capacity upgrades). The
  number of shuffled locations never changes.
* **Maps and compasses "Start with", small keys / boss keys "Removed"**: the saved
  `DungeonInfo.<folder>` values are written at the end of the opening
  (`event_patch.add_start_values`, `key_adapter.start_dungeon_values`):
  `IsGetMap`/`IsGetCompass`, `SmallKeyNum` = the AP key count, `IsGetBossKey` of the
  five temples. Their chests hold rupees; the logic holds the keys from the start.
  **Not validated in game.**
* **Day/night cycle from the start**: vanilla holds the clock until Kaepora's first
  Hyrule Field arrival (`Goto_HyruleCastle_Kaepora_00`). Its saved effects
  (`HyruleField_ArriveEntrance`, `HavePlayedEvent.Dm_HrlField_0000/0005/0010`, the
  challenge menu) are written at the end of the opening, so the scene never plays
  (no black screen) and the clock runs from the start, child castle skipped or not.
  The amiibo menu it gave is a starting item, and its `Goto_HyruleCastle` `Step02`
  follows the Deku Tree escape (`owl_advice.field_step_after_escape`).
  **Not validated in game.**
* **Night skulltulas without Sun's Song** (AP logic option
  `logic_no_night_tokens_without_suns_song`): `at_night` of the GS Token locations
  needs the Ocarina and Sun's Song. Logic only: the game is not changed.
* **Night skulltulas present day and night** (application setting
  `skulltulas_always_present`, off by default, also available for an Archipelago
  patch since no placement changes): `Enemy_Skulltula_Gold_Nocturnal` is set to
  false on the 30 night-only gold skulltulas (18 maps,
  `qol_patches.NOCTURNAL_SKULLTULA_MAPS`). The logic is unchanged (it still expects
  the night or Sun's Song), so the game is only more permissive. **Not validated in game.**
* **Fast chests** (`fast_chests`): same patch as the "chests without cutscene" skip.

## Songs (`song_adapter.py`)

Songs are pouch actors (`Item_Melody_<song>`, a rupee model as placeholder). Each
song cutscene teaches its melody through `Dm_SY_Ocarina/LearningOcarina*` (the NPC
plays it, the player plays it back, then `LearningOcarinaPlayAuto`/`…ForSeek` adds
the melody of the current `MelodyType`) and also adds it silently
(`GetPouchContent/GetPouchContentByActorName`).

* **Modes**: vanilla; shuffled among the song locations; song locations and
  dungeon rewards; anywhere a cutscene can give them (song locations, dungeon
  rewards, great fairies, story rewards; the matching options must be on); anywhere,
  chests and pickups too (`everywhere`: also chests, freestanding spots, pots, crates,
  gold skulltulas… when shuffled). Never in shops or NPC gifts. Never at Queen Gohma
  either (her gift is given back after the cutscene with a pose).
* **Harp in the song's colour** (`song_models.py`, `everywhere` only): a song in a
  chest or as a pickup is held up or stands in the world, so it gets the model of
  Sheik's harp. Each placed song has its own copy of the harp
  (`Model/Item_Harp_<song>.Item_Harp_Sheik.bfres`) whose material `Mt_Harp_Sheik`
  has its six colour parameters (`ns_param_color0`–`5`, white in the game) set to the
  song's colour of the ocarina menu; its ModelInfo and ActorInfo row name that
  project, and its pickups (`Obj_Rando_Item_Melody_*`) copy them. The pickup is
  raised by the harp's depth below its origin (0.25 m).
* **Text only**: a song is given by the silent add followed by
  `GetPouchContent/DisplayGetByActorName`, the game's get window without pose
  ("You learned Saria's Song!" and its caption; the same call Saria's ocarina gift
  uses). A pose-based get (`Dm_SY_GetInEvent/*`, great fairies) becomes the silent
  add. A source that already has its own display call (Ocarina of Time, Ruto's
  sapphire) gets no second window. Received from another world: same hand-over.
* **Every song cutscene** (songs shuffled or not): the NPC no longer plays the melody
  to memorise (`LearningOcarinaPlayExample` only sets the melody, `RandoLearningPrepare`);
  the player still plays it back, then Link's tune (Sheik's duet for the warp songs)
  plays the notes just input: it stays silent without them (tested in game 19/11).
* **Song location giving another item**: the end of the teaching plays Link's tune
  without adding the melody (`Rando*` entries added to `Dm_SY_Ocarina`), the placed
  item is added silently and its get window shown. Sheik in Crater's direct write of
  `IsGet.Item_Melody_FireBolero` follows the placed song (or is removed). The NPC's
  lines still speak of the vanilla song.
* **Windmill**: the adult windmill man plays the Song of Storms cutscene only while
  `IsGet.Item_Melody_StormSong` is false; his four checks read the check's own
  collection flag instead. The other song cutscenes start from quest steps.
* **Not validated in game.**

## Big Poes to bring back (`big_poes.py`)

`big_poe_count` (1 to 10): the collector (`Npc_Hylia_048_BottleShop`) compares the
points held before a sale (100 per Big Poe): `Event70` against 100 × (N − 1)
instead of 900, `Event265` lets those points through. **Not validated in game.**

## Item forms and derived actors (`item_forms.py`)

The remake gives an item through three kinds of actors: `Item_*` (chest, event),
`Obj_*` (picked up from the ground, dropped by an enemy or a pot) and `Shop_*`
(stall). When the native form is missing (hookshot on the ground, heart piece in
a shop…), the generator builds `Obj_Rando_<item>` (behaviour of the gold token,
model and content of the item) or `Shop_Rando_<item>` (behaviour of an arrow
stall), with their RSDB rows and RESTBL entry. AP "Buy …" purchases never leave
the shops. Modes 1–8 and random keep at least one copy of each purchase used by the
logic on sale; Whole shops shuffles all 64 slots and relies on world refills instead.

Gold skulltula drops: the skulltula hands its saved `Bool64bitKey` row to its drop
(blackboard `GoldTokenGmdHash`), and only the token's AI writes it, when the get
event of the pickup ends. A native rupee, heart or ammo pickup never does: the
skulltula came back and its check was never counted. Every skulltula drop but the
token is therefore built on the token: `<native pickup>_GS` (e.g. `Obj_Rupee_Red_GS`,
names of REALAZK's token kits, at most 25 characters) or `Obj_Rando_<item>`. Their
pouch sets `PlayGetEventManyTimes` and `IsPlayGetEventPouchMax`, so the get event
plays on every pickup, even at full capacity. The tracker reads the same row.

Pots, bushes, rocks, crates, beehives and trees: their first-collection pickup
(`Obj_RandoOnce_*`) is built on a native falling drop (`Obj_DekuNut`), not
on the token. The token's AI keeps it standing where it spawns
(`ExecuteKeepStandingPosture`), so an item shaken from a tree or out of a pot thrown at
a wall hung in the air. Native drops share `Obj_Item_Base`'s `DropItem` AI
(`ExecuteDropBound`: fall, bounce, land), physics, blackboard and death.
The source itself keeps its map entry, but for its drop: no `Presence` and no vanilla
copy. The game remembers a broken pot, rock, crate, bush or beehive by its hash (a
`Bool64bitKey`) until the scene changes; a copy under another hash, or a source under a
`Presence` condition, came back while the area stayed loaded. Each pickup runs its own
clone of the `DropItem` AI: when it spawns, it reads its check flag and deletes itself
once the check is collected. A collected source therefore drops nothing afterwards
(not its vanilla rupee or heart).

## Dungeon-specific keys (`key_adapter.py`)

Remake keys are generic: `Item_Dungeon_SmallKey`/`BossKey` are credited by native
code to the dungeon Link is in. Each dungeon's state lives in the saved GameData
structure `DungeonInfo.<folder>` (RSDB `DungeonParam` rows): `.SmallKeyNum`,
`.IsGetBossKey`, `.IsGetMap`, `.IsGetCompass`.

* **Key rings = All dungeons** (required as soon as small keys leave their place):
  one `Item_KeyRing_<dungeon>` per dungeon (Forest 5, Fire 8, Water 6, Shadow 5,
  Spirit 5, Well 3, Training Ground 9, Ganon's Castle 2 keys). Small key chests
  receive other items.
* **Boss keys = Any dungeon / Anywhere**: `Item_BossKey_<dungeon>`.
* Items are built like souls (key item template of the Forest Medallion, 3D model
  of the native key, texts in 16 languages, `IsGet` flag).
* Effect: every item get ends with `ActionGuide/ActionGuide`; this flow first checks
  each key of the seed (`IsExistInPouch`): key ring not applied yet →
  `AddOrSubGameDataInt DungeonInfo.<d>.SmallKeyNum +N` then flag `RandoKeyRing.<d>`;
  boss key → `DungeonInfo.<d>.IsGetBossKey = true`.
* Logic: a key ring counts as every small key of its dungeon (`Logic.bundles`).
* **Not validated in game**: opening a door with a key ring found outside the
  dungeon, the boss door with a key found elsewhere.

## Progressive items (`progressive.py`)

Issue #23: a copy placed with a fixed level could be found before the lower one (the
large bullet bag before the slingshot), and a later lower level could take capacity
away. Every copy is now a *token* that becomes the next level in game:

* Each copy placed in this world is its own pouch actor `Item_Prog_<family>_<n>`
  (built like the souls: Forest Medallion key item, model of the family's first
  level, texts, `IsGet` flag), plus a saved flag `RandoProg.<token>`.
* So are the unshuffled sources of a fixed level (a chest or a freestanding item
  left in place, Darunia's bracelet: `STATIC_TIER_SOURCES`): found after a shuffled
  copy, their own level could be lower than the one Link holds. The other native
  sources (bag and wallet upgrades of NPCs) already give the next level.
* Converter: `ActionGuide/ActionGuide` (end of every item get) and
  `ActionGuide/ActionGuideForShop` (shops) first call the entry `RandoProgressive`:
  for each token got (`IsGet`) and not converted yet, set its flag, take it out of the
  pouch (as trade items are) and give the level above the highest one held, through
  `GetPouchContent/GetPouchContentByActorName` (get window, no pose; the ocarinas
  too). Levels are tested on their pouch names (`Weapon_Range_Bow`,
  `Armor_Child_Gauntlet_Goron`…) and the magic meter on `IsGet.Item_FairyBless_*`.
  Holding the last level gives it again.
* Gifts whose flow never reaches `ActionGuide` (boss rewards, Saria, Darunia…)
  call `RandoProgressive` right after the gift (`RandoProgAfter_<event>`). A token got
  any other way is converted at the next item get.
* Archipelago: progressive copies can go to any world. Copies received from other
  worlds go through the mailbox, which gives the same next level (`ap_mailbox`).
* **Not validated in game**: the token get then the level's window, a token in a shop,
  a token from Saria, a boss or Darunia, the take out of the pouch.

## Enemy souls (`soul_adapter.py`)

Modes `bosses`, `regional`, `all` (46 souls, 845 enemies). `Presence` is added to
enemies without an existing condition; `Item_Soul_*` items (key item template of
the Forest Medallion, 3D model of the Poe soul); RSDB rows `ActorInfo`,
`GameActorInfo`, `PouchActorInfo`; saved flags `IsGet.Item_Soul_*`; RESTBL entries;
get texts (`<actor>_Name/_Caption/_GetMessage/_GetCaption` in
`ActorMsg/PouchContent.msbt` of the 16 languages, via `msbt.py`) — without them
the dialogue box stayed empty and blocked the game. A new save is required.

## Logic safety rules

- A chest without a reliable match never receives an item useful to the logic.
- A group of k interchangeable chests is only reachable once **all** its k AP
  locations are reachable.
- Skulltulas, stalls: conservative group per zone. The remake puts Lake Hylia and
  Lon Lon Ranch in the Hyrule Field maps; the matching accounts for it.
- Pots, bushes, rocks, crates, beehives, trees, lying rupees: rule of the **whole zone**.
- A source found only in the child maps (`*_Child_*`) or only in the adult maps
  (`*_Adult_*`) is collected at that age: each of its AP locations that this age can
  ever reach must be reachable **at that age** (`Child|`/`Adult|` members, the AP
  `is_child`/`is_adult` rules). Being adult needs `Time Travel` (Door of Time: Song
  of Time, which the child gets for the three spiritual stones). A source with no
  such location only receives filler. Its tracker name ends in `(child)`/`(adult)`;
  an object on both maps under one hash is one check for either age.
- NPCs: exact AP location; for the man on the roof (adult only in the remake) and
  the lake lab (child only), the age rule is added.
- A group holding a location that the AP rules never reach only receives filler.
- Progressive items (hookshot/longshot, gauntlets, bomb bag, bow, slingshot,
  wallets, scales…): each copy gives the level above the one Link holds, so the
  n-th copy found is level n, as the AP logic counts them (see *Progressive items*
  below). `progressive_order` and `progressive_strict` no longer change anything.
- Souls: entering a dungeon requires the souls of the families present; a boss
  room requires the boss soul; conditional chests require the souls of their map.
  Excluded from souls: Poes, Stalchildren, Leevers, Gerudo, gold skulltulas,
  Ganon, business scrubs, story enemies.

### Remake differences fixed in `logic/world/remake.json`

| Location | OoTR/AP | Remake | Fix |
|---|---|---|---|
| `Links Pocket` (Light Medallion) | given at start | given by Rauru after the first pull of the Master Sword | `Time_Travel` rule |
| Kokiri shop | full stock from the start | reduced stock before the Deku Tree | `open_kokiri_shop` / `release_kokiri_shop_goods` patches |
| `LW Near Shortcuts Grotto Chest` | grotto under a rock | ledge of the scrub room, only reached by the adult bean platform near the bridge | `is_adult and at('Lost Woods', can_plant_bean)` |
| `Song from Saria` | Zelda's Letter | learnt during the Fire stone quest (after Darunia) | letter + Darunia's chamber as child |
| `here(...)` with `can_plant_bean` | current age | the child plants, the adult uses | becomes `at(<region>, ...)` |

Kokiri Forest positions (`extra_sources.kokiri_spot`): copies in the village (before
Mido, outside the grotto) use `KF Links House Pot`, at the age of their maps (child
copies at start, adult-only copies once the adult reaches the forest); bean platform
rupees use `KF Bean Platform Red Rupee`.
Mido's house: the 4 grouped chests are matched to Mido's 4 AP chests.

## Mechanism cutscenes are never skippable

Skipping the switch cutscene that lowers the water in the Deku Tree left the water
high (game blocked). These cutscenes send `EventRequestActor.EventTriggerSetEventBool`
to a scenery object (valve, grate, appearing chest…) that plays its change while
the camera shows it; the skip interrupts it and replaying it afterwards does not
restart it. A cutscene entry sending such a signal (directly or through a sub-flow)
gets no skip window.

## Rules audit (`python -m oot_rando audit`)

```
python -m oot_rando audit [game.nup] [--no-fixes] [--matching scene|strict] [--output folder]
```

Read-only, about 4 s. Report: `build/audit/rules_audit.md` (+ `.json`).

1. **Clues** for each matched location (chests, skulltulas, heart pieces, heart
   containers): nearby obstacles (`audit_rules.HINTS`: hookshot target, cracked
   wall, web, Song of Time block, invisible chest, bean soil, hammer or eye switch,
   red ice…), links followed one step, map age (`_Child_`/`_Adult_`), chest event
   (`GetEventName`).
2. **Necessity test** on the compiled logic: everything is given, the clue's items
   are removed (region events too). If AP still reaches the location in the
   remake's age, it is a mismatch. Alternative clues (explosives *or* strength)
   that block together are not reported.
3. **Control**: `--no-fixes` alone finds the Lost Woods chest again (bean soil via
   `DestinationAnchor`, 2.9 m); with the fixes it disappears (`tests/test_audit_rules.py`).

Nothing is applied automatically: each line is to be confirmed before adding a rule.
Limits: purely geometric obstacles (no actor) are invisible; NPCs, songs and quests
outside the maps are not covered (except chest events).

## In-game pilots still to do (new save)

1. **Chests**: a major item comes out of a rupee chest; event chests (Dampé, Sheik,
   Nabooru…) continue their story; persistence after save/reload.
2. **Souls**: Queen Gohma does not appear without her soul; the soul item is
   received from a chest; the boss appears afterwards.
3. **Skulltula**: a gold skulltula carrying another item (rupee, arrows, heart piece…)
   drops it (and not a token too); after the pickup the skulltula stays dead after a
   reload and its check counts in the tracker.
4. **Derived freestanding item** (`Obj_Rando_*`): visible model, pickup, name, no respawn.
5. **Shop**: a `Shop_Rando_*` item shows (name, price 10), the purchase gives the item.
6. **NPC**: e.g. Dampé's digging or bowling gives the placed item and the NPC continues.
7. **Dungeon reward**: after Gohma, the Deku Tree gives the placed item and the
   story (Mido, the Tree's death) continues.
8. **Great fairy / quest**: the right item is given; a replaced Saria ocarina does
   not also add the vanilla ocarina.
9. **Boss heart container**: the placed item (visible on entering the room) can be picked up.
10. **Progressive items**: find the higher copy of a family first (e.g. a slingshot
    token after the bullet bag was expected): the first one found gives the slingshot,
    the next one the bag; a native chest found later never takes capacity away.
11. **Songs**: a song cutscene giving another song shows only its text and adds the
    right song (menu, playable); one giving an item does not add its melody; no NPC
    plays the melody to memorise, the player plays it back, Link's tune plays; a song
    at a great fairy or a dungeon reward shows its text, nothing held; the windmill
    still plays its cutscene once Song of Storms was found elsewhere.
12. **Big Poes**: with 3 to bring back, the collector rewards the third sale.
13. **Skip child Hyrule Castle** (`skip_child_zelda`): new game without Zelda's Letter
    and Lullaby (found elsewhere, the lullaby possibly as a harp in a chest); with the forest closed, the Kokiri guard and Mido still wait for the Deku
    Tree; Saria teaches her song in the meadow; the Kakariko gate opens with the letter;
    Talon and Malon are at Lon Lon Ranch (Epona's Song, the cucco game); Kaepora's first
    field talk does not move the castle quest back; with the three stones, Zelda flees
    and the Door of Time opens.
14. **Pickup visuals**: progressive slingshot, bow and hookshot copies use their
    native item poses. Gold Skulltula drops no longer use the skull-shaped aura.
    Items without an effect borrow the moat ocarina glow; check visibility under
    water and confirm it does not obscure the item. Resource tests pass; appearance
    still needs an in-game check.
15. **Child Death Mountain Crater**: child actors remain vanilla and are excluded
    from both shuffle candidates and logic. Adult copies remain eligible. Child
    bean planting is also out of logic, including for the adult volcano heart.

Known limits: some NPCs decide "already given" from the vanilla item (e.g. silver
scale for the diving game) and can give their new item again; shop texts of
derived items are not added (the item's name is reused).
