#!/usr/bin/env python3
"""
gen_z80_corpus.py — Z80「文書化された全命令」のコーパス生成器

M7（L4）段階0の後半。docs/notes/l4-asm-oracle.md 参照。

Zilog 公式ニーモニック表（ハードウェア仕様＝資料区分(a)、ROM とは無関係の
公開 ISA 情報）に基づき、1行1命令でテストケースを列挙する。レジスタは
全組み合わせ、即値・番地・変位は境界値を中心にした代表値を使う。
未文書化命令（IXH/IXL 直接アクセス、SLL、DD/FD CB の「おまけ」書き込み先、
IN F,(C)/OUT (C),0 等）は入れない。

出力: 指定した .asm ファイルと、対応する manifest（1行ごとの命令テキストと
期待バイト長を記録した TSV）。manifest の期待長は「その命令形が何バイトに
なるか」という Z80 ISA の一般知識から決めるもので、正誤判定そのものは
別ツール（oracle_crosscheck.py）が外部アセンブラ2種の出力バイト列を突き合わせて行う。
"""

import argparse
import os
import pathlib
import sys

R8 = ["B", "C", "D", "E", "H", "L", "(HL)", "A"]
RP = ["BC", "DE", "HL", "SP"]
RP2 = ["BC", "DE", "HL", "AF"]
CC8 = ["NZ", "Z", "NC", "C", "PO", "PE", "P", "M"]
CC4 = ["NZ", "Z", "NC", "C"]
ALU = ["ADD A,", "ADC A,", "SUB ", "SBC A,", "AND ", "XOR ", "OR ", "CP "]
CB_ROT = ["RLC", "RRC", "RL", "RR", "SLA", "SRA", "SRL"]

N8 = [0, 1, 0x7F, 0x80, 0xFF]
N16 = [0, 1, 0x7FFF, 0x8000, 0xFFFF, 0x1234]
NN_SMALL = [0, 0x1234, 0xFFFF]
D_VALUES = [-128, -1, 0, 1, 127]
RST_P = [0x00, 0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38]
PORT_N = [0, 0x7F, 0xFF]

# 行 = (テキスト, 期待バイト長, タグ)
rows = []


def emit(text, length, tag):
    rows.append((text, length, tag))


def h8(v):
    return f"0x{v & 0xFF:02X}"


def h16(v):
    return f"0x{v & 0xFFFF:04X}"


def hd(v):
    # (IX+d)/(IY+d) の変位。負値はそのまま "-N" で書く（0x 表記は非負のみ扱う）。
    return f"{v}" if v < 0 else f"+{v}" if v > 0 else "+0"


# --- 主命令ページ（256 - 4前置き = 252 通り） ---------------------------

# LD r,r'（0x40-0x7F, ただし (HL),(HL) は無く HALT）
for dst in R8:
    for src in R8:
        if dst == "(HL)" and src == "(HL)":
            continue
        emit(f"LD {dst},{src}", 1, "main:ld_r_r")
emit("HALT", 1, "main:halt")

# LD r,n
for r in R8:
    for n in N8:
        emit(f"LD {r},{h8(n)}", 2, "main:ld_r_n")

# LD rp,nn
for rp in RP:
    for nn in N16:
        emit(f"LD {rp},{h16(nn)}", 3, "main:ld_rp_nn")

# LD (BC),A / LD A,(BC) / LD (DE),A / LD A,(DE)
emit("LD (BC),A", 1, "main:ld_mem8")
emit("LD A,(BC)", 1, "main:ld_mem8")
emit("LD (DE),A", 1, "main:ld_mem8")
emit("LD A,(DE)", 1, "main:ld_mem8")

# LD (nn),HL / LD HL,(nn) / LD (nn),A / LD A,(nn)
for nn in NN_SMALL:
    emit(f"LD ({h16(nn)}),HL", 3, "main:ld_mem16")
    emit(f"LD HL,({h16(nn)})", 3, "main:ld_mem16")
    emit(f"LD ({h16(nn)}),A", 3, "main:ld_mem16")
    emit(f"LD A,({h16(nn)})", 3, "main:ld_mem16")

# INC/DEC r, rp
for r in R8:
    emit(f"INC {r}", 1, "main:inc_r")
    emit(f"DEC {r}", 1, "main:dec_r")
for rp in RP:
    emit(f"INC {rp}", 1, "main:inc_rp")
    emit(f"DEC {rp}", 1, "main:dec_rp")

# ADD HL,rp
for rp in RP:
    emit(f"ADD HL,{rp}", 1, "main:add_hl_rp")

# ALU A,r / ALU n
for op in ALU:
    for r in R8:
        emit(f"{op}{r}", 1, "main:alu_r")
    for n in N8:
        emit(f"{op}{h8(n)}", 2, "main:alu_n")

