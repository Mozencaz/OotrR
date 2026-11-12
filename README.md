# OoT Randomizer — Hookshot and emulator

[![Latest release](https://img.shields.io/github/v/release/Mozencaz/OotrR?label=download)](https://github.com/Mozencaz/OotrR/releases/latest)

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

For **Hookshot on Windows**, keep the NUP as the source and choose the `mods`
folder next to `hookshot.exe`, `image.bin` and `romfs` (create it if needed). The
seed is installed in its own sub-folder, without replacing the original resources.

## Tracking

Checks confirmed by the save show their reward; upcoming rewards stay hidden.
**Show blocked** and **Show completed** filter the list and the game window; the
search covers names and zones. Accessibility uses the items seen in the save and
the seed's rules, without crediting rewards of locations not picked up yet.

**Unknown** means the reading or the matching is not reliable enough. These rows
stay visible; a manual fallback mark is possible without revealing the reward.
Old seeds still open, but must be regenerated to get the newer metadata. The
tracker refuses a save that does not carry the new-game marker of the selected seed.

For pots, crates, beehives, bushes and rocks shuffled by the full mode, the
randomized reward is limited to the first pickup. A private get event sets a
persistent flag, then the source goes back to its native loot (a rock without
vanilla loot gives nothing again). A guard forbids a second randomized reward
coming from an old copy of the same drop.

The **in-game overlay** (Windows, Hookshot) shows the item grid plus the soul and
check counts over the game window; toggle it with **Ctrl + Shift + O**.

## Skippable cutscenes and quality of life

Code: [qol_patches.py](src/oot_rando/patching/qol_patches.py).

| Feature | Mechanism | Status |
|---|---|---|
| **Skippable cutscenes** — intro (`Dm_Kokiri_0000`) | `SkipSetting = DisableSkip` removed | validated in game |
| … other locked cutscenes | same removal: title screen demo (`Dm_Title_0005` and its six follow-ups), end credits (`Dm_StaffCredit_0005`) | to test |
| … area and dungeon presentations (31 flows `Dm_<Zone>_0000`, `Goto_<Dungeon>`: fly-over + area name) | flow-driven cutscenes are only skippable between `EventSystemActor.EventTriggerSkipAcceptStart` and `EventTriggerSkipEnd` (native mechanism of the great fairy fountains): a window is added at the start and after the last junction; their `NoPauseEvent` rows → `FlowchartEvent` | to test |
| … automatic dialogues (12 `NPCStepStart` rows) | rows moved to `FlowchartEvent` | to test |
| **Flow-driven cutscenes, up to their events** | the native skip *jumps* to `EventTriggerSkipEnd`. Each entry is cut into units (action, sub-flow, fork, branch): cosmetic actions are skippable; idempotent writes (constant flag, "has talked", absolute warp of Link, sound mode) are skippable when run on every path, then **replayed** after `SkipEnd` when the skip was used (`EventQueryIsEventSkipedMostRecent`); anything else (transition, pouch, quest, choice, unknown action…) is a barrier. Flows that talk are never covered (skipping Saria at the ladder crashed the game) | to test |
| **Chests without cutscene** | `Dm_SY_Treasurebox/Success_`: `Success_PlayerPerform` (camera, Link's kick, spinning item, ~9 s) and the 90-frame wait are replaced by `/Open` (lid) then the item get and its window. `Dm_SY_TreasureboxSmall/Success_`: `/Open` (Link's opening animation, event cameras, Navi) is replaced by the lid's actions (not awaited), Link's get pose and `/Pack_ItemDisplay` | to retest |
| **Ocarina found before the Deku Tree** (full randomizer) | `ActionGuide/ActionGuide` first runs `OpenActionGuideSceenForOcarina` when the Fairy Ocarina is in the pouch (guide shown once) | to test |
| **Turbo A** | holding X during a dialogue taps A (keyboard key bound to A in `hookshot_options.ini`) | always on |

NPC conversations are not skippable (an earlier attempt crashed the game); turbo
A speeds up their text instead. Presentation flows that write data or change map
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
   Windows) and the goal (Ganon defeated, read live: set just before the ending). The row
   also shows the server messages and takes chat or server commands (`!hint`…).
   Checks ticked by hand in the tracker are sent too.

Items of other players show in game as an Archipelago medallion with the item and player
name. Limits of this stage: items of this game received from other worlds and Archipelago
starting items are listed by the client but **not given in game** (no proven mechanism yet);
chest checks reach the server once the game writes its save; dungeon-bound keys and
progressive items stay in your world.

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

## Layout

```
src/oot_rando/
  __main__.py      entry point (GUI; audit, verify, memory, selftest, apworld, ap-install, ap-client)
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
