#!/usr/bin/env python3
"""
z80text_selftest.py — z80text.py 単体の境界・代表命令チェック。

段階0（M7）の「小さな単体検査」担当分:
  - jr の -128/+127（境界内は成功・範囲外はエラー）
  - (IX+d)/(IY+d) の -128/+127（境界内は成功・範囲外はエラー）
  - ds（件数ぶんのバイトを fill 値で埋める）
  - equ の前方参照（後で定義される EQU を先に使う。EQU 同士の連鎖も）
  - 主要命令グループ（LD 系・ALU・CB系・ED系・DD/FD系・分岐・スタック）の
    代表例がバイト列として正しいこと

外部アセンブラとの全命令突き合わせ（段階0後半）は別担当が別途行う。
ここは z80text.py 単体の内部整合性チェック。
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import z80text as z  # noqa: E402


def check_eq(name, got, expect):
    if got != expect:
        raise SystemExit(f"NG {name}: got={got!r} expect={expect!r}")
    print(f"OK  {name}")


def check_raises(name, fn):
    try:
        fn()
    except z.AsmError:
        print(f"OK  {name}（期待通りエラー）")
        return
    raise SystemExit(f"NG {name}: エラーになるべきなのに成功した")


def encode(mnem_operand, pc=0):
    parts = mnem_operand.split(None, 1)
    mnem = parts[0]
    operand = parts[1] if len(parts) > 1 else ""
    return z.encode_line(mnem, operand, {}, pc, length_only=False)


def assemble_text(text, tmpdir):
    p = pathlib.Path(tmpdir) / "t.asm"
    p.write_text(text, encoding="utf-8")
    return z.Assembler().assemble(p)


def main():
    # ---- 代表命令（表駆動の各分岐を1つずつ踏む）----
    cases = [
        ("nop", bytes([0])),
        ("halt", bytes([0x76])),
        ("ld a,5", bytes([0x3E, 5])),
        ("ld a,0FFh", bytes([0x3E, 0xFF])),
        ("ld b,c", bytes([0x41])),
        ("ld (hl),a", bytes([0x77])),
        ("ld (hl),42", bytes([0x36, 42])),
        ("ld (ix+2),7", bytes([0xDD, 0x36, 2, 7])),
        ("ld hl,1234h", bytes([0x21, 0x34, 0x12])),
        ("ld (1234h),hl", bytes([0x22, 0x34, 0x12])),
        ("ld hl,(1234h)", bytes([0x2A, 0x34, 0x12])),
        ("ld bc,1234h", bytes([0x01, 0x34, 0x12])),
        ("ld (1234h),bc", bytes([0xED, 0x43, 0x34, 0x12])),
        ("ld bc,(1234h)", bytes([0xED, 0x4B, 0x34, 0x12])),
        ("ld sp,hl", bytes([0xF9])),
        ("ld sp,ix", bytes([0xDD, 0xF9])),
        ("ld a,(bc)", bytes([0x0A])),
        ("ld (de),a", bytes([0x12])),
        ("ld a,i", bytes([0xED, 0x57])),
        ("ld r,a", bytes([0xED, 0x4F])),
        ("push af", bytes([0xF5])),
        ("pop bc", bytes([0xC1])),
        ("push ix", bytes([0xDD, 0xE5])),
        ("pop iy", bytes([0xFD, 0xE1])),
        ("add hl,de", bytes([0x19])),
        ("adc hl,bc", bytes([0xED, 0x4A])),
        ("sbc hl,de", bytes([0xED, 0x52])),
        ("add ix,bc", bytes([0xDD, 0x09])),
        ("add iy,iy", bytes([0xFD, 0x29])),
        ("inc de", bytes([0x13])),
        ("dec bc", bytes([0x0B])),
        ("inc ix", bytes([0xDD, 0x23])),
        ("inc (hl)", bytes([0x34])),
        ("inc (ix+5)", bytes([0xDD, 0x34, 0x05])),
        ("dec (iy-1)", bytes([0xFD, 0x35, 0xFF])),
        ("add a,b", bytes([0x80])),
        ("add a,5", bytes([0xC6, 5])),
        ("adc a,(ix+1)", bytes([0xDD, 0x8E, 1])),
        ("sub c", bytes([0x91])),
        ("sbc a,3", bytes([0xDE, 3])),
        ("and 0Fh", bytes([0xE6, 0x0F])),
        ("xor a", bytes([0xAF])),
        ("or b", bytes([0xB0])),
        ("cp (hl)", bytes([0xBE])),
        ("in a,(30h)", bytes([0xDB, 0x30])),
        ("out (30h),a", bytes([0xD3, 0x30])),
        ("in b,(c)", bytes([0xED, 0x40])),
        ("out (c),b", bytes([0xED, 0x41])),
        ("rlc b", bytes([0xCB, 0x00])),
        ("rrc (hl)", bytes([0xCB, 0x0E])),
        ("rl (ix+3)", bytes([0xDD, 0xCB, 3, 0x16])),
        ("rr (iy+3)", bytes([0xFD, 0xCB, 3, 0x1E])),
        ("sla c", bytes([0xCB, 0x21])),
        ("sra d", bytes([0xCB, 0x2A])),
        ("srl e", bytes([0xCB, 0x3B])),
        ("bit 3,a", bytes([0xCB, 0x5F])),
        ("bit 0,(hl)", bytes([0xCB, 0x46])),
        ("bit 7,(iy+1)", bytes([0xFD, 0xCB, 1, 0x7E])),
        ("set 1,(ix+0)", bytes([0xDD, 0xCB, 0, 0xCE])),
        ("res 2,c", bytes([0xCB, 0x91])),
        ("call 1234h", bytes([0xCD, 0x34, 0x12])),
        ("call nz,1234h", bytes([0xC4, 0x34, 0x12])),
        ("jp 1234h", bytes([0xC3, 0x34, 0x12])),
        ("jp c,1234h", bytes([0xDA, 0x34, 0x12])),
        ("jp (hl)", bytes([0xE9])),
        ("jp (ix)", bytes([0xDD, 0xE9])),
        ("jp (iy)", bytes([0xFD, 0xE9])),
        ("ret", bytes([0xC9])),
        ("ret z", bytes([0xC8])),
        ("reti", bytes([0xED, 0x4D])),
        ("retn", bytes([0xED, 0x45])),
        ("rst 38h", bytes([0xFF])),
        ("rst 0", bytes([0xC7])),
        ("ex de,hl", bytes([0xEB])),
        ("ex af,af'", bytes([0x08])),
        ("exx", bytes([0xD9])),
        ("ex (sp),hl", bytes([0xE3])),
        ("ex (sp),ix", bytes([0xDD, 0xE3])),
        ("im 0", bytes([0xED, 0x46])),
        ("im 1", bytes([0xED, 0x56])),
        ("im 2", bytes([0xED, 0x5E])),
        ("ldi", bytes([0xED, 0xA0])),
        ("ldir", bytes([0xED, 0xB0])),
        ("ldd", bytes([0xED, 0xA8])),
        ("lddr", bytes([0xED, 0xB8])),
        ("cpi", bytes([0xED, 0xA1])),
        ("cpir", bytes([0xED, 0xB1])),
        ("cpd", bytes([0xED, 0xA9])),
        ("cpdr", bytes([0xED, 0xB9])),
        ("ini", bytes([0xED, 0xA2])),
        ("inir", bytes([0xED, 0xB2])),
        ("ind", bytes([0xED, 0xAA])),
        ("indr", bytes([0xED, 0xBA])),
        ("outi", bytes([0xED, 0xA3])),
        ("otir", bytes([0xED, 0xB3])),
        ("outd", bytes([0xED, 0xAB])),
        ("otdr", bytes([0xED, 0xBB])),
        ("neg", bytes([0xED, 0x44])),
        ("rrd", bytes([0xED, 0x67])),
        ("rld", bytes([0xED, 0x6F])),
        ("rlca", bytes([0x07])),
        ("rla", bytes([0x17])),
        ("rrca", bytes([0x0F])),
        ("rra", bytes([0x1F])),
        ("daa", bytes([0x27])),
        ("cpl", bytes([0x2F])),
        ("scf", bytes([0x37])),
        ("ccf", bytes([0x3F])),
        ("di", bytes([0xF3])),
        ("ei", bytes([0xFB])),
    ]
    for src, expect in cases:
        check_eq(f"encode {src!r}", encode(src), expect)

    # ---- LD (HL),(HL) は不正（HALT を使うべき） ----
    check_raises("LD (HL),(HL) はエラー", lambda: encode("ld (hl),(hl)"))

    with tempfile.TemporaryDirectory() as td:
        # ---- jr 境界: -128/+127 は成功、+128 は失敗 ----
        code = assemble_text("    org 4\nTARGET:\n    nop\n    org 130\n"
                              "    jr TARGET\n", td)
        check_eq("jr delta=-128 は成功しRelが0x80", code[-1], 0x80)

        code = assemble_text("    org 0\n    jr TARGET\n    org 129\nTARGET:\n"
                              "    nop\n", td)
        check_eq("jr delta=+127 は成功しRelが0x7F", code[1], 0x7F)

        check_raises(
            "jr delta=+128 はエラー",
            lambda: assemble_text(
                "    org 0\n    jr TARGET\n    org 130\nTARGET:\n    nop\n", td))

        # ---- djnz も同じ境界を持つ ----
        code = assemble_text("    org 0\n    djnz TARGET\n    org 129\nTARGET:\n"
                              "    nop\n", td)
        check_eq("djnz delta=+127 は成功", code[1], 0x7F)
        check_raises(
            "djnz delta=+128 はエラー",
            lambda: assemble_text(
                "    org 0\n    djnz TARGET\n    org 130\nTARGET:\n    nop\n", td))

        # ---- (IX+d)/(IY+d) 境界: -128/+127 は成功、範囲外は失敗 ----
        code = assemble_text("    ld a,(ix+127)\n    ld a,(ix-128)\n", td)
        check_eq("(ix+127)/(ix-128) 境界", code, bytes([0xDD, 0x7E, 0x7F,
                                                          0xDD, 0x7E, 0x80]))
        check_raises("(ix+128) はエラー",
                     lambda: assemble_text("    ld a,(ix+128)\n", td))
        check_raises("(iy-129) はエラー",
                     lambda: assemble_text("    ld a,(iy-129)\n", td))

        # ---- ds ----
        code = assemble_text("    ds 5,0AAh\n", td)
        check_eq("ds 5,0AAh", code, bytes([0xAA]) * 5)
        code = assemble_text("    ds 3\n", td)
        check_eq("ds 3（fill省略時は0）", code, bytes([0]) * 3)

        # ---- equ の前方参照（単純・連鎖・EQU間の連鎖） ----
        code = assemble_text(
            "    org 0\n"
            "    ld a,VALUE\n"
            "VALUE: equ 5+FOO\n"
            "FOO: equ BAR*2\n"
            "BAR: equ 3\n",
            td)
        check_eq("equ 前方参照の連鎖（5+3*2=11）", code, bytes([0x3E, 11]))

        # ---- equ の循環参照はエラー ----
        check_raises(
            "equ 循環参照はエラー",
            lambda: assemble_text("X: equ Y+1\nY: equ X+1\n", td))

        # ---- ラベル重複はエラー ----
        check_raises("ラベル重複はエラー",
                     lambda: assemble_text("A: nop\nA: nop\n", td))

        # ---- 未定義ラベルはエラー ----
        check_raises("未定義ラベルはエラー",
                     lambda: assemble_text("    jp NOPE\n", td))

        # ---- include ----
        (pathlib.Path(td) / "inc1.asm").write_text("    nop\n    nop\n",
                                                     encoding="utf-8")
        code = assemble_text('    ld a,1\n    include "inc1.asm"\n    ld a,2\n',
                              td)
        check_eq("include", code, bytes([0x3E, 1, 0, 0, 0x3E, 2]))

        # ---- db の文字列とバイトの混在、10進・16進・文字定数 ----
        code = assemble_text('    db "AB", 1, 0Ah, 0x0B, \'C\'\n', td)
        check_eq("db 混在", code, bytes([0x41, 0x42, 1, 0x0A, 0x0B, 0x43]))

        # ---- $ = 現在アドレス（org は手前をゼロ埋めするので末尾2バイトを見る）----
        code = assemble_text("    org 100\n    dw $\n", td)
        check_eq("$ は現在アドレス", code[-2:], bytes([100, 0]))

    print("\nすべて OK")


if __name__ == "__main__":
    main()
