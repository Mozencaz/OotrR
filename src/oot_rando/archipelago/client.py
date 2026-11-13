"""Archipelago client of an installed OoT Remake seed.

Sends the checks the tracker observes (save + running game) as ``LocationChecks`` and
the goal as ``StatusUpdate``. Items of this game found in other worlds are handed to
the running game one at a time (``archipelago.receive``: a Bool written in its memory
starts the item get the mod prepared). Starting items are given by the mod itself.

Protocol: https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md
The connection runs in one thread; ``update`` and ``say`` only queue work for it.
"""
from collections import deque
import json
import threading
import time
import uuid

from oot_rando.archipelago.bridge import GAME

DEFAULT_PORT = 38281
VERSION = {'major': 0, 'minor': 6, 'build': 6, 'class': 'Version'}
ITEMS_HANDLING = 0b111          # own-world, other-world and starting items: all listed
CLIENT_GOAL = 30                # ClientStatus.CLIENT_GOAL
RETRY_SECONDS = 5
FATAL_REFUSALS = {'InvalidSlot', 'InvalidGame', 'IncompatibleVersion', 'InvalidPassword', 'InvalidItemsHandling'}
# NetworkItem.flags
PROGRESSION, USEFUL, TRAP = 0b001, 0b010, 0b100


class ClientError(Exception):
    """Configuration that no retry can fix (wrong seed, slot, password...)."""


def archipelago_info(manifest):
    """(slot name, gid → location id, seed key) of an installed Archipelago seed, else ClientError."""
    info = manifest.get('archipelago')
    patch = (manifest.get('settings') or {}).get('archipelago') or {}
    if not info or not info.get('location_ids'):
        raise ClientError('This seed was not generated from an Archipelago patch (.aprmk).')
    return info.get('slot_name') or patch.get('slot_name') or '', dict(info['location_ids']), patch.get('seed_key')


def server_urls(address):
    """WebSocket URLs to try for an address typed by the player (secure first, like Archipelago's clients)."""
    address = address.strip()
    if not address:
        raise ClientError('Enter the server address (for example archipelago.gg:38281).')
    if address.startswith('/connect '):
        address = address[len('/connect '):].strip()
    if '://' in address:
        return [address]
    host = address
    if ':' not in host.rsplit(']', 1)[-1]:
        host = f'{host}:{DEFAULT_PORT}'
    return [f'wss://{host}', f'ws://{host}']


class LocationReporter:
    """Which observed checks the server still has to learn (pure: no network)."""

    def __init__(self, location_ids):
        self.location_ids = {gid: int(ident) for gid, ident in location_ids.items()}
        self.server_checked = set()     # location ids the server confirmed
        self.sent = set()               # location ids sent on this connection

    def reset_connection(self, checked=()):
        self.server_checked, self.sent = {int(i) for i in checked}, set()

    def pending(self, completed_gids):
        ids = {self.location_ids[gid] for gid in completed_gids if gid in self.location_ids}
        return sorted(ids - self.server_checked - self.sent)

    def counts(self, completed_gids):
        """(checks known to the server, checks of this seed)."""
        done = {self.location_ids[gid] for gid in completed_gids if gid in self.location_ids}
        return len(done | self.server_checked), len(self.location_ids)


def render(parts, names):
    """Plain text of a PrintJSON message. ``names``: function(kind, value, player) → text."""
    out = []
    for part in parts or ():
        kind, text = part.get('type', 'text'), part.get('text', '')
        if kind == 'player_id':
            out.append(names('player', int(text), None))
        elif kind == 'item_id':
            out.append(names('item', int(text), part.get('player')))
        elif kind == 'location_id':
            out.append(names('location', int(text), part.get('player')))
        else:
            out.append(str(text))
    return ''.join(out)