# 単純命令
for m in ["RLCA", "RRCA", "RLA", "RRA", "DAA", "CPL", "SCF", "CCF", "NOP"]:
    emit(m, 1, "main:simple")

# EX / EXX
emit("EX AF,AF'", 1, "main:ex")
emit("EX DE,HL", 1, "main:ex")
emit("EX (SP),HL", 1, "main:ex")
emit("EXX", 1, "main:exx")

# DI / EI
emit("DI", 1, "main:di_ei")
emit("EI", 1, "main:di_ei")

# JP
for nn in NN_SMALL:
    emit(f"JP {h16(nn)}", 3, "main:jp_nn")
for cc in CC8:
    for nn in [0, 0x1234]:
        emit(f"JP {cc},{h16(nn)}", 3, "main:jp_cc_nn")
emit("JP (HL)", 1, "main:jp_hl")

# JR（無条件）: d = -128, +127, 0, -2(自分自身)
emit("JR $-126", 2, "main:jr")
emit("JR $+129", 2, "main:jr")
emit("JR $+2", 2, "main:jr")
emit("JR $", 2, "main:jr")

# JR cc,e（NZ,Z,NC,C のみ）: d = -128, +127
for cc in CC4:
    emit(f"JR {cc},$-126", 2, "main:jr_cc")
    emit(f"JR {cc},$+129", 2, "main:jr_cc")

# DJNZ e: d = -128, +127
emit("DJNZ $-126", 2, "main:djnz")
emit("DJNZ $+129", 2, "main:djnz")

# CALL
for nn in [0, 0x1234]:
    emit(f"CALL {h16(nn)}", 3, "main:call_nn")
for cc in CC8:
    for nn in [0, 0x1234]:
        emit(f"CALL {cc},{h16(nn)}", 3, "main:call_cc_nn")

# RET
emit("RET", 1, "main:ret")
for cc in CC8:
    emit(f"RET {cc}", 1, "main:ret_cc")

# RST
for p in RST_P:
    emit(f"RST {h8(p)}", 1, "main:rst")

# PUSH/POP
for rp in RP2:
    emit(f"PUSH {rp}", 1, "main:push")
    emit(f"POP {rp}", 1, "main:pop")

# IN A,(n) / OUT (n),A
for n in PORT_N:
    emit(f"IN A,({h8(n)})", 2, "main:in_a_n")
    emit(f"OUT ({h8(n)}),A", 2, "main:out_n_a")

# LD SP,HL
emit("LD SP,HL", 1, "main:ld_sp_hl")

# --- CB ページ（256 - 8(SLL) = 248 通り） -------------------------------

for op in CB_ROT:
    for r in R8:
        emit(f"{op} {r}", 2, "cb:rot")
for b in range(8):
    for r in R8:
        emit(f"BIT {b},{r}", 2, "cb:bit")
        emit(f"RES {b},{r}", 2, "cb:res")
        emit(f"SET {b},{r}", 2, "cb:set")

# --- ED ページ（文書化分） -----------------------------------------------

for r in [x for x in R8 if x != "(HL)"]:
    emit(f"IN {r},(C)", 2, "ed:in_r_c")
    emit(f"OUT (C),{r}", 2, "ed:out_c_r")
for rp in RP:
    emit(f"SBC HL,{rp}", 2, "ed:sbc_hl_rp")
    emit(f"ADC HL,{rp}", 2, "ed:adc_hl_rp")
# HL は main ページに 3 バイトの LD (nn),HL / LD HL,(nn) が既にあり、
# 同じニーモニック文字列は（重複エンコードのため）どのアセンブラも短い方の
# 3バイト形を選ぶ。ED前置き4バイト形はその文字列からは到達できないので
# ここでは BC/DE/SP のみを対象にする。
for rp in ["BC", "DE", "SP"]:
    for nn in [0, 0x1234, 0xFFFF]:
        emit(f"LD ({h16(nn)}),{rp}", 4, "ed:ld_mem_rp")
        emit(f"LD {rp},({h16(nn)})", 4, "ed:ld_rp_mem")
emit("NEG", 2, "ed:neg")
emit("RETN", 2, "ed:retn")
emit("RETI", 2, "ed:reti")
emit("IM 0", 2, "ed:im")
emit("IM 1", 2, "ed:im")
emit("IM 2", 2, "ed:im")
emit("RRD", 2, "ed:rrd")
emit("RLD", 2, "ed:rld")
for m in ["LDI", "LDD", "LDIR", "LDDR",
          "CPI", "CPD", "CPIR", "CPDR",
          "INI", "IND", "INIR", "INDR",
          "OUTI", "OUTD", "OTIR", "OTDR"]:
    emit(m, 2, "ed:block")
