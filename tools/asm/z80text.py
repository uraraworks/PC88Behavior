#!/usr/bin/env python3
"""
z80text.py — python3 だけで動く（外部依存ゼロ）Z80 テキストアセンブラ

M7（L4）段階0「アセンブラ」の道具。docs/notes/l4-design.md 段階0参照。
z88dk の `z80asm` と紛れないよう、あえてこの名前にしてある。

## スコープ

Z80 の **文書化された全命令**（主命令表・CB・ED・DD/FD・DD CB d / FD CB d 形）
を表駆動（フォーミュラ駆動）で符号化する。

**未文書化命令は入れない。** 理由:
  1. 公式資料に載っていない挙動を実装として持ち込むと、後段（外部アセンブラ
     との全命令突き合わせ）で「文書化されている命令が一致するか」という
     素直な検査ができなくなる。
  2. このリポジトリの成果物（自作 ROM）は文書化された命令だけで書ける
     （実際、既存の make_ipl_rom.py / make_subrom.py も未文書化命令を
     一切使っていない）。無い機能を持ち込む理由が無い。
  3. IXH/IXL 単体アクセスや SLL、DD CB d の「結果を別レジスタにも書く」形は
     Z80 メーカー資料に無い、ダイの副作用を利用した挙動であり、実機・
     エミュレータ間で扱いが割れることがある。

具体的に**入れていない**もの: SLL（未文書化シフト、CB 0x30-0x37 相当）、
IXH/IXL/IYH/IYL の直接読み書き（DD/FD 付き 8 ビットレジスタ命令で H/L
スロットを使うもの）、DD CB d / FD CB d で結果を (HL) 相当以外のレジスタにも
書き込む「おまけ」形（CB のオペランド r が 6 以外になる DD/FD CB 命令）。

## 2 パス方式

パス1: 各行を字句解析し、命令・疑似命令の**バイト長だけ**を求めてラベルの
番地を確定する（オペランドの値は評価しない。相対分岐の飛び先や (IX+d) の
値は「文字面としてその形か」だけで長さが決まるため、値の評価は要らない）。
`org` と `ds` の引数だけは例外で、パス1の時点で確定した記号（前方参照が
出てくる前に登場したラベル・EQU）だけで評価できることを要求する。

`equ` はパス1では**式の文字列だけ**を覚え、値は評価しない。ラベルの位置が
全て確定した後（パス1の後）に、EQU 同士の前方参照も解決できるよう遅延評価
する（循環参照は検出してエラーにする）。

パス2: 全ラベル・EQU が定まった状態で、命令を実際のバイト列へ符号化する。
"""

import argparse
import pathlib
import re
import sys


class AsmError(Exception):
    def __init__(self, message, line_no=None, line_text=None):
        self.message = message
        self.line_no = line_no
        self.line_text = line_text
        if line_no is not None:
            full = f"行 {line_no}: {message}"
            if line_text is not None:
                full += f"  | {line_text.strip()}"
        else:
            full = message
        super().__init__(full)


# ==========================================================================
# レジスタ・条件コードの表
# ==========================================================================

R8_INDEX = {"B": 0, "C": 1, "D": 2, "E": 3, "H": 4, "L": 5, "A": 7}
RP_INDEX = {"BC": 0, "DE": 1, "HL": 2, "SP": 3}          # 16bit系（SP終端）
RP2_INDEX = {"BC": 0, "DE": 1, "HL": 2, "AF": 3}          # PUSH/POP系（AF終端）
CC_INDEX = {"NZ": 0, "Z": 1, "NC": 2, "C": 3, "PO": 4, "PE": 5, "P": 6, "M": 7}
CC_JR = {"NZ": 0x20, "Z": 0x28, "NC": 0x30, "C": 0x38}

ALU_INDEX = {"ADD": 0, "ADC": 1, "SUB": 2, "SBC": 3,
             "AND": 4, "XOR": 5, "OR": 6, "CP": 7}
CB_ROT_INDEX = {"RLC": 0, "RRC": 1, "RL": 2, "RR": 3,
                "SLA": 4, "SRA": 5, "SRL": 7}   # 0x30(SLL)は未文書化なので無い

IDX_PREFIX = {"IX": 0xDD, "IY": 0xFD}


# ==========================================================================
# 式パーサ（+ - * / & | ^ << >> ~、括弧、$、10進・0x・$FF・0FFh、'A'）
# ==========================================================================

_TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<hexdollar>\$[0-9A-Fa-f]+)      |
        (?P<hex0x>0[xX][0-9A-Fa-f]+)       |
        (?P<hexsuf>[0-9][0-9A-Fa-f]*[hH])  |
        (?P<dec>[0-9]+)                    |
        (?P<char>'(?:[^'\\]|\\.)')          |
        (?P<shl><<)                        |
        (?P<shr>>>)                        |
        (?P<ident>[A-Za-z_.][A-Za-z0-9_.]*) |
        (?P<dollar>\$)                      |
        (?P<punct>[()+\-*/&|^~])
    )
