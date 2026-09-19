#!/usr/bin/env python3
"""
make_ext_rom_test.py — 拡張ROMバンク(4th ROM)測定 ext1 専用の合成ROM生成

docs/notes/ext1-rom-bank-preregistration.md（改訂1、コミット bd15c51）の
器具。ここで出力するバイト列は全て自分で書いたものであり、公式ROMとは
何の関係もない（make_test_rom.py と同じ立場）。private/ は一切参照しない。

生成するROM一式:
  N88.ROM   (32KB, 常駐部)  — --arm で内容が変わる
  DISK.ROM  (2KB, サブCPU用。何もせず止まるだけ)
  N88_0.ROM〜N88_3.ROM (各8KB, 拡張ROMバンク) — --arm で内容が変わる

--arm の種類:
  ra    B1(基準読み)・B2(読み分け)・B3(復帰)・B9(0x79D7独立性)用。
        常駐部が起動直後に単独で読み分け〜復帰の手順を全部実行し、
        結果をRAM 0xC100-0xC134 へ書く。割り込みは使わない。
        バンクファイルはヘッダ/フッタの識別バイトのみ(0xA0+n/0xB0+n)。
  q3-b5 Q3陽性対照(割り込み無効)。200往復、バンク側は長時間ループ。
  q3-b6 Q3本体(安全な設計)。割り込みハンドラは窓の外で
        「バンク有効中フラグ」を見て受理回数を数えるだけ。
  q3-b7 Q3陰性対照(禁止設計)。割り込みハンドラが無条件に窓の中
        (0x6030)へCALLする。メインROM側の0x6030には安全なルーチンを
        置くが、バンク側には置かない(禁止事項に触れない自作の
        「窓の中の番地は中身が不定」という事実だけを使う)。

--omit-bank N: 指定したバンク番号のファイルを生成しない(B4、欠落検査用)。
--swap-banks A B: 生成後、バンクAとBのファイルの中身を入れ替える
                  (G6、故障注入用)。

出力先RAM番地・ポート番号は本スクリプト内のみで完結する自作の割り当てで、
公式ROMのワークエリア番地とは無関係(下調べ・事前登録のいずれの段階でも
公式ROMの番地は参照していない)。
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

# --- 自作の識別パターン(バンク) -------------------------------------------
def bank_head(n):
    return 0xA0 + n


def bank_tail(n):
    return 0xB0 + n


# --- RAM番地・ポート番地(すべて自作、本スクリプト専用の割り当て) ---------
RAM = dict(
    RB1_HEAD=0xC100, RB1_TAIL=0xC101, RB1_ROMVER=0xC102, RB1_OTHER=0xC103,
    RB2_BASE=0xC110,
    RB3_HEAD=0xC130, RB3_TAIL=0xC131, RB3_ROMVER=0xC132, RB3_OTHER=0xC133,
    BANK_ACTIVE=0xC1E0, ACTIVE_HIT=0xC1E1,
    COMPLETED=0xC1F0, MATCH=0xC1F2, WINCALL=0xC1F4,
    SCR_BANKNO=0xC1F6, SCR_SAVE71=0xC1F7, SCR_SAVE32=0xC1F8,
    SCR_TMP0=0xC1F9, SCR_TMP1=0xC1FA, SCR_TMP2=0xC1FB,
    SCR_OUTPTR=0xC1FC, ITER=0xC1FE,
)
PORT_EROM = 0x71
PORT_MISC = 0x32
PORT_INT_LEVEL = 0xE4
PORT_INT_MASK = 0xE6
WINDOW_HEAD = 0x6000
WINDOW_TAIL = 0x7FFF
WINDOW_ROMVER = 0x79D7
BANK_ROUTINE = 0x6020   # Q3: バンク側の長時間ループ
WINDOW_CALL_TARGET = 0x6030  # B7: 禁止設計が呼ぶ窓の中の番地
MAIN_WINDOW_FILL = 0xE0
MAIN_ROMVER_MARK = 0xC7


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
        f"WINDOW_ROMVER EQU {WINDOW_ROMVER:#06x}\n" \
        f"BANK_ROUTINE EQU {BANK_ROUTINE:#06x}\n" \
        f"WINDOW_CALL_TARGET EQU {WINDOW_CALL_TARGET:#06x}\n"


# ---------------------------------------------------------------------------
# バンクROM (8KB): 識別バイトのみ ("ra" 系列、B1〜B4・G6で使う)
# ---------------------------------------------------------------------------
def build_bank_ra(n: int) -> bytes:
    src = f"""
        ORG 0000h
        DB {bank_head(n):#04x}
        DS {EXT_SIZE - 2},000h
        DB {bank_tail(n):#04x}
    """
    code = asm(src)
    assert len(code) == EXT_SIZE, len(code)
    return code


# ---------------------------------------------------------------------------
# バンクROM (8KB): Q3用。0x0020(窓6020h)に長時間ループ、他は0xFF埋め
# (0xFFはRST 38hに解釈される — Z80の文書化された挙動。B7で禁止設計が
#  窓の中の不定番地を呼んだときに何が起きるかを見せるのに使う)
# ---------------------------------------------------------------------------
def build_bank_q3(n: int) -> bytes:
    # 長時間ループの目安: DE=5385からの16bitデクリメント
    #   1回= DEC DE(6T)+LD A,D(4T)+OR E(4T)+JR NZ(12T taken)=26T
    #   26T*5385 ≈ 140,010T ≈ 2.1フレーム分(1フレーム≈66,666T、4MHz/60Hz換算)
    #   フレーム境界をまたぐことを狙った自作の見積り(公式資料ではない)。
    src = f"""
        {equs()}
        ORG 0000h
        DB {bank_head(n):#04x}
        ORG 0020h
LONGLOOP:
        LD DE,5385
LL1:
        DEC DE
        LD A,D
        OR E
        JR NZ,LL1
        RET
        ORG {EXT_SIZE - 1:#06x}
        DB {bank_tail(n):#04x}
    """
    code = asm(src)
    # 未使用領域を0xFFで埋め直す(z80textのDSデフォルト埋めは0なので、
    # 生成後にバッファ側で0の箇所のうちコード外を0xFFへ塗り替える)
    buf = bytearray(code)
    used = set(range(0x0000, 0x0001)) | set(range(0x0020, 0x0020 + len(_ll1_bytes()))) \
        | {EXT_SIZE - 1}
    for i in range(EXT_SIZE):
        if i not in used:
            buf[i] = 0xFF
    return bytes(buf)


def _ll1_bytes():
    # LONGLOOPルーチンの長さだけを求めるための小アセンブル(埋め計算用)
    src = """
        ORG 0000h
        LD DE,5385
LL1:
        DEC DE
        LD A,D
        OR E
        JR NZ,LL1
        RET
    """
    return asm(src)


# ---------------------------------------------------------------------------
# DISK.ROM (2KB): サブCPU用、何もせず止まるだけ
# ---------------------------------------------------------------------------
def build_disk() -> bytes:
    buf = bytearray([0x00] * DISK_SIZE)
    buf[0:2] = bytes([0x18, 0xFE])  # JR $
    return bytes(buf)


# ---------------------------------------------------------------------------
# N88.ROM ("ra"): B1・B2・B3・B9 を単独で実行する常駐部
# ---------------------------------------------------------------------------
def build_main_ra() -> bytes:
    src = f"""
        {equs()}
        ORG 0000h
        JP INIT

        ORG 0038h
        RETI

        ORG 0100h
INIT:
        LD SP,0fffeh

        ; 結果マーカー領域 0xC100-0xC1FF を0で初期化
        LD HL,0c100h
        LD (HL),0
        LD DE,0c101h
        LD BC,00ffh
        LDIR

        ; --- B1: 切り替えずに窓を読む ---
        LD A,(WINDOW_HEAD)
        LD (RB1_HEAD),A
        LD A,(WINDOW_TAIL)
        LD (RB1_TAIL),A
        LD A,(WINDOW_ROMVER)
        LD (RB1_ROMVER),A

        ; 無関係ビット(PMODE=bit5)をあらかじめ立てておく
        LD A,020h
        OUT (PORT_MISC),A
        LD (RB1_OTHER),A

        ; 出力カーソルを RB2_BASE へ
        LD HL,RB2_BASE
        LD (SCR_OUTPTR),HL
        XOR A
        LD (SCR_BANKNO),A

BANKLOOP:
        IN A,(PORT_EROM)
        LD (SCR_SAVE71),A
        IN A,(PORT_MISC)
        LD (SCR_SAVE32),A

        LD A,(SCR_SAVE71)
        AND 0feh
        OUT (PORT_EROM),A

        LD A,(SCR_SAVE32)
        AND 0fch
        LD HL,SCR_BANKNO
        OR (HL)
        OUT (PORT_MISC),A

        LD A,(WINDOW_HEAD)
        LD (SCR_TMP0),A
        LD A,(WINDOW_TAIL)
        LD (SCR_TMP1),A
        LD A,(WINDOW_ROMVER)
        LD (SCR_TMP2),A

        LD A,(SCR_SAVE71)
        OUT (PORT_EROM),A
        LD A,(SCR_SAVE32)
        OUT (PORT_MISC),A

        LD HL,(SCR_OUTPTR)
        LD A,(SCR_TMP0)
        LD (HL),A
        INC HL
        LD A,(SCR_TMP1)
        LD (HL),A
        INC HL
        LD A,(SCR_TMP2)
        LD (HL),A
        INC HL
        LD (SCR_OUTPTR),HL

        LD A,(SCR_BANKNO)
        INC A
        LD (SCR_BANKNO),A
        CP 4
        JR NZ,BANKLOOP

        ; --- B3/B9: 復帰確認 ---
        LD A,(WINDOW_HEAD)
        LD (RB3_HEAD),A
        LD A,(WINDOW_TAIL)
        LD (RB3_TAIL),A
        LD A,(WINDOW_ROMVER)
        LD (RB3_ROMVER),A
        IN A,(PORT_MISC)
        LD (RB3_OTHER),A

DONE:
        JR DONE

        ORG 6000h
        DB {MAIN_WINDOW_FILL:#04x}
        DS {WINDOW_ROMVER - WINDOW_HEAD - 1},{MAIN_WINDOW_FILL:#04x}
        DB {MAIN_ROMVER_MARK:#04x}
        DS {WINDOW_TAIL - WINDOW_ROMVER - 1},{MAIN_WINDOW_FILL:#04x}
        DB {MAIN_WINDOW_FILL + 1:#04x}
    """
    code = asm(src)
    buf = bytearray(code) + bytearray([0] * (N88_SIZE - len(code)))
    return bytes(buf[:N88_SIZE])


# ---------------------------------------------------------------------------
# N88.ROM ("q3-*"): 200往復ループ。variant で割り込みの扱いが変わる
# ---------------------------------------------------------------------------
def build_main_q3(variant: str) -> bytes:
    assert variant in ("b5", "b6", "b7")

    if variant == "b5":
        arm_block = "        ; b5: 割り込みは有効化しない(陽性対照)\n"
        isr_body = "        RETI\n"
    else:
        arm_block = f"""
        LD A,02h
        OUT (PORT_INT_LEVEL),A
        LD A,02h
        OUT (PORT_INT_MASK),A
        IM 1
        EI
"""
        if variant == "b6":
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
        else:  # b7: 禁止設計。窓の中(0x6030)へ無条件でCALLする
            isr_body = """
        LD A,02h
        OUT (PORT_INT_LEVEL),A
        LD A,(BANK_ACTIVE)
        OR A
        JR Z,ISR_SKIP_HIT
        LD HL,(ACTIVE_HIT)
        INC HL
        LD (ACTIVE_HIT),HL
ISR_SKIP_HIT:
        CALL WINDOW_CALL_TARGET
        EI
        RET
"""

    # b7のみ、窓の中の main ROM 側 0x6030 に「安全なルーチン」を置く。
    # バンク側(build_bank_q3)には同じ番地に何も置かない(0xFF埋め)ので、
    # 「バンクが無効なときだけ安全、有効にすると同じ番地が不定になる」
    # という禁止設計の実演になる。埋めの途中に割り込ませるため、
    # 前半の埋め・ルーチン本体・後半の埋め の3つに分けて書く。
    if variant == "b7":
        winsafe_body = """
WINSAFE:
        LD HL,(WINCALL)
        INC HL
        LD (WINCALL),HL
        RET
"""
        # LD HL,(nn)=3 + INC HL=1 + LD (nn),HL=3 + RET=1 = 8バイト
        winsafe_len = 8
    else:
        winsafe_body = ""
        winsafe_len = 0

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

        LD HL,0c100h
        LD (HL),0
        LD DE,0c101h
        LD BC,00ffh
        LDIR

{arm_block}
        LD HL,0
        LD (ITER),HL

LOOP:
        LD A,(ITER)
        AND 03h
        LD (SCR_BANKNO),A

        LD A,1
        LD (BANK_ACTIVE),A

        IN A,(PORT_EROM)
        LD (SCR_SAVE71),A
        IN A,(PORT_MISC)
        LD (SCR_SAVE32),A

        LD A,(SCR_SAVE71)
        AND 0feh
        OUT (PORT_EROM),A
        LD A,(SCR_SAVE32)
        AND 0fch
        LD HL,SCR_BANKNO
        OR (HL)
        OUT (PORT_MISC),A

        CALL BANK_ROUTINE

        LD A,(WINDOW_HEAD)
        LD C,A
        LD A,(SCR_BANKNO)
        LD B,A
        LD A,0a0h
        ADD A,B
        CP C
        JR NZ,NOMATCH
        LD HL,(MATCH)
        INC HL
        LD (MATCH),HL
NOMATCH:

        LD A,(SCR_SAVE71)
        OUT (PORT_EROM),A
        LD A,(SCR_SAVE32)
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

        ORG 6000h
        DB {MAIN_WINDOW_FILL:#04x}
        DS {WINDOW_CALL_TARGET - WINDOW_HEAD - 1},{MAIN_WINDOW_FILL:#04x}
{winsafe_body}
        DS {WINDOW_TAIL - WINDOW_HEAD - 1 - (WINDOW_CALL_TARGET - WINDOW_HEAD - 1) - winsafe_len},{MAIN_WINDOW_FILL:#04x}
        DB {MAIN_WINDOW_FILL + 1:#04x}
    """
    code = asm(src)
    buf = bytearray(code) + bytearray([0] * (N88_SIZE - len(code)))
    return bytes(buf[:N88_SIZE])


def write_rom_set(outdir: pathlib.Path, arm: str, omit_bank=None, swap_banks=None):
    outdir.mkdir(parents=True, exist_ok=True)

    if arm == "ra":
        main = build_main_ra()
        banks = {n: build_bank_ra(n) for n in range(4)}
    else:
        variant = arm.split("-", 1)[1]
        main = build_main_q3(variant)
        banks = {n: build_bank_q3(n) for n in range(4)}

    (outdir / "N88.ROM").write_bytes(main)
    (outdir / "DISK.ROM").write_bytes(build_disk())

    if swap_banks is not None:
        a, b = swap_banks
        banks[a], banks[b] = banks[b], banks[a]

    for n, data in banks.items():
        if omit_bank is not None and n == omit_bank:
            continue
        (outdir / f"N88_{n}.ROM").write_bytes(data)

    print(f"生成した({arm}): {outdir}")
    if omit_bank is not None:
        print(f"  N88_{omit_bank}.ROM は意図的に省略(B4用)")
    if swap_banks is not None:
        print(f"  バンク{swap_banks[0]}と{swap_banks[1]}の中身を入れ替え済み(G6用)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--arm", required=True,
                     choices=["ra", "q3-b5", "q3-b6", "q3-b7"])
    ap.add_argument("--omit-bank", type=int, default=None, choices=[0, 1, 2, 3])
    ap.add_argument("--swap-banks", nargs=2, type=int, default=None, metavar=("A", "B"))
    args = ap.parse_args()

    write_rom_set(pathlib.Path(args.outdir), args.arm,
                  omit_bank=args.omit_bank,
                  swap_banks=tuple(args.swap_banks) if args.swap_banks else None)

    print()
    print("RAM番地一覧:")
    for k, v in RAM.items():
        print(f"  {k:<12} = {v:#06x}")


if __name__ == "__main__":
    main()
