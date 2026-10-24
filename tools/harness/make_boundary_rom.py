#!/usr/bin/env python3
"""
make_boundary_rom.py — ROM 境界の横断記録(q88h_boundary)の自己検査用 ROM を作る

ここで出力するバイト列は make_test_rom.py / make_trap_rom.py と同じく
**すべて自分で書いたもの**で、公式 ROM とは何の関係もない。

起動コード(ROM)が小さな試験ルーチンを RAM の 9000h へ写して飛ぶ。
ルーチンが ROM の既知の番地を CALL / JP / RST で叩き、ROM の番地をデータとして読み、
RAM の番地を ROM 側ルーチンと共有する。何がどう記録されるべきかは
下の表と boundary_selftest.sh の判定が対応している。

  --variant main  (既定)
    ROM:
      0000  JP 0100h
      0028  RET                       ; RST 28h の飛び先 (RST)
      0100  起動コード:
              LD SP,B000h
              CALL 0200h             ; ROM 内部どうしの CALL (陰性対照)
              LD HL,0300h / LD DE,9000h / LD BC,len / LDIR   ; ルーチンを RAM へ写す
              JP 9000h
      0200  RET
      0300  ルーチンの像(RAM 9000h へ写される)
      1000  X: LD A,(A800h) / LD (A800h),A / CALL 1100h / RET
              ; W=A800h を読み書きする (共有 RAM 番地の ROM 側)
      1100  LD A,(1200h) / RET        ; ROM が ROM を読む (b の陰性対照)
      1200  データ (ROM 内部から読まれるだけ)
      2000  Y: JP 9020h               ; 飛び込まれて RAM へ JP で戻る
      3000  Z: データ E1 5A            ; RAM から読まれる (b)
    RAM (9000h〜):
      9000  LD HL,A5C3h               ; 目印(レジスタ)
      9003  LD A,A5h                  ; 目印(データ)
      9005  LD (A800h),A              ; W に書く
      9008  CALL 1000h                ; X 1回目
      900B  CALL 1000h                ; X 2回目
      900E  LD A,(A800h)              ; W を読む
      9011  LD (A900h),A              ; W2 (RAM 側だけが触る)
      9014  LD A,(A900h)
      9017  LD A,(3000h)              ; Z をデータとして読む
      901A  LD HL,(3000h)             ; Z, Z+1 を読む (HL=5AE1h: 目印)
      901D  JP 2000h                  ; Y へ飛び込み
      9020  RST 28h                   ; RST の呼び出し
      9021  CALL 9040h                ; RAM 内部どうしの CALL (陰性対照)
      9024  JR $
      9040  RET

  --variant int  (割り込み受理直後の横断の確認)
    起動コードは main と同じ形で、RAM ルーチンが
      LD A,02h / OUT (E4h),A / OUT (E6h),A / IM 1 / EI / JR $
    を実行する。VSYNC 割り込み(IM1)が来るたび RAM の JR $ から ROM の 0038h
    (レベル/マスクを張り直して EI / RETI)へ入り、RAM へ戻る。
"""

import argparse
import pathlib

N88_SIZE  = 0x8000
DISK_SIZE = 0x0800

RAM_ENTRY = 0x9000
STACK     = 0xB000
W         = 0xA800    # ROM 側ルーチンと RAM 側ルーチンの両方が触る番地
W2        = 0xA900    # RAM 側だけが触る番地
X         = 0x1000
X_INNER   = 0x1100
X_DATA    = 0x1200
Y         = 0x2000
Z         = 0x3000
RST_ADDR  = 0x0028
Y_BACK    = 0x9020
RAM_SUB   = 0x9040

MARK_HL   = 0xA5C3    # レジスタの目印
MARK_BYTE = 0xA5      # RAM データの目印
MARK_ROM  = bytes([0xE1, 0x5A])   # Z に置く ROM データの目印 (LD HL,(Z) で HL=5AE1h)


def w16(v): return bytes([v & 0xFF, (v >> 8) & 0xFF])