class ArchipelagoClient:
    """One connection to one slot. ``on_change()`` is called from the network thread."""

    def __init__(self, manifest, address, password='', slot=None, on_change=None, connect=None, delivery=None):
        self.slot_name, location_ids, self.seed_key = archipelago_info(manifest)
        if slot:
            self.slot_name = slot
        if not self.slot_name:
            raise ClientError('Slot name unknown: enter it.')
        self.urls = server_urls(address)
        self.password = password or None
        self.reporter = LocationReporter(location_ids)
        self.on_change = on_change or (lambda: None)
        self._connect = connect
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._outbox = deque()
        self._completed, self._goal, self._goal_sent = set(), False, False
        self.uuid = uuid.uuid4().hex
        self.status, self.connected, self.fatal = 'Not connected', False, False
        self.log, self.log_count = deque(maxlen=300), 0
        self.received = []              # NetworkItem dicts, in server order
        self.slot, self.team, self.players, self.slot_info = None, None, {}, {}
        self.names = {}                 # game → {'item': {id: name}, 'location': {id: name}}
        self.room_seed = None
        # Items handed to the running game (None: not on this system, or disabled).
        self.delivery = delivery
        if self.delivery is None and __import__('os').name == 'nt':
            from oot_rando.archipelago.receive import LiveDelivery
            self.delivery = LiveDelivery(manifest)
        self._delivery_thread = None

    # --------------------------------------------------------------- public
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name='archipelago', daemon=True)
            self._thread.start()
        if self.delivery is not None and self._delivery_thread is None:
            self._delivery_thread = threading.Thread(target=self._deliver_loop, name='archipelago-items',
                                                     daemon=True)
            self._delivery_thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def update(self, completed_gids, goal):
        """Latest observed checks (tracker gids) and goal flag; sent at the next network turn."""
        with self._lock:
            self._completed = set(completed_gids)
            self._goal = self._goal or bool(goal)
        self._wake.set()

    def say(self, text):
        """Chat message or server command (``!hint``, ``!release``...)."""
        if text.strip():
            with self._lock:
                self._outbox.append({'cmd': 'Say', 'text': text.strip()})
            self._wake.set()

    def summary(self):
        with self._lock:
            done, total = self.reporter.counts(self._completed)
            remote = [i for i in self.received if i.get('player') != self.slot]
            delivery = self.delivery
            return {'status': self.status, 'connected': self.connected, 'checks': done, 'total': total,
                    'received': len(self.received), 'from_other_worlds': len(remote),
                    'to_hand_over': delivery.waiting if delivery else len(remote),
                    'delivery': delivery.status if delivery else 'items are not handed to the game here',
                    'goal': self._goal_sent}

    def item_name(self, item, player=None):
        return self._name('item', item, player if player is not None else self.slot)

    def received_rows(self):
        """(item name, from player, location name, not given in game) of every received item."""
        rows = []
        for entry in list(self.received):
            sender = entry.get('player')
            location = entry.get('location')
            where = ('starting item' if location == -2 else 'server' if location == -1
                     else self._name('location', location, sender))
            rows.append((self.item_name(entry.get('item')), self._name('player', sender, None), where,
                         sender != self.slot))
        return rows

    def received_keys(self):
        """Reception keys of the items received from other worlds (``archipelago.receive``)."""
        from oot_rando.archipelago.receive import received_keys
        with self._lock:
            entries = list(self.received)
            slot, names = self.slot, dict(self.names)
        player = lambda s: str((self.slot_info.get(s) or {}).get('name') or '')
        location = lambda value, s: ((names.get((self.slot_info.get(s) or {}).get('game')) or {})
                                     .get('location') or {}).get(value) or ''
        return [k for k in received_keys(entries, slot, player, location) if k]

    def _deliver_loop(self):
        while not self._stop.wait(1.0):
            if not self.connected:
                continue
            try:
                record = self.delivery.step(self.received_keys())
            except Exception as error:  # noqa: BLE001 - never stop the client for the game side
                self.delivery.status = 'item hand-over failed: ' + str(error)
                record = None
            stuck = getattr(getattr(self.delivery, 'deliverer', None), 'take_stuck', lambda: [])()
            if record is not None or stuck:
                with self._lock:
                    for item in stuck:
                        self._log(f'{item["item"]} (from {item["player"]}) was not taken by the game: '
                                  'set aside, the next items go on; it is tried again in a minute.')
                    if record is not None:
                        self._log(f'Handing over {record["item"]} (from {record["player"]}) in game...')
            self.on_change()

    # -------------------------------------------------------------- network
    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except ClientError as error:
                self._set_status(str(error), connected=False, fatal=True)
                return
            except Exception as error:  # noqa: BLE001 - network errors: retry
                self._set_status(f'Disconnected ({error}); retrying in {RETRY_SECONDS} s', connected=False)
            if self._stop.wait(RETRY_SECONDS):
                break
        self._set_status('Disconnected', connected=False)

    def _open(self):
        connect = self._connect
        if connect is None:
            from websockets.sync.client import connect
        last = None
        for url in self.urls:
            try:
                self._set_status('Connecting to ' + url + '...')
                return connect(url, max_size=None, open_timeout=10)
            except Exception as error:  # noqa: BLE001 - try the next scheme
                last = error
        raise last

    def _session(self):
        socket = self._open()
        try:
            with self._lock:
                self.reporter.reset_connection()
                self._goal_sent = False
            while not self._stop.is_set():
                self._flush(socket)
                try:
                    raw = socket.recv(timeout=0.25)
                except TimeoutError:
                    continue
                for packet in json.loads(raw):
                    self._handle(socket, packet)
        finally:
            try:
                socket.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self.connected = False

    def _send(self, socket, *packets):
        socket.send(json.dumps(list(packets)))

    def _flush(self, socket):
        packets = []
        with self._lock:
            while self._outbox:
                packets.append(self._outbox.popleft())
            if self.connected:
                pending = self.reporter.pending(self._completed)
                if pending:
                    packets.append({'cmd': 'LocationChecks', 'locations': pending})
                    self.reporter.sent.update(pending)
                if self._goal and not self._goal_sent:
                    packets.append({'cmd': 'StatusUpdate', 'status': CLIENT_GOAL})
                    self._goal_sent = True
                    self._log('Goal reached: sent to the server.')
        if packets:
            self._send(socket, *packets)
            self.on_change()

    def _handle(self, socket, packet):
        cmd = packet.get('cmd')
        if cmd == 'RoomInfo':
            self.room_seed = packet.get('seed_name')
            games = sorted(set(packet.get('games') or []) | {GAME})
            self._send(socket, {'cmd': 'GetDataPackage', 'games': games},
                       {'cmd': 'Connect', 'password': self.password, 'game': GAME, 'name': self.slot_name,
                        'uuid': self.uuid, 'version': VERSION, 'items_handling': ITEMS_HANDLING,
                        'tags': [], 'slot_data': True})
            self._set_status('Room found, joining as ' + self.slot_name + '...')
        elif cmd == 'ConnectionRefused':
            errors = packet.get('errors') or ['refused']
            message = 'Connection refused: ' + ', '.join(errors)
            if FATAL_REFUSALS & set(errors):
                raise ClientError(message + self._refusal_hint(errors))
            raise ConnectionError(message)
        elif cmd == 'Connected':
            slot_data = packet.get('slot_data') or {}
            if self.seed_key and slot_data.get('seed_key') and slot_data['seed_key'] != self.seed_key:
                raise ClientError('This slot belongs to another multiworld or another patch: '
                                  'install the mod of this slot\'s .aprmk patch.')
            with self._lock:
                self.slot, self.team = packet.get('slot'), packet.get('team')
                self.players = {p['slot']: p.get('alias') or p.get('name') for p in packet.get('players', [])
                                if p.get('team') == self.team}
                self.slot_info = {int(k): v for k, v in (packet.get('slot_info') or {}).items()}
                self.reporter.reset_connection(packet.get('checked_locations') or [])
                self.received = []
                self.connected = True
            self._set_status(f'Connected as {self.slot_name}', connected=True)
        elif cmd == 'ReceivedItems':
            index, items = packet.get('index', 0), packet.get('items') or []
            with self._lock:
                if index == 0:
                    self.received = []
                if index != len(self.received):
                    resync = True
                else:
                    resync = False
                    self.received.extend(items)
            if resync:
                self._send(socket, {'cmd': 'Sync'})
            else:
                for item in items:
                    if item.get('player') != self.slot:
                        self._log(f'Received {self.item_name(item.get("item"))} from '
                                  f'{self._name("player", item.get("player"), None)}')
            self.on_change()
        elif cmd == 'RoomUpdate':
            with self._lock:
                self.reporter.server_checked.update(int(i) for i in packet.get('checked_locations') or [])
                for p in packet.get('players') or []:
                    if p.get('team') == self.team:
                        self.players[p['slot']] = p.get('alias') or p.get('name')
            self.on_change()
        elif cmd == 'DataPackage':
            games = (packet.get('data') or {}).get('games') or {}
            with self._lock:
                for game, data in games.items():
                    self.names[game] = {
                        'item': {v: k for k, v in (data.get('item_name_to_id') or {}).items()},
                        'location': {v: k for k, v in (data.get('location_name_to_id') or {}).items()}}
            self.on_change()
        elif cmd == 'PrintJSON':
            text = render(packet.get('data'), self._name)
            if text:
                with self._lock:
                    self._log(text)
                self.on_change()
        elif cmd == 'InvalidPacket':
            with self._lock:
                self._log('Server rejected a packet: ' + str(packet.get('text', '')))
            self.on_change()

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _refusal_hint(errors):
        if 'InvalidSlot' in errors:
            return ' (slot name unknown to this room)'
        if 'InvalidGame' in errors:
            return ' (this slot plays another game)'
        if 'InvalidPassword' in errors:
            return ' (wrong or missing password)'
        return ''

    def _name(self, kind, value, player):
        if kind == 'player':
            return str(self.players.get(value) or (self.slot_info.get(value) or {}).get('name') or f'Player {value}')
        game = (self.slot_info.get(player) or {}).get('game') if player is not None else None
        table = (self.names.get(game or GAME) or {}).get(kind) or {}
        return table.get(value) or f'{kind} {value}'

    def _log(self, text):
        self.log.append(text)
        self.log_count += 1

    def _set_status(self, text, connected=None, fatal=None):
        with self._lock:
            self.status = text
            if connected is not None:
                self.connected = connected
            if fatal is not None:
                self.fatal = fatal
            self._log(text)
        self.on_change()


