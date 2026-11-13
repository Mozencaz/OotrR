"""Ed25519 signature verification (RFC 8032), pure Python: used once per update.

Verification only: the application never signs. Follows the reference algorithm of
RFC 8032 section 5.1.7 (extended coordinates, cofactorless check, s < L enforced).
"""
import hashlib

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    ea = (y1 - x1) * (y2 - x2) % _P
    eb = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = eb - ea, d - c, d + c, eb + ea
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _mul(scalar, point):
    result = (0, 1, 1, 0)
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _decode(data):
    y = int.from_bytes(data, 'little')
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_G = (_recover_x(_GY, 0), _GY, 1, _recover_x(_GY, 0) * _GY % _P)


def verify(public_key, message, signature):
    """True when ``signature`` (64 bytes) of ``message`` is valid for ``public_key`` (32 bytes)."""
    if not isinstance(public_key, bytes) or not isinstance(signature, bytes):
        return False
    if len(public_key) != 32 or len(signature) != 64:
        return False
    point = _decode(public_key)
    r = _decode(signature[:32])
    if point is None or r is None:
        return False
    s = int.from_bytes(signature[32:], 'little')
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), 'little') % _L
    return _equal(_mul(s, _G), _add(r, _mul(h, point)))
