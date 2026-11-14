# Third-party code

Both are used as sloperinaGZ ships them (GPL-3 project, see ../../README.md).

- `stb_truetype.h`: [stb_truetype](https://github.com/nothings/stb) by Sean Barrett. Public domain, or MIT as you choose; the licence text
  is at the end of the file.
- `zstd_decompress.c`, `zstd_decompress.h`, `zstd_shim.h`: zstd's educational decoder (Meta Platforms, Inc.), BSD-style or GPLv2 as you
  choose; the licence notice is at the top of each file. The shim is ours (it supplies what the decoder takes from zstd's tree).