def main(argv=None):
    """``ap-client MOD_FOLDER SERVER [--password P] [--slot NAME] [--save progress.sav]``: headless client."""
    import argparse
    import os
    from pathlib import Path
    from oot_rando.randomizer.randomizer_services import read_artifact
    from oot_rando.tracker.auto_tracker import TrackerSession, newest_save
    from oot_rando.patching.randomize_kokiri import TITLE
    parser = argparse.ArgumentParser(prog='ap-client', description=main.__doc__)
    parser.add_argument('mod', type=Path)
    parser.add_argument('server')
    parser.add_argument('--password', default='')
    parser.add_argument('--slot')
    parser.add_argument('--save', help='progress.sav to follow (default: the most recently written)')
    parser.add_argument('--hookshot', help='Hookshot folder (default: the mod folder\'s parent of mods/)')
    args = parser.parse_args(argv)
    manifest, _ = read_artifact(args.mod)
    hookshot = args.hookshot or (args.mod.resolve().parent.parent if args.mod.resolve().parent.name.lower() == 'mods'
                                 else None)
    live = None
    if os.name == 'nt':
        from oot_rando.tracker.live_memory import LiveGameData
        live = LiveGameData()
    tracker = TrackerSession(args.mod, 'archipelago', save_path=args.save or '', live=live)
    shown = [0]

    def changed():
        lines, count = list(client.log), client.log_count
        for line in lines[max(0, len(lines) - (count - shown[0])):]:
            print(line, flush=True)
        shown[0] = count

    client = ArchipelagoClient(manifest, args.server, args.password, args.slot, on_change=changed)
    client.start()
    try:
        while not client.fatal:
            if not args.save:
                path = newest_save(hookshot, TITLE)
                tracker.save_path = str(path) if path else ''
            tracker.refresh()
            client.update(tracker.completed, tracker.goal_reached)
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
    return 1 if client.fatal else 0
