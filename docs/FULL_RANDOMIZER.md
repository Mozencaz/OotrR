# Full randomizer — design notes

Every ticked category is shuffled together: a hookshot can come out of a bush, a
skulltula token out of a pot or a shop, a heart piece out of a skulltula. Generation
and logic are checked statically (`python -m oot_rando verify`); items marked
"experimental" in the settings still wait for the in-game pilots listed at the end.

## Sources (Items tab)

| Option | Source | Write into the game |
|---|---|---|
| **Chests** (`shuffle_chests`) | every chest, major items included, and the Market Treasure Chest Game first prize | `Dynamic.Drop__DropActor` of the chest |
| **Gold Skulltulas** (`tokensanity`: dungeons / overworld / all) | 100 skulltulas = the 100 AP locations | `Drop__DropActor` added to the enemy (native instance parameter); every item but the token is dropped by a pickup built on the token (see below) |
| **Shops** (`shopsanity`: 1 to 8 items per shop, random 1–4, or Whole shops) | 64 stalls across 8 shops, masks excluded | stall `Gyaml`; fixed price of 10 rupees; bought once |
| **Freestanding items** (`shuffle_freestanding_items`) | non-respawning heart pieces, rupees and hearts | item `Gyaml` |
| **NPC gifts and minigames** (`shuffle_npc_gifts`) | 31 gifts, including King Zora and adult Darunia Jr. (`extra_sources.NPC_GIFTS`) | item parameter of the event (`ActorName`, `ReveiveItem`…) via `evfl` |
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

* **Ice arrows melt red ice** (`blue_fire_arrows`, Items tab, off by default):
  usable ice arrows trigger the native red-ice melting sequence, including its
  saved destruction and linked events. Requires adult Link, a bow, ice arrows,
  and magic in the logic. Normal, fire, and light arrow attacks are unchanged;
  bottled blue fire remains usable. The seven meltable red-ice variants are
  covered; passive decorative ice stays vanilla. **Not validated in game.**
* **Magic capacity comes only from Magic Meter upgrades**: Din's Fire, Farore's
  Wind, Nayru's Love, elemental arrows and the Lens of Truth no longer grant the
  first magic bar implicitly. Their shared expansion reference is detached in
  native and generated actor packs, and their pouch database entries agree
  (`patching/magic_capacity.py`). Both real magic upgrades retain their effects.
  Regenerate seeds to apply this fix. **Not validated in game.**
* **Bows and elemental arrows**: the normal bow menu actor uses `Bow`, correcting
  its native `IceArrow` assignment. Ice Arrows remain a separate pool item when
  their chest is shuffled. Fire, Ice and Light Arrows retain their native adult
  menu selection. Disabling the standalone entries blocked selection even with
  a bow and magic; generator 0.12.17 restores them (`patching/elemental_arrows.py`).
  Logic still requires adult Link, the corresponding arrows, a bow and magic.
  Regenerate seeds to apply the fix. **Fix not yet validated in game.**
* **Bomb refills never grant a bomb bag**: bombs and bombchus have their native
  `SmallBagActor` automatic grant cleared in every embedded pouch component,
  including generated world, drop and shop packs (`patching/bomb_refills.py`).
  This applies to chests, gifts, purchases, pickups and Archipelago reception.
  Refill amounts and real bag upgrades are preserved. **Not validated in game.**
* **Starting inventory** (`start_inventory_from_pool`, AP name): items held from the
  start, given silently at the end of the opening (`event_patch.add_pouch_items`). A
  copy found in the item pool is replaced by rupees; progressive copies take the
  lowest levels of their family. Songs are given the same way (`Item_Melody_*`);
  tunics and trade items have no pouch actor yet. In a multiworld, the apworld's own `start_inventory_from_pool` is used.
* **Item pool** (`item_pool_value`): plentiful (one extra copy of each major
  non-progressive item, replacing filler), scarce (at most 3 bottles, half the
  hearts), minimal (one bottle, no hearts, double defense or capacity upgrades). The
  number of shuffled locations never changes.
