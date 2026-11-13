"""Turbo A and skipping with X, by key presses sent to the game (nothing in the game changes).

Turbo A: hold A, A is pressed repeatedly (dialogues scroll fast). A short press stays
one press (an ocarina note, opening a door…); the taps start once A has been held
``HOLD_DELAY_S``, and only while the game plays an event (``live_memory.LiveEventState``,
seen within ``TURBO_EVENT_GRACE_S``: the state flickers); in free play (and memory
unreadable) a held A stays held (diving: the turbo without the memory, 11/11, broke
it, user test 12/11). Once the left stick moves during a hold, that hold stays a
plain held A (grabbing and pulling a block).

Hookshot (tools/host/nn_hid.c) reads the pads (XInput) and the keyboard
(``GetAsyncKeyState``) itself and ORs them: while the pad's A is held, the game sees
A held whatever is sent. So A is taken away from Hookshot: in hookshot_options.ini,
``pad_a=-1`` (no pad button) and ``key_a`` = ``VIRTUAL_A`` (F24, a key no keyboard
has); the A the player presses (the ini's former ``pad_a`` / ``key_a``, kept in
``turbo_binds.json``) is read here and played on F24. Hookshot reads the ini once,
when the game starts: a game started before the turbo keeps its A (no turbo until
it restarts). ``restore()`` (the app closing) writes the former A back, so a game
started without the app has its A; a game still running then has no A until it
restarts (the app warns).

Skip with X: a press of X while the game plays an event (cutscene, dialogue…,
``live_memory.LiveEventState``) is followed, ``SKIP_PLUS_DELAY_S`` later, by a press
of Plus (held ``SKIP_PLUS_HOLD_S``): the X itself reaches the game and brings up the
skip prompt, Plus confirms it, as the player did by hand (user request 12/11: X then
Plus worked, X alone should do it). The former version wanted X *held* 0.4 s and no
long hold was ever logged in the next test: the player taps X. Only during an event
(Plus in free play opens the pause menu); memory unreadable: no skip. Ocarina: Y
pressed during an event (a note; no item in a cutscene) cancels a waiting Plus and no
skip is sent until the event has ended or no note (A, X, Y) has been pressed for
``SKIP_LATCH_IDLE_S``. Pressing X again or A does not latch (the 12/11 version latched
on X X or X A: the player's repeated X then never skipped, "ocarina notes" in the log). Each X press during play is logged (``turbo.log``)
with what the memory said and whether Plus was sent.

``parse_binds``, ``remap_ini``, ``TurboClock``, ``ATurbo`` and ``SkipWithX`` are pure
(testable anywhere); ``TurboA`` is Windows-only.
"""
import ctypes
import json
import os
import threading
import time
from pathlib import Path

# Hookshot's pad codes (gpu/vk/vk_api.h HOS_PAD_*) -> XInput wButtons masks.
# Triggers are axes (bLeftTrigger / bRightTrigger > 64 in Hookshot).
PAD_LTRIGGER, PAD_RTRIGGER = 15, 16
PAD_TO_XINPUT = {
    0: 0x1000,   # SOUTH  (Xbox A)
    1: 0x2000,   # EAST   (Xbox B)
    2: 0x4000,   # WEST   (Xbox X)
    3: 0x8000,   # NORTH  (Xbox Y)
    4: 0x0020,   # BACK
    6: 0x0010,   # START
    7: 0x0040,   # LSTICK
    8: 0x0080,   # RSTICK
    9: 0x0100,   # LSHOULDER
    10: 0x0200,  # RSHOULDER
    11: 0x0001,  # UP
    12: 0x0002,  # DOWN
    13: 0x0004,  # LEFT
    14: 0x0008,  # RIGHT
}
# Hookshot's defaults (nn_hid.c pad_default / key_default) when the ini has no line.
DEFAULTS = {'pad_a': 1, 'key_a': (ord('E'), 0), 'pad_x': 3, 'key_x': (0x20, 0), 'pad_y': 2, 'key_y': (0, 0),
            'key_plus': (0x09, 0x0D),
            'key_move_up': (ord('W'), 0), 'key_move_down': (ord('S'), 0),
            'key_move_left': (ord('A'), 0), 'key_move_right': (ord('D'), 0)}
