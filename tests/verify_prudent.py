"""Independent semantic checks of a generated prudent release against the NUP."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'src'))
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import tempfile

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import Byml, dictionaries, decompress
from oot_rando.randomizer.randomizer_core import Settings, generate, MAP, ADULT_MAP, STATIC
from oot_rando.randomizer.randomizer_services import read_artifact
from oot_rando.game.world_maps import effective_members, SAFE_CHESTS
from oot_rando.patching.qol_patches import GUARD, WALL, REACTION, AREAS, LOGIC_GROUP


def verify(nup_path):
    nup = Nup(nup_path)
    try:
        dic, members = dictionaries(nup), effective_members(nup)
        with tempfile.TemporaryDirectory(prefix='oot-prudent-check-') as temporary:
            output, repeated = Path(temporary) / 'a', Path(temporary) / 'b'
            settings = Settings('integration-prudente', categories={'world_chests': True})
            manifest = generate(nup_path, output, settings)
            read_artifact(output)
            assert generate(nup_path, repeated, settings) == manifest
            for path in output.rglob('*'):
                if path.is_file():
                    assert path.read_bytes() == (repeated / path.relative_to(output)).read_bytes(), path
            private = json.loads((output / 'spoiler.json').read_text(encoding='utf-8'))
            world = [p for p in private['placements'] if p['category'] == 'world_chests']
            assert world and Counter(p['before'] for p in world) == Counter(p['after'] for p in world)
            assert all(p['before'] in SAFE_CHESTS and p['after'] in SAFE_CHESTS for p in world)
            maps = [p for p in manifest['files'] if p.endswith('.bcett.byml.zs')]
            for path in maps:
                expected = copy.deepcopy(Byml(decompress(nup.read(members[path]), dic)).root)
                for placement in private['placements']:
                    if path not in placement['resources']:
                        continue
                    matches = [actor for actor in expected['Actors'] if str(actor.get('Hash')) == placement['hash']]
                    assert len(matches) == 1
                    actor = matches[0]
                    if placement['category'] == 'world_chests':
                        assert actor['Gyaml'] == 'Obj_TBox_A_01'
                        assert not any(key in actor['Dynamic'] for key in ('GetEventName', 'Drop__DropActor_Substitute', 'Drop__CheckActor', 'IsEnableRepeatOpen', 'Drop__DropTable'))
                    assert actor['Dynamic']['Drop__DropActor'] == placement['before']
                    actor['Dynamic']['Drop__DropActor'] = placement['after']
                if path == MAP:
                    expected['Actors'] = [a for a in expected['Actors'] if a.get('Hash') != WALL]
                if path == STATIC:
                    expected['Actors'] = [a for a in expected['Actors'] if a.get('Hash') not in {GUARD, REACTION} | AREAS]
                    expected['AiGroups'] = [g for g in expected['AiGroups'] if g.get('Hash') != LOGIC_GROUP]
                    for key in ('FarDeleteGroups', 'SimultaneousGroups'):
                        expected[key] = [group for group in expected[key] if set(group) != {REACTION} | AREAS]
                actual = Byml(decompress((output / 'romfs' / path).read_bytes(), dic)).root
                assert actual == expected, 'Unexpected semantic changes in ' + path
            assert MAP in maps and ADULT_MAP in maps
            public = json.loads((output / 'checks.json').read_text(encoding='utf-8'))
            assert len(public['checks']) == 4 + len(world)
            assert manifest['complete_randomizer'] is False and manifest['progression_randomized'] is False
            assert 'placements' not in manifest and 'placements' not in public
            return {'map_semantic_comparisons': len(maps), 'ordinary_chests': len(world),
                    'public_checks': len(public['checks']), 'reproduction': 'byte-identical',
                    'progression_randomized': False, 'game_launched': False}
    finally:
        nup.stream.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nup', type=Path)
    print(json.dumps(verify(parser.parse_args().nup), indent=2))