* **Fake item traps** (`fake_item_traps`, Items tab, `none` by default, not offered to
  Archipelago). `some`: one fake copy of each major item of the pool (`catalog/traps.py`:
  hookshot, bow, slingshot, boomerang, bomb bag, hammer, boots, strength, scale, lens,
  magic, elemental arrows, spells, ocarina, Kokiri Sword, Mirror Shield, tunics, Stone
  of Agony). `plentiful`: two copies of each of them, plus one of each medallion,
  spiritual stone and song (in the pool or not). Each trap replaces a filler item
  (rupees and ammunition, lowest value first; when filler runs out, the first copies
  of the major items come first, then the dungeon rewards and songs, then the second
  copies). Traps go into chests and ground checks (freestanding items, Gold
  Skulltulas, pots, rocks, bushes, crates), never NPC gifts, scrubs or shops, whose
  items may be given without the get event that writes the trap's `IsGet` flag (as
  for the souls). They are junk for the logic. A trap is a pouch actor
  `Item_Trap_<code>` (`<code>2` for a second copy: each copy has its own flags and
  freezes once) built like the
  souls, with the model, pose, name and description of the item it imitates (songs
  have no description: their name stands in); its get
  text says "Too bad, it's a trap!" (English and French; other languages read the
  English text). Every item get ends in `ActionGuide/ActionGuide`: once a trap's
  `IsGet` flag is set and its saved `RandoTrap.<code>` is not,
  `GameSystemActor.EventTriggerRequestCreateConditionSensor` spawns
  `RandoIceTrapSensor` (`patching/fake_traps.py`), the event the Sun's Song uses for
  its own sensor. The copy carries the vanilla ice-trap chest attack (`Obj_TBox_A_04`,
  damage element `Frozen`) and hits the player in a 1.5 m cylinder around Link
  instead of enemies within 12 m: an enemy attack sensor (`Enemy_BabyDodongo`'s
  `EnemyAttack` layer, `HitToPlayer` mask, `EnemyAttackReceipt` contacts) owned by an
  object (`ObjectCommon` affiliation, as the trap chest and Twinrova's ice field).
  Its own AI waits 30 frames (the end of the get event), attacks for 30 frames, then
  removes the sensor. Each trap freezes once. Child Link cannot be frozen in the
  vanilla game (`Player_Child` `ConditionParam`: `IsEnableFrozen: false`): with traps
  in the seed it is turned on, so any ice attack can freeze child Link too. Earlier
  tests were all made as child Link, which explains why the hits only hurt him. In
  game (27/11) the first version, which kept the Sun's Song hit setup, did not touch
  Link; the second, attacking at once, hurt him just after the text without freezing
  him; with the child freeze on, he froze with no ice shell around him. His ELink
  user (`Player`) plays `@Blank` for `Condition_Frozen` and `Condition_Frozen_End`.
  With traps, adult Link's trees for those calls are grafted into it
  (`formats/xlink.py`, `ELink2/elink2.Product.110.belnk`, the copy the game loads).
  The shatter is copied as is; it shows in game (27/11). The adult shell is a grid
  on the equipped weapon and its kind, with adult items only, so child Link matched
  no cell and got no shell. He gets its whole-body branch (`全身凍結`: 16 poses and
  the cap pieces) directly. The game only has the adult emitter sets
  (`Ply_Frozen_*_Adult`), so the shell is sized for adult Link. **Not validated in
  game**: the shell on child Link.
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

## Cuccos to bring back (`cuccos.py`)

`chicken_count` (1 to 7): the cucco lady's pen in Kakariko (child). In
`Logic/MiniGame_CatchCucco_c69b.logic.module.ainb` (patched in place), node 17 compares
the cuccos in the pen with N − 1 instead of 7, and `Npc_Hylia_049_Child_Cucco06_IsInTheCage`
(the flag her flows test before the reward) is set when more than N − 1 are in the pen
instead of exactly 7; it is still cleared below N − 1, so N − 1 after having had N keeps
it. In `Minigame_CatchCucco`, `Event3` (her "left to find" count, N minus the pen) and
`Event82` (some brought back) use N. Her request and reward lines (`Talk_19`, `Talk_21`,
`Talk_21_1`, `Talk_40` of `Npc_Hylia_049_Child.msbt`) name N, as a digit, in every
language. 0 (a reward without a cucco) is not supported. **Not validated in game.**

With `shuffle_npc_gifts` enabled, King Zora's tunic (`ZD King Zora Thawed`)
and adult Darunia Jr.'s tunic (`GC Rolling Goron as Adult`) are shuffled NPC checks.
Their tunics enter the item pool. Darunia Jr.'s quest and ordinary talks share
one saved collection flag and the same reward; collecting either prevents a
second gift. King Zora's unclaimed gift remains available even when Link already
owns a Zora Tunic. Generate a new seed to apply these changes.

## Shops open day and night (`shop_hours.py`)

New full-randomizer seeds remove opening hours from the Market and Kakariko
shops and minigames, including both Kakariko potion-shop doors. The shooting
gallery, Treasure Chest Game, Market potion shop, Bombchu Shop and Happy Mask
Shop also use their normal service dialogue at either time of day. Bombchu
Bowling already permits entry all day with the existing story fix.

Native attendants and their challenge schedules remain in place, including the
bowling attendant's wake-up interaction. Age and quest requirements, purchase
prices, minigame payments, rewards and locks during an active game are preserved.
The world clock continues normally. Tracker and Archipelago entrance rules match
the new hours; regenerate the seed and use the updated apworld to apply this.
**Not validated in game.**

## Market lost dog from the start (`lost_dog.py`)

The quest's `DependFlagName`, both Kakariko gate readers in the Market dog/chase
module and the gate reader of the random-appear dog pool module
(`HrlMarket_Child_Dog_Prefab_7574`, which spawns the dog at its random Market
spots) now read `Sequence_IsChildhood`. The native schedules, time checks, dog
identification and return sequence remain intact. The first reward tests
`SubEvent_FindRichard_GetHeartPiece`, set after its handover; subsequent returns
give the native blue rupee. The tracker collection marker still runs only after
the shuffled reward. Logic requires child Link at night, with no Zelda's Letter
or Kakariko gate requirement. Existing seeds need regeneration to include this
patch. **Not validated in game.**

## King Zora's gift after Morpha (`story_fixes.py`)

Defeating Morpha before meeting frozen King Zora removes his red ice and releases
his quest dialogue, which used to make the Zora Tunic gift unavailable. His normal
and side-position talks now offer the original `SageOfWater/Event242` reward when
the Water quest is complete and its saved gift receipt is still false. The native
receipt prevents repeat gifts; owning a tunic from elsewhere does not suppress it.
The completed quest stays complete. Registered in generation and `verify` through
the story-fix list. **Not validated in game.**

## Adult Link the Goron's rolling (`link_goron.py`)

The playable Darunia Jr. now spawns on the first adult Goron City load, without
waiting for `SageOfFire_GenerateDaruniaJr` from the introduction. His `Ready`
schedule uses the native `StopDaruniaJr` rolling and bomb/talk behavior, so an
unplayed introduction does not leave him immune to the normal stun sequence.
The introductory camera sequence is bypassed and its two stationary doubles are
hidden, leaving only the playable Goron. Its native spawn/played flags are still
set when the arrival event runs. Requests for
`StopDaruniaJr`, `TalkDaruniaJr` and `MoveStatue` cannot move a later Fire quest
backward. Regenerate a seed to apply these changes. **Not validated in game.**

## Multi-level mini-games (`minigame_rewards.py`)

The **Treasure Chest Game** first prize is part of `shuffle_chests`. Its special
shop chest (`Market#16881481538337649070`) contributes one ordinary Piece of Heart
to the pool and uses the `Market Treasure Chest Game Reward` Lens of Truth rule.
Both its content and Lens preview are shuffled, and its opening is tracked through
the original minigame event. The native completion flag still selects a separate
red-rupee chest on repeat wins; intermediate key and rupee chests stay vanilla.
Requires a newly generated seed (generator 0.12.18+) and a rebuilt AP world for
multiworld. Static resource and logic checks pass; an in-game pilot remains needed.

The first success hands over the prizes of every level (they are separate checks), and
the saved progress jumps to the end so that later wins only pay the repeat reward.
Always on with the complete randomizer; registered with the story fixes, so `verify`
replays them. Events are found by name and the gifts are followed through the collection
markers inserted after them.

* **Bombchu Bowling** (`MiniGame_BombchuBowling`): `GetPrise` chains the Bombchus
  (`Event309`), the bomb bag (`Event76` → `Event304`/`Event306`) and the heart piece
  (`Event143`); the clear count sets `ClearSecondTime` and `ClearThirdTime` with the first.
* **Ocarina memory game** (`Npc_SkullKid_Child_02`): the first session chains the blue
  rupee (`Event22`), the red rupee (`Event23`) and the heart piece (`Event64` → `Event24`),
  and sets the next session's grade to 8 (`Event11`), the last one.
* **Horseback archery** (`Minigame_HorsebackArchery`): the 750 points heart piece
  (`Event117`) continues with the quiver (`Event110`, as 1400 points already did).
* **Slingshot and bow ranges** (`MiniGame_HitTarget`): nothing to merge: the bag / quiver is
  given once (`Get_BulletBag`, `Get_Quiver`), the hard mode only pays rupees.

**Not validated in game.**

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
The source keeps its hash, transform and native condition. Its drop changes, and
the texture adapter changes its `Gyaml` to a private source actor: no additional
`Presence` and no vanilla physical copy. The game records broken sources by their
hash (`Bool64bitKey`). The native reset metadata and `GameActorInfo.IsRespawn`
remain unchanged; the precise reset transition requires testing in the target
engine. A copy under another hash, or a source under a
`Presence` condition, came back while the area stayed loaded. Each pickup runs its own
clone of the `DropItem` AI: when it spawns, it reads its check flag, and once the check
is collected it hands over to the source's vanilla drop. The pickup carries that drop
as its own `DropRef`: the source pack's drop component (its lottery: hearts, magic,
ammo, nuts and bombs from pots, grass and crates, rupees from rocks and beehives) or,
for a source whose map entry names its drop (`Drop__DropActor`), a table of that one
rupee or heart. The pickup reserves that drop and requests its death, as the Poe's
lantern does when it leaves its spirit (`Weapon_PoeCantera.root`:
`OneShotDropReserveDropItemCreate`, then `OneShotDeathRequestDeath`, reason 10). A
source whose drop is unknown (its pack has none, or its map entry names a table)
drops nothing once collected. Not validated in game.

