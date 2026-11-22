"""Measure generation from exported settings or a manifest, without installing a mod.

python tools/benchmark_generation.py GAME.nup SETTINGS.json NEW_OUTPUT [--profile]
"""
import argparse
import cProfile
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from oot_rando.randomizer.randomizer_core import Settings, generate  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nup', type=Path)
    parser.add_argument('settings', type=Path)
    parser.add_argument('output', type=Path, help='New folder; existing output is never overwritten')
    parser.add_argument('--profile', action='store_true', help='Also record cProfile data (adds overhead)')
    args = parser.parse_args()
    payload = json.loads(args.settings.read_text(encoding='utf-8'))
    settings = Settings.from_dict(payload.get('settings', payload))
    stages = []
    start = time.perf_counter()

    def progress(message):
        elapsed = time.perf_counter() - start
        stages.append({'seconds': elapsed, 'message': message})
        print(f'{elapsed:8.2f}s  {message}', flush=True)

    profile = cProfile.Profile() if args.profile else None
    if profile:
        profile.enable()
    try:
        manifest = generate(args.nup, args.output, settings, progress)
    finally:
        if profile:
            profile.disable()
    elapsed = time.perf_counter() - start
    report = {'seconds': elapsed, 'profiled': args.profile, 'output': str(args.output.resolve()),
              'generator_version': manifest['generator_version'], 'seed_id': manifest['seed_id'],
              'resources': len(manifest['files']), 'stages': stages}
    destination = args.output.parent / (args.output.name + '.benchmark.json')
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if profile:
        profile.dump_stats(str(args.output.parent / (args.output.name + '.prof')))
    print(f'Completed in {elapsed:.2f}s; measurements: {destination}', flush=True)


if __name__ == '__main__':
    main()
