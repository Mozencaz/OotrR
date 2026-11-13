"""Handing the items of other worlds to the running game (``patching.ap_mailbox``).

The client signals one item at a time: it sets the item's ``RandoAP.Recv`` Bool in
the game's memory, the game's global sequence starts its item get, and the event
sets the saved ``RandoAP.Got`` Bool. Until Got is true the item is pending: a signal
lost (an event already playing, a save loaded meanwhile) is sent again after
``RETRY_SECONDS``. Got comes back with the save, so loading an older save gives back
what it does not hold, and nothing is given twice.

Only while the running game carries this seed's marker (a save of this seed is
loaded). Memory access: ``tracker.live_memory`` (Hookshot or a yuzu-family emulator).
"""
import time

from oot_rando.patching.ap_mailbox import record_key

RETRY_SECONDS = 8.0
# One item that never arrives must not hold back the ones after it: after this many
# signals without Got (the game dropped the event: cutscene, loading...), it goes
# behind the others and is tried again after a pause, its count reset.
MAX_SIGNALS = 5
ASIDE_SECONDS = 60.0


class Deliverer:
    """Which item to signal now (pure: no game access)."""

    def __init__(self, records, hash_of):
        self.records = {r['key']: r for r in records}
        self.recv = {key: hash_of(r['recv']) for key, r in self.records.items()}
        self.got = {key: hash_of(r['got']) for key, r in self.records.items()}
        self.in_flight, self.sent_at = None, 0.0
        self.signals = {}
        self.aside = {}              # key -> time it may be signalled again
        self.newly_stuck = []

    def pending(self, keys, bools):
        """Keys received from the server that the game does not hold yet (server order)."""
        seen, result = set(), []
        for key in keys:
            if key in self.records and key not in seen and bools.get(self.got[key]) is False:
                seen.add(key)
                result.append(key)
        return result

    @property
    def stuck(self):
        """Keys set aside (they go behind the others, retried later)."""
        return list(self.aside)

    def _set_aside(self, key, now):
        self.aside[key] = now + ASIDE_SECONDS
        self.signals[key] = 0
        self.newly_stuck.append(key)
        if self.in_flight == key:
            self.in_flight = None

    def step(self, keys, bools, now):
        """Key to signal now, or None. ``bools``: the game's {hash: value}."""
        pending = self.pending(keys, bools)
        for key in [k for k in self.aside if k not in pending]:
            del self.aside[key]      # handed over after all
        if self.in_flight not in pending:
            self.in_flight = None
        if not pending:
            return None
        if self.in_flight is not None and now - self.sent_at < RETRY_SECONDS:
            return None
        # One signal at a time: a Recv still set is a sequence the game has not
        # started (paused, menu open); a second one would race it.
        if any(bools.get(self.recv[key]) is True for key in pending):
            return None
        ready = ([k for k in pending if k not in self.aside]
                 + [k for k in pending if k in self.aside and now >= self.aside[k]])
        if not ready:
            return None
        head = ready[0]
        if self.signals.get(head, 0) >= MAX_SIGNALS:
            self._set_aside(head, now)
            return self.step(keys, bools, now)
        self.aside.pop(head, None)
        self.signals[head] = self.signals.get(head, 0) + 1
        self.in_flight, self.sent_at = head, now
        return head

    def take_stuck(self):
        """Records set aside since the last call (to report once)."""
        taken, self.newly_stuck = self.newly_stuck, []
        return [self.records[key] for key in taken]


def received_keys(entries, slot, player_name, location_name):
    """Record keys of received items found at a location, in server order.

    Items found in this world count too: the copies of a dynamic progressive family
    are handed over by the client wherever they are (the other ones of this world
    have no record and are ignored by :class:`Deliverer`). ``slot``: unused, kept
    for the callers. ``entries``: NetworkItem dicts; ``player_name(slot)``,
    ``location_name(location, slot)``.
    """
    keys = []
    for entry in entries:
        finder = entry.get('player')
        if entry.get('location', -1) < 0:
            continue
        keys.append(record_key(player_name(finder), location_name(entry['location'], finder)))
    return keys


class LiveDelivery:
    """Deliverer bound to the running game (``set`` and ``snapshot`` from live_memory)."""

    def __init__(self, manifest, live=None, clock=time.monotonic):
        from oot_rando.patching.soul_adapter import murmur3
        self.records = ((manifest.get('skips') or {}).get('ap_mailbox') or {}).get('items', [])
        self.marker = murmur3('RandoSeed.' + str(manifest.get('seed_id', '')))
        self.deliverer = Deliverer(self.records, murmur3)
        self.live, self.clock = live, clock
        self.status, self.waiting = '', 0

    def step(self, keys):
        """One delivery turn. Returns the record signalled, or None."""
        from oot_rando.tracker.live_memory import LiveGameData, LiveUnavailable, set_bool_in
        if not self.records:
            self.status = 'this seed receives no item from other worlds'
            return None
        if self.live is None:
            self.live = LiveGameData()
        try:
            bools = self.live.snapshot()['bool']
        except LiveUnavailable as error:
            self.status = 'game not reachable (' + str(error) + ')'
            return None
        if bools.get(self.marker) is not True:
            self.status = 'no save of this seed loaded'
            return None
        self.waiting = len(self.deliverer.pending(keys, bools))
        key = self.deliverer.step(keys, bools, self.clock())
        self.status = f'{self.waiting} item(s) to hand over' if self.waiting else 'every received item is in game'
        if self.deliverer.aside:
            self.status += f' ({len(self.deliverer.aside)} set aside: not taken yet, retried later)'
        if key is None:
            return None
        try:
            set_bool_in(self.live, self.deliverer.recv[key], True)
        except LiveUnavailable as error:
            self.status = 'cannot signal the item (' + str(error) + ')'
            return None
        return self.deliverer.records[key]