`source_textures.py` bundles the user-supplied BNTX albedos and clones the native
BFRES at generation time, preserving geometry, UVs, shaders and other textures.
Each shuffled source keeps a vanilla main model and a gold submodel. Native
material visibility actions read the saved check flag on every AI update; they
do not depend on restarting a selector branch or respawning the actor. Both the
pre-actor component and `ActorInfo.UsePreActorRenderer` disable pre-rendering for
these instances so it cannot bypass material selection. Tests exercise all 20
supported actor variants and flip the flag on an already-loaded graph. These
are static/data-flow tests, not an in-engine respawn or animation test. Validate
tree collection in place and KF destruction/exit/return in the target PC port.

When the check is collected depends on the reward. A key reward plays its get event
on every pickup, and that event's graph sets the check flag once the item is in the
pouch. A minor reward (rupees, ammunition, recovery hearts, magic jars) keeps the
native pick-up, without Link stopping: the game plays its get event only the first
time an item of that kind is ever got, so that graph cannot record the check. No
graph sees the short pick-up: `DropItem.root` holds no pick-up node, and no node of
the game's AI reads a pick-up. Its drop AI therefore sets the check flag when the
pickup spawns, right after the "already collected" test, if the pouch can take the
reward then (`QueryPouchMgrIsEnablePushToPouch`): a full wallet keeps a rupee check
for later. A minor drop that is not picked up while the pouch has room still counts
as collected.

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

