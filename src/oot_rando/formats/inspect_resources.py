"""Local resource decoding helpers for the Kokiri prototype."""
import struct
import zstandard as zstd


def sarc(data):
    if data[:4] != b'SARC':
        raise ValueError('Expected SARC')
    header = struct.unpack_from('<H', data, 4)[0]
    count = struct.unpack_from('<H', data, header+6)[0]
    names = header + 12 + count*16 + 8
    base = struct.unpack_from('<I', data, 12)[0]
    result = {}
    for i in range(count):
        _, attr, start, end = struct.unpack_from('<IIII', data, header+12+i*16)
        off = names + (attr & 0xffffff)*4
        name = data[off:data.index(b'\0', off)].decode()
        result[name] = data[base+start:base+end]
    return result


def dictionaries(nup):
    return sarc(zstd.ZstdDecompressor().decompress(nup.read('1/romfs/Pack/ZsDic.pack.zs')))


def decompress(data, dictionaries):
    ident = zstd.get_frame_parameters(data).dict_id
    if ident:
        for raw in dictionaries.values():
            dic = zstd.ZstdCompressionDict(raw)
            if dic.dict_id() == ident:
                return zstd.ZstdDecompressor(dict_data=dic).decompress(data)
        raise ValueError(f'Missing dictionary {ident}')
    return zstd.ZstdDecompressor().decompress(data)


class Byml:
    def __init__(self, data):
        self.data = data
        if data[:2] not in (b'YB', b'BY'):
            raise ValueError('Expected BYML')
        self.endian = '<' if data[:2] == b'YB' else '>'
        self.byteorder = 'little' if self.endian == '<' else 'big'
        self.keys = self.string_table(self.u32(4))
        self.strings = self.string_table(self.u32(8))
        self.root = self.node(self.u32(12))

    def u32(self, o):
        return struct.unpack_from(self.endian+'I', self.data, o)[0]

    def u24(self, o):
        return int.from_bytes(self.data[o:o+3], self.byteorder)

    def string_table(self, off):
        if not off:
            return []
        return [self.data[off+self.u32(off+4+i*4):].split(b'\0',1)[0].decode() for i in range(self.u24(off+1))]

    def value(self, typ, off):
        val = self.u32(off)
        if typ in (0xc0, 0xc1):
            return self.node(val)
        if typ == 0xa0:
            return self.strings[val]
        if typ == 0xd0:
            return bool(val)
        if typ == 0xd1:
            return struct.unpack_from(self.endian+'i', self.data, off)[0]
        if typ == 0xd2:
            return struct.unpack_from(self.endian+'f', self.data, off)[0]
        if typ == 0xd3:
            return val
        if typ in (0xd4, 0xd5, 0xd6):
            return struct.unpack_from(self.endian+{0xd4:'q',0xd5:'Q',0xd6:'d'}[typ], self.data, val)[0]
        if typ == 0xff:
            return None
        raise ValueError(f'Unsupported BYML type {typ:#x} at {off:#x}')

    def node(self, off):
        typ, count = self.data[off], self.u24(off+1)
        if typ == 0xc1:
            return {self.keys[self.u24(off+4+i*8)]: self.value(self.data[off+7+i*8], off+8+i*8) for i in range(count)}
        if typ == 0xc0:
            values = (off+4+count+3)&~3
            return [self.value(self.data[off+4+i],values+i*4) for i in range(count)]
        raise ValueError(f'Unsupported node {typ:#x}')

