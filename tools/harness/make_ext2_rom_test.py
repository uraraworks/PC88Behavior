#!/usr/bin/env python3
"""
make_ext2_rom_test.py — 拡張ROMバンク(4th ROM)測定 ext2 専用の合成ROM生成

docs/notes/ext2-relay-to-resident-preregistration.md の器具。ここで出力する
バイト列は全て自分で書いたものであり、公式ROMとは何の関係もない
(tools/harness/make_ext_rom_test.py と同じ立場、ext1のROM生成と対になる)。
private/ は一切参照しない。

測る対象は「バンク側(窓の中)ルーチンが常駐部(0x1000番地、窓の外)の
ルーチンをCALLして戻ってくる」設計が、Z80のCALL/RET機構としてポート
切替(0x71/0x32)と衝突せず成立するか、割り込み安全か、という素のCPU動作。

生成するROM一式:
  N88.ROM   (32KB, 常駐部)  — --arm で内容が変わる
  DISK.ROM  (2KB, サブCPU用。何もせず止まるだけ)
  N88_0.ROM〜N88_3.ROM (各8KB, 拡張ROMバンク) — --arm で内容が変わる

--arm の種類:
  call      Q1(バンク→常駐CALL、多数回・値照合)・Q4(常駐ルーチンの
            RAM/スタック使用が窓に影響しないこと)用。割り込みは使わない。
  call-b5   Q2陽性対照(割り込み無効)。200往復、バンク側が長時間の
            常駐ルーチン(RESIDENT_LONGLOOP)をCALLする。
  call-b6   Q2本体(安全な設計)。割り込みハンドラは窓の外で
            「バンク有効中フラグ」を見て受理回数を数えるだけ。
  call-neg  Q3陰性対照(禁止設計)。バンク側中継が窓の中の番地(0x6050)を
            「共有ルーチンのつもり」でCALLする。0x6050の中身はバンクごとに
            異なる値を置いてあり、バンク依存の内容が実行されることを示す。
  call-badadd  G6故障注入用。RESIDENT_ADDの演算をB+CからB-Cへ変え、
               call腕の判定ロジック(MATCH)に検出力があることを確認する。

出力先RAM番地・ポート番号は本スクリプト内のみで完結する自作の割り当てで、
公式ROMのワークエリア番地とは無関係。
"""

import argparse
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "asm"))
from z80text import Assembler, AsmError  # noqa: E402

N88_SIZE = 0x8000
EXT_SIZE = 0x2000
DISK_SIZE = 0x0800


def bank_head(n):
    return 0xA0 + n


def bank_tail(n):
    return 0xB0 + n


def neg_val(n):
    return 0xD0 + n


# --- RAM番地・ポート番地(すべて自作、本スクリプト専用の割り当て。ext1の
#     0xC1xx帯と衝突しない0xC2xx帯を使う) -------------------------------
RAM = dict(
    ITER=0xC200, COMPLETED=0xC202, MATCH=0xC204, WIN_OK=0xC206,
    RESID_HITS=0xC208, BANK_ACTIVE=0xC20A, ACTIVE_HIT=0xC20B,
    SAVE71=0xC20D, SAVE32=0xC20E, BANKNO=0xC20F,
    RESULT_TMP=0xC210, WIN_TMP=0xC211,
    NEG_VALS=0xC220,  # 4バイト(バンク0-3)
)
PORT_EROM = 0x71
PORT_MISC = 0x32
PORT_INT_LEVEL = 0xE4
PORT_INT_MASK = 0xE6
WINDOW_HEAD = 0x6000
WINDOW_TAIL = 0x7FFF
BANK_ENTRY_CALL = 0x6010     # call腕: CALL RESIDENT_ADD; RET
BANK_ENTRY_LONGCALL = 0x6020  # call-b5/b6腕: CALL RESIDENT_LONGLOOP; RET
BANK_ENTRY_NEGSTUB = 0x6010   # call-neg腕: CALL WINDOW_SHARED; RET
WINDOW_SHARED = 0x6050        # call-neg腕: バンクごとに違う値を置く番地
MAIN_WINDOW_FILL = 0xFF
RESIDENT_ADD = 0x1000
RESIDENT_LONGLOOP = 0x1010


def asm(src: str) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "src.asm"
        p.write_text(src, encoding="utf-8")
        a = Assembler()
        try:
            code = a.assemble(p)
        except AsmError as e:
            raise SystemExit(f"アセンブルエラー: {e}")
        return code


