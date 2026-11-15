"""``archipelago.json`` in a seed folder (next to ``manifest.json``): how to connect to its room.

``{"server": "archipelago.gg:38281", "slot": "Link", "password": "", "auto_connect": true}``.
Written when the player ticks "Connect automatically" on the Archipelago page (and on each connect
while it is ticked), read when the seed is opened to fill the page, and editable by hand. With
``auto_connect`` the application connects by itself once the emulator runs this seed.

The password is kept as plain text, like the room's address: anyone who can read the seed folder
can read it. It is never logged or shown. Neither the emulator nor the seed checks read this file
(they go by ``manifest.json``); a seed generated again from the same patch keeps it
(``randomizer_services.generate_in_mods``).
"""
import json
import os
from pathlib import Path

FILE_NAME = 'archipelago.json'
FIELDS = (('server', str), ('slot', str), ('password', str), ('auto_connect', bool))


def read(folder):
    """The settings of the seed in ``folder`` (every field present, wrong types dropped), or None
    without a readable file."""
    try:
        value = json.loads((Path(folder) / FILE_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    defaults = {'server': '', 'slot': '', 'password': '', 'auto_connect': False}
    return {name: value[name] if isinstance(value.get(name), kind) else defaults[name] for name, kind in FIELDS}


def write(folder, server, slot, password, auto_connect):
    """Writes the file whole (a temporary file moved over it); OSError if the folder can't be written."""
    path = Path(folder) / FILE_NAME
    text = json.dumps({'server': server.strip(), 'slot': slot.strip(), 'password': password,
                       'auto_connect': bool(auto_connect)}, indent=2) + '\n'
    temporary = path.with_name(FILE_NAME + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)


def raw(folder):
    """The file's bytes as they are (to carry over to a seed generated again), or None."""
    try:
        return (Path(folder) / FILE_NAME).read_bytes()
    except OSError:
        return None