def ld_sp(v):  return b"\x31" + w16(v)
def ld_hl(v):  return b"\x21" + w16(v)
def ld_de(v):  return b"\x11" + w16(v)
def ld_bc(v):  return b"\x01" + w16(v)
def ld_a(v):   return bytes([0x3E, v])
def ld_a_m(a): return b"\x3A" + w16(a)
def ld_m_a(a): return b"\x32" + w16(a)
def ld_hl_m(a): return b"\x2A" + w16(a)
def call(a):   return b"\xCD" + w16(a)
def jp(a):     return b"\xC3" + w16(a)
RET  = b"\xC9"
RST28 = b"\xEF"
JR_SELF = b"\x18\xFE"


def ram_routine_main() -> bytes:
    r = b"".join([
        ld_hl(MARK_HL),            # 9000
        ld_a(MARK_BYTE),           # 9003
        ld_m_a(W),                 # 9005
        call(X),                   # 9008
        call(X),                   # 900B
        ld_a_m(W),                 # 900E
        ld_m_a(W2),                # 9011
        ld_a_m(W2),                # 9014
        ld_a_m(Z),                 # 9017
        ld_hl_m(Z),                # 901A
        jp(Y),                     # 901D
    ])
    assert len(r) == Y_BACK - RAM_ENTRY, hex(len(r))
    r += RST28                     # 9020
    r += call(RAM_SUB)             # 9021
    r += JR_SELF                   # 9024
    r += bytes(RAM_SUB - RAM_ENTRY - len(r))
    r += RET                       # 9040
    return r


def ram_routine_int() -> bytes:
    return b"".join([
        ld_a(0x02),
        b"\xD3\xE4",               # OUT (E4h),A  割り込みレベル
        b"\xD3\xE6",               # OUT (E6h),A  割り込みマスク
        b"\xED\x56",               # IM 1
        b"\xFB",                   # EI
        JR_SELF,
    ])


def build_n88(variant: str) -> bytearray:
    rom = bytearray(N88_SIZE)
    img = ram_routine_main() if variant == "main" else ram_routine_int()
    IMG = 0x0300

    rom[0x0000:0x0003] = jp(0x0100)
    rom[RST_ADDR:RST_ADDR + 1] = RET
    boot = b"".join([
        ld_sp(STACK),
        call(0x0200),              # ROM 内部どうしの CALL (陰性対照)
        ld_hl(IMG), ld_de(RAM_ENTRY), ld_bc(len(img)),
        b"\xED\xB0",               # LDIR (ROM が RAM へ書く)
        jp(RAM_ENTRY),
    ])
    rom[0x0100:0x0100 + len(boot)] = boot
    rom[0x0200:0x0201] = RET
    rom[IMG:IMG + len(img)] = img

    if variant == "main":
        x = b"".join([ld_a_m(W), ld_m_a(W), call(X_INNER), RET])
        rom[X:X + len(x)] = x
        inner = ld_a_m(X_DATA) + RET
        rom[X_INNER:X_INNER + len(inner)] = inner
        rom[X_DATA:X_DATA + 2] = bytes([0x11, 0x22])
        rom[Y:Y + 3] = jp(Y_BACK)
        rom[Z:Z + 2] = MARK_ROM
    else:
        # ハンドラは割り込みレベルとマスクを毎回張り直す (受理のたびに落ちるため。
        # intlog_selftest の ROM も同じ OUT 列を毎回通る)。
        h = ld_a(0x02) + b"\xD3\xE4" + b"\xD3\xE6" + b"\xFB" + b"\xED\x4D"
        rom[0x0038:0x0038 + len(h)] = h   # LD A,2 / OUT E4 / OUT E6 / EI / RETI
    return rom


def build_disk() -> bytearray:
    rom = bytearray(DISK_SIZE)
    rom[0:2] = JR_SELF
    return rom


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--variant", choices=["main", "int"], default="main")
    args = ap.parse_args()
    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "N88.ROM").write_bytes(build_n88(args.variant))
    (d / "DISK.ROM").write_bytes(build_disk())
    print(f"生成した: {d/'N88.ROM'} ({N88_SIZE} bytes, variant={args.variant})")


if __name__ == "__main__":
    main()
