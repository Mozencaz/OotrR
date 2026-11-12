"""The logic world of the remake, shipped with the application.

Two layers, both in ``logic/world/``:

* the **base world** (``regions/*.json``, ``helpers.json``, ``locations.json``,
  ``items.json``): glitchless OoT rules derived from the Archipelago OoT world
  (MIT, see ``LICENSE-archipelago-oot.txt``), refreshed with
  ``tools/import_archipelago_world.py``;
* the **remake layer** (``remake.json``): rules and regions where the remake
  differs, each with its reason.

Nothing is read from an Archipelago installation at run time.
"""
import hashlib
import json

from oot_rando.paths import resource

WORLD_DIR = ('logic', 'world')


def _load(*parts):
    path = resource(*WORLD_DIR, *parts)
    if path.is_file():
        return json.loads(path.read_text(encoding='utf-8'))
    # Packaged inside a zip (the Archipelago .apworld): read through the loader.
    import pkgutil
    return json.loads(pkgutil.get_data('oot_rando', '/'.join(WORLD_DIR + parts)).decode('utf-8'))


_REMAKE = _load('remake.json')
# Mutable on purpose: ``audit --no-fixes`` empties them temporarily.
REMAKE_LOCATION_RULES = {name: entry['rule'] for name, entry in _REMAKE['location_rules'].items()}
REMAKE_LOCATION_REGIONS = {name: (entry['from'], entry['to'])
                           for name, entry in _REMAKE['location_regions'].items()}


class World:
    """Regions, helpers, location and item tables of the remake logic (read-only)."""

    def __init__(self):
        origin = _load('origin.json')
        self.base_version = origin['archipelago_world_version']
        self.helpers = _load('helpers.json')
        self.regions = []
        for name in origin['region_files']:
            self.regions.extend(_load('regions', name))
        self.location_table = _load('locations.json')
        self.item_table = _load('items.json')
        self.remake = {'location_rules': dict(REMAKE_LOCATION_RULES),
                       'location_regions': {k: list(v) for k, v in REMAKE_LOCATION_REGIONS.items()}}

    @property
    def version(self):
        return f'remake-{self.fingerprint()[:12]} (base AP OoT {self.base_version})'

    def fingerprint(self):
        """SHA-256 of the logic content (stable across platforms and line endings)."""
        content = {'helpers': self.helpers, 'regions': self.regions, 'locations': self.location_table,
                   'items': self.item_table, 'remake': self.remake}
        return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def is_progression(self, item):
        entry = self.item_table.get(item)
        return bool(entry and entry['progression'])

    def vanilla_item(self, location):
        entry = self.location_table.get(location)
        return entry['vanilla'] if entry else None

    def location_type(self, location):
        entry = self.location_table.get(location)
        return entry['type'] if entry else None

    def location_areas(self, location):
        entry = self.location_table.get(location)
        return tuple(entry['categories']) if entry else ()