def equs():
    return "\n".join(f"{k} EQU {v:#06x}" for k, v in RAM.items()) + "\n" + \
        f"PORT_EROM EQU {PORT_EROM:#04x}\n" \
        f"PORT_MISC EQU {PORT_MISC:#04x}\n" \
        f"PORT_INT_LEVEL EQU {PORT_INT_LEVEL:#04x}\n" \
        f"PORT_INT_MASK EQU {PORT_INT_MASK:#04x}\n" \
        f"WINDOW_HEAD EQU {WINDOW_HEAD:#06x}\n" \
        f"WINDOW_TAIL EQU {WINDOW_TAIL:#06x}\n" \
        f"BANK_ENTRY_CALL EQU {BANK_ENTRY_CALL:#06x}\n" \
        f"BANK_ENTRY_LONGCALL EQU {BANK_ENTRY_LONGCALL:#06x}\n" \
        f"BANK_ENTRY_NEGSTUB EQU {BANK_ENTRY_NEGSTUB:#06x}\n" \
        f"WINDOW_SHARED EQU {WINDOW_SHARED:#06x}\n" \
        f"RESIDENT_ADD_ADDR EQU {RESIDENT_ADD:#06x}\n" \
        f"RESIDENT_LONGLOOP_ADDR EQU {RESIDENT_LONGLOOP:#06x}\n"


# ---------------------------------------------------------------------------
# 常駐部の共通ルーチン(RESIDENT_ADD/RESIDENT_LONGLOOP)。全ての --arm に含める
# (使わない腕でも同居させるだけで無害。呼ばれなければ実行されない)。
# ---------------------------------------------------------------------------
def resident_routines(bad_add: bool = False):
    op = "SUB C" if bad_add else "ADD A,C"
    return f"""
        ORG {RESIDENT_ADD:#06x}
RESIDENT_ADD:
        PUSH HL
        LD HL,(RESID_HITS)
        INC HL
        LD (RESID_HITS),HL
        POP HL
        LD A,B
        {op}
        RET

        ORG {RESIDENT_LONGLOOP:#06x}
RESIDENT_LONGLOOP:
        PUSH HL
        LD HL,(RESID_HITS)
        INC HL
        LD (RESID_HITS),HL
        POP HL
        PUSH DE
        LD DE,5385
LL1:
        DEC DE
        LD A,D
        OR E
        JR NZ,LL1
        POP DE
        LD A,0aah
        RET
"""


# ---------------------------------------------------------------------------
# バンクROM (8KB)
# ---------------------------------------------------------------------------
def build_bank_call(n: int) -> bytes:
    """call/call-badadd腕: 0x6010に CALL RESIDENT_ADD; RET"""
    src = f"""
        {equs()}
        ORG 0000h
        DB {bank_head(n):#04x}
        ORG 0010h
        CALL RESIDENT_ADD_ADDR
        RET
        ORG {EXT_SIZE - 1:#06x}
        DB {bank_tail(n):#04x}
    """
    code = asm(src)
    assert len(code) == EXT_SIZE, len(code)
    return code


def build_bank_q2(n: int) -> bytes:
    """call-b5/call-b6腕: 0x6020に CALL RESIDENT_LONGLOOP; RET、他はFF埋め"""
    src = f"""
        {equs()}
        ORG 0000h
        DB {bank_head(n):#04x}
        ORG 0020h
        CALL RESIDENT_LONGLOOP_ADDR
        RET
        ORG {EXT_SIZE - 1:#06x}
        DB {bank_tail(n):#04x}
    """
    code = asm(src)
    buf = bytearray(code)
    # CALL nn(3バイト) + RET(1バイト) = 4バイト(0x20-0x23)。この範囲を
    # FF埋めで壊すとRETが0xFF(RST 38h相当)に化け、呼び出し元へ戻れず
    # 暴走する(実際に踏んだ不具合、修正前はrange(0x20,0x23)でRET分を
    # 保護し忘れていた)。
    used = {0} | set(range(0x0020, 0x0024)) | {EXT_SIZE - 1}
    for i in range(EXT_SIZE):
        if i not in used:
            buf[i] = MAIN_WINDOW_FILL
    return bytes(buf)


def build_bank_neg(n: int) -> bytes:
    """call-neg腕: 0x6010に CALL 0x6050(禁止設計); RET、0x6050にバンク固有値"""
    src = f"""
        {equs()}
        ORG 0000h
        DB {bank_head(n):#04x}
        ORG 0010h
        CALL WINDOW_SHARED
        RET
        ORG 0050h
        LD A,{neg_val(n):#04x}
        RET
        ORG {EXT_SIZE - 1:#06x}
        DB {bank_tail(n):#04x}
    """
    code = asm(src)
    assert len(code) == EXT_SIZE, len(code)
    return code


