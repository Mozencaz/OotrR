# OOTRR cutscene and dialogue comparison

Reviewed 2026-11-23. This is a source review, not an in-game validation or an implementation.

Our baseline: `feature/song-lesson-skip`, `cb61edeaa31bcfa9279e3730b8ed9944a5e7734a`.
External baseline: `ootrando/ootrr`, `nightly`, `def150e64118947283424f282120fac2db2d52e8`.
The external checkout is in ignored `build/research-ootrr`.

## Finding

OOTRR's most useful advantage is explicit replacement of complete, known story sequences with short reward/state paths. Our generic timeline/window system already covers many visual scenes, but that does not eliminate all surrounding dialogue, fades, scene loads or reward ceremonies. Neither implementation's source alone proves runtime correctness. OOTRR's source includes reports of actual failures and fixes, plus structural tests; some tests return early without game assets.

Our `song_lessons.py` and `timeline_skip.py` already acknowledge OOTRR's method. This is an incremental comparison, not a proposal to replace our system.

## Existing overlap

Our code already has:

- `qol_patches.py`: unlock locked movies, add native skip windows with state replay, and shorten both chest flows.
- `area_presentations.py`: premark suitable first visits and shorten other arrivals while retaining quest effects, loading waits and map visit flags.
- `timeline_skip.py`: replace selected timeline transitions with played flags and required time/boss/music effects, resolve relevant skipped queries, and handle fades. Its safety rules retain unsupported world mutations and ending families.
- `skip_auto.py`: bypass analysed skip windows, retaining the skipped branch and required fade/loading handling. Din and the Water Temple water-level windows are deliberately excluded.
- `song_lessons.py`: ten song checks replaced in their triggering flows, with the placed reward, check marker, scene state and Sheik counter calls retained. External flow dependencies are completed by `event_info.py`.
- `npc_dialogue_skip.py`: remove selected Kokiri non-choice lines while preserving choices and their response paths, and handle speaker/dialogue-close dependencies. Experimental, not runtime validated.
- `owl_advice.py`: field tutorial shortcuts that preserve optional transport and the initial field clock/menu effects.

Do not describe OOTRR as introducing these mechanisms to our branch.

## Concrete additions worth adapting

### Opening movie and wake-up scene

OOTRR's `intro_skip.rs` directly patches `OpeningEvent` to skip both `Dm_Kokiri_0000` and `Dm_Kokiri_0030`, handling the skipped query and music restoration. Our old `skip_intro` name maps to `skip_locked_cutscenes`: unlocking the movie for a button press is different from starting immediately at player control. Our timeline adapter deliberately retains the loading-sensitive opening. Source: [intro_skip.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/intro_skip.rs).

Adaptation: a dedicated opening adapter that bypasses presentation only, preserving the complete opening tail, starting inventory/state writes and our seed/save binding marker. Compose it with the existing patched OpeningEvent rather than rebuilding from vanilla after start values have been added. Verify fresh-game control, screen visibility, music and save identity in-engine.

### 1. Tutorial suppression, including engine-triggered guides

OOTRR rewrites five `ActionGuide` entries to a one-frame wait, sets all 53 `ActionGuide_IsEnd.*` flags for a new game, and marks map/compass first-get state and two shield hints. This covers event calls and guides opened directly by game code. Source: [no_tutorials.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/no_tutorials.rs).

Adaptation: an optional tutorial patch and explicit start values. Preserve our `story_fixes.zelda_escape_on_item_get`, which prepends the stone/progression check to `ActionGuide/ActionGuide`. Redirect only the tutorial body after that check, or move the check to an equally reliable item-get boundary first. Replacing the entire entry would remove gameplay logic in our project. Verify the map flags do not grant individual dungeon maps or unwanted logical inventory.

### 2. First consumable pickup text

OOTRR marks 16 repeatable pickup presentation flags as played. It also initializes the smallest nut/stick bags when absent; skipping the first presentation alone is insufficient for correct first pickup accounting. Existing higher tiers are respected. Chests and equipment retain their messages. Source: [first_pickups.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/first_pickups.rs).

Adaptation: separate `skip_first_pickup_text` setting; add flags and capacity initialization through our existing opening/start-values machinery. Test fresh saves, higher starting capacities, and the first ground pickup. Our silent AP consumable delivery is a separate path and does not implement this world-pickup feature.

### 3. Ocarina of Time lesson and Requiem