# LD I,A / LD R,A / LD A,I / LD A,R
# 2026-09-15: ED 系が 52 種しか無かった。Zilog の文書化命令は 56 種のはずで、
# この4命令がまるごと抜けていた（下記コメントの数え上げ参照）。
emit("LD I,A", 2, "ed:ld_ir_a")
emit("LD R,A", 2, "ed:ld_ir_a")
emit("LD A,I", 2, "ed:ld_a_ir")
emit("LD A,R", 2, "ed:ld_a_ir")

# --- DD/FD ページ（IX/IY、文書化分） ------------------------------------

for idx in ["IX", "IY"]:
    for rp in ["BC", "DE", idx, "SP"]:
        emit(f"ADD {idx},{rp}", 2, "ddfd:add_idx_rp")
    for nn in N16:
        emit(f"LD {idx},{h16(nn)}", 4, "ddfd:ld_idx_nn")
    for nn in NN_SMALL:
        emit(f"LD ({h16(nn)}),{idx}", 4, "ddfd:ld_mem_idx")
        emit(f"LD {idx},({h16(nn)})", 4, "ddfd:ld_idx_mem")
    emit(f"INC {idx}", 2, "ddfd:inc_idx")
    emit(f"DEC {idx}", 2, "ddfd:dec_idx")
    for d in D_VALUES:
        emit(f"INC ({idx}{hd(d)})", 3, "ddfd:inc_mem_idx")
        emit(f"DEC ({idx}{hd(d)})", 3, "ddfd:dec_mem_idx")
        emit(f"LD ({idx}{hd(d)}),{h8(0x12)}", 4, "ddfd:ld_mem_idx_n")
    for r in ["B", "C", "D", "E", "H", "L", "A"]:
        for d in D_VALUES:
            emit(f"LD {r},({idx}{hd(d)})", 3, "ddfd:ld_r_mem_idx")
            emit(f"LD ({idx}{hd(d)}),{r}", 3, "ddfd:ld_mem_idx_r")
    for op in ALU:
        for d in D_VALUES:
            emit(f"{op}({idx}{hd(d)})", 3, "ddfd:alu_mem_idx")
    emit(f"PUSH {idx}", 2, "ddfd:push_idx")
    emit(f"POP {idx}", 2, "ddfd:pop_idx")
    emit(f"EX (SP),{idx}", 2, "ddfd:ex_sp_idx")
    emit(f"JP ({idx})", 2, "ddfd:jp_idx")
    emit(f"LD SP,{idx}", 2, "ddfd:ld_sp_idx")
    # DD CB d / FD CB d（回転・BIT・RES・SET, (HL)相当のみ＝おまけ書き込み無し）
    for op in CB_ROT:
        for d in D_VALUES:
            emit(f"{op} ({idx}{hd(d)})", 4, "ddfdcb:rot")
    for b in range(8):
        for d in D_VALUES:
            emit(f"BIT {b},({idx}{hd(d)})", 4, "ddfdcb:bit")
            emit(f"RES {b},({idx}{hd(d)})", 4, "ddfdcb:res")
            emit(f"SET {b},({idx}{hd(d)})", 4, "ddfdcb:set")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", required=True, help="出力 .asm")
    ap.add_argument("-m", "--manifest", required=True, help="出力 manifest (TSV)")
    args = ap.parse_args()

    # 陽性対照専用: コーパスから1命令をまるごと除く故障注入。
    # 環境変数 Z80_CORPUS_OMIT_TEXT に命令テキスト（完全一致、例 "LD I,A"）を
    # 渡すと、その行を生成しない。oracle_crosscheck.py の網羅検査が
    # NG になることを確認する目的専用。既定では何も除かない。
    omit_text = os.environ.get("Z80_CORPUS_OMIT_TEXT")
    global rows
    if omit_text:
        before = len(rows)
        rows = [r for r in rows if r[0] != omit_text]
        removed = before - len(rows)
        print(f"[故障注入] 除外: {omit_text!r} ({removed}件)", file=sys.stderr)
        if removed == 0:
            print(f"[故障注入] 警告: {omit_text!r} に一致する行が無かった", file=sys.stderr)

    asm_lines = ["    ORG 0x0000"]
    manifest_lines = ["index\ttext\texpect_len\ttag"]
    for i, (text, length, tag) in enumerate(rows):
        asm_lines.append(f"    {text}")
        manifest_lines.append(f"{i}\t{text}\t{length}\t{tag}")

    pathlib.Path(args.output).write_text("\n".join(asm_lines) + "\n", encoding="utf-8")
    pathlib.Path(args.manifest).write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"生成: {len(rows)} 行 -> {args.output} / {args.manifest}")


if __name__ == "__main__":
    main()