# ---------------------------------------------------------------------------
# DISK.ROM (2KB): サブCPU用、何もせず止まるだけ
# ---------------------------------------------------------------------------
def build_disk() -> bytes:
    buf = bytearray([0x00] * DISK_SIZE)
    buf[0:2] = bytes([0x18, 0xFE])  # JR $
    return bytes(buf)


# ---------------------------------------------------------------------------
# N88.ROM ("call"/"call-badadd"): Q1・Q4。200往復、値まで照合
# ---------------------------------------------------------------------------
def build_main_call(bad_add: bool = False) -> bytes:
    src = f"""
        {equs()}
        ORG 0000h
        JP INIT

        ORG 0038h
        RETI

        ORG 0100h
INIT:
        LD SP,0fffeh

        LD HL,0c200h
        LD (HL),0
        LD DE,0c201h
        LD BC,002fh
        LDIR

        LD HL,0
        LD (ITER),HL

LOOP:
        LD A,(ITER)
        AND 03h
        LD (BANKNO),A

        LD A,(ITER)
        LD B,A
        LD C,05h

        IN A,(PORT_EROM)
        LD (SAVE71),A
        IN A,(PORT_MISC)
        LD (SAVE32),A

        LD A,(SAVE71)
        AND 0feh
        OUT (PORT_EROM),A
        LD A,(SAVE32)
        AND 0fch
        LD HL,BANKNO
        OR (HL)
        OUT (PORT_MISC),A

        CALL BANK_ENTRY_CALL
        LD (RESULT_TMP),A

        LD A,(WINDOW_HEAD)
        LD (WIN_TMP),A

        LD A,(SAVE71)
        OUT (PORT_EROM),A
        LD A,(SAVE32)
        OUT (PORT_MISC),A

        ; --- Q1判定: 結果 == (B+C)&0xFF ---
        LD A,(ITER)
        ADD A,05h
        LD HL,RESULT_TMP
        CP (HL)
        JR NZ,SKIP_MATCH
        LD HL,(MATCH)
        INC HL
        LD (MATCH),HL
SKIP_MATCH:

        ; --- Q4判定: 復元前の窓ヘッダ == 0xA0+bankno ---
        LD A,(BANKNO)
        ADD A,0a0h
        LD HL,WIN_TMP
        CP (HL)
        JR NZ,SKIP_WIN
        LD HL,(WIN_OK)
        INC HL
        LD (WIN_OK),HL
SKIP_WIN:

        LD HL,(COMPLETED)
        INC HL
        LD (COMPLETED),HL

        LD HL,(ITER)
        INC HL
        LD (ITER),HL
        LD DE,200
        OR A
        SBC HL,DE
        JR NZ,LOOP

HALT_LOOP:
        JR HALT_LOOP

{resident_routines(bad_add=bad_add)}
    """
    code = asm(src)
    buf = bytearray(code) + bytearray([0] * (N88_SIZE - len(code)))
    return bytes(buf[:N88_SIZE])


# ---------------------------------------------------------------------------
# N88.ROM ("call-b5"/"call-b6"): Q2。200往復ループ、variantで割り込みの扱いが変わる
# ---------------------------------------------------------------------------
def build_main_q2(variant: str) -> bytes:
    assert variant in ("b5", "b6")

    if variant == "b5":
        arm_block = "        ; b5: 割り込みは有効化しない(陽性対照)\n"
        isr_body = "        RETI\n"
    else:
        arm_block = """
        LD A,02h
        OUT (PORT_INT_LEVEL),A
        LD A,02h
        OUT (PORT_INT_MASK),A
        IM 1
        EI
"""
        isr_body = """
        LD A,02h
        OUT (PORT_INT_LEVEL),A
        LD A,(BANK_ACTIVE)
        OR A
        JR Z,ISR_DONE
        LD HL,(ACTIVE_HIT)
        INC HL
        LD (ACTIVE_HIT),HL
ISR_DONE:
        EI
        RET
"""

    src = f"""
        {equs()}
        ORG 0000h
        JP INIT

        ORG 0038h
ISR:
{isr_body}
        ORG 0100h
INIT:
        LD SP,0fffeh

        LD HL,0c200h
        LD (HL),0
        LD DE,0c201h
        LD BC,002fh
        LDIR

{arm_block}
        LD HL,0
        LD (ITER),HL

LOOP:
        LD A,(ITER)
        AND 03h
        LD (BANKNO),A

        LD A,1
        LD (BANK_ACTIVE),A

        IN A,(PORT_EROM)
        LD (SAVE71),A
        IN A,(PORT_MISC)
        LD (SAVE32),A

        LD A,(SAVE71)
        AND 0feh
        OUT (PORT_EROM),A
        LD A,(SAVE32)
        AND 0fch
        LD HL,BANKNO
        OR (HL)
        OUT (PORT_MISC),A

        CALL BANK_ENTRY_LONGCALL

        LD A,(WINDOW_HEAD)
        LD C,A
        LD A,(BANKNO)
        LD B,A
        LD A,0a0h
        ADD A,B
        CP C
        JR NZ,NOMATCH
        LD HL,(MATCH)
        INC HL
        LD (MATCH),HL
NOMATCH:

        LD A,(SAVE71)
        OUT (PORT_EROM),A
        LD A,(SAVE32)
        OUT (PORT_MISC),A

        XOR A
        LD (BANK_ACTIVE),A

        LD HL,(COMPLETED)
        INC HL
        LD (COMPLETED),HL

        LD HL,(ITER)
        INC HL
        LD (ITER),HL
        LD DE,200
        OR A
        SBC HL,DE
        JR NZ,LOOP

HALT_LOOP:
        JR HALT_LOOP

{resident_routines()}
    """
    code = asm(src)
    buf = bytearray(code) + bytearray([0] * (N88_SIZE - len(code)))
    return bytes(buf[:N88_SIZE])


