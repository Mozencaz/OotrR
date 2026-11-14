"""Entry point: ``python -m oot_rando [commande]`` (or the portable executable).

Without a command, the graphical application starts. Commands:

* ``audit``   — audit of the logic against the remake maps (``logic.audit_rules``);
* ``verify``  — logic replay of a generated seed (``randomizer.verify``);
* ``memory``  — read-only diagnostic of the running game memory;
* ``apworld GAME.nup [OUT.apworld]`` — build the Archipelago world from the game;
* ``ap-install PATCH.aprmk GAME.nup MODS_FOLDER [--no-ingame-tracker]`` — build and install
  the mod of an Archipelago patch (with the in-game tracker module, unless told not to);
* ``update-tracker SEED_OR_MODS_FOLDER [--add] [--nup GAME.nup]`` — bring an installed seed's
  in-game tracker (its data file and module) to this version; ``--add`` gives it to a seed made
  without it, ``--nup`` makes the items' icons from the game too;
* ``ap-client MOD_FOLDER SERVER [--password P] [--slot NAME]`` — Archipelago client without
  the window: sends the checks and the goal of the running game;
* ``ap-give SEED_FOLDER [N]`` — test of the Archipelago reception: lists the items other
  worlds can send, or signals item N to the running game (Hookshot);
* ``reload-test GAME.nup SEED_FOLDER a|b|off`` — in-game test: is a mod file rewritten
  while the game runs read again (Kokiri Forest message board)?
"""
import sys

NO_INGAME_TRACKER = '--no-ingame-tracker'
ADD_INGAME_TRACKER = '--add'
NUP_OPTION = '--nup'


