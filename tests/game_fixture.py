"""Game scans shared by the tests of one process (``OOT_NUP`` only).

Each scan runs once per process; every call returns a fresh copy (tests and the
planner mutate what they get), much cheaper than scanning the game again.
"""
import functools
import os
import pickle

NUP = os.environ.get('OOT_NUP')


def _open():
    from oot_rando.formats.inspect_nup import Nup
    from oot_rando.formats.inspect_resources import dictionaries
    from oot_rando.game.world_maps import effective_members
    nup = Nup(NUP)
    return nup, dictionaries(nup), effective_members(nup)


@functools.cache
def _scan(kind):
    from oot_rando.game.extra_sources import scan_world
    from oot_rando.game.remake_world import scan_maps
    nup, dictionaries, members = _open()
    try:
        result = (scan_maps if kind == 'maps' else scan_world)(nup, dictionaries, members)
    finally:
        nup.stream.close()
    return pickle.dumps(result, pickle.HIGHEST_PROTOCOL)


def scan_maps():
    """A copy of ``remake_world.scan_maps`` on the game: (maps, groups, enemies)."""
    return pickle.loads(_scan('maps'))


def scan_world():
    """A copy of ``extra_sources.scan_world`` on the game: (maps, groups, enemies, extra)."""
    return pickle.loads(_scan('world'))
