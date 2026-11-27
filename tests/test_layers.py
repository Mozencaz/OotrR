"""Import layers of the application: a module only imports modules of its own layer or below.

Checked on every import, including the ones inside functions (an import deferred to
dodge a cycle is still a dependency). Layers, lowest first:

0. ``formats``, ``catalog``, ``paths``, ``ed25519``, ``update_key``, ``system``, ``versions``,
   ``pc_port``, ``path_safety``, ``native_dialogs``: file formats, the names of the game, where
   files live, emulators and PC ports, version numbers, path limits, file pickers;
1. ``game``: the remake's world model (sources, items, maps);
2. ``logic``: the AP rules and the options;
3. ``patching``: the patches applied to the game files;
4. ``randomizer.full_randomizer``: the solver (also vendored in the apworld);
5. ``archipelago.bridge``, ``archipelago.apworld_build``: the Archipelago world;
6. the rest of ``randomizer``: seed generation, verification, installed seeds; ``party_health``;
7. ``tracker``, the rest of ``archipelago`` (client), ``updater``, ``parties``;
8. ``gui``, ``__main__``.

A new upward import is a design error: move the shared code down instead
(names of the game go to ``catalog``).
"""
import _src_path  # noqa: F401
import ast
from pathlib import Path
import unittest

PACKAGE = Path(__file__).resolve().parents[1] / 'src' / 'oot_rando'

LAYERS = [
    ('formats', 'catalog', 'paths', 'ed25519', 'update_key', 'system', 'versions', 'pc_port',
     'path_safety', 'native_dialogs', ''),
    ('game',),
    ('logic',),
    ('patching',),
    ('randomizer.full_randomizer',),
    ('archipelago.bridge', 'archipelago.apworld_build', 'archipelago'),
    ('randomizer', 'party_health'),
    ('tracker', 'archipelago.client', 'archipelago.receive', 'archipelago.reload_test', 'updater', 'parties'),
    ('gui', '__main__'),
]


def layer_of(module):
    """Layer of ``module`` (dotted, without ``oot_rando.``): the most specific prefix wins."""
    best = None
    for index, prefixes in enumerate(LAYERS):
        for prefix in prefixes:
            if module == prefix or (prefix and module.startswith(prefix + '.')):
                if best is None or len(prefix) > best[1]:
                    best = (index, len(prefix))
    if best is None:
        raise AssertionError('Module without a layer: ' + module)
    return best[0]


def module_name(path):
    parts = list(path.relative_to(PACKAGE).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def imports(path):
    """Every ``oot_rando`` module imported by ``path`` (top level or not), with its line."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    package = module_name(path).split('.') if path.name != '__init__.py' else module_name(path).split('.') + ['_']
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith('oot_rando.'):
                    yield alias.name[len('oot_rando.'):], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - node.level]
                target = '.'.join(base + ([node.module] if node.module else []))
            elif node.module == 'oot_rando':
                for alias in node.names:   # a module of the package, or a name of its __init__
                    is_module = (PACKAGE / (alias.name + '.py')).is_file() or (PACKAGE / alias.name).is_dir()
                    yield (alias.name if is_module else ''), node.lineno
                continue
            elif node.module and node.module.startswith('oot_rando.'):
                target = node.module[len('oot_rando.'):]
            else:
                continue
            yield target, node.lineno


def violations():
    found = []
    for path in sorted(PACKAGE.rglob('*.py')):
        source = module_name(path)
        own = layer_of(source)
        for target, line in imports(path):
            if layer_of(target) > own:
                found.append(f'{path.relative_to(PACKAGE).as_posix()}:{line} {source} -> {target}')
    return found


class LayerTest(unittest.TestCase):
    def test_no_upward_import(self):
        self.assertEqual(violations(), [])

    def test_every_module_has_a_layer(self):
        for path in PACKAGE.rglob('*.py'):
            layer_of(module_name(path))


if __name__ == '__main__':
    for line in violations():
        print(line)
