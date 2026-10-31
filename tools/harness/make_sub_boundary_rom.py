#!/usr/bin/env python3
"""サブ境界の検査に使う自作 ROM を生成する。"""
import pathlib
import sys

d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
main = bytearray(0x8000); main[:2] = b'\x18\xfe'
rom = bytearray(0x800)
def put(addr, data): rom[addr:addr + len(data)] = data
# ROM 内部の呼出し後、試験コードを RAM に写して実行。
ram = bytes.fromhex('21 c3 a5 3e a5 32 00 50 cd 00 01 cd 00 01 cd 40 40 c3 50 01')
ram += bytes(0x20 - len(ram)) + bytes.fromhex('18 fe')
ram += bytes(0x40 - len(ram)) + b'\xc9'
boot = bytes.fromhex('31 00 60 cd 80 01 21 00 02 11 00 40 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 c3 00 40')
put(0, boot); put(0x100, bytes.fromhex('3e a5 32 01 50 c9'))
put(0x150, bytes.fromhex('c3 20 40')); put(0x180, b'\xc9'); put(0x200, ram)
(d / 'N88.ROM').write_bytes(main); (d / 'DISK.ROM').write_bytes(rom)
