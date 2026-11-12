"""Integration verification against the local NUP; no game launch or real install."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'src'))
import argparse
import itertools
import json
import tempfile
from pathlib import Path

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import Byml, decompress, dictionaries
from oot_rando.randomizer.randomizer_core import Settings, generate, placements_for, ADULT_MAP
from oot_rando.randomizer.randomizer_services import read_artifact, ManualTracker
from oot_rando.patching.randomize_kokiri import MAP, RESTBL, CHESTS
from oot_rando.patching.qol_patches import (STATIC, INTRO, PHYSICS, EVENT_SETTINGS, LOCKED_CUTSCENES, list_path,
                         AREA_PRESENTATIONS, flow_path)


def verify(nup_path):
    nup = Nup(nup_path)
    try:
        dic = dictionaries(nup)
        original = Byml(decompress(nup.read('1/romfs/' + MAP), dic)).root
    finally:
        nup.stream.close()
    with tempfile.TemporaryDirectory(prefix='oot-verification-') as temporary:
        base = Path(temporary)
        # Exercise every combination of the three validated QoL adapters, always with chests.
        for index, values in enumerate(itertools.product((False, True), repeat=3)):
            settings = Settings('interface check', open_forest=values[0], skip_locked_cutscenes=values[1],
                                skip_auto_dialogues=values[2], excluded_checks=[str(min(CHESTS))])
            output = base / str(index)
            manifest = generate(nup_path, output, settings)
            read_artifact(output)
            expected_files = {MAP, ADULT_MAP, RESTBL, 'GameData/GameDataList.Product.110.byml.zs',
                              'Event/EventFlow/OpeningEvent.bfevfl.zs'}
            if values[0]:
                expected_files |= {STATIC, PHYSICS}
            if values[1]:
                expected_files |= {INTRO} | {list_path(name) for name in LOCKED_CUTSCENES} | {
                    flow_path(name) for name in AREA_PRESENTATIONS}
                expected_files |= {flow_path(name) for name in manifest['skips']['cutscene_windows']}
            if values[1] or values[2]:
                expected_files.add(EVENT_SETTINGS)
            assert set(manifest["files"]) == expected_files, (values, sorted(set(manifest["files"]) ^ expected_files)[:10])
            actual = Byml(decompress((output / 'romfs' / MAP).read_bytes(), dic)).root
            for actor in actual['Actors']:
                if actor.get('Hash') in CHESTS:
                    assert actor['Dynamic']['Drop__DropActor'] == placements_for(settings)[actor['Hash']]
            untouched = {a['Hash']: a for a in original['Actors'] if a.get('Hash') not in CHESTS}
            for actor in actual['Actors']:
                if actor.get('Hash') not in CHESTS:
                    assert actor == untouched[actor['Hash']]
            public = json.dumps(manifest) + (output / 'checks.json').read_text(encoding='utf-8')
            assert 'placements' not in public and 'before' not in json.dumps(manifest.get('settings'))
            if index == 7:
                second = base / 'reproduced'
                assert generate(nup_path, second, settings) == manifest
                for path in output.rglob('*'):
                    if path.is_file():
                        assert path.read_bytes() == (second / path.relative_to(output)).read_bytes()
        # Reward-free QoL generation.
        only_qol = base / 'qol'
        manifest = generate(nup_path, only_qol, Settings('qol-only', randomize_chests=False, pool=[]))
        assert RESTBL in manifest['files']  # saved seed marker grows GameData even without rewards
        read_artifact(only_qol)
        ids = [str(h) for h in CHESTS]
        tracker = ManualTracker(base / 'tracker', manifest['seed_id'], 'test', ids)
        tracker.set_completed(ids[0], True)
        assert ManualTracker(base / 'tracker', manifest['seed_id'], 'test', ids).completed == {ids[0]}
        assert not ManualTracker(base / 'tracker', manifest['seed_id'], 'other', ids).completed
        assert not ManualTracker(base / 'tracker', 'different', 'test', ids).completed
        member = next(iter(manifest['files']))
        (only_qol / 'romfs' / member).write_bytes(b'corrupted')
        try:
            read_artifact(only_qol)
        except ValueError:
            pass
        else:
            raise AssertionError('Corrupted resource accepted')
    return {'qol_combinations': 8, 'reproduction': 'byte-identical',
            'qol_without_rewards': 'passed', 'isolated_install_and_tracker': 'passed',
            'game_launched': False, 'real_mods_modified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nup', type=Path)
    print(json.dumps(verify(parser.parse_args().nup), indent=2))
