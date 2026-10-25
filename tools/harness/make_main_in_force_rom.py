#!/usr/bin/env python3
"""
make_main_in_force_rom.py — main_in_force_selftest.sh 用の自作試験 ROM

バイト列はすべて自分で書いたもので、公式 ROM とは無関係。

起動後、IN A,(40h) を64回繰り返し、読んだ値をそのまま OUT (99h),A で外へ出す。
読み間に待ちループを挟み、複数フレームにわたって採取する。
IN 40 は VRTC などの変動ビットを含むので、強制で変わるビット／変わらない
ビットを実走の列から選んで検査できる。

    0000  C3 34 12        JP 1234h
    1234  06 40            LD B,40h         ; 64回
    1236  DB 40            IN A,(40h)       ; 強制の対象
    1238  D3 99            OUT (99h),A
    123A  21 00 08         LD HL,0800h
    123D  2B               DEC HL
    123E  7C               LD A,H
    123F  B5               OR L
    1240  20 FB            JR NZ,123Dh
    1242  10 F2            DJNZ 1236h
    1244  18 FE            JR $
"""
import argparse, pathlib


def build_n88():
    rom = bytearray(0x8000)
    rom[0:3] = bytes([0xC3, 0x34, 0x12])
    prog = bytes([
        0x06, 0x40,
        0xDB, 0x40,
        0xD3, 0x99,
        0x21, 0x00, 0x08,
        0x2B,
        0x7C,
        0xB5,
        0x20, 0xFB,
        0x10, 0xF2,
        0x18, 0xFE,
    ])
    rom[0x1234:0x1234 + len(prog)] = prog
    return rom


def build_disk():
    rom = bytearray(0x0800)
    rom[0:2] = bytes([0x18, 0xFE])
    return rom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args()
    d = pathlib.Path(a.outdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "N88.ROM").write_bytes(build_n88())
    (d / "DISK.ROM").write_bytes(build_disk())


if __name__ == "__main__":
    main()
