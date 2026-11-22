"""Entry script of the portable executables (see oot_rando.spec)."""
import sys

from oot_rando.__main__ import main

if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()
    sys.exit(main())