Our `song_lessons.NOT_SKIPPED` excludes both. OOTRR has eleven trigger-based lessons: the Time lesson supplies both the ocarina check and song check. Requiem receives a special patch to its own entry and event settings because its map starts it. It starts/participates/unequips the player and uses the short reward path. Source: [story_skip.rs, song triggers and Requiem](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/story_skip.rs#L1485).

The enabling change is their ocarina display/grant handling: show an animated pickup actor instead of the equipment actor, then apply the real item grant and write `PlayerStatus.EquipOcarina`. Their comments report that granting only the pickup actor left the D-pad unusable until reload. Source: [ocarina_hold.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/ocarina_hold.rs).

Adaptation: first support safe ocarina display/grant forms, progressive tiers and immediate equip; then let a lesson carry multiple rewards. Preserve two independent tracker/AP collection markers for the Time scene. Give Requiem its own adapter rather than pretending it has a normal flow trigger. Confirm preload lists, event style and pickup pack dependencies against our game assets.

### 4. Complete story reward shortcuts

OOTRR replaces Saria's bridge gift, the first Master Sword/Rauru sequence, and the Light Arrows sequence with explicit shorter routes. The first sword draw reuses the game's later child-to-adult draw event. The Light Arrows path drops surrounding camera/fade/wait work, retains progression, and avoids forcing the sword equipment. Darunia's song/bracelet and ruby talks also have explicit cuts. Source: [story_skip.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/story_skip.rs).

Adaptation: small scene-specific adapters, each defining trigger, grant, ordered state writes, retained calls, loading/fade work and exit. Read rewards from our patched placements, not vanilla item names. Preserve progressive selection, dungeon credit and AP delivery/check semantics. Our timeline removal can shorten a movie inside one of these sequences while leaving its dialogue and loading scaffolding; these adapters would remove the complete ceremony.

### 5. Dungeon rewards before leaving the boss room

OOTRR moves eight dungeon checks into first-clear blue-warp paths, grants the placed reward before warping, substitutes the old reward scenes with their flags/state, and bypasses five Chamber of Sages stops while retaining their writes and destination loads. Source: [story_skip.rs, reward gives](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/story_skip.rs#L1047).

Adaptation: a separate dungeon-ending setting and patch of `Dm_SY_BancChange_EscapeDungeon`. Keep the reward conditional on accepting the warp and on first clear. Preserve boss completion, world restoration, destination, child/adult state and subsequent progression. Move collection markers to the actual grant point; retire the old grant to avoid duplicates. Test repeat warps and all reward shuffle modes. This offers substantial shortening beyond deleting awakening animations, but has a larger integration surface than tutorials.

### 6. All six Great Fairy gift sequences

OOTRR retains initial talk/payment and Din's magic gate, removes rising/parting presentation, invokes the fairy's own `C15-01` item routine and retains healing through `TriForcePoint/Recover`. It also releases music ducking and repairs entry sub-call lists. The code uses the existing patched grant routine; its SceneGive argument is unused in the patch body. Source: [story_skip.rs, fairy give](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/story_skip.rs#L1305).

Adaptation: preserve our shuffled fairy grant and its native routine; shorten presentation around it. This could cover Din, which our automatic native-window shortcut deliberately refuses. Do not achieve coverage by merely removing that exclusion. Verify payment once, item once, magic prerequisites, healing and repeat visits for each fountain.

### 7. Burning Kakariko and loading boundaries

OOTRR retains the native two-load route through ordinary Kakariko before the alternate burning village and removes scenes inside it. Its comments/tests specifically warn that directly changing into the alternate village never finishes. Its song shortcut gives Nocturne before a later load boundary. Source: [story_skip.rs, burning village](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/story_skip.rs#L2130).

Adaptation: inspect our `Dm_SY_BancChangeArrive` path and implement an explicit sequence adapter if we want to remove surrounding scaffolding. Preserve our medallion-based trigger rules. Treat grant timing and map loads as observable behavior; deleting two timeline transitions is not proof the complete arrival remains valid.

## Things not demonstrated as better

- General dialogue acceleration: no global text-speed patch or general NPC line-removal system was found in the inspected core. Their `EventTalk` edits target specific ceremonies. Our Kokiri choice-aware patch has wider general-dialogue intent, though it still needs playtesting.
- Skip-lock removal: their `Off/Story/All` controls only lock removal; Story unlocks opening and first credits, All flips the shared lock including title demos. It is not a general automatic story-skip setting. Our separate timeline/window controls address a different problem. Source: [qol/skip.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/qol/skip.rs).
- First-visit flags: both implementations preserve map availability; our arrival handling distinguishes quest-bearing paths. Do not replace that with blanket premarking. Source: [area_intros.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/area_intros.rs).
- Fast chests: OOTRR copies the small-chest path for big lids and explicitly adds big-chest map/compass/boss-key credit. We already shorten both chest flows. This is an alternative animation policy, not established evidence of a faster or more reliable result here. Source: [qol/chest_anim.rs](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/randomizer/core/src/qol/chest_anim.rs).

## Suggested implementation order

1. Optional tutorial suppression and first-pickup messages; retain the ActionGuide progression hook. Add the dedicated opening shortcut while preserving its initialization tail.
2. Ocarina display/grant/equip support, then Time lesson and Requiem.
3. Complete Saria/Rauru/Light Arrows shortcuts and all-six fairy adapters.
4. Dungeon reward relocation and explicit complex arrival shortcuts.
5. Expand general dialogue skipping by audited NPC groups, preserving choices, prices, hints, minigame instructions and meaningful responses.

For each adapter: operate on current patched bytes; verify expected original structure; preserve ordered state effects; repair entry sub-call indices and transitive `GameAnalyzedEventInfo` dependencies; record the transformation in the manifest and verify it from original assets. Test option off/on, shuffled/unshuffled and AP cases, repeat triggers, save/reload, immediate equipment usability, and fade/camera/music cleanup. Structural tests are necessary but cannot replace engine tests.

## Reuse boundary

The reviewed external revision is GPL-3.0-or-later; its NOTICE says releases through 0.4.0 remain MIT. Our project declares MIT. Reimplement the behavior using our own game analysis and existing patching code; direct code reuse would require an explicit compatible licensing decision. Source: [NOTICE](https://github.com/ootrando/ootrr/blob/def150e64118947283424f282120fac2db2d52e8/NOTICE). This is a concrete dependency of copying code, not a reason to delay the independent implementation proposed above.
