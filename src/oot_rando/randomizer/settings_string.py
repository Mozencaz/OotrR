"""Seed strings: a seed name and its settings in one short text to copy and paste.

``OOTR-`` followed by URL-safe base64 (no padding) of a zlib-compressed JSON
``{"v": generator version, "s": settings}``. Only the values that differ from the
defaults are written, so the default settings give a string of a few dozen
characters. The generator version travels with the string: the same seed name and
settings reproduce the same game only with the same generator.
"""
import base64
import binascii
import json
import zlib

from oot_rando.logic import rando_options
from oot_rando.randomizer.randomizer_core import GENERATOR_VERSION, Settings

PREFIX = 'OOTR-'
MAX_LENGTH = 20000          # a pasted text longer than this is not a seed string
MAX_JSON = 200000           # decompression limit (no zip bomb)


def _defaults():
    return Settings('-').to_dict()


def encode(settings):
    """The seed string of ``settings`` (seed name included)."""
    if settings.archipelago is not None:
        raise ValueError('An Archipelago seed is shared by its .aprmk patch, not by a seed string.')
    current = settings.to_dict()
    defaults = _defaults()
    diff = {}
    for name, value in current.items():
        if name == 'full':
            base = rando_options.defaults()
            diff['full'] = {k: v for k, v in value.items() if base.get(k) != v}
        elif name == 'categories':
            changed = {k: v for k, v in value.items() if defaults['categories'].get(k) != v}
            if changed:
                diff['categories'] = changed
        elif name == 'seed' or defaults.get(name) != value:
            diff[name] = value
    data = json.dumps({'v': GENERATOR_VERSION, 's': diff}, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(data, 9)).decode('ascii').rstrip('=')


def decode(text):
    """``(settings, generator_version)`` of a seed string; ValueError if it is not one."""
    text = ''.join(str(text).split())   # tolerate line breaks and spaces from chat apps
    if not text.upper().startswith(PREFIX) or len(text) > MAX_LENGTH:
        raise ValueError('This is not a seed string (it starts with ' + PREFIX + ').')
    body = text[len(PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(body + '=' * (-len(body) % 4))
        inflater = zlib.decompressobj()
        data = inflater.decompress(raw, MAX_JSON)
        if inflater.unconsumed_tail or not inflater.eof:
            raise ValueError
        payload = json.loads(data.decode('utf-8'))
    except (ValueError, binascii.Error, zlib.error, UnicodeDecodeError):
        raise ValueError('The seed string is damaged or incomplete (copy it again).') from None
    if (not isinstance(payload, dict) or not isinstance(payload.get('v'), str)
            or not isinstance(payload.get('s'), dict)):
        raise ValueError('The seed string is damaged or incomplete (copy it again).')
    diff = dict(payload['s'])
    value = _defaults()
    value.pop('full', None)
    if 'categories' in diff:
        if not isinstance(diff['categories'], dict):
            raise ValueError('Unknown categories or non-boolean values.')
        value['categories'] = {**value['categories'], **diff.pop('categories')}
    if 'full' in diff:
        full = diff.pop('full')
        if not isinstance(full, dict):
            raise ValueError('Invalid full randomizer options.')
        value['full'] = {**rando_options.defaults(), **full}
    value.update(diff)
    return Settings.from_dict(value), payload['v']