Modes `bosses`, `regional`, `all` (8 boss souls, 26 regional souls or 47 family souls
in the current build). `Presence` is added to
enemies without an existing condition; `Item_Soul_*` items (key item template of
the Forest Medallion, 3D model of the Poe soul); RSDB rows `ActorInfo`,
`GameActorInfo`, `PouchActorInfo`; saved flags `IsGet.Item_Soul_*`; RESTBL entries;
get texts (`<actor>_Name/_Caption/_GetMessage/_GetCaption` in
`ActorMsg/PouchContent.msbt` of the 16 languages, via `msbt.py`) — without them
the dialogue box stayed empty and blocked the game. A new save is required.

Native combat dependencies are scanned by `game/combat.py`: map counters,
AI groups, used enemy defeat outputs (including generic actor controllers)
and nested logic modules. Script-created chests need not have `SpawnType=1`.
Their actor IDs associate the fight with its actual reward, including merged
child/adult chest variants. The Royal Family's Tomb requires the Keese soul
before its song can be collected; hiding a shutter does not prove a scripted
passage is open. See [the complete native inventory](SOUL_COMBAT_AUDIT.md) and
its machine-readable `soul_combat_audit.json`.

Solo fill and replay must recover **every soul** from real pickups, even with
minimal accessibility. No soul is assumed during final validation. The first
child route to the Door of Time follows these combat requirements, rejecting
Song of Time in the Royal Tomb when the Keese soul can only be found as adult.
Existing seed files remain readable, but their placements are not repaired:
regenerate them. Archipelago needs a rebuilt `.apworld` and new placements;
native combat evidence intentionally changes the scan fingerprint.

