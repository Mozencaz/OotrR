"""Developer tool: refresh the logic world of the project from an Archipelago OoT world.

The application never reads Archipelago: its glitchless logic lives in
``src/oot_rando/logic/world/`` (MIT-licensed data derived from the Archipelago
OoT world, itself derived from OoT Randomizer). This tool re-imports the base
layer when the upstream rules change:

* ``data/World/*.json`` (vanilla dungeons only, no Master Quest) → ``regions/*.json``;
* ``data/LogicHelpers.json`` → ``helpers.json``;
* ``LocationList.pyc`` / ``Items.pyc`` tables → ``locations.json`` / ``items.json``
  (only the fields the logic uses);
* ``LICENSE`` → ``LICENSE-archipelago-oot.txt``.

The remake layer (``remake.json``) is hand-written and never touched here.

Usage: ``python tools/import_archipelago_world.py <Archipelago>/lib/worlds/oot`` (Python 3.13,
the version the ``.pyc`` tables are compiled for).
"""
import hashlib
import json
import marshal
import sys
import types
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / 'src' / 'oot_rando' / 'logic' / 'world'
WORLD_FILES = ('Overworld.json', 'Bosses.json', 'Deku Tree.json', 'Dodongos Cavern.json',
               'Jabu Jabus Belly.json', 'Forest Temple.json', 'Fire Temple.json', 'Water Temple.json',
               'Shadow Temple.json', 'Spirit Temple.json', 'Bottom of the Well.json', 'Ice Cavern.json',
               'Gerudo Training Ground.json', 'Ganons Castle.json')


def strip_comments(text):
    """AP rule files are JSON with ``#`` comments and multi-line strings."""
    out, i, inside = [], 0, False
    while i < len(text):
        char = text[i]
        if inside:
            out.append(char)
            if char == '\\':
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                inside = False
        elif char == '"':
            inside = True
            out.append(char)
        elif char == '#':
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        else:
            out.append(char)
        i += 1
    return ''.join(out)


def read_rules(path):
    return json.loads(strip_comments(path.read_text(encoding='utf-8')), strict=False)


def load_pyc(path, name):
    """Execute a data-only AP module from bytecode with a stubbed ``BaseClasses``."""
    if sys.version_info[:2] != (3, 13):
        raise SystemExit('The Archipelago tables (.pyc) need Python 3.13.')
    stub = types.ModuleType('BaseClasses')

    class Item:
        pass

    class ItemClassification:
        filler, progression, useful, trap = 0, 1, 2, 4
        skip_balancing, progression_skip_balancing = 8, 9

    stub.Item, stub.ItemClassification = Item, ItemClassification
    previous = sys.modules.get('BaseClasses')
    sys.modules['BaseClasses'] = stub
    try:
        namespace = {'__name__': 'worlds.oot.' + name, '__package__': 'worlds.oot'}
        exec(marshal.loads(path.read_bytes()[16:]), namespace)
        return namespace
    finally:
        if previous is None:
            sys.modules.pop('BaseClasses', None)
        else:
            sys.modules['BaseClasses'] = previous


def one_line(rule):
    return ' '.join(rule.split()) if isinstance(rule, str) else rule


def normalise_region(region):
    """Rules on one line (whitespace is not significant in the rule language)."""
    region = dict(region)
    for key in ('locations', 'events', 'exits'):
        if key in region:
            region[key] = {name: one_line(rule) for name, rule in region[key].items()}
    return region


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        raise SystemExit('Usage: python tools/import_archipelago_world.py <Archipelago>/lib/worlds/oot')
    root = Path(argv[0])
    sources = {}

    def source(relative):
        path = root / relative
        if not path.is_file():
            raise SystemExit('Archipelago file not found: ' + str(path))
        sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    manifest = json.loads(source('archipelago.json').read_text(encoding='utf-8'))
    for name in WORLD_FILES:
        regions = [normalise_region(r) for r in read_rules(source('data/World/' + name))]
        write_json(TARGET / 'regions' / name, regions)
    write_json(TARGET / 'helpers.json', {k: one_line(v) for k, v in read_rules(source('data/LogicHelpers.json')).items()})
    locations = load_pyc(source('LocationList.pyc'), 'LocationList')['location_table']
    write_json(TARGET / 'locations.json', {
        name: {'type': entry[0], 'scene': entry[1], 'vanilla': entry[4],
               'categories': [entry[5]] if isinstance(entry[5], str) else list(entry[5] or ())}
        for name, entry in locations.items()})
    items = load_pyc(source('Items.pyc'), 'Items')['item_table']
    write_json(TARGET / 'items.json', {name: {'type': entry[0], 'progression': bool(entry[1])}
                                       for name, entry in items.items()})
    (TARGET / 'LICENSE-archipelago-oot.txt').write_text(source('LICENSE').read_text(encoding='utf-8'),
                                                        encoding='utf-8', newline='\n')
    write_json(TARGET / 'origin.json', {
        'description': 'Base layer imported from the Archipelago OoT world (MIT), see LICENSE-archipelago-oot.txt.',
        'archipelago_world_version': manifest.get('world_version') or manifest.get('version'),
        'region_files': list(WORLD_FILES), 'sources_sha256': dict(sorted(sources.items()))})
    print(f'World imported into {TARGET} ({len(locations)} locations, {len(items)} items).')


if __name__ == '__main__':
    main()
