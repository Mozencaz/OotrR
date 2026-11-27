"""Golden seeds: fingerprint the output of a few reference generations.

A refactor that must not change behaviour keeps the fingerprint identical:

    python tools/golden_seeds.py GAME.nup golden.json              # record
    python tools/golden_seeds.py GAME.nup new.json --compare golden.json

A content change with the same ``GENERATOR_VERSION`` is reported as an error: the seed
id would no longer identify the output. Every file of the produced mod is hashed
(``romfs/`` byte for byte, the JSON documents canonicalised without ``app_version``).
Generation and ``verify`` times are recorded too; ``--src`` runs another copy of the sources.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

CASES = {
    'ap_defaults': {'full': 'ap_defaults'},
    'everything_qol': {'full': 'everything', 'skip_locked_cutscenes': True, 'skip_auto_dialogues': True,
                       'skip_chest_cutscenes': True, 'skulltulas_always_present': True},
    'prudent': {'full': 'prudent'},
}
VOLATILE = ('app_version',)


def _canonical_json(raw):
    value = json.loads(raw)

    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in VOLATILE}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    value = strip(value)
    if isinstance(value, dict):
        # The tracking digest in the manifest hashes the exact tracking bytes: kept apart.
        if isinstance(value.get('tracking'), dict):
            value['tracking'].pop('sha256', None)
        # Resources consulted while generating: some reads stop at the first path found
        # (event flow searches), so this list varies between runs. Informational only.
        value.pop('source_files', None)
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')


def _source_files(raw):
    value = json.loads(raw)
    sources = value.get('source_files') if isinstance(value, dict) else None
    return json.dumps(sources, sort_keys=True).encode('utf-8') if sources is not None else None


def fingerprint(directory):
    """{relative path: sha256} of a mod folder; JSON files canonicalised, plus their raw hash."""
    directory = Path(directory)
    result = {}
    for path in sorted(p for p in directory.rglob('*') if p.is_file()):
        name = path.relative_to(directory).as_posix()
        data = path.read_bytes()
        if path.suffix == '.json':
            result[name] = hashlib.sha256(_canonical_json(data)).hexdigest()
            result[name + '#raw'] = hashlib.sha256(data).hexdigest()
            sources = _source_files(data)
            if sources is not None:
                result[name + '#raw-sources'] = hashlib.sha256(sources).hexdigest()
        elif path.suffix == '.txt':
            result[name] = hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()
        else:
            result[name] = hashlib.sha256(data).hexdigest()
    return result


def run(nup, cases, check, keep=None):
    from oot_rando.logic import rando_options
    from oot_rando.randomizer.randomizer_core import Settings, generate
    from oot_rando.randomizer.verify import verify
    report = {}
    with tempfile.TemporaryDirectory(prefix='golden-') as temporary:
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=True)
            temporary = keep
        for name in cases:
            spec = dict(CASES[name])
            spec['full'] = rando_options.preset(spec['full'])
            settings = Settings.from_dict({'seed': 'golden-' + name, 'randomize_chests': False, **spec})
            output = Path(temporary) / name
            start = time.perf_counter()
            manifest = generate(nup, output, settings)
            generated = time.perf_counter() - start
            entry = {'seed_id': manifest['seed_id'], 'generate_seconds': round(generated, 2),
                     'generator_version': manifest['generator_version']}
            if check:
                start = time.perf_counter()
                result = verify(nup, output)
                entry['verify_seconds'] = round(time.perf_counter() - start, 2)
                entry['beatable'] = result['beatable']
            entry['files'] = fingerprint(output)
            report[name] = entry
            print(f"{name}: generate {entry['generate_seconds']}s"
                  + (f", verify {entry['verify_seconds']}s, beatable={entry['beatable']}" if check else ''),
                  flush=True)
    return report


def compare(new, old):
    """Lines describing every difference of content (timings ignored)."""
    lines = []
    for name in sorted(set(new) | set(old)):
        a, b = old.get(name), new.get(name)
        if a is None or b is None:
            lines.append(f'{name}: only in {"new" if a is None else "reference"}')
            continue
        for path in sorted(set(a['files']) | set(b['files'])):
            if a['files'].get(path) != b['files'].get(path):
                lines.append(f'{name}: {path} differs')
        for key in ('seed_id', 'beatable'):
            if key in a and key in b and a[key] != b[key]:
                lines.append(f'{name}: {key} {a[key]} -> {b[key]}')
    return lines


def version_bumped(new, old):
    """Whether every case was generated by another GENERATOR_VERSION than in the reference
    (a reference recorded before the version was kept counts as bumped: unknown)."""
    versions = [(old[name].get('generator_version'), new[name].get('generator_version'))
                for name in set(new) & set(old)]
    return all(before is None or before != after for before, after in versions)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('nup', type=Path)
    parser.add_argument('output', type=Path, help='JSON report to write')
    parser.add_argument('--compare', type=Path, help='Reference report: exit 1 on any content difference')
    parser.add_argument('--src', type=Path, default=Path(__file__).resolve().parents[1] / 'src')
    parser.add_argument('--case', action='append', choices=sorted(CASES), help='Only these cases (repeatable)')
    parser.add_argument('--no-verify', action='store_true')
    parser.add_argument('--keep', type=Path, help='Keep the generated mods in this new folder')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.src.resolve()))
    report = run(args.nup, args.case or list(CASES), not args.no_verify, args.keep)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True), encoding='utf-8')
    if args.compare:
        differences = compare(report, json.loads(args.compare.read_text(encoding='utf-8')))
        raw_only = [d for d in differences if '#raw' in d]
        content = [d for d in differences if d not in raw_only]
        for line in differences:
            print(('  (raw) ' if line in raw_only else '  DIFF ') + line)
        print('Identical content.' if not content else f'{len(content)} content difference(s).')
        if content and not version_bumped(report, json.loads(args.compare.read_text(encoding='utf-8'))):
            # Same generator version, other files: two different seeds would share one seed id
            # and ``verify`` would accept a seed it can no longer rebuild.
            print('ERROR: the output changed but GENERATOR_VERSION did not (randomizer/randomizer_core.py). '
                  'Bump it, or find what changed the output.')
        return 1 if content else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
