#!/usr/bin/env python3
"""B34 自己検査用の自作 ROM。"""
import pathlib
import sys

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
main = bytearray(0x8000); main[:2] = bytes.fromhex('18 fe')
rom = bytearray(0x800)
# ROM から 5100 を書き、5200 を読む。RAM のコードを 4000 にコピー。
ram = bytes.fromhex('3a 00 01 3a 00 53 3a 00 51 3e a5 32 00 54 3a 00 54 18 fe')
boot = bytes.fromhex('31 00 60 3e a5 32 00 51 3a 00 52 21 00 02 11 00 40 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 c3 00 40')
rom[:len(boot)] = boot
rom[0x200:0x200 + len(ram)] = ram
(out / 'N88.ROM').write_bytes(main)
(out / 'DISK.ROM').write_bytes(rom)