def main(argv=None):
    """Run a command; a crash is also written to ``<data>/error.log`` (windowed builds have no console)."""
    try:
        return _run(argv)
    except SystemExit:
        raise
    except BaseException:
        import traceback
        from oot_rando.paths import data_dir
        try:
            data_dir().mkdir(parents=True, exist_ok=True)
            (data_dir() / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        except OSError:
            pass
        raise


def _run(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv and not argv[0].startswith('-') else 'gui'
    if command == 'gui':
        from oot_rando.gui.randomizer_gui import main as gui
        return gui(argv)
    if command == 'audit':
        from oot_rando.logic.audit_rules import main as audit
        return audit(argv)
    if command == 'verify':
        from oot_rando.randomizer.verify import main as verify
        return verify(argv)
    if command == 'memory':
        from oot_rando.tracker.live_memory import main as memory
        return memory()
    if command == 'selftest':
        return selftest(argv)
    if command == 'apworld':
        return apworld(argv)
    if command == 'ap-install':
        return ap_install(argv)
    if command == 'update-tracker':
        return update_tracker(argv)
    if command == 'ap-client':
        from oot_rando.archipelago.client import main as client
        return client(argv)
    if command == 'ap-give':
        return ap_give(argv)
    if command == 'reload-test':
        from oot_rando.archipelago.reload_test import main as reload_test
        return reload_test(argv)
    print(__doc__)
    return 2


def ap_give(argv):
    """``ap-give SEED_FOLDER [N]``: test of the Archipelago reception (Hookshot, game running).

    Without N, lists the items other worlds can send; with N, signals item N to the game.
    """
    import json
    from pathlib import Path
    from oot_rando.patching.soul_adapter import murmur3
    from oot_rando.tracker.live_memory import LiveGameData, LiveUnavailable, set_bool_in
    if not argv:
        print('Usage: ap-give SEED_FOLDER [N]')
        return 2
    manifest = json.loads((Path(argv[0]) / 'manifest.json').read_text(encoding='utf-8'))
    items = (manifest.get('skips') or {}).get('ap_mailbox', {}).get('items', [])
    if len(argv) == 1:
        for index, record in enumerate(items):
            print(f'{index}: {record["item"]} (from {record["player"]}, {record["location"]})')
        return 0
    record = items[int(argv[1])]
    try:
        done = set_bool_in(LiveGameData(), murmur3(record['recv']), True)
    except LiveUnavailable as error:
        print('Game unreachable:', error)
        return 1
    print(f'{record["item"]} signalled: its item get should start.' if done
          else 'Flag unknown to the running game: is this seed the one installed?')
    return 0 if done else 1


def apworld(argv):
    from pathlib import Path
    from oot_rando.archipelago.apworld_build import build_apworld
    from oot_rando.paths import data_dir
    if not argv:
        print('Usage: apworld GAME.nup [OUTPUT.apworld]')
        return 2
    output = Path(argv[1]) if len(argv) > 1 else data_dir() / 'oot_remake.apworld'
    path = build_apworld(argv[0], output, print)
    print(f'Written: {path}')
    print('Copy it into the custom_worlds folder of Archipelago.')
    return 0


def ap_install(argv):
    from oot_rando.archipelago.bridge import load_patch, settings_from_patch
    from oot_rando.paths import data_dir
    from oot_rando.randomizer.randomizer_services import generate_in_mods
    ingame_tracker = NO_INGAME_TRACKER not in argv
    argv = [argument for argument in argv if argument != NO_INGAME_TRACKER]
    if len(argv) != 3:
        print(f'Usage: ap-install PATCH.aprmk GAME.nup MODS_FOLDER [{NO_INGAME_TRACKER}]')
        return 2
    settings = settings_from_patch(load_patch(argv[0]))
    installed = generate_in_mods(argv[1], argv[2], settings, print, archive=data_dir() / 'seeds-uninstalled',
                                 ingame_tracker=ingame_tracker)
    print(f'Installed: {installed}')
    return 0


def update_tracker(argv):
    from oot_rando.randomizer.randomizer_services import update_ingame_trackers
    add = ADD_INGAME_TRACKER in argv
    argv = [argument for argument in argv if argument != ADD_INGAME_TRACKER]
    nup = None
    if NUP_OPTION in argv[:-1]:
        at = argv.index(NUP_OPTION)
        nup = argv[at + 1]
        del argv[at:at + 2]
    if len(argv) != 1 or NUP_OPTION in argv:
        print(f'Usage: update-tracker SEED_OR_MODS_FOLDER [{ADD_INGAME_TRACKER}] [{NUP_OPTION} GAME.nup]')
        return 2
    try:
        results = update_ingame_trackers(argv[0], add=add, nup=nup)
    except ValueError as error:
        print(error)
        return 1
    for seed, written in results:
        print(f'Updated {seed}: ' + ', '.join(written) if written else f'Already up to date: {seed}')
    return 0


def selftest(argv):
    """Check a (frozen) build: ``selftest [GAME.nup OUTPUT_FOLDER [SEED]]``.

    Imports every module, loads the logic world and compiles it. With a game
    file, also generates a seed into a new folder and replays it (``verify``).
    The report goes to ``<data>/selftest.json`` (a windowed build has no console).
    """
    import importlib
    import json
    import pkgutil
    import traceback
    from pathlib import Path

    import oot_rando
    from oot_rando.paths import FROZEN, data_dir
    report = {'frozen': FROZEN, 'version': oot_rando.__version__, 'ok': False}
    try:
        modules = [m.name for m in pkgutil.walk_packages(oot_rando.__path__, 'oot_rando.')]
        for name in modules:
            importlib.import_module(name)
        report['modules'] = len(modules)
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        world = World()
        logic = Logic(world, {'open_forest': 'closed_deku'})
        report.update(world=world.version, locations=len(logic.location_names()))
        if len(argv) >= 2:
            from oot_rando.randomizer.randomizer_core import Settings, generate
            from oot_rando.randomizer.verify import verify
            from oot_rando.logic import rando_options
            options = rando_options.preset('ap_defaults')
            settings = Settings.from_dict({'seed': argv[2] if len(argv) > 2 else 'selftest', 'randomize_chests': False,
                                          'full': options})
            generate(Path(argv[0]), Path(argv[1]), settings)
            result = verify(argv[0], argv[1])
            report.update(beatable=result['beatable'], spheres=result['spheres'])
        report['ok'] = True
    except Exception:  # noqa: BLE001 - the report must say what failed
        report['error'] = traceback.format_exc()
    out = data_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'selftest.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
