# OoT Remake Randomizer — rules for working in this repository

Python 3.11+, no runtime type checker. Sources in `src/oot_rando`, tests in `tests`
(unittest), tools in `tools`. The code and its docs are in English.

## Layers (enforced by `tests/test_layers.py`, deferred imports included)

Lowest first; a module imports only its own layer or lower ones:

0. `formats` (file formats), `catalog` (names of the game: actors, items, flags,
   `murmur3`), `paths`, `system` (emulators), `versions`, `pc_port`, `ed25519`, `update_key`,
   `path_safety` (path length limits), `native_dialogs` (file pickers)
1. `game` (world model) → 2. `logic` (AP rules, options) → 3. `patching` (game file patches)
4. `randomizer.full_randomizer` (solver) → 5. `archipelago.bridge`, `archipelago.apworld_build`
6. rest of `randomizer` (generation, `verify`, `artifact`, `mods_folder`, `save_patch`), `party_health`
7. `tracker`, rest of `archipelago` (client), `updater`, `parties` → 8. `gui`, `__main__`

A name several layers need (an actor name, a flag prefix) goes to `catalog`, never to a
patch module. Do not dodge the test with a deferred import. Do not import a `_private`
name from another module: make it public where it belongs (evfl helpers live in
`formats/evfl_tools.py`).

## Seed output and versions

- `GENERATOR_VERSION` (`randomizer/randomizer_core.py`) must change whenever the
  produced files change for the same settings, and the new version goes into
  `ACCEPTED_GENERATORS` (`randomizer/artifact.py`). A refactor must not change the
  output: check it with `tools/golden_seeds.py` (record before, `--compare` after).
- `tests/test_seed_identity.py` freezes `Settings.to_dict()` (the seed id hashes it).
  A changed value there means every installed seed changes identity: only on purpose.
- The application version has one source: `__version__` in `src/oot_rando/__init__.py`.

## Archipelago world

`apworld/oot_remake.apworld` is committed. Rebuild it after any change to a module in
`apworld_build.VENDORED` (or to `logic/world/`):
`python -m oot_rando apworld GAME.nup apworld/oot_remake.apworld`.
`tests/test_apworld_drift.py` fails while it is stale. Vendored modules must import
without `zstandard`, `evfl` and `ainb`, and only other vendored modules.

## Tests and checks

- `python tests/run_parallel.py` (CI: Windows + Linux, without the game).
- With the game: set `OOT_NUP` to the NUP path; about a third of the tests need it.
- `ruff check src tools tests` (rules in `pyproject.toml`) runs in CI.
- `python -m oot_rando verify GAME.nup SEED` replays a seed; it shares the patch code
  and the logic with the generator, `verify.output_invariants` does not.

## Git

`main` = stable, `dev` = experimental (protected, PR required). Branch `feature/…` or
`fix/…` from `dev`, pull request into `dev`. Releases: `packaging/README.md`.

## Pitfalls

- Edit files as UTF-8; git normalises line endings (`core.autocrlf`), keep diffs free
  of whole-file line ending changes.
- Nothing about the game itself is validated without playing: say so in commits and
  PRs when a change was not tested in game.
