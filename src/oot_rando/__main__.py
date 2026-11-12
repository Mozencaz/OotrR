"""Entry point: ``python -m oot_rando [commande]`` (or the portable executable).

Without a command, the graphical application starts. Commands:

* ``audit``   — audit of the logic against the remake maps (``logic.audit_rules``);
* ``verify``  — logic replay of a generated seed (``randomizer.verify``);
* ``memory``  — read-only diagnostic of the running game memory;
* ``apworld GAME.nup [OUT.apworld]`` — build the Archipelago world from the game;
* ``ap-install PATCH.aprmk GAME.nup MODS_FOLDER`` — build and install the mod of an
  Archipelago patch.
"""
import sys


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
    print(__doc__)
    return 2


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
    if len(argv) != 3:
        print('Usage: ap-install PATCH.aprmk GAME.nup MODS_FOLDER')
        return 2
    settings = settings_from_patch(load_patch(argv[0]))
    installed = generate_in_mods(argv[1], argv[2], settings, print, archive=data_dir() / 'seeds-uninstalled')
    print(f'Installed: {installed}')
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
