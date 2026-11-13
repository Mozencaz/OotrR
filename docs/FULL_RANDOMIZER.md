# Full randomizer — design notes

Every ticked category is shuffled together: a hookshot can come out of a bush, a
skulltula token out of a pot or a shop, a heart piece out of a skulltula. Generation
and logic are checked statically (`python -m oot_rando verify`); items marked
"experimental" in the settings still wait for the in-game pilots listed at the end.

## Sources (Items tab)

| Option | Source | Write into the game |
|---|---|---|
| **Chests** (`shuffle_chests`) | every chest, major items included | `Dynamic.Drop__DropActor` of the chest |
| **Gold Skulltulas** (`tokensanity`: dungeons / overworld / all) | 100 skulltulas = the 100 AP locations | `Drop__DropActor` added to the enemy (native instance parameter) |
| **Shops** (`shopsanity`: 1 to 4 items per shop, or random) | 64 stalls, masks excluded | stall `Gyaml`; fixed price of 10 rupees; bought once |
| **Freestanding items** (`shuffle_freestanding_items`) | non-respawning heart pieces, rupees and hearts | item `Gyaml` |
| **NPC gifts and minigames** (`shuffle_npc_gifts`) | 29 gifts (`extra_sources.NPC_GIFTS`) | item parameter of the event (`ActorName`, `ReveiveItem`…) via `evfl` |
| **Bosses and dungeon rewards** (`shuffle_boss_rewards`) | 3 stones, 6 medallions (Rauru's included), 8 boss heart containers | hand-over event (`GetPouchContentByActorName`); placed heart container `Gyaml` |
| **Great Fairies** (`shuffle_great_fairies`) | Din, Farore, Nayru, magic, double magic, double defense | `ActorName` of the fairy cutscene |
| **Quest rewards** (`shuffle_quest_rewards`) | Saria's ocarina, Ocarina of Time, Zelda's Letter, Light Arrows, Biggoron Sword | `ActorName` of the cutscene; ocarinas: also the silent pouch add |
| **Pots, crates, beehives, bushes, rocks** | explicit-drop objects (rupee, heart); empty rocks (≈ 195, no drop table) | existing `Drop__DropActor`, or added on rocks whose pack declares it as an instance parameter |
| **Business Scrubs** (`shuffle_scrubs`) | single-sale remake scrubs only: stick upgrade (`LW Deku Scrub Near Bridge`), nut upgrade (`LW Deku Scrub Grotto Front`), field and crater heart pieces | `ActorName` and `Price` of each `SimpleShopSub_Scrub_Business_OneTime` call in `Enemy_Scrub_Business_Common` |

Never changed: the whole adult trade quest up to the Biggoron Sword, songs, the
child trade (egg, letter, masks), cows, the Gerudo card, beans, the lake Fire
Arrows. Repeatable sources (pots, crates, beehives, bushes, rocks) give their
shuffled reward only once (`repeatable_adapter.py`), then go back to their vanilla loot.

## Starting inventory, item pool, removed keys

* **Starting inventory** (`start_inventory_from_pool`, AP name): items held from the
  start, given silently at the end of the opening (`event_patch.add_pouch_items`). A
  copy found in the item pool is replaced by rupees; progressive copies take the
  lowest tiers of their family. Songs, tunics and trade items have no pouch actor
  yet. In a multiworld, the apworld's own `start_inventory_from_pool` is used.
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

## Item forms and derived actors (`item_forms.py`)

The remake gives an item through three kinds of actors: `Item_*` (chest, event),
`Obj_*` (picked up from the ground, dropped by an enemy or a pot) and `Shop_*`
(stall). When the native form is missing (hookshot on the ground, heart piece in
a shop…), the generator builds `Obj_Rando_<item>` (behaviour of the gold token,
model and content of the item) or `Shop_Rando_<item>` (behaviour of an arrow
stall), with their RSDB rows and RESTBL entry. AP "Buy …" purchases never leave
the shops and keep at least one copy on sale.

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
- Pots, bushes, rocks, crates, beehives, lying rupees: rule of the **whole zone**.
- NPCs: exact AP location; for the man on the roof (adult only in the remake) and
  the lake lab (child only), the age rule is added.
- A group holding a location that the AP rules never reach only receives filler.
- Progressive items (hookshot/longshot, gauntlets, bomb bag, bow, slingshot,
  wallets, scales): the lower level always goes to the earliest sphere (the two
  values are swapped when needed); optional strict order.
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

Kokiri Forest positions (`extra_sources.kokiri_spot`): copies in the child map, in
the village (before Mido, outside the grotto) are reachable at start; adult-only
copies after time travel; bean platform rupees use `KF Bean Platform Red Rupee`.
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
3. **Skulltula**: a gold skulltula carrying another item drops it (and not a token too).
4. **Derived freestanding item** (`Obj_Rando_*`): visible model, pickup, name, no respawn.
5. **Shop**: a `Shop_Rando_*` item shows (name, price 10), the purchase gives the item.
6. **NPC**: e.g. Dampé's digging or bowling gives the placed item and the NPC continues.
7. **Dungeon reward**: after Gohma, the Deku Tree gives the placed item and the
   story (Mido, the Tree's death) continues.
8. **Great fairy / quest**: the right item is given; a replaced Saria ocarina does
   not also add the vanilla ocarina.
9. **Boss heart container**: the placed item (visible on entering the room) can be picked up.

Known limits: some NPCs decide "already given" from the vanilla item (e.g. silver
scale for the diving game) and can give their new item again; shop texts of
derived items are not added (the item's name is reused).