MOVE_KEYS = ('key_move_up', 'key_move_down', 'key_move_left', 'key_move_right')
VIRTUAL_A = 0x87   # VK_F24: the key Hookshot reads as A while the turbo runs
# One tap: held and released long enough for the game to see both (60 fps frames).
PRESS_S, RELEASE_S = 0.05, 0.05
# A held this long before the first tap: a short press is one press.
HOLD_DELAY_S = 0.3
# X pressed during an event: Plus this long after the press (the skip prompt is up),
# held this long (several frames at 60 fps).
SKIP_PLUS_DELAY_S = 0.25
SKIP_PLUS_HOLD_S = 0.12
# The event is looked for this long after the press (the memory state flickers).
SKIP_DECIDE_S = 0.25
# An event is over once not seen this long (ends the ocarina latch).
SKIP_END_GRACE_S = 0.5
# The turbo runs while an event was seen this recently (the memory state flickers).
TURBO_EVENT_GRACE_S = 0.5
# The ocarina latch ends once no note has been pressed this long (the event state can stay up).
SKIP_LATCH_IDLE_S = 4.0
# Left stick: moved past this (of 32767) = Link walks, pulls…
STICK_DEAD = 12000
LOG_MAX_BYTES = 256 * 1024


def parse_binds(text):
    """The bindings of hookshot_options.ini the turbo needs: ``pad_*`` int or None, ``key_*`` (vk, vk)."""
    binds = dict(DEFAULTS)
    for line in text.splitlines():
        name, sep, value = line.partition('=')
        name = name.strip()
        if not sep or name not in DEFAULTS:
            continue
        try:
            if name.startswith('pad_'):
                code = int(value.strip())
                binds[name] = code if code >= 0 else None
            else:
                parts = [int(p) for p in value.split(',')[:2]] + [0, 0]
                binds[name] = tuple(v if 0 < v < 256 else 0 for v in parts[:2])
        except ValueError:
            continue
    return binds


def ini_a(binds):
    """The ini lines of an A binding: {'pad_a': '0', 'key_a': '69,0'}."""
    pad, keys = binds['pad_a'], binds['key_a']
    return {'pad_a': str(-1 if pad is None else pad), 'key_a': f'{keys[0]},{keys[1]}'}


TURBO_LINES = {'pad_a': '-1', 'key_a': f'{VIRTUAL_A},0'}


def is_remapped(text):
    """The ini already gives A to the turbo (``TURBO_LINES``)."""
    binds = parse_binds(text)
    return binds['pad_a'] is None and binds['key_a'] == (VIRTUAL_A, 0)


def set_ini_lines(text, lines):
    """``text`` with ``name=value`` for each of ``lines`` (replaced, or added at the end)."""
    out, done = [], set()
    for line in text.splitlines():
        name = line.partition('=')[0].strip()
        if name in lines and '=' in line:
            if name not in done:
                out.append(f'{name}={lines[name]}')
                done.add(name)
            continue
        out.append(line)
    out += [f'{name}={value}' for name, value in lines.items() if name not in done]
    return '\n'.join(out) + '\n'


def remap_ini(text, saved=None):
    """(new ini text, the player's A as ini lines) for the turbo.

    ``saved``: the A kept by an earlier run (used when the ini is already remapped,
    e.g. the app did not close normally). Remapped without anything saved: Hookshot's
    default A.
    """
    if is_remapped(text):
        player = dict(saved) if saved else ini_a(DEFAULTS)
    else:
        player = ini_a(parse_binds(text))
    return set_ini_lines(text, TURBO_LINES), player


class TurboClock:
    """A's state from whether the player holds A and the time: held, then taps."""

    def __init__(self, press=PRESS_S, release=RELEASE_S, delay=HOLD_DELAY_S):
        self.press, self.release, self.delay = press, release, delay
        self.started = None

    def a_down(self, held, now, turbo=True):
        if not held:
            self.started = None
            return False
        if self.started is None:
            self.started = now
        elapsed = now - self.started - self.delay
        if elapsed < 0 or not turbo:
            return True   # (a short press, or a plain hold)
        return elapsed % (self.press + self.release) < self.press


class ATurbo:
    """One decision per poll (pure): the A the game sees, from the player's A and stick."""

    def __init__(self, delay=HOLD_DELAY_S, grace=TURBO_EVENT_GRACE_S):
        self.clock = TurboClock(delay=delay)
        self.grace, self.last_event = grace, None
        self.moved = False   # the stick moved during this hold
        self.hold = None     # {'start', 'taps', 'moved'} while A is held
        self.finished = []
        self.down = False

    def step(self, a, stick, now, event=True):
        """``event``: True / False / None (unreadable): the game plays an event."""
        if event is True:
            self.last_event = now
        in_event = self.last_event is not None and now - self.last_event < self.grace
        if a:
            if self.hold is None:
                self.hold, self.moved = {'start': now, 'taps': 0, 'moved': False, 'event': False}, False
            self.moved = self.moved or stick
            self.hold['moved'] = self.moved
            self.hold['event'] = self.hold['event'] or in_event
        elif self.hold is not None:
            self.hold['end'] = now
            self.finished.append(self.hold)
            self.hold = None
        want = self.clock.a_down(a, now, turbo=not self.moved and in_event)
        if want and not self.down and self.hold is not None and now - self.hold['start'] > 0:
            self.hold['taps'] += 1
        self.down = want
        return want


