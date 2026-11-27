"""Run the test modules in parallel processes (standard library only).

    python tests/run_parallel.py [-j N] [--durations N] [MODULE ...]

Each ``test_*.py`` module runs in its own ``python -m unittest`` process, the
slowest ones first. The exit status is non-zero when any module fails; the
output of failing modules is printed in full. A module stuck longer than
``--timeout`` seconds is stopped and reported as failed.
"""
import argparse
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
# Known slow modules first, so that they do not start last and stretch the run.
SLOW_FIRST = ('test_full_randomizer', 'test_progressive', 'test_world_openings', 'test_child_time_door',
              'test_extra_sources', 'test_archipelago', 'test_determinism', 'test_rules',
              'test_time_door_settings', 'test_item_forms', 'test_start_options', 'test_story_fixes')


def _text(value):
    return value.decode('utf-8', 'replace') if isinstance(value, bytes) else (value or '')


def run_module(name, timeout):
    # A hung module dumps every thread's stack shortly before its timeout, then exits.
    script = (f'import faulthandler, unittest; faulthandler.dump_traceback_later({max(timeout - 30, 1)}, exit=True); '
              f'unittest.main(module=None, argv=["unittest", {name!r}])')
    start = time.perf_counter()
    try:
        done = subprocess.run([sys.executable, '-c', script], cwd=HERE, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout)
        code, output = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as error:
        code, output = -1, f'Timed out after {timeout} s.\n' + _text(error.stdout) + _text(error.stderr)
    return name, code, output, time.perf_counter() - start


def summary_line(output):
    for line in reversed(output.splitlines()):
        if line.startswith(('OK', 'FAILED')):
            return line
    return '?'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-j', '--jobs', type=int, default=os.cpu_count() or 2)
    parser.add_argument('--durations', type=int, default=10, help='Print the N slowest modules')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('modules', nargs='*')
    args = parser.parse_args(argv)
    names = args.modules or sorted(p.stem for p in HERE.glob('test_*.py'))
    names.sort(key=lambda n: (SLOW_FIRST.index(n) if n in SLOW_FIRST else len(SLOW_FIRST), n))
    start = time.perf_counter()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for name, code, output, seconds in pool.map(lambda n: run_module(n, args.timeout), names):
            results.append((name, code, output, seconds))
            if code:
                print(f'\n===== {name} FAILED =====\n{output}', flush=True)
    failed = [r for r in results if r[1]]
    ran = skipped = 0
    for _, _, output, _ in results:
        for line in output.splitlines():
            if line.startswith('Ran '):
                ran += int(line.split()[1])
        line = summary_line(output)
        if 'skipped=' in line:
            skipped += int(line.split('skipped=')[1].split(')')[0].split(',')[0])
    if args.durations:
        print(f'\nSlowest {args.durations} modules:')
        for name, _, _, seconds in sorted(results, key=lambda r: -r[3])[:args.durations]:
            print(f'{seconds:8.1f}s  {name}')
    print(f'\n{len(names)} modules, {ran} tests ({skipped} skipped) in {time.perf_counter() - start:.1f}s '
          f'with {args.jobs} processes: ' + ('OK' if not failed else f'{len(failed)} module(s) FAILED: '
                                              + ', '.join(r[0] for r in failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
