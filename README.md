# OoT Randomizer — Hookshot and emulator

[![Latest release](https://img.shields.io/github/v/release/Mozencaz/OotrR?label=download)](https://github.com/Mozencaz/OotrR/releases/latest) [![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/dnqs4eRZC)

**[Download the latest release](https://github.com/Mozencaz/OotrR/releases/latest)**
(Windows `.zip` or Linux `.tar.gz`, portable, no installation).

> **AI disclosure:** this project was built relying on AI for coding. Most of the
> code was written with AI assistance (Claude Code), then reviewed and tested by
> the maintainer.

Desktop application that builds a randomized seed of the Ocarina of Time remake
from your local NUP game file, and installs it as a RomFS mod for Hookshot or an
emulator.

Full glitchless randomizer (built-in remake logic, no Archipelago install needed):
enemy souls, skulltulas, shops, freestanding items, NPC gifts, pots / bushes /
rocks, automatic save tracking with accessibility filters, an in-game overlay and
the quality-of-life options below. Details of the full mode and in-game pilots:
[docs/FULL_RANDOMIZER.md](docs/FULL_RANDOMIZER.md).

## Usage

1. Portable build: run **`OoT-Randomizer.exe`** (Windows) or **`OoT-Randomizer`** (Linux);
   no installation or Python needed. Seeds and state go to `data/` next to it.
   From the sources: **`run_from_source.cmd`** (or `python -m oot_rando` with `src` on `PYTHONPATH`).
   Dependencies: Python with Tkinter, then `python -m pip install -r requirements.txt`.
2. In **Game**, choose the NUP file and the mods folder (both are remembered).
   Choose a preset and the options in **Settings**. JSON and YAML import/export are available.
3. With the game closed, click **Generate and install** at the bottom of **Settings**.
   The seed is written to `OoT_Randomizer_<identity>` inside the title's mods folder.
   The previous seed of this application is uninstalled automatically (moved to
   `seeds-uninstalled` in the data folder); other mods are never changed, and a
   conflict with them stops the installation without writing anything.
4. Start a **new game**: tracking and first collections need the markers added by
   the seed. Save after the intro.
5. In **Tracker**, click **Detect** or select your `progress.sav`, then load the
   tracker. It rereads the save about every two seconds; changes show up when the
   game saves.

**Updates:** the portable build checks the latest GitHub release at start-up
(Help → *Check at start-up*; also a *Check for updates* button). Accepting
downloads the archive, verifies it against the release's `SHA256SUMS.txt`, swaps
the executable in place and restarts; `data/` (seeds, settings) is kept. Run from
the sources, it only points to the release page (use `git pull`).

**Experimental versions:** tick *Use experimental versions (pre-releases)* in
Setup to also be offered the GitHub pre-releases (`vX.Y.Z-beta.N`): new features
first, possibly buggy. Untick it to be offered the latest stable release, even when
its version is lower than the experimental build.

**Save Warp:** in the game's pause menu, open **System → Save Warp**, then save.
Link returns to the dungeon entrance, to his house as a child outside dungeons,
or to the Temple of Time as an adult. Cancel or B leaves the game where it was.

The game file must hold the base game **and** update v131072 in one `.nup`; the
order of the packages inside it does not matter.

For a **PC port** (Hookshot, its successor Longshot — on Windows, or Longshot's native
Linux build — or any fork with the same layout), keep the NUP as the source and choose
the `mods` folder next to `image.bin` and `romfs` (create it if needed). Longshot's Linux
build keeps its saves in `~/.local/share/longshot/save`; the tracker finds them. The
seed is installed in its own sub-folder, without replacing the original resources.

## Tracking

Checks confirmed by the save show their reward; upcoming rewards stay hidden.
**Show blocked** and **Show completed** filter the list and the game window; the
search covers names and zones. Accessibility uses the items seen in the save and
the seed's rules, without crediting rewards of locations not picked up yet.

**Unknown** means the reading or the matching is not reliable enough. These rows
stay visible; a manual fallback mark is possible without revealing the reward.
**not tracked** marks a row the save never records (an NPC gift or a shop refill
left in place, for example): only a manual mark completes it.
Old seeds still open, but must be regenerated to get the newer metadata. The
tracker refuses a save that does not carry the new-game marker of the selected seed.

For pots, crates, beehives, bushes, rocks and trees shuffled by the full mode, the
randomized reward is limited to the first pickup. A private get event sets a
persistent flag, then the source goes back to its native loot (a rock without
vanilla loot gives nothing again). A guard forbids a second randomized reward
coming from an old copy of the same drop.

New full-mode seeds use the supplied gold textures for unchecked pots, rocks,
crates, beehives, bushes, grass and reward trees. The existing collection flag
switches their materials back to vanilla, including a tree that stays loaded
after its reward is collected. Regenerate older seeds to include these assets.
The texture adapter preserves native destruction and respawn settings; static
checks do not establish when a particular PC port reloads a broken source.

Live reading of the game memory finds Hookshot and the yuzu-family emulators
Lichii, Ryuchii, Eden, yuzu, suyu, citron and sudachi on Windows, and the native
Linux builds of Longshot and of these emulators (Ryuchii on a Steam Deck, for instance)
on Linux.
On Linux, run the Linux application (`OoT-Randomizer`): the Windows `.exe` started
through Proton or Wine cannot read a native Linux process. Another fork can be added
by its executable name in **Setup → Other emulator executables** (on Linux, with or
without `.exe`).

On Linux, the yuzu-family emulators keep the game's memory in a file
(`/memfd:HostMemory`, Longshot: `/memfd:longshot-guest`). The application reads it through `/proc/<pid>/fd` at the
offsets `/proc/<pid>/maps` gives. That only needs the same user as the game, so
it also works with `kernel.yama.ptrace_scope` at 1 (SteamOS, Ubuntu). For an
emulator without that file it reads `/proc/<pid>/mem`, which `ptrace_scope` 1 allows
only when the emulator allows it (`prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY)`) or the
setting is 0; the Tracker tab names the value when Linux refuses. The application
never changes it.

The **in-game overlay** (Windows, Hookshot) shows the item grid plus the soul and
check counts over the game window; toggle it with **Ctrl + Shift + O**.

## Skippable cutscenes and quality of life

Code: [qol_patches.py](src/oot_rando/patching/qol_patches.py).

| Feature | Mechanism | Status |
|---|---|---|
| **Skippable cutscenes** — intro (`Dm_Kokiri_0000`) | `SkipSetting = DisableSkip` removed | validated in game |
| … other locked cutscenes | same removal: title screen demo (`Dm_Title_0005` and its six follow-ups), end credits (`Dm_StaffCredit_0005`) | to test |
| **Area and dungeon presentations never play** (30 flows `Dm_<Zone>_0000`, `Goto_<Dungeon>`: fly-over + area name; always on) | [area_presentations.py](src/oot_rando/patching/area_presentations.py). 11 gated by a saved `HavePlayedEvent` flag that only picks between them and the normal arrival: the flag and the area's `IsVisitLocation` (map) are set at the opening (full randomizer). The 19 others (first arrivals that move a quest — Death Mountain Trail, Zora's Domain, Colossus, Market, Deku Tree, Goron City, Forest Temple, Training Ground, Crater —, BoolExp gates, `EventRequestActor` or quest-flow calls): a native skip window (`EventTriggerSkipAcceptStart` … `EventTriggerSkipEnd`, as the great fairy fountains) is entered and left on the first frame, quest steps inside it (`SageOfForest Step05`) still run; their `NoPauseEvent` rows → `FlowchartEvent` | statically verified; to test in game |
| … automatic dialogues (12 `NPCStepStart` rows) | rows moved to `FlowchartEvent` | to test |
| **Flow-driven cutscenes, up to their events** | the native skip *jumps* to `EventTriggerSkipEnd`. Each entry is cut into units (action, sub-flow, fork, branch): cosmetic actions are skippable; idempotent writes (constant flag, "has talked", absolute warp of Link, sound mode) are skippable when run on every path, then **replayed** after `SkipEnd` when the skip was used (`EventQueryIsEventSkipedMostRecent`); anything else (transition, pouch, quest, choice, unknown action…) is a barrier. Flows that talk are never covered (skipping Saria at the ladder crashed the game) | to test |
| **Chests without cutscene** | `Dm_SY_Treasurebox/Success_`: `Success_PlayerPerform` (camera, Link's kick, spinning item, ~9 s) and the 90-frame wait are replaced by `/Open` (lid) then the item get and its window. `Dm_SY_TreasureboxSmall/Success_`: `/Open` (Link's opening animation, event cameras, Navi) is replaced by the lid's actions (not awaited), Link's get pose and `/Pack_ItemDisplay` | to retest |
| **Ocarina found before the Deku Tree** (full randomizer) | `ActionGuide/ActionGuide` first runs `OpenActionGuideSceenForOcarina` when the Fairy Ocarina is in the pouch (guide shown once) | to test |
| **Owl advice removed** (full randomizer) | tutorial flags are set at the opening; the first field conversation keeps its quest work; Death Mountain and Lake Hylia keep a single ride choice. The Dream World introduction unlocks the service silently | statically verified; to test in game |
| **Skip child Hyrule Castle** (full randomizer, `skip_child_zelda`) | the opening replays the native quest requests the castle makes (`Goto_HyruleCastle` complete, `DoorOfTime` at Impa's send-off, `Get_StoneOfFire` at Kakariko) and sets Talon's wake-up flags; Zelda's Letter and Lullaby are shuffled elsewhere (the lullaby anywhere a song can be given); the castle's shuffled checks hold green rupees (Great Fairy apart); castle requests of earlier steps are skipped once the quest is complete ([child_castle_skip.py](src/oot_rando/patching/child_castle_skip.py)) | statically verified; to test in game |
| **Turbo A** | holding A during a dialogue repeats A (keyboard key bound to A in `hookshot_options.ini`) | optional; remembered between app starts |

Other NPC conversations are not skippable (an earlier attempt crashed the game); turbo
A speeds up their text instead. The owl patch bypasses specific advice triggers and keeps
transport cleanup and Dream World functionality. Presentation flows that write data or change map
(`Dm_Kokiri_0045`, `Dm_LakeHrl_0003/0005`, `Dm_LonLon_0010`) are left alone. Each
patch is read back and compared semantically; `python -m oot_rando verify` reapplies
the quality-of-life patches on the original flows.

## Archipelago multiworld

The full randomizer can take part in an [Archipelago](https://archipelago.gg)
multiworld as the game **OoT Remake**: Archipelago places the items over every
world, with the same locations, item pool and glitchless rules as the built-in fill.

1. **Build the apworld** (Settings tab, or `python -m oot_rando apworld GAME.nup`):
   it holds the logic and a catalog of the remake's locations read from your game
   (identifiers only, no game asset). Whoever generates the multiworld copies
   `oot_remake.apworld` into Archipelago's `custom_worlds` folder.
2. **Export my multiworld YAML** with your options and send it to the host.
3. The host generates; your `.aprmk` patch is in the zip produced by Archipelago.
4. **Generate from a patch (.aprmk)** (or `python -m oot_rando ap-install PATCH GAME.nup MODS`)
   builds and installs the mod; the apworld must come from the same game and
   application version. Start a new game with it.
5. **Connect** in the Archipelago row of the Tracker tab (server address, slot, password),
   or run `python -m oot_rando ap-client MOD_FOLDER SERVER [--password P]` without the window.
   The client sends the checks the tracker sees (save, plus the running game's memory on
   Windows and Linux) and the goal (Ganon defeated, read live: set just before the ending). The row
   also shows the server messages and takes chat or server commands (`!hint`…).
   Checks ticked by hand in the tracker are sent too.

Items of other players show in game as an Archipelago medallion with the item and player
name. Items of this game found in other worlds are handed over in game by the client
while a save of the seed is loaded (Hookshot, Longshot or a yuzu-family emulator on Windows, Longshot's Linux build or a native
yuzu-family emulator on Linux), one at
a time in server order: Link holds the item up (consumables arrive as a pickup). An item
the game does not take after several tries is set aside and reported in the client log,
so the next ones still arrive. Archipelago starting items are given at the end of the
opening. Progressive items (hookshot, bow, bomb bag, wallet…) can be in any world:
every copy, found in your world or received, gives the level above the one Link holds,
in any order. Limits: chest checks reach the server once the game writes its save;
dungeon-bound keys (other than key rings and dungeon boss keys) stay in your world.

Generator 0.12.3 uses one shared Archipelago mailbox watcher, keeping the global
sequence small even when hundreds of items come from other worlds (issue #86).
Regenerate the mod from its `.aprmk` to apply this change and use the updated
application/client for delivery. The updated client still supports older mods.

Desktop seed generation runs in a separate process so the window can keep
responding during CPU-heavy work. The log reports actor-building progress and
event analysis/compression stages. See [performance measurements](docs/PERFORMANCE.md).

External AP trackers use conservative area-wide requirements for filler-only
checks without a reliable location match. These checks remain excluded from
progression placement; they become reachable only when every supported check in
their area is reachable, with source age and known chest guards preserved.
The Dream World boss-rush interval chests use a deliberately late estimate:
every supported world check must be reachable. AP does not track the museum's
native enemy records or the boss-rush round, so this cannot show their exact
unlock time. Other areas without a logic mapping stay unavailable. Rebuild the
host's `.apworld` with the updated application to use these rules; existing
generated multiworlds keep their original logic.

## Development

```powershell
$env:PYTHONPATH = 'src'
$env:OOT_NUP = 'PATH_TO_THE_GAME.nup'           # optional: enables integration tests
$env:OOT_HOOKSHOT_DIR = 'PATH_TO_HOOKSHOT'      # optional: game icon tests
python -m unittest discover -s tests -v
python tests\verify_application.py $env:OOT_NUP
python -m oot_rando verify $env:OOT_NUP 'build\seeds\OoT_Randomizer_xxxx'
python -m oot_rando audit                       # audit of the logic against the remake maps
```

Without `OOT_NUP`, integration tests are skipped. No test launches the game or
changes a real mods folder.

Portable applications: `packaging/build_windows.cmd` (Windows exe) and
`packaging/build_linux.sh` (Linux binary, run on Linux or WSL); output in `dist/`.
See [packaging/README.md](packaging/README.md), which also describes the GitHub
Actions workflows (CI, tag, release).

## Logic

The glitchless logic is built in: `src/oot_rando/logic/world/`.

- base layer (`regions/`, `helpers.json`, `locations.json`, `items.json`): OoT rules
  derived from the Archipelago OoT world (MIT licence, `LICENSE-archipelago-oot.txt`),
  updated by `tools/import_archipelago_world.py`;
- remake layer (`remake.json`): rules where the remake differs, each one justified.

Archipelago itself is not needed. Settings import/export in the Archipelago YAML
format stays available (optional PyYAML).

## Quality of life only

To keep the game as it is and only skip the introduction cutscene and open chests without
their cutscene, use the **Quality of life only** card of the Setup tab, or

```
python -m oot_rando qol-install GAME.nup MODS_FOLDER [--no-intro-skip] [--no-fast-chests]
```

It writes `OoT_QoL` (with a `manifest.json`, no seed) into the emulator's title folder
`load/0400486024DEC000`, generated from your own game file. Installing again replaces
it. A randomizer seed already contains these patches: while a seed is enabled, turn
`OoT_QoL` off (the install warns about it).

## Layout

```
src/oot_rando/
  __main__.py      entry point (GUI; audit, verify, memory, selftest, apworld, ap-install, qol-install, ap-client)
  paths.py         application folders (sources: build/; portable: data/)
  formats/         NUP, zstd/SARC resources, BYML, MSBT
  game/            remake map reading, matching, item forms
  logic/           rule engine (rules.py), remake world (world/), options, audit
  patching/        map, event and quality-of-life patches, souls, repeatable sources
  randomizer/      generation (core), planner (full_randomizer), verification, spoiler
  tracker/         automatic tracking, saves, live memory, overlay, turbo A
  archipelago/     apworld build, Archipelago bridge, multiworld patches, client
  gui/             Tk interface
tests/             unit tests and verifiers
tools/             development tools (base world import)
packaging/         Windows and Linux portable builds
docs/              design notes
```

Generated resources come from your local game: keep them local and do not
distribute them.

## License

[MIT](LICENSE). The logic data derived from the Archipelago OoT world keeps its own
MIT licence (`src/oot_rando/logic/world/LICENSE-archipelago-oot.txt`).
