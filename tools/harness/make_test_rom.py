#!/usr/bin/env python3
"""
make_test_rom.py — 計測フックの疎通確認用の合成 ROM を作る

ここで出力するバイト列は**すべて自分で書いたもの**である。
公式 ROM とは何の関係もない。だからこの ROM 自体はリポジトリに置いてよいし、
第三者が同じものを再生成できる。

目的は 1 つ。「フックが末端まで生きているか」を実測することである。
既知の番地・既知のポートに、既知の種類のアクセスを故意に発生させ、
それが採取結果に現れることを確認する。

  過去の教訓: 値がコアとホストで一致していても、経路が通っている証明にはならない。
  実際に末端まで届くことを測るまでは、繋がっているとは言わない。

生成する N88.ROM (32KB) の中身:

    0000  C3 34 12       JP  1234h        ; リセットから既知の番地へ飛ぶ
    ...
    1234  3A 00 C0       LD  A,(C000h)    ; RAM を読む          → mem_read
    1237  D3 99          OUT (99h),A      ; ポートへ出す        → io_out
    1239  DB 99          IN  A,(99h)      ; ポートから読む      → io_in
    123B  32 01 C0       LD  (C001h),A    ; RAM へ書く          → mem_write
    123E  18 FE          JR  123Eh        ; その場で無限ループ

    → mem_exec は 0000 と 1234 付近に現れるはず

DISK.ROM (2KB) はサブ CPU 用。何もせず止まるだけのものを置く。
"""

import argparse
import pathlib

# 検査に使う番地とポート。frontend の --expect-* に渡す値と一致させる。
ENTRY      = 0x1234
RAM_READ   = 0xC000
RAM_WRITE  = 0xC001
IO_PORT    = 0x99      # PC-88 で標準的に使われていない番号を選ぶ

N88_SIZE   = 0x8000
DISK_SIZE  = 0x0800

FILL       = 0x00      # 未使用領域は NOP で埋める


def lo(v): return v & 0xFF
def hi(v): return (v >> 8) & 0xFF


def build_n88() -> bytearray:
    rom = bytearray([FILL] * N88_SIZE)

    # 0000: JP ENTRY
    rom[0x0000:0x0003] = bytes([0xC3, lo(ENTRY), hi(ENTRY)])

    prog = bytes([
        0x3A, lo(RAM_READ),  hi(RAM_READ),    # LD A,(RAM_READ)
        0xD3, IO_PORT,                        # OUT (IO_PORT),A
        0xDB, IO_PORT,                        # IN  A,(IO_PORT)
        0x32, lo(RAM_WRITE), hi(RAM_WRITE),   # LD (RAM_WRITE),A
        0x18, 0xFE,                           # JR $
    ])
    rom[ENTRY:ENTRY + len(prog)] = prog
    return rom


def build_disk() -> bytearray:
    # サブ CPU は測定対象に含めない。暴走せず止まっていればよい。
    rom = bytearray([FILL] * DISK_SIZE)
    rom[0x0000:0x0002] = bytes([0x18, 0xFE])   # JR $
    return rom


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", help="ROM を書き出すディレクトリ")
    args = ap.parse_args()

    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)

    (d / "N88.ROM").write_bytes(build_n88())
    (d / "DISK.ROM").write_bytes(build_disk())

    print(f"生成した: {d/'N88.ROM'} ({N88_SIZE} bytes)")
    print(f"生成した: {d/'DISK.ROM'} ({DISK_SIZE} bytes)")
    print()
    print("検査に使う値:")
    print(f"  --expect-exec   0x0000  --expect-exec 0x{ENTRY:04X}")
    print(f"  --expect-read   0x{RAM_READ:04X}")
    print(f"  --expect-write  0x{RAM_WRITE:04X}")
    print(f"  --expect-io-in  0x{IO_PORT:02X}   --expect-io-out 0x{IO_PORT:02X}")


if __name__ == "__main__":
    main()
