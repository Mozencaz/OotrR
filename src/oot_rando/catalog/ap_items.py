
"""Items of other Archipelago players: planner names and pouch actor names.

Their model and texts are built by ``patching/ap_item.py``.
"""
import hashlib

PREFIX = 'Archipelago: '
ACTOR_PREFIX = 'Item_AP_'


# ------------------------------------------------------------------ items and actors
def is_ap_item(item):
    return item.startswith(PREFIX)


def ap_item(label):
    """Planner item name of another player's item (``label``: "Sword (Ami)")."""
    return PREFIX + label


def ap_actor(item):
    """Pouch actor of an Archipelago item: stable, independent of the order of the items."""
    return ACTOR_PREFIX + hashlib.sha256(item.encode('utf-8')).hexdigest()[:12]


def is_ap_actor(actor):
    return actor.startswith(ACTOR_PREFIX)