""", re.VERBOSE)


def tokenize_expr(text):
    toks = []
    pos = 0
    n = len(text)
    while pos < n:
        if text[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            raise AsmError(f"式を解釈できない: {text!r} (位置 {pos})")
        pos = m.end()
        kind = m.lastgroup
        val = m.group(kind)
        toks.append((kind, val))
    toks.append(("eof", ""))
    return toks


class ExprParser:
    """再帰下降パーサ。ASTはタプル ('op', left, right) / ('num', n) /
    ('cur',) / ('sym', name) / ('neg', x) / ('not', x)。"""

    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect_punct(self, ch):
        kind, val = self.peek()
        if val != ch:
            raise AsmError(f"'{ch}' を期待したが '{val}' が来た")
        self.next()

    def parse(self):
        node = self.parse_bitor()
        kind, val = self.peek()
        if kind != "eof":
            raise AsmError(f"式の末尾に余分なトークン: {val!r}")
        return node

    def parse_bitor(self):
        node = self.parse_bitxor()
        while self.peek()[1] == "|":
            self.next()
            node = ("or", node, self.parse_bitxor())
        return node

    def parse_bitxor(self):
        node = self.parse_bitand()
        while self.peek()[1] == "^":
            self.next()
            node = ("xor", node, self.parse_bitand())
        return node

    def parse_bitand(self):
        node = self.parse_shift()
        while self.peek()[1] == "&":
            self.next()
            node = ("and", node, self.parse_shift())
        return node

    def parse_shift(self):
        node = self.parse_addsub()
        while self.peek()[0] in ("shl", "shr"):
            kind, _ = self.next()
            node = (kind, node, self.parse_addsub())
        return node

    def parse_addsub(self):
        node = self.parse_term()
        while self.peek()[1] in ("+", "-"):
            _, op = self.next()
            node = ("add" if op == "+" else "sub", node, self.parse_term())
        return node

    def parse_term(self):
        node = self.parse_unary()
        while self.peek()[1] in ("*", "/"):
            _, op = self.next()
            node = ("mul" if op == "*" else "div", node, self.parse_unary())
        return node

    def parse_unary(self):
        kind, val = self.peek()
        if val == "-":
            self.next()
            return ("neg", self.parse_unary())
        if val == "~":
            self.next()
            return ("not", self.parse_unary())
        if val == "+":
            self.next()
            return self.parse_unary()
        return self.parse_primary()

    def parse_primary(self):
        kind, val = self.next()
        if kind == "hexdollar":
            return ("num", int(val[1:], 16))
        if kind == "hex0x":
            return ("num", int(val, 16))
        if kind == "hexsuf":
            return ("num", int(val[:-1], 16))
        if kind == "dec":
            return ("num", int(val, 10))
        if kind == "char":
            inner = val[1:-1]
            if inner.startswith("\\"):
                inner = inner[1:]
            if len(inner) != 1:
                raise AsmError(f"文字定数は1文字のみ対応: {val!r}")
            return ("num", ord(inner))
        if kind == "dollar":
            return ("cur",)
        if kind == "ident":
            return ("sym", val)
        if val == "(":
            node = self.parse_bitor()
            self.expect_punct(")")
            return node
        raise AsmError(f"式の項として不正: {val!r}")


def parse_expr(text):
    return ExprParser(tokenize_expr(text)).parse()


def eval_expr(node, symtab, cur_pc):
    op = node[0]
    if op == "num":
        return node[1]
    if op == "cur":
        return cur_pc
    if op == "sym":
        name = node[1]
        if name not in symtab:
            raise AsmError(f"未定義ラベル: {name}")
        return symtab[name]
    if op == "neg":
        return -eval_expr(node[1], symtab, cur_pc)
    if op == "not":
        return ~eval_expr(node[1], symtab, cur_pc)
    a = eval_expr(node[1], symtab, cur_pc)
    b = eval_expr(node[2], symtab, cur_pc)
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    if op == "div":
        return a // b
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    if op == "shl":
        return a << b
    if op == "shr":
        return a >> b
    raise AsmError(f"未知の演算: {op}")


def collect_symbol_refs(node, out):
    """式に出てくる sym 参照名を集める（EQU の依存グラフ用）。"""
    if node[0] == "sym":
        out.add(node[1])
    elif node[0] in ("neg", "not"):
        collect_symbol_refs(node[1], out)
    elif node[0] not in ("num", "cur"):
        collect_symbol_refs(node[1], out)
        collect_symbol_refs(node[2], out)


# ==========================================================================
# 命令ごとの符号化
# ==========================================================================

def split_operands(text):
    """トップレベルのカンマで分割する（括弧・文字定数の中は割らない）。"""
    parts = []
    depth = 0
    cur = []
    i = 0
    in_char = False
    while i < len(text):
        ch = text[i]
        if in_char:
            cur.append(ch)
            if ch == "'":
                in_char = False
            i += 1
            continue
        if ch == "'":
            in_char = True
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    tail = "".join(cur).strip()
    if tail or parts:
        parts.append(tail)
    return [p for p in parts if p != ""] if text.strip() else []


_IDXMEM_RE = re.compile(r"^\(\s*(IX|IY)\s*([+-]\s*[^)]+)?\s*\)$", re.I)
_MEMREG_RE = re.compile(r"^\(\s*(BC|DE|HL|SP)\s*\)$", re.I)
_MEMC_RE = re.compile(r"^\(\s*C\s*\)$", re.I)
_MEM_RE = re.compile(r"^\((.*)\)$", re.S)


def classify(op):
    """オペランド1個を分類する。戻り値は種別タグ付きタプル。"""
    t = op.strip()
    tu = t.upper()
    if tu in R8_INDEX:
        return ("r8", tu)
    if tu in ("BC", "DE", "HL", "SP", "AF", "IX", "IY"):
        return ("rp", tu)
    if tu == "AF'":
        return ("af2",)
    if tu in CC_INDEX:
        return ("cc", tu)
    m = _IDXMEM_RE.match(t)
    if m:
        reg = m.group(1).upper()
        disp = m.group(2)
        disp = disp.replace(" ", "") if disp else "+0"
        return ("idxmem", reg, disp)
    m = _MEMREG_RE.match(t)
    if m:
        return ("memreg", m.group(1).upper())
    if _MEMC_RE.match(t):
        return ("portc",)
    m = _MEM_RE.match(t)
    if m:
        return ("mem", m.group(1).strip())
    return ("expr", t)


class Encoder:
    """1命令ぶんのオペランド解析結果から、バイト列を組み立てる。

    命令の**長さ**はパス1で `length_only=True` として求める（この時オペランド
    の値は評価しない）。パス2では `length_only=False` で実際の値を使って
    バイトを埋める。
    """

    def __init__(self, symtab, cur_pc, length_only):
        self.symtab = symtab
        self.cur_pc = cur_pc
        self.length_only = length_only
        self.out = bytearray()

    def val(self, text):
        if self.length_only:
            return 0
        try:
            node = parse_expr(text)
        except AsmError:
            raise
        return eval_expr(node, self.symtab, self.cur_pc)

    def byte_val(self, text, what="値"):
        v = self.val(text)
        if self.length_only:
            return 0
        if not -128 <= v <= 255:
            raise AsmError(f"{what}がバイト範囲外: {text!r} = {v}")
        return v & 0xFF

    def word_val(self, text):
        v = self.val(text)
        if self.length_only:
            return 0
        return v & 0xFFFF

    def disp_val(self, text):
        v = self.val(text)
        if self.length_only:
            return 0
        if not -128 <= v <= 127:
            raise AsmError(f"(IX+d)/(IY+d) の d が範囲外: {text!r} = {v}")
        return v & 0xFF

    def emit(self, *bs):
        self.out.extend(bs)

    def emit_word(self, w):
        self.out.append(w & 0xFF)
        self.out.append((w >> 8) & 0xFF)


def cc_value(op):
    """条件コードとしての文字列値を返す（無ければ None）。

    "C" はレジスタ C とキャリー条件 C の綴りが衝突するため、classify() は
    常に ("r8","C") を返す。条件コードを期待する文脈だけ、ここで文字列値を
    見て条件として解釈し直す。"NZ"/"Z"/"NC"/"PO"/"PE"/"P"/"M" は
    レジスタ名と衝突しないのでそのまま "cc" タグで来る。
    """
    if op[0] == "cc":
        return op[1]
    if op[0] == "r8" and op[1] == "C":
        return "C"
    return None


def r8_slot(op):
    """(index, prefix_or_None, disp_text_or_None) を返す。r8/idxmem 以外は None。"""
    kind = op[0]
    if kind == "r8":
        return (R8_INDEX[op[1]], None, None)
    if kind == "memreg" and op[1] == "HL":
        return (6, None, None)
    if kind == "idxmem":
        return (6, op[1], op[2])
    return None


def encode_line(mnemonic, operand_text, symtab, cur_pc, length_only):
    """1つの命令行を符号化する。戻り値はバイト列(bytes)。"""
    mnem = mnemonic.upper()
    ops = [classify(o) for o in split_operands(operand_text)]
    enc = Encoder(symtab, cur_pc, length_only)

    def need(n):
        if len(ops) != n:
            raise AsmError(f"{mnem} はオペランド{n}個が必要（{len(ops)}個指定）")

    # ---- オペランド無しの固定命令 ----
    FIXED0 = {
        "NOP": (0x00,), "HALT": (0x76,), "DI": (0xF3,), "EI": (0xFB,),
        "RET": (0xC9,), "RETI": (0xED, 0x4D), "RETN": (0xED, 0x45),
        "RLCA": (0x07,), "RLA": (0x17,), "RRCA": (0x0F,), "RRA": (0x1F,),
        "DAA": (0x27,), "CPL": (0x2F,), "SCF": (0x37,), "CCF": (0x3F,),
        "EXX": (0xD9,), "NEG": (0xED, 0x44), "RRD": (0xED, 0x67),
        "RLD": (0xED, 0x6F),
        "LDI": (0xED, 0xA0), "LDIR": (0xED, 0xB0),
        "LDD": (0xED, 0xA8), "LDDR": (0xED, 0xB8),
        "CPI": (0xED, 0xA1), "CPIR": (0xED, 0xB1),
        "CPD": (0xED, 0xA9), "CPDR": (0xED, 0xB9),
        "INI": (0xED, 0xA2), "INIR": (0xED, 0xB2),
        "IND": (0xED, 0xAA), "INDR": (0xED, 0xBA),
        "OUTI": (0xED, 0xA3), "OTIR": (0xED, 0xB3),
        "OUTD": (0xED, 0xAB), "OTDR": (0xED, 0xBB),
    }
    if mnem in FIXED0 and operand_text.strip() == "":
        enc.emit(*FIXED0[mnem])
        return bytes(enc.out)

    if mnem == "RET" and len(ops) == 1 and cc_value(ops[0]) in CC_INDEX:
        enc.emit(0xC0 + CC_INDEX[cc_value(ops[0])] * 8)
        return bytes(enc.out)

    if mnem == "EX":
        need(2)
        a, b = ops
        if {a[0], b[0]} == {"rp"} and {a[1] if a[0] == "rp" else None,
                                        b[1] if b[0] == "rp" else None} == {"DE", "HL"}:
            enc.emit(0xEB)
            return bytes(enc.out)
        if a[0] == "af2" and b[0] == "rp" and b[1] == "AF":
            enc.emit(0x08)
            return bytes(enc.out)
        if a[0] == "rp" and a[1] == "AF" and b[0] == "af2":
            enc.emit(0x08)
            return bytes(enc.out)
        if a[0] == "memreg" and a[1] == "SP" and b[0] == "rp" and b[1] == "HL":
            enc.emit(0xE3)
            return bytes(enc.out)
        if a[0] == "memreg" and a[1] == "SP" and b[0] == "rp" and b[1] in IDX_PREFIX:
            enc.emit(IDX_PREFIX[b[1]], 0xE3)
            return bytes(enc.out)
        raise AsmError(f"EX の組み合わせが未対応: {operand_text!r}")

    if mnem == "IM":
        need(1)
        text = split_operands(operand_text)[0]
        if length_only:
            enc.emit(0xED, 0x00)
            return bytes(enc.out)
        v = enc.val(text)
        if v not in (0, 1, 2):
            raise AsmError(f"IM のオペランドは 0/1/2: {text!r}")
        enc.emit(0xED, {0: 0x46, 1: 0x56, 2: 0x5E}[v])
        return bytes(enc.out)

    if mnem in ("JP", "CALL") and len(ops) == 1 and ops[0][0] == "memreg" and ops[0][1] == "HL":
        if mnem == "JP":
            enc.emit(0xE9)
            return bytes(enc.out)
    if mnem == "JP" and len(ops) == 1 and ops[0][0] == "idxmem" and ops[0][2] in ("+0",):
        enc.emit(IDX_PREFIX[ops[0][1]], 0xE9)
        return bytes(enc.out)
    if mnem == "JP" and len(ops) == 1 and ops[0][0] == "rp" and ops[0][1] in IDX_PREFIX:
        # "JP (IX)" は classify で idxmem になるはずだが、"JP IX" 形の誤記は拒否
        raise AsmError("JP は (IX)/(IY) の括弧付きで書く")

    if mnem in ("JP", "CALL"):
        if len(ops) == 2 and cc_value(ops[0]) in CC_INDEX:
            cc = CC_INDEX[cc_value(ops[0])]
            target = split_operands(operand_text)[1]
            base = 0xC2 if mnem == "JP" else 0xC4
            enc.emit(base + cc * 8)
            enc.emit_word(enc.word_val(target))
            return bytes(enc.out)
        if len(ops) == 1:
            target = split_operands(operand_text)[0]
            enc.emit(0xC3 if mnem == "JP" else 0xCD)
            enc.emit_word(enc.word_val(target))
            return bytes(enc.out)
        raise AsmError(f"{mnem} のオペランドが不正: {operand_text!r}")

    if mnem == "JR":
        if len(ops) == 2 and cc_value(ops[0]) in CC_JR:
            target = split_operands(operand_text)[1]
            enc.emit(CC_JR[cc_value(ops[0])])
        elif len(ops) == 1:
            target = split_operands(operand_text)[0]
            enc.emit(0x18)
        else:
            raise AsmError(f"JR のオペランドが不正: {operand_text!r}")
        if length_only:
            enc.emit(0x00)
            return bytes(enc.out)
        target_addr = enc.val(target)
        delta = target_addr - (cur_pc + 2)
        if not -128 <= delta <= 127:
            raise AsmError(f"相対ジャンプが届かない: {target!r} (delta={delta})")
        enc.emit(delta & 0xFF)
        return bytes(enc.out)

    if mnem == "DJNZ":
        need(1)
        target = split_operands(operand_text)[0]
        enc.emit(0x10)
        if length_only:
            enc.emit(0x00)
            return bytes(enc.out)
        target_addr = enc.val(target)
        delta = target_addr - (cur_pc + 2)
        if not -128 <= delta <= 127:
            raise AsmError(f"DJNZ が届かない: {target!r} (delta={delta})")
        enc.emit(delta & 0xFF)
        return bytes(enc.out)

    if mnem == "RST":
        need(1)
        text = split_operands(operand_text)[0]
        if length_only:
            enc.emit(0xC7)
            return bytes(enc.out)
        p = enc.val(text)
        if p not in (0x00, 0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38):
            raise AsmError(f"RST の番地が不正: {text!r} = {p:#x}")
        enc.emit(0xC7 + (p // 8) * 8)
        return bytes(enc.out)

    if mnem in ("PUSH", "POP"):
        need(1)
        o = ops[0]
        if o[0] == "rp" and o[1] in IDX_PREFIX:
            enc.emit(IDX_PREFIX[o[1]], 0xE5 if mnem == "PUSH" else 0xE1)
            return bytes(enc.out)
        if o[0] == "rp" and o[1] in RP2_INDEX:
            base = 0xC5 if mnem == "PUSH" else 0xC1
            enc.emit(base + RP2_INDEX[o[1]] * 16)
            return bytes(enc.out)
        raise AsmError(f"{mnem} のオペランドが不正: {operand_text!r}")

    if mnem in ("INC", "DEC"):
        need(1)
        o = ops[0]
        slot = r8_slot(o)
        if slot is not None:
            idx, prefix, disp = slot
            base = 0x04 if mnem == "INC" else 0x05
            if prefix:
                enc.emit(IDX_PREFIX[prefix])
                enc.emit(base + idx * 8)
                enc.emit(enc.disp_val(disp))
            else:
                enc.emit(base + idx * 8)
            return bytes(enc.out)
        if o[0] == "rp":
            if o[1] in IDX_PREFIX:
                enc.emit(IDX_PREFIX[o[1]])
                enc.emit((0x03 if mnem == "INC" else 0x0B) + 2 * 16)
                return bytes(enc.out)
            if o[1] in RP_INDEX:
                base = 0x03 if mnem == "INC" else 0x0B
                enc.emit(base + RP_INDEX[o[1]] * 16)
                return bytes(enc.out)
        raise AsmError(f"{mnem} のオペランドが不正: {operand_text!r}")

    if mnem in ("ADD", "ADC", "SBC") and len(ops) == 2 and ops[0][0] == "rp":
        # 16bit系: ADD HL,ss / ADC HL,ss / SBC HL,ss / ADD IX,pp / ADD IY,rr
        dst, src = ops
        raw_src = split_operands(operand_text)[1]
        if dst[1] == "HL" and src[0] == "rp" and src[1] in RP_INDEX:
            rp = RP_INDEX[src[1]]
            if mnem == "ADD":
                enc.emit(0x09 + rp * 16)
            elif mnem == "ADC":
                enc.emit(0xED, 0x4A + rp * 16)
            else:
                enc.emit(0xED, 0x42 + rp * 16)
            return bytes(enc.out)
        if dst[1] in IDX_PREFIX and mnem == "ADD" and src[0] == "rp":
            same = dst[1]
            allowed = {"BC": 0, "DE": 1, same: 2, "SP": 3}
            if src[1] not in allowed:
                raise AsmError(f"ADD {same},{src[1]} は不正な組み合わせ")
            enc.emit(IDX_PREFIX[same])
            enc.emit(0x09 + allowed[src[1]] * 16)
            return bytes(enc.out)
        raise AsmError(f"{mnem} のオペランドが不正: {operand_text!r}")

    if mnem in ALU_INDEX:
        raw = split_operands(operand_text)
        if len(raw) == 2:
            a0 = classify(raw[0])
            if not (a0[0] == "r8" and a0[1] == "A"):
                raise AsmError(f"{mnem} の1個目は A のみ許容: {operand_text!r}")
            src_text = raw[1]
        elif len(raw) == 1:
            src_text = raw[0]
        else:
            raise AsmError(f"{mnem} のオペランド個数が不正: {operand_text!r}")
        src = classify(src_text)
        op_idx = ALU_INDEX[mnem]
        slot = r8_slot(src)
        if slot is not None:
            idx, prefix, disp = slot
            if prefix:
                enc.emit(IDX_PREFIX[prefix])
                enc.emit(0x80 + op_idx * 8 + idx)
                enc.emit(enc.disp_val(disp))
            else:
                enc.emit(0x80 + op_idx * 8 + idx)
            return bytes(enc.out)
        # 即値
        enc.emit(0xC6 + op_idx * 8)
        enc.emit(enc.byte_val(src_text, f"{mnem} の即値"))
        return bytes(enc.out)

    if mnem == "IN":
        need(2)
        a, b = ops
        raw = split_operands(operand_text)
        if a[0] == "r8" and b[0] == "portc":
            r = R8_INDEX[a[1]]
            enc.emit(0xED, 0x40 + r * 8)
            return bytes(enc.out)
        if a[0] == "r8" and a[1] == "A" and b[0] == "mem":
            enc.emit(0xDB)
            enc.emit(enc.byte_val(b[1], "IN のポート番号"))
            return bytes(enc.out)
        raise AsmError(f"IN のオペランドが不正: {operand_text!r}")

    if mnem == "OUT":
        need(2)
        a, b = ops
        if a[0] == "portc" and b[0] == "r8":
            r = R8_INDEX[b[1]]
            enc.emit(0xED, 0x41 + r * 8)
            return bytes(enc.out)
        if a[0] == "mem" and b[0] == "r8" and b[1] == "A":
            enc.emit(0xD3)
            enc.emit(enc.byte_val(a[1], "OUT のポート番号"))
            return bytes(enc.out)
        raise AsmError(f"OUT のオペランドが不正: {operand_text!r}")

    if mnem in CB_ROT_INDEX:
        need(1)
        slot = r8_slot(ops[0])
        if slot is None:
            raise AsmError(f"{mnem} のオペランドが不正: {operand_text!r}")
        idx, prefix, disp = slot
        opv = CB_ROT_INDEX[mnem]
        if prefix:
            enc.emit(IDX_PREFIX[prefix], 0xCB)
            enc.emit(enc.disp_val(disp))
            enc.emit(opv * 8 + 6)
        else:
            enc.emit(0xCB, opv * 8 + idx)
        return bytes(enc.out)

    if mnem in ("BIT", "SET", "RES"):
        need(2)
        raw = split_operands(operand_text)
        bit_text = raw[0]
        slot = r8_slot(ops[1])
        if slot is None:
            raise AsmError(f"{mnem} の2個目のオペランドが不正: {operand_text!r}")
        idx, prefix, disp = slot
        base = {"BIT": 0x40, "RES": 0x80, "SET": 0xC0}[mnem]
        if length_only:
            b = 0
        else:
            b = enc.val(bit_text)
            if not 0 <= b <= 7:
                raise AsmError(f"{mnem} のビット番号が範囲外: {bit_text!r} = {b}")
        if prefix:
            enc.emit(IDX_PREFIX[prefix], 0xCB)
            enc.emit(enc.disp_val(disp))
            enc.emit(base + b * 8 + 6)
        else:
            enc.emit(0xCB, base + b * 8 + idx)
        return bytes(enc.out)

    if mnem == "LD":
        need(2)
        raw = split_operands(operand_text)
        a, b = ops
        a_text, b_text = raw

        # ---- LD SP,HL / LD SP,IX / LD SP,IY ----
        if a[0] == "rp" and a[1] == "SP" and b[0] == "rp":
            if b[1] == "HL":
                enc.emit(0xF9)
                return bytes(enc.out)
            if b[1] in IDX_PREFIX:
                enc.emit(IDX_PREFIX[b[1]], 0xF9)
                return bytes(enc.out)

        # ---- LD A,I / LD A,R / LD I,A / LD R,A ----
        if a[0] == "r8" and a[1] == "A" and b[0] == "expr" and b_text.strip().upper() in ("I", "R"):
            enc.emit(0xED, 0x57 if b_text.strip().upper() == "I" else 0x5F)
            return bytes(enc.out)
        if b[0] == "r8" and b[1] == "A" and a[0] == "expr" and a_text.strip().upper() in ("I", "R"):
            enc.emit(0xED, 0x47 if a_text.strip().upper() == "I" else 0x4F)
            return bytes(enc.out)

        # ---- LD A,(BC) / LD A,(DE) / LD (BC),A / LD (DE),A ----
        if a[0] == "r8" and a[1] == "A" and b[0] == "memreg" and b[1] in ("BC", "DE"):
            enc.emit(0x0A if b[1] == "BC" else 0x1A)
            return bytes(enc.out)
        if a[0] == "memreg" and a[1] in ("BC", "DE") and b[0] == "r8" and b[1] == "A":
            enc.emit(0x02 if a[1] == "BC" else 0x12)
            return bytes(enc.out)

        # ---- LD (nn),HL / LD HL,(nn) / LD (nn),IX / LD IX,(nn) など ----
        if a[0] == "mem" and b[0] == "rp":
            if b[1] == "HL":
                enc.emit(0x22)
                enc.emit_word(enc.word_val(a[1]))
                return bytes(enc.out)
            if b[1] in IDX_PREFIX:
                enc.emit(IDX_PREFIX[b[1]], 0x22)
                enc.emit_word(enc.word_val(a[1]))
                return bytes(enc.out)
            if b[1] in RP_INDEX:
                enc.emit(0xED, 0x43 + RP_INDEX[b[1]] * 16)
                enc.emit_word(enc.word_val(a[1]))
                return bytes(enc.out)
        if a[0] == "rp" and b[0] == "mem":
            if a[1] == "HL":
                enc.emit(0x2A)
                enc.emit_word(enc.word_val(b[1]))
                return bytes(enc.out)
            if a[1] in IDX_PREFIX:
                enc.emit(IDX_PREFIX[a[1]], 0x2A)
                enc.emit_word(enc.word_val(b[1]))
                return bytes(enc.out)
            if a[1] in RP_INDEX:
                enc.emit(0xED, 0x4B + RP_INDEX[a[1]] * 16)
                enc.emit_word(enc.word_val(b[1]))
                return bytes(enc.out)

        # ---- LD A,(nn) / LD (nn),A ----
        if a[0] == "r8" and a[1] == "A" and b[0] == "mem":
            enc.emit(0x3A)
            enc.emit_word(enc.word_val(b[1]))
            return bytes(enc.out)
        if a[0] == "mem" and b[0] == "r8" and b[1] == "A":
            enc.emit(0x32)
            enc.emit_word(enc.word_val(a[1]))
            return bytes(enc.out)

        # ---- LD rp,nn（IX/IY含む） ----
        if a[0] == "rp" and b[0] == "expr":
            if a[1] in IDX_PREFIX:
                enc.emit(IDX_PREFIX[a[1]], 0x21)
                enc.emit_word(enc.word_val(b_text))
                return bytes(enc.out)
            if a[1] in RP_INDEX:
                enc.emit(0x01 + RP_INDEX[a[1]] * 16)
                enc.emit_word(enc.word_val(b_text))
                return bytes(enc.out)

        # ---- LD (HL),n / LD (IX+d),n / LD (IY+d),n ----
        dst_slot = r8_slot(a)
        if dst_slot is not None and dst_slot[0] == 6 and b[0] == "expr":
            idx, prefix, disp = dst_slot
            if prefix:
                enc.emit(IDX_PREFIX[prefix], 0x36)
                enc.emit(enc.disp_val(disp))
                enc.emit(enc.byte_val(b_text, "LD の即値"))
            else:
                enc.emit(0x36)
                enc.emit(enc.byte_val(b_text, "LD の即値"))
            return bytes(enc.out)

        # ---- LD r,n ----
        dst_slot = r8_slot(a)
        if dst_slot is not None and b[0] == "expr":
            idx, prefix, disp = dst_slot
            if idx == 6 and not prefix:
                pass  # 上で処理済みのはず
            if prefix:
                enc.emit(IDX_PREFIX[prefix])
                enc.emit(0x06 + idx * 8)
                enc.emit(enc.disp_val(disp))
                enc.emit(enc.byte_val(b_text, "LD の即値"))
            else:
                enc.emit(0x06 + idx * 8)
                enc.emit(enc.byte_val(b_text, "LD の即値"))
            return bytes(enc.out)

        # ---- LD r,r' （(HL)/(IX+d)/(IY+d) 込み） ----
        dst_slot = r8_slot(a)
        src_slot = r8_slot(b)
        if dst_slot is not None and src_slot is not None:
            didx, dprefix, ddisp = dst_slot
            sidx, sprefix, sdisp = src_slot
            if dprefix and sprefix:
                raise AsmError("LD の両辺を同時に (IX+d)/(IY+d) にはできない")
            if didx == 6 and sidx == 6 and not dprefix and not sprefix:
                raise AsmError("LD (HL),(HL) は不正（HALT を使うこと）")
            prefix = dprefix or sprefix
            disp = ddisp if dprefix else sdisp
            if prefix:
                enc.emit(IDX_PREFIX[prefix])
                enc.emit(0x40 + didx * 8 + sidx)
                enc.emit(enc.disp_val(disp))
            else:
                enc.emit(0x40 + didx * 8 + sidx)
            return bytes(enc.out)

        raise AsmError(f"LD のオペランドが不正: {operand_text!r}")

    raise AsmError(f"未対応の命令: {mnem}")


INSTRUCTION_NAMES = set(FIXED0_NAMES := [
    "NOP", "HALT", "DI", "EI", "RET", "RETI", "RETN", "RLCA", "RLA", "RRCA",
    "RRA", "DAA", "CPL", "SCF", "CCF", "EXX", "NEG", "RRD", "RLD",
    "LDI", "LDIR", "LDD", "LDDR", "CPI", "CPIR", "CPD", "CPDR",
    "INI", "INIR", "IND", "INDR", "OUTI", "OTIR", "OUTD", "OTDR",
]) | {"EX", "IM", "JP", "CALL", "JR", "DJNZ", "RST", "PUSH", "POP",
      "INC", "DEC", "IN", "OUT", "LD"} | set(ALU_INDEX) | set(CB_ROT_INDEX) \
    | {"BIT", "SET", "RES"}


# ==========================================================================
# 行のパース（ラベル・疑似命令・命令）
# ==========================================================================

_LABEL_RE = re.compile(r"^([A-Za-z_.][A-Za-z0-9_.]*):?\s*")
_STMT_SPLIT_RE = re.compile(r"^([A-Za-z_.][A-Za-z0-9_.]*)\s*(.*)$", re.S)


def strip_comment(line):
    out = []
    in_char = False
    for ch in line:
        if in_char:
            out.append(ch)
            if ch == "'":
                in_char = False
            continue
        if ch == "'":
            in_char = True
            out.append(ch)
            continue
        if ch == ";":
            break
        out.append(ch)
    return "".join(out)


class SourceLine:
    __slots__ = ("no", "raw", "label", "mnem", "operand", "kind")

    def __init__(self, no, raw):
        self.no = no
        self.raw = raw
        self.label = None
        self.mnem = None
        self.operand = ""
        self.kind = None   # 'label_only' | 'equ' | 'directive' | 'instr' | 'blank'


DIRECTIVES = {"ORG", "EQU", "DB", "DEFB", "DW", "DEFW", "DS", "DEFS", "INCLUDE"}


def parse_line(no, raw):
    sl = SourceLine(no, raw)
    text = strip_comment(raw).rstrip()
    if text.strip() == "":
        sl.kind = "blank"
        return sl

    rest = text
    # 行頭のラベル（コロン有無どちらも許容）。ただし EQU 行は
    # 「NAME EQU expr」（コロン無し）の形も多いので、先にキーワード全体を
    # 見てから判定する。
    m = re.match(r"^\s*([A-Za-z_.][A-Za-z0-9_.]*)\s*:", rest)
    if m:
        sl.label = m.group(1)
        rest = rest[m.end():]
    else:
        # コロン無しラベル + EQU の形を先読みする
        m2 = re.match(r"^\s*([A-Za-z_.][A-Za-z0-9_.]*)\s+(EQU|equ)\b\s*(.*)$", rest)
        if m2:
            sl.label = m2.group(1)
            sl.mnem = "EQU"
            sl.operand = m2.group(3).strip()
            sl.kind = "equ"
            return sl

    rest = rest.strip()
    if rest == "":
        sl.kind = "label_only"
        return sl

    m = _STMT_SPLIT_RE.match(rest)
    if not m:
        raise AsmError(f"行を解釈できない: {raw!r}", no, raw)
    mnem, operand = m.group(1), m.group(2).strip()
    sl.mnem = mnem.upper()
    sl.operand = operand
    if sl.mnem == "EQU":
        if sl.label is None:
            raise AsmError("EQU にはラベル名が必要", no, raw)
        sl.kind = "equ"
    elif sl.mnem in DIRECTIVES:
        sl.kind = "directive"
    elif sl.mnem in INSTRUCTION_NAMES:
        sl.kind = "instr"
    else:
        raise AsmError(f"未知の命令/疑似命令: {sl.mnem}", no, raw)
    return sl


def parse_db_items(text):
    """db の項目リストを返す。各項目は ('str', bytes) か ('expr', text)。"""
    items = []
    depth = 0
    cur = []
    i = 0
    in_str = False
    while i < len(text):
        ch = text[i]
        if in_str:
            cur.append(ch)
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    tail = "".join(cur).strip()
    if tail or items:
        items.append(tail)
    result = []
    for it in items:
        if len(it) >= 2 and it[0] == '"' and it[-1] == '"':
            result.append(("str", it[1:-1].encode("ascii")))
        else:
            result.append(("expr", it))
    return result


# ==========================================================================
# アセンブラ本体
# ==========================================================================

class Assembler:
    def __init__(self):
        self.labels = {}
        self.equ_expr = {}      # name -> raw expr text（未評価）
        self.equ_line = {}      # name -> 行番号（エラーメッセージ用）
        self.lines = []         # SourceLine のリスト（include 展開済み）
        self.symtab = {}        # labels + equ 解決後
        self.listing = []       # (addr, bytes, raw_line) のリスト

    # ---- ソース読み込み（include展開） ----
    def load(self, path, seen=None):
        path = pathlib.Path(path)
        if seen is None:
            seen = set()
        rp = path.resolve()
        if rp in seen:
            raise AsmError(f"include が循環している: {path}")
        seen = seen | {rp}
        text = path.read_text(encoding="utf-8")
        out = []
        for i, raw in enumerate(text.splitlines(), start=1):
            sl = parse_line(i, raw)
            if sl.kind == "directive" and sl.mnem == "INCLUDE":
                m = re.match(r'^"(.*)"$', sl.operand.strip())
                if not m:
                    raise AsmError("include はファイル名をダブルクォートで囲む",
                                   sl.no, sl.raw)
                inc_path = path.parent / m.group(1)
                out.extend(self.load(inc_path, seen))
            else:
                out.append(sl)
        return out

    # ---- パス1: レイアウト確定 ----
    def pass1(self, lines):
        pc = 0
        for sl in lines:
            if sl.label is not None and sl.kind != "equ":
                if sl.label in self.labels or sl.label in self.equ_expr:
                    raise AsmError(f"ラベル重複: {sl.label}", sl.no, sl.raw)
                self.labels[sl.label] = pc

            if sl.kind in ("blank", "label_only"):
                continue
            if sl.kind == "equ":
                if sl.label in self.labels or sl.label in self.equ_expr:
                    raise AsmError(f"ラベル重複: {sl.label}", sl.no, sl.raw)
                self.equ_expr[sl.label] = sl.operand
                self.equ_line[sl.label] = sl.no
                continue
            if sl.kind == "directive":
                if sl.mnem == "ORG":
                    try:
                        pc = eval_expr(parse_expr(sl.operand), self._early_symtab(), pc)
                    except AsmError as e:
                        raise AsmError(f"org の式を評価できない（前方参照不可）: {e.message}",
                                       sl.no, sl.raw)
                    pc &= 0xFFFF
                    # org 直後の位置を改めてラベルにも反映
                    if sl.label is not None:
                        self.labels[sl.label] = pc
                elif sl.mnem in ("DB", "DEFB"):
                    n = 0
                    for kind, val in parse_db_items(sl.operand):
                        n += len(val) if kind == "str" else 1
                    pc += n
                elif sl.mnem in ("DW", "DEFW"):
                    items = split_operands(sl.operand)
                    pc += 2 * len(items)
                elif sl.mnem in ("DS", "DEFS"):
                    parts = split_operands(sl.operand)
                    if not parts:
                        raise AsmError("ds には件数が必要", sl.no, sl.raw)
                    try:
                        count = eval_expr(parse_expr(parts[0]), self._early_symtab(), pc)
                    except AsmError as e:
                        raise AsmError(f"ds の件数を評価できない（前方参照不可）: {e.message}",
                                       sl.no, sl.raw)
                    pc += count
                continue
            if sl.kind == "instr":
                b = encode_line(sl.mnem, sl.operand, {}, pc, length_only=True)
                pc += len(b)
                continue
        if pc > 0x10000:
            raise AsmError("アドレスが 64KB を超えた")

    def _early_symtab(self):
        """org/ds のためだけの、パス1時点で確定済みのラベルのビュー。"""
        return dict(self.labels)

    # ---- EQU の遅延解決（前方参照・相互参照対応） ----
    def resolve_equs(self):
        resolving = set()
        resolved = {}

        def resolve(name, chain):
            if name in resolved:
                return resolved[name]
            if name in self.labels:
                return self.labels[name]
            if name not in self.equ_expr:
                raise AsmError(f"未定義のシンボル: {name}")
            if name in chain:
                raise AsmError(f"EQU の循環参照: {' -> '.join(list(chain) + [name])}",
                                self.equ_line[name])
            node = parse_expr(self.equ_expr[name])
            refs = set()
            collect_symbol_refs(node, refs)
            for r in refs:
                resolve(r, chain | {name})
            val = eval_expr(node, {**self.labels, **resolved}, 0)
            resolved[name] = val
            return val

        for name in list(self.equ_expr):
            resolve(name, frozenset())
        self.symtab = {**self.labels, **resolved}

    # ---- パス2: 実バイト生成 ----
    def pass2(self, lines):
        pc = 0
        out = bytearray()
        listing = []
        for sl in lines:
            if sl.kind in ("blank", "label_only", "equ"):
                continue
            if sl.kind == "directive":
                start = pc
                if sl.mnem == "ORG":
                    pc = eval_expr(parse_expr(sl.operand), self.symtab, pc) & 0xFFFF
                    # org は前方に飛ぶ場合ギャップを 0 で埋める
                    if pc > len(out):
                        out.extend([0] * (pc - len(out)))
                    elif pc < len(out):
                        raise AsmError("org が既に書いた領域より手前を指している",
                                       sl.no, sl.raw)
                    continue
                if sl.mnem in ("DB", "DEFB"):
                    chunk = bytearray()
                    for kind, val in parse_db_items(sl.operand):
                        if kind == "str":
                            chunk.extend(val)
                        else:
                            v = eval_expr(parse_expr(val), self.symtab, pc)
                            if not -128 <= v <= 255:
                                raise AsmError(f"db の値が範囲外: {val!r} = {v}",
                                               sl.no, sl.raw)
                            chunk.append(v & 0xFF)
                    out.extend(chunk)
                    listing.append((start, bytes(chunk), sl.no, sl.raw))
                    pc += len(chunk)
                    continue
                if sl.mnem in ("DW", "DEFW"):
                    chunk = bytearray()
                    for it in split_operands(sl.operand):
                        v = eval_expr(parse_expr(it), self.symtab, pc) & 0xFFFF
                        chunk.append(v & 0xFF)
                        chunk.append((v >> 8) & 0xFF)
                    out.extend(chunk)
                    listing.append((start, bytes(chunk), sl.no, sl.raw))
                    pc += len(chunk)
                    continue
                if sl.mnem in ("DS", "DEFS"):
                    parts = split_operands(sl.operand)
                    count = eval_expr(parse_expr(parts[0]), self.symtab, pc)
                    fill = 0
                    if len(parts) > 1:
                        fill = eval_expr(parse_expr(parts[1]), self.symtab, pc) & 0xFF
                    chunk = bytes([fill]) * count
                    out.extend(chunk)
                    listing.append((start, chunk, sl.no, sl.raw))
                    pc += count
                    continue
                continue
            if sl.kind == "instr":
                start = pc
                try:
                    b = encode_line(sl.mnem, sl.operand, self.symtab, pc, length_only=False)
                except AsmError as e:
                    raise AsmError(e.message, sl.no, sl.raw)
                out.extend(b)
                listing.append((start, b, sl.no, sl.raw))
                pc += len(b)
                continue
        self.code = bytes(out)
        self.listing = listing

    def assemble(self, path):
        self.lines = self.load(path)
        self.pass1(self.lines)
        self.resolve_equs()
        self.pass2(self.lines)
        return self.code


def format_listing(asm):
    out = []
    for addr, b, no, raw in asm.listing:
        hexb = " ".join(f"{x:02X}" for x in b)
        out.append(f"{addr:04X}  {hexb:<24} {no:5d}  {raw.rstrip()}")
    return "\n".join(out) + ("\n" if out else "")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Z80 テキストアセンブラ（外部依存ゼロ）")
    ap.add_argument("source", help="入力 .asm ファイル")
    ap.add_argument("-o", "--output", required=True, help="出力バイナリ")
    ap.add_argument("--list", help="リストファイル（番地・バイト・元の行）")
    args = ap.parse_args(argv)

    asm = Assembler()
    try:
        code = asm.assemble(args.source)
    except AsmError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    pathlib.Path(args.output).write_bytes(code)
    if args.list:
        pathlib.Path(args.list).write_text(format_listing(asm), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
