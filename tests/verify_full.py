"""Compatibility wrapper: ``python tests/verify_full.py GAME.nup SEED_FOLDER``."""
import sys

import _src_path  # noqa: F401
from oot_rando.randomizer.verify import main, verify  # noqa: F401

if __name__ == '__main__':
    sys.exit(main())