class SkipWithX:
    """A press of X during an event: Plus pressed ``delay`` later, held ``hold`` (pure).

    ``step(x, note, event, now, y=False)`` -> plus_down. ``x``: X held; ``note``:
    another note button held (A, Y); ``y``: Y held; ``event``: True / False / None
    (unreadable), read only when ``needs_event`` says so. One Plus per X press (X
    again while a Plus waits: the same Plus); Y pressed during an event cancels it and
    latches (no skip) until the event has ended or no note came for ``idle``.
    """

    def __init__(self, delay=SKIP_PLUS_DELAY_S, hold=SKIP_PLUS_HOLD_S, decide=SKIP_DECIDE_S,
                 grace=SKIP_END_GRACE_S, idle=SKIP_LATCH_IDLE_S):
        self.delay, self.hold, self.decide, self.grace, self.idle = delay, hold, decide, grace, idle
        self.prev_x = self.prev_note = self.prev_y = False
        self.last_note = None
        self.pending = None      # the X press waiting for its Plus: record
        self.plus_until = None
        self.latched, self.last_event = False, None
        self.finished = []

    def needs_event(self, x, now):
        return x and not self.prev_x or self.pending is not None or self.latched

    def _finish(self, why):
        self.pending['result'] = why
        self.finished.append(self.pending)
        self.pending = None

    def step(self, x, note, event, now, y=False):
        x_down, note_down, y_down = x and not self.prev_x, note and not self.prev_note, y and not self.prev_y
        self.prev_x, self.prev_note, self.prev_y = x, note, y
        if event is True:
            self.last_event = now
        if self.latched and (self.last_event is None or now - self.last_event >= self.grace
                             or now - self.last_note >= self.idle):
            self.latched = False   # (the melody's event is over)
        if x_down or note_down or y_down:
            self.last_note = now
        if y_down and event is True:
            if self.pending is not None:
                self._finish('cancelled (Y: ocarina)')
            self.latched = True
        if x_down and self.pending is not None:
            x_down = False   # (X again: the Plus already waiting)
        if x_down:
            self.pending = {'start': now, 'events': set(), 'result': None}
            if self.latched:
                self._finish('no skip (ocarina notes in this event)')
        if self.pending is not None:
            self.pending['events'].add(event)
            seen = True in self.pending['events']
            if not seen and now - self.pending['start'] >= self.decide:
                self._finish('no skip (no event seen)')
            elif seen and now - self.pending['start'] >= self.delay:
                self._finish('Plus sent')
                self.plus_until = now + self.hold
        if self.plus_until is not None:
            if now < self.plus_until:
                return True
            self.plus_until = None
        return False


def describe_skip(record):
    """One log line for an X press during play."""
    events = record['events']
    seen = '/'.join(name for value, name in ((True, 'yes'), (False, 'no'), (None, 'unreadable')) if value in events)
    return f"X pressed: event {seen or '?'}, {record['result']}"


class EventGate:
    """The game's event state: ``open(now)`` -> True / False, or None when unreadable.

    ``playing()`` is cached ``ttl`` seconds.
    """

    def __init__(self, playing, ttl=0.1):
        self.playing, self.ttl = playing, ttl
        self.checked, self.value, self.error = None, None, None

    def open(self, now):
        if self.checked is None or now - self.checked >= self.ttl:
            self.checked = now
            try:
                self.value, self.error = bool(self.playing()), None
            except Exception as error:   # LiveUnavailable, or anything from the reader
                self.value, self.error = None, str(error)
        return self.value


def describe_hold(hold):
    """One log line for a finished A hold."""
    line = f"A held {hold['end'] - hold['start']:.2f} s: {hold['taps']} taps"
    if hold['moved']:
        line += ' (stick moved: plain hold)'
    elif not hold.get('event', True):
        line += ' (no event: plain hold)'
    return line