The requested behavior of doors when a required soul is missing is specified in
[the room door policy](SOUL_ROOM_DOOR_POLICY.md). That policy distinguishes safe
entry/retreat from combat-gated exits and preserves native key locks. It is a
specification; its physical door-control changes are not implemented yet.

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
  `is_child`/`is_adult` rules). Being adult needs `Time Travel` (reach the sword
  through the Door of Time, following *Door of Time requirements* below). A source with no
  such location only receives filler. Its tracker name ends in `(child)`/`(adult)`;
  an object on both maps under one hash is one check for either age.
- NPCs: exact AP location; for the man on the roof (adult only in the remake) and
  the lake lab (child only), the age rule is added.
- A group holding a location that the AP rules never reach only receives filler.
- Progressive items (hookshot/longshot, gauntlets, bomb bag, bow, slingshot,
  wallets, scales…): each copy gives the level above the one Link holds, so the
  n-th copy found is level n, as the AP logic counts them (see *Progressive items*
  below). `progressive_order` and `progressive_strict` no longer change anything.
- Souls: entering a dungeon conservatively requires the souls of its mechanical
  enemies and native combat groups; a boss room requires the boss soul.
  Native combat rewards require their group's souls, even without a conditional
  chest flag. Conditional chests also require the souls of their map.
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

### Door of Time requirements (`door_of_time_requirement`)

Zelda's escape has its own **Require Spiritual Stones** setting in the same card.
Changing the door requirements does not change the escape requirements. New seeds
require all three stones for the escape by default; **Vanilla** requires Ruby and
Sapphire. Seeds previously saved with `spiritual_stones: door` retain their linked
behavior, including the immediate escape when their door requirement is `song`.
The legacy linked value is accepted on import but is not offered for new choices.

Play the Song of Time with an ocarina in front of the door. The *Open world* card
adds a separate choice of stones required at that moment:

| Value | Door requirements |
|---|---|
| `song` (default) | Ocarina and Song of Time |
| `vanilla` | Ocarina, Song of Time, Goron Ruby and Zora Sapphire |
| `all` | Ocarina, Song of Time and all three Spiritual Stones |

`open_door_of_time` opens the door from the start and overrides this choice. Beyond
the door, the child can pull the sword without another stone requirement. The setting
is independent of Zelda's escape below. The solver applies its exit rule in Python,
preserving the world's fingerprint. Missing stored values mean `song`, and that value
is omitted from stored settings to preserve earlier seed identities. Behaviour in game
still needs confirmation.

### Adult start (`starting_age` = `adult`)

A new game begins as adult Link at the Temple of Time pedestal. The engine still loads
Kokiri Forest first: the opening's seed marker, starting items and start values are
written there as usual, then `Opening_Introduction` (right after its own quest request,
`Event8`) sets `Sequence_IsChildhood` to false and reserves the banc change to
`Market_Adult`, a copy of the native `Market_Child_Field_ChildToAdult` arrival (boot event
`Dm_TimeTemple_0085`). The forest introduction no longer plays (`patching/adult_start.py`).

* The Door of Time is open: `open_door_of_time` is forced on when the option is validated,
  so the existing opening and pedestal fixes apply and time travel works both ways.
* Link holds the Master Sword (`Weapon_Sword_Master`, added to the silent starting pouch
  items): putting the sword back at the pedestal needs it. Every other starting item is the
  `start_inventory_from_pool` choice; nothing else is given.
* The solver already knows the option (`Root Exits`: starting age or `Time Travel`); the
  child side only opens once the pedestal's `Time Travel` is reached.
* `random` stays unavailable. New save required. The gameplay chain is built from the
  native flows' dumps only, no game file was run: to be confirmed in game.

Before accepting a local seed, generation and replay independently sweep its actual
placements from the starting inventory with every `Time Travel` grant disabled.
With a closed door, the child must collect at least one ocarina, the Song of Time,
and the stones selected above. This includes dependencies: a pickup on a child map
does not qualify if reaching it requires an item available only as adult. Spare
ocarinas may remain on adult maps; starting items and sources shared by both ages
count. An open door skips this check. Archipelago retains its multiworld validation,
since required items can arrive from other players.

