"""The same seed plans the same way in every process (string hashing is randomised per process)."""
import _src_path  # noqa: F401
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent

PLAN = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import _src_path  # noqa: F401
from game_fixture import scan_world
from oot_rando.logic import rando_options
from oot_rando.logic.world import World
from oot_rando.randomizer import full_randomizer
_, groups, enemies, extra = scan_world()
result = full_randomizer.plan(World(), rando_options.preset('everything'), groups, enemies, 'determinism',
                              extra=extra)
# Exactly what generate() writes to tracking.json and the spoiler, in its own order.
print(json.dumps({key: result[key] for key in ('tracking_logic', 'placements', 'spoiler', 'playthrough')},
                 ensure_ascii=False))
"""


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class DeterminismTests(unittest.TestCase):
    def test_plan_output_does_not_depend_on_string_hashing(self):
        outputs = []
        for hash_seed in ('1', '2'):
            env = dict(os.environ, PYTHONHASHSEED=hash_seed)
            done = subprocess.run([sys.executable, '-c', PLAN, str(HERE)], cwd=HERE, env=env,
                                  capture_output=True, text=True, encoding='utf-8', check=True)
            outputs.append(json.loads(done.stdout.strip().splitlines()[-1]))
        for key in outputs[0]:
            self.assertEqual(json.dumps(outputs[0][key], ensure_ascii=False),
                             json.dumps(outputs[1][key], ensure_ascii=False), key)


if __name__ == '__main__':
    unittest.main()
