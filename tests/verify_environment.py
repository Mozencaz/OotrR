"""Local static integration: environment toggles, composition and reproduction."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'src'))
import copy
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import Byml, decompress, dictionaries
from oot_rando.randomizer.randomizer_core import Settings, generate
from oot_rando.randomizer.randomizer_services import read_artifact
from oot_rando.game.world_maps import build_world, effective_members, NATIVE_POOL


def verify(nup_path):
    categories = ('pots', 'bushes', 'rocks')
    nup = Nup(nup_path)
    try:
        dic = dictionaries(nup)
        members = effective_members(nup)
        for category in categories:
            result = build_world(nup, dic, {category: True}, 'toggle-test')
            assert set(result['coverage']) == {category}
            assert result['placements'], category
            assert all(p['category'] == category for p in result['placements'])
            edits = defaultdict(list)
            for placement in result['placements']:
                assert placement['after'] in NATIVE_POOL
                assert placement['before'] != placement['after']
                assert placement['repeatable']
                for resource in placement['resources']:
                    edits[resource].append(placement)
            for resource, changes in edits.items():
                expected = copy.deepcopy(Byml(decompress(nup.read(members[resource]), dic)).root)
                for change in changes:
                    actors = [a for a in expected['Actors'] if str(a.get('Hash')) == change['hash']]
                    assert len(actors) == 1
                    actor = actors[0]
                    assert actor['Dynamic']['Drop__DropActor'] == change['before']
                    assert not actor['Dynamic'].get('Drop__DropTable')
                    actor['Dynamic']['Drop__DropActor'] = change['after']
                assert Byml(result['raw_maps'][resource]).root == expected
        with tempfile.TemporaryDirectory(prefix='oot-environment-') as temporary:
            base = Path(temporary)
            settings = Settings('environment-composed', categories=dict.fromkeys(categories + ('world_chests',), True))
            first = generate(nup_path, base / 'first', settings)
            read_artifact(base / 'first')
            second = generate(nup_path, base / 'second', settings)
            assert first == second
            for path in (base / 'first').rglob('*'):
                if path.is_file():
                    assert path.read_bytes() == (base / 'second' / path.relative_to(base / 'first')).read_bytes()
            assert all(first['coverage'][c]['changed_instances'] > 0 for c in categories)
            print(json.dumps(first['coverage'], ensure_ascii=False, indent=2))
    finally:
        nup.stream.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('nup', type=Path)
    verify(parser.parse_args().nup)
