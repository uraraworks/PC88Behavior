#!/usr/bin/env python3
"""
make_trap_rom.py — 全域トラップROMと足場自己検証用ROMを作る

ここで出力するバイト列は make_test_rom.py と同じく**すべて自分で書いたもの**である。
公式 ROM とは何の関係もない。だからこの ROM 自体はリポジトリに置いてよいし、
第三者が同じものを再生成できる。

目的は M2 の完了条件「全域トラップROMで起動し、何番地が要求されたかが
一覧で出る」を満たすこと。既定では ROM 全域を埋め草バイト(0x00)で埋め、
trap.map で全域をトラップ対象にする。RET モードでは要求された番地に
実行が来るたびに RET を返して先へ進め、STOP モードでは最初の1件で止める。

  過去の教訓: 値がコアとホストで一致していても、経路が通っている証明にはならない。
  「フックが末端まで生きているか」を実測するまでは、繋がっているとは言わない。
  --selftest はそのための足場で、既知の番地に既知の入口状態で
  アクセスさせ、それが採取結果に現れることを検査する。

生成する N88.ROM (32KB) の中身:

  既定（--selftest 無し）:
    全バイト 0x00 埋め。trap.map が main 0000-7FFF 全域をトラップ対象にする
    ので、リセット直後の JP/CALL 先が即座にトラップへ落ちる。

  --selftest:
    0000  31 80 F3       LD  SP,0xF380
    0003  CD 00 10       CALL 1000h        ; 1回目
    0006  01 34 12       LD  BC,1234h      ; トラップ入口でのレジスタ観測用
    0009  11 78 56       LD  DE,5678h
    000C  21 BC 9A       LD  HL,9ABCh
    000F  CD 00 20       CALL 2000h        ; 引数観測はここで見る
    0012  CD 00 10       CALL 1000h        ; 2回目（hit回数の確認用）
    0015  3A 00 30       LD  A,(3000h)     ; データアクセス
    0018  18 FE          JR  0018h         ; その場で無限ループ

    このブートストラップ自体は自分で書いたコードなので、その範囲
    (0000-00FF) は trap.map から除外する。1000h/2000h/3000h は
    trap.map の対象内なので、そこへ触れた瞬間にトラップが発火する。

DISK.ROM (2KB) はサブ CPU 用。何もせず止まるだけのものを置く
（make_test_rom.py と同じ）。--selftest でもサブ側は検査対象に含めない
ので、trap.map にサブの行は出さない。
"""

import argparse
import pathlib

N88_SIZE  = 0x8000
DISK_SIZE = 0x0800
FILL      = 0x00

BOOT_END    = 0x0100   # ブートストラップとして trap.map から除外する範囲
TRAP_ENTRY1 = 0x1000
TRAP_ENTRY2 = 0x2000
TRAP_DATA   = 0x3000


def lo(v): return v & 0xFF
def hi(v): return (v >> 8) & 0xFF


def build_n88_blank() -> bytearray:
    return bytearray([FILL] * N88_SIZE)


def build_n88_selftest() -> bytearray:
    rom = bytearray([FILL] * N88_SIZE)
    prog = bytes([
        0x31, lo(0xF380), hi(0xF380),         # LD SP,0xF380
        0xCD, lo(TRAP_ENTRY1), hi(TRAP_ENTRY1),  # CALL 1000h (1回目)
        0x01, lo(0x1234), hi(0x1234),         # LD BC,1234h
        0x11, lo(0x5678), hi(0x5678),         # LD DE,5678h
        0x21, lo(0x9ABC), hi(0x9ABC),         # LD HL,9ABCh
        0xCD, lo(TRAP_ENTRY2), hi(TRAP_ENTRY2),  # CALL 2000h
        0xCD, lo(TRAP_ENTRY1), hi(TRAP_ENTRY1),  # CALL 1000h (2回目)
        0x3A, lo(TRAP_DATA), hi(TRAP_DATA),   # LD A,(3000h)
        0x18, 0xFE,                           # JR $ (自分自身へ)
    ])
    assert len(prog) <= BOOT_END, "ブートストラップが確保域からはみ出た"
    rom[0x0000:len(prog)] = prog
    return rom


def build_disk() -> bytearray:
    rom = bytearray([FILL] * DISK_SIZE)
    rom[0x0000:0x0002] = bytes([0x18, 0xFE])   # JR $
    return rom


def write_trap_map(path: pathlib.Path, selftest: bool):
    lines = [
        "# trap.map — q88measure --trap-map が読む、トラップ対象範囲の一覧",
        "# 書式: 「main|sub 開始-終了」（16進、両端を含む）。# 以降はコメント。",
    ]
    if selftest:
        lines.append(
            f"# ブートストラップ (0000-{BOOT_END-1:04X}) は自作コードなので"
            " トラップ対象から除外する"
        )
        lines.append(f"main {BOOT_END:04X}-7FFF")
        lines.append(
            "# サブCPUは --selftest の検査対象に含めないので行を出さない"
        )
    else:
        lines.append("main 0000-7FFF")
        lines.append("sub  0000-07FF")
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("outdir", help="ROM / trap.map を書き出すディレクトリ")
    ap.add_argument("--selftest", action="store_true",
                     help="足場自己検証用のブートストラップを仕込む")
    args = ap.parse_args()

    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)

    n88 = build_n88_selftest() if args.selftest else build_n88_blank()
    (d / "N88.ROM").write_bytes(n88)
    (d / "DISK.ROM").write_bytes(build_disk())
    write_trap_map(d / "trap.map", args.selftest)

    print(f"生成した: {d/'N88.ROM'} ({N88_SIZE} bytes)")
    print(f"生成した: {d/'DISK.ROM'} ({DISK_SIZE} bytes)")
    print(f"生成した: {d/'trap.map'}")
    if args.selftest:
        print()
        print("検査に使う値:")
        print(f"  --expect-trap-exec 0x{TRAP_ENTRY1:04X}"
              f"  --expect-trap-exec 0x{TRAP_ENTRY2:04X}")
        print(f"  --expect-trap-data 0x{TRAP_DATA:04X}")
        print(f"  0x{TRAP_ENTRY1:04X} の実行回数は 2 のはず")
        print(f"  0x{TRAP_ENTRY2:04X} 入口では BC=1234 DE=5678 HL=9ABC のはず")


if __name__ == "__main__":
    main()