# ---------------------------------------------------------------------------
# N88.ROM ("call-neg"): Q3陰性対照。200往復、バンクごとの返り値を記録
# ---------------------------------------------------------------------------
def build_main_neg() -> bytes:
    src = f"""
        {equs()}
        ORG 0000h
        JP INIT

        ORG 0038h
        RETI

        ORG 0100h
INIT:
        LD SP,0fffeh

        LD HL,0c200h
        LD (HL),0
        LD DE,0c201h
        LD BC,002fh
        LDIR

        LD HL,0
        LD (ITER),HL

LOOP:
        LD A,(ITER)
        AND 03h
        LD (BANKNO),A

        IN A,(PORT_EROM)
        LD (SAVE71),A
        IN A,(PORT_MISC)
        LD (SAVE32),A

        LD A,(SAVE71)
        AND 0feh
        OUT (PORT_EROM),A
        LD A,(SAVE32)
        AND 0fch
        LD HL,BANKNO
        OR (HL)
        OUT (PORT_MISC),A

        CALL BANK_ENTRY_NEGSTUB
        LD (RESULT_TMP),A

        LD A,(SAVE71)
        OUT (PORT_EROM),A
        LD A,(SAVE32)
        OUT (PORT_MISC),A

        LD A,(BANKNO)
        LD HL,NEG_VALS
        LD D,0
        LD E,A
        ADD HL,DE
        LD A,(RESULT_TMP)
        LD (HL),A

        LD HL,(COMPLETED)
        INC HL
        LD (COMPLETED),HL

        LD HL,(ITER)
        INC HL
        LD (ITER),HL
        LD DE,200
        OR A
        SBC HL,DE
        JR NZ,LOOP

HALT_LOOP:
        JR HALT_LOOP

{resident_routines()}
    """
    code = asm(src)
    buf = bytearray(code) + bytearray([0] * (N88_SIZE - len(code)))
    return bytes(buf[:N88_SIZE])


def write_rom_set(outdir: pathlib.Path, arm: str):
    outdir.mkdir(parents=True, exist_ok=True)

    if arm == "call":
        main = build_main_call(bad_add=False)
        banks = {n: build_bank_call(n) for n in range(4)}
    elif arm == "call-badadd":
        main = build_main_call(bad_add=True)
        banks = {n: build_bank_call(n) for n in range(4)}
    elif arm in ("call-b5", "call-b6"):
        variant = arm.split("-", 1)[1]
        main = build_main_q2(variant)
        banks = {n: build_bank_q2(n) for n in range(4)}
    elif arm == "call-neg":
        main = build_main_neg()
        banks = {n: build_bank_neg(n) for n in range(4)}
    else:
        raise SystemExit(f"未知のarm: {arm}")

    (outdir / "N88.ROM").write_bytes(main)
    (outdir / "DISK.ROM").write_bytes(build_disk())
    for n, data in banks.items():
        (outdir / f"N88_{n}.ROM").write_bytes(data)

    print(f"生成した({arm}): {outdir}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--arm", required=True,
                     choices=["call", "call-badadd", "call-b5", "call-b6", "call-neg"])
    args = ap.parse_args()

    write_rom_set(pathlib.Path(args.outdir), args.arm)

    print()
    print("RAM番地一覧:")
    for k, v in RAM.items():
        print(f"  {k:<12} = {v:#06x}")


if __name__ == "__main__":
    main()