class TurboA:
    """Background thread; ``start()`` / ``stop()`` / ``restore()``. ``status`` describes its state."""

    def __init__(self, hookshot_root, poll=0.01, playing=None, log_path=None, state_path=None,
                 game_running=None):
        self.root, self.poll = Path(hookshot_root), poll
        self.playing = playing   # () -> bool; default: the game's event state in memory
        self.thread, self.running = None, False
        self.status = 'Turbo A off'
        self.presses = 0
        self.last_hold = ''
        self.remapped = False
        from oot_rando.paths import data_dir
        self.log_path = Path(log_path) if log_path else data_dir() / 'turbo.log'
        self.state_path = Path(state_path) if state_path else data_dir() / 'app' / 'turbo_binds.json'
        self.game_running = game_running   # () -> bool; default: a hookshot.exe process

    @property
    def ini(self):
        return self.root / 'hookshot_options.ini'

    def _log(self, line):
        self.last_hold = line
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.log_path.exists() and self.log_path.stat().st_size > LOG_MAX_BYTES:
                self.log_path.replace(self.log_path.with_suffix('.old.log'))
            with self.log_path.open('a', encoding='utf-8') as stream:
                stream.write(time.strftime('%Y-%m-%d %H:%M:%S ') + line + '\n')
        except OSError:
            pass

    # ------------------------------------------------------- the ini
    def _saved(self):
        try:
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            return {k: str(data[k]) for k in ('pad_a', 'key_a')}
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def remap(self):
        """Gives A to the turbo in the ini; returns the player's A bindings, or None."""
        try:
            text = self.ini.read_text(encoding='utf-8', errors='replace')
        except OSError:
            text = ''
        new, player = remap_ini(text, self._saved())
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(player), encoding='utf-8')
            if new != text:
                self.ini.write_text(new, encoding='utf-8')
        except OSError as error:
            self.status = 'Turbo A: cannot write hookshot_options.ini (' + str(error) + ')'
            return None
        self.remapped = True
        return parse_binds('\n'.join(f'{k}={v}' for k, v in player.items()))

    def restore(self):
        """Writes the player's A back in the ini (a game started without the app keeps its A)."""
        if not self.remapped:
            return
        player = self._saved()
        try:
            text = self.ini.read_text(encoding='utf-8', errors='replace')
            if player and is_remapped(text):
                self.ini.write_text(set_ini_lines(text, player), encoding='utf-8')
        except OSError:
            pass
        self.remapped = False

    def game_is_running(self):
        if self.game_running is not None:
            return self.game_running()
        if os.name != 'nt':
            return False
        import subprocess
        try:
            out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq hookshot.exe', '/NH'], capture_output=True,
                                 text=True, timeout=5, creationflags=0x08000000).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return 'hookshot.exe' in out.lower()

    # ---------------------------------------------------------- windows
    def _setup(self):
        from ctypes import wintypes
        from oot_rando.tracker.game_overlay import _Win32
        self.win = _Win32()
        self.user32 = ctypes.windll.user32
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.xinput = None
        for name in ('xinput1_4.dll', 'xinput9_1_0.dll'):
            try:
                self.xinput = getattr(ctypes.windll, name.replace('.dll', ''))
                break
            except OSError:
                continue

        class GAMEPAD(ctypes.Structure):
            _fields_ = [('wButtons', wintypes.WORD), ('bLeftTrigger', ctypes.c_ubyte),
                        ('bRightTrigger', ctypes.c_ubyte), ('sThumbLX', ctypes.c_short),
                        ('sThumbLY', ctypes.c_short), ('sThumbRX', ctypes.c_short), ('sThumbRY', ctypes.c_short)]

        class STATE(ctypes.Structure):
            _fields_ = [('dwPacketNumber', wintypes.DWORD), ('Gamepad', GAMEPAD)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                        ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

        class _UNION(ctypes.Union):
            # MOUSEINPUT is the largest member: keep INPUT's size right for SendInput.
            _fields_ = [('ki', KEYBDINPUT), ('pad', ctypes.c_byte * 32)]

        class INPUT(ctypes.Structure):
            _fields_ = [('type', wintypes.DWORD), ('u', _UNION)]

        self.STATE, self.INPUT = STATE, INPUT
        self.pad_retry = [0.0] * 4

    def _pads(self):
        """The connected pads' states (absent pad: as Hookshot, retried once a second)."""
        if self.xinput is None:
            return []
        now, pads = time.monotonic(), []
        for index in range(4):
            if now < self.pad_retry[index]:
                continue
            state = self.STATE()
            if self.xinput.XInputGetState(index, ctypes.byref(state)) != 0:
                self.pad_retry[index] = now + 1.0
                continue
            pads.append(state.Gamepad)
        return pads

    @staticmethod
    def _pad_held(pads, code):
        if code is None:
            return False
        for pad in pads:
            if code == PAD_LTRIGGER and pad.bLeftTrigger > 64 or code == PAD_RTRIGGER and pad.bRightTrigger > 64:
                return True
            if pad.wButtons & PAD_TO_XINPUT.get(code, 0):
                return True
        return False

    def _key_held(self, keys):
        return any(vk and self.user32.GetAsyncKeyState(vk) & 0x8000 for vk in keys)

    def _game_in_front(self):
        hwnd = self.user32.GetForegroundWindow()
        return bool(hwnd) and self.win.exe(self.win.pid(hwnd)) == 'hookshot.exe'

    def _send(self, vk, down):
        event = self.INPUT(type=1)   # INPUT_KEYBOARD
        event.u.ki.wVk = vk
        event.u.ki.wScan = self.user32.MapVirtualKeyW(vk, 0)
        event.u.ki.dwFlags = 0 if down else 0x0002   # KEYEVENTF_KEYUP
        self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(self.INPUT))

    # ------------------------------------------------------------ loop
    def start(self):
        if os.name != 'nt':
            self.status = 'Turbo A: Windows only'
            return False
        if self.running:
            return True
        if not (self.root / 'hookshot.exe').exists() and not self.ini.exists():
            self.status = 'Turbo A: Hookshot folder not found'
            return False
        running_before = self.game_is_running()
        player = self.remap()
        if player is None:
            return False
        if not getattr(self, '_restore_at_exit', False):
            # The app ending another way than its window (exception, sys.exit) still gives
            # the game its A back; a killed process is mended by remap_ini at the next start.
            import atexit
            atexit.register(self.restore)
            self._restore_at_exit = True
        self._setup()
        binds = read_binds(self.root)
        plus = binds['key_plus'][0] or binds['key_plus'][1]
        self.player, self.binds, self.plus = player, binds, plus
        if self.playing is None:
            from oot_rando.tracker.live_memory import LiveEventState
            self.playing = LiveEventState().playing
        self.gate = EventGate(self.playing)
        self.running = True
        self.status = ('Turbo A on: hold A in a dialogue (events only); press X to skip a cutscene'
                       + (' (restart the game for turbo A)' if running_before else ''))
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
            self.thread = None
        self.restore()
        self.status = 'Turbo A off'

    def _run(self):
        turbo, skip = ATurbo(), SkipWithX()
        a_down = plus_down = False
        front_checked, front = 0.0, False
        player_keys, move_keys = self.player['key_a'], tuple(vk for n in MOVE_KEYS for vk in self.binds[n])
        try:
            while self.running:
                now = time.monotonic()
                if now - front_checked > 0.25:
                    front, front_checked = self._game_in_front(), now
                pads = self._pads() if front else []
                a = front and (self._pad_held(pads, self.player['pad_a']) or self._key_held(player_keys))
                stick = front and (any(abs(p.sThumbLX) > STICK_DEAD or abs(p.sThumbLY) > STICK_DEAD for p in pads)
                                   or self._key_held(move_keys))
                x = front and (self._pad_held(pads, self.binds['pad_x']) or self._key_held(self.binds['key_x']))
                y = front and (self._pad_held(pads, self.binds['pad_y']) or self._key_held(self.binds['key_y']))
                # (memory read only while A is held or around an X press)
                event = self.gate.open(now) if a or skip.needs_event(x, now) else False
                want_a = turbo.step(a, stick, now, event)
                want_plus = bool(self.plus) and skip.step(x, a or y, event, now, y=y)
                if want_a != a_down:
                    self._send(VIRTUAL_A, want_a)
                    a_down = want_a
                    self.presses += want_a
                if want_plus != plus_down:
                    self._send(self.plus, want_plus)
                    plus_down = want_plus
                while skip.finished:
                    record = skip.finished.pop(0)
                    if record['events'] != {False}:   # (X in free play: an item, not logged)
                        self._log(describe_skip(record))
                while turbo.finished:
                    hold = turbo.finished.pop(0)
                    if hold['end'] - hold['start'] >= HOLD_DELAY_S:
                        self._log(describe_hold(hold))
                time.sleep(self.poll)
        finally:
            if a_down:
                self._send(VIRTUAL_A, False)
            if plus_down:
                self._send(self.plus, False)


def read_binds(hookshot_root):
    try:
        text = (Path(hookshot_root) / 'hookshot_options.ini').read_text(encoding='utf-8', errors='replace')
    except OSError:
        text = ''
    return parse_binds(text)
