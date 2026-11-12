"""Read-only NUP inspection helper; never modifies the game container."""
import hashlib
import json
import struct
from pathlib import Path


class Nup:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = self.path.open('rb')
        head = self.stream.read(128)
        if head[:4] != b'NUP\x01':
            raise ValueError('Not a NUP container')
        offset, size = struct.unpack_from('<QQ', head, 8)
        self.stream.seek(offset)
        toc = self.stream.read(size)
        if hashlib.sha256(toc).digest() != head[24:56]:
            raise ValueError('Invalid TOC hash')
        magic, pc, dc, fc, pool, plen, _ = struct.unpack_from('<IIQQQQQ', toc)
        if magic != 0x01434f54:
            raise ValueError('Invalid TOC')
        self.packages = [struct.unpack_from('<QIIII', toc, 48 + i*64) for i in range(pc)]
        pos = 48 + pc*64
        dirs = [struct.unpack_from('<IIIIQ', toc, pos+i*24) for i in range(dc)]
        pos += dc*24
        files = [struct.unpack_from('<IIQQQ32sB', toc, pos+i*80) for i in range(fc)]
        pos += fc*80
        children = struct.unpack_from('<' + 'I'*((pool-pos)//4), toc, pos)
        def name(o, n):
            return toc[pool+o:pool+o+n].decode('utf-8')
        self.entries = {}
        def walk(idx, prefix):
            o, n, first, count, _ = dirs[idx]
            for child in children[first:first+count]:
                if child < dc:
                    d = dirs[child]
                    walk(child, prefix + name(d[0], d[1]) + '/')
                else:
                    f = files[child-dc]
                    self.entries[prefix+name(f[0], f[1])] = f
        for i, p in enumerate(self.packages):
            walk(p[1], f'{i}/')

    def read(self, path):
        _, _, size, offset, extent, digest, codec = self.entries[path]
        self.stream.seek(offset)
        data = self.stream.read(extent)
        if codec == 1:
            import zstandard
            data = zstandard.ZstdDecompressor().decompress(data, max_output_size=size)
        elif codec != 0:
            raise ValueError('Unknown NUP codec')
        if len(data) != size or hashlib.sha256(data).digest() != digest:
            raise ValueError('Invalid member hash: ' + path)
        return data


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('nup', type=Path)
    parser.add_argument('--match', default='')
    parser.add_argument('--index', type=Path)
    args = parser.parse_args()
    nup = Nup(args.nup)
    print('Packages:', nup.packages)
    matches = {p: {'size': f[2], 'offset': f[3], 'codec': f[6]} for p, f in nup.entries.items() if args.match.lower() in p.lower()}
    if args.index:
        args.index.write_text(json.dumps(matches, indent=2), encoding='utf-8')
        print('Index:', args.index, 'entries:', len(matches))
    else:
        for p, f in matches.items():
            print(p, f)