The native altar pack (`Obj_TimeTemple_SpiritStoneBase_A_01`) checks the invalid-condition
`Market_Child_TimeTempleDoor_OcarinaReacts` before calling the opening event. Its original
expression rejects the song outside `DoorOfTime` step `Step05`, even after the event flow
was freed in 0.7.3. The generator now replaces that expression with "door already open OR
required stones missing"; the native ocarina point still recognises the Song of Time.
Independent verification checks the emitted expression against the selected requirement.

The child pedestal module also routes the first pull through the inverse of the native
`AllSage IsAfter Ready` check used for subsequent pulls. Comparing `IsBefore Ready`
instead left both requests disabled at exactly `Ready`: the prompt appeared but pressing
the action did nothing. Both requests still require the pedestal action, and exactly one
can run regardless of the current quest step.

### Spiritual Stones for Zelda's escape (`spiritual_stones`)

The game's own check (`DoorOfTime/DoorOfTime_CheckStoneNum`) reads only the Fire and
Water stone quests (`Get_StoneOfFire`, `Get_StoneOfWater`), never the Kokiri Emerald.
The **Require Spiritual Stones** row in *Open world* controls the escape independently
of the Door of Time. New settings default to `all`; choose `vanilla` to require only
Ruby and Sapphire. This gates the Ocarina of Time (`HF Ocarina of Time Item`) and
the Song of Time. The old `door` value is still readable for existing linked seeds,
but is not offered in the dropdown. Loading and exporting preserves that value
until an explicit escape choice is made.

| Value | Stones | Logic and patch |
|---|---|---|
| `all` (default, "Require all") | Kokiri Emerald, Goron Ruby, Zora Sapphire | `has_all_stones` (the rules of the base world); `story_fixes.STONE_SETS['all']` checks the three saved `IsGet.Item_Stone_*` flags |
| `vanilla` ("Vanilla") | Goron Ruby, Zora Sapphire | the Goron Ruby and the Zora Sapphire in the rules, and `Met Zelda` for the ocarina item too; `STONE_SETS['vanilla']` checks the two |

The logic files (`remake.json`, `helpers.json`) keep the rules of one value, the one the
builds before the option used (`rando_options.UNRECORDED`); `rules.ESCAPE_RULES` holds both,
and the other value replaces them in `Logic` when the rules compile. So the world
fingerprint (`World.fingerprint`, a hash of those files that seeds and Archipelago
patches keep) does not change with the option, and a seed or patch made before it loads
and tracks as before. Seeds and patches that chose the other value store it in their
settings, from which the tracker and the apworld rebuild the same logic. The Mask of
Truth (`has_all_stones`) is not affected.

Seed identity: an option at the default value is left out of the stored settings
(`rando_options.UNRECORDED`, `Settings.to_dict`), so seeds made before the option, whose
settings never held it, keep their identity and regenerate identically; `vanilla` is
stored. The seed string already writes only the values that differ from the defaults.

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
    field talk does not move the castle quest back; with the stones the option asks
    for (all three, or the Goron Ruby and the Zora Sapphire), Zelda flees and the Door
    of Time opens.
14. **Pickup visuals**: progressive slingshot, bow and hookshot copies use their
    native item poses. Gold Skulltula drops no longer use the skull-shaped aura.
    Items without an effect borrow the moat ocarina glow; check visibility under
    water and confirm it does not obscure the item. Resource tests pass; appearance
    still needs an in-game check.
15. **Child Death Mountain Crater**: child actors remain vanilla and are excluded
    from both shuffle candidates and logic. Adult copies remain eligible. Child
    bean planting is also out of logic, including for the adult volcano heart.
16. **Cuccos**: with 3 to bring back, the cucco lady's request says 3, her "left to find"
    count starts at 3, and she gives her reward once 3 are in the pen.
17. **Fake item traps** (`fake_item_traps`): open a chest holding a trap. The real
    item's model and name show, then "Too bad, it's a trap!", then Link is frozen
    once; the same trap never freezes again (reload included). Check that a Kokiri
    or Zora nearby is not frozen and that Link can move again. With `plentiful`, also
    pick a trap on the ground (freestanding item, skulltula token), a second copy of
    the same item (it freezes too), and a medallion or song trap.

Known limits: some NPCs decide "already given" from the vanilla item (e.g. silver
scale for the diving game) and can give their new item again; shop texts of
derived items are not added (the item's name is reused).
