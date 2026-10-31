#!/usr/bin/env python3
"""事前登録 B12 の媒体を生成する。"""
import argparse
import struct
from pathlib import Path

IDENT = 0xA1

def build():
    header = bytearray(688)
    body = bytearray()
    for t in range(80):
        c, h = divmod(t, 2)
        size, sectors = (256, 16) if t == 0 else (1024, 5)
        struct.pack_into('<I', header, 32 + t * 4, len(header) + len(body))
        for r in range(1, sectors + 1):
            sh = bytearray(16)
            sh[:4] = bytes((c, h, r, 1 if size == 256 else 3))
            struct.pack_into('<H', sh, 4, sectors)
            struct.pack_into('<H', sh, 14, size)
            body += sh
            for block in range(size // 256):
                body += bytes((IDENT, c, h, r, block)) + bytes([0x55]) * 251
    struct.pack_into('<I', header, 28, len(header) + len(body))
    return bytes(header + body)

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('outfile', type=Path)
    p.parse_args().outfile.write_bytes(build())
