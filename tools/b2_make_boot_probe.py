#!/usr/bin/env python3
"""
b2_make_boot_probe.py — 起動用セクタ (0,0,1) に置く自作の Z80 コードを生成し、媒体を作る

根拠: docs/notes/goal-b-policy-addendum1-boot-sector-2026-10-24.md 第3・4節。
事前登録: docs/notes/b2-boot-sector-handoff-preregistration.md。

ここで出力するバイト列は**すべて自分で書いたもの**で、公式 ROM・公式ディスクとは
何の関係もない。コードは入った直後に次を控える（追補1 第3節 1〜2）:

  AF・BC・DE・HL・IX・IY・SP、割り込みの許可状態（LD A,I の P/V ＝ IFF2）、
  CALL→POP で知った自分の番地、スタックの先頭2バイト（戻り先）
  ＋ 他のセクタに置いた自作の目印が自分の領域の続きに現れるか

控えは**自分のセクタの中**の決まった位置（セクタ先頭 + REC_OFF）に、見出し
'B2P1' つきで書く。

## 追補1 第4節の禁止を構造で守る

読んでよいのは次の3つだけ:
  (1) 自分のセクタ  [B, B+255]
  (2) 目印を調べる範囲  B+256*k+j  (k=1..K, j=0..3)  ←この 4K バイトだけ
  (3) スタック: 入口の SP の先頭2バイト（戻り先）と、自分が積んだ語

これを2段で確かめる（組み立て時に毎回、通らなければファイルを出さない）:
  a. 命令の種類を絞る: 下の `Z80Mini` が実装している命令だけ。メモリを読む形は
     POP / RET / LD r,(IX+d) / LD A,(IY+d) の4種に限られ、(HL)・(BC)・(DE)・(nn)
     で読む命令、LDIR 等のブロック命令、EX (SP),HL は**実装が無く、出てきたら
     例外になる**（組み立てが止まる）。
  b. 実行して読み出し番地を全部記録し、許可範囲に収まることを確かめる。
     コードの制御の流れは読んだ値に依存しない（分岐は読んだ値を比べた結果で
     1命令飛ばすだけで、読む番地は変わらない）ので、目印の置き方を3通り
     （全部合う・全部無い・乱数）変えて**読み出し番地の列が同一**であることも確かめる。
     読み出し許可の範囲外が1つでもあれば組み立てを止める。
  さらに、実行されない命令が紛れていないよう、線形に読んだ命令の先頭が
  実行された命令の先頭の集合に含まれることも確かめる。

## 腕（--arm）

  ret     控えたあと、レジスタ・SP を入口の状態へ戻して RET する
  halt    控えたあと HALT で止まる（割り込みの許可状態はそのまま）
  dihalt  控えたあと DI して HALT で止まる

## アドレスについて（重要）

Z80 には番地を相対で得る命令が無く、CALL のオペランドは絶対番地になる。
そのため生成器は `--load-addr`（セクタ先頭が置かれる番地）を受け取り、その値で
CALL のオペランドを組む。**実際の読み込み先が違えば CALL は別の所へ飛び、控えは
現れない**（抽出器は no_record と報告する）。読み込み先は、事前に RET 敷き詰めの
腕（段階0）の ROM 書き込み範囲と実行番地から**番地として**知る。
控えの「自分の番地」（POP した値）は CALL オペランド由来なので、
**真の番地の独立な出所は書き込み記録の発行元 PC** である（抽出器が三者照合する）。

## 使い方

  b2_make_boot_probe.py --arm ret --load-addr 0xC000 [--entry-offset 0]
      [--marker-layout seq|rev|head1|none]
      [--out-disk X.d88] [--out-sector X.bin] [--out-layout X.json]

故障注入（器具の自己検査専用）:
  --fault-base-off       控える「自分の番地」だけを +1 ずらす
  --fault-swap-order     BC と DE を積む順を入れ替える（控えの BC/DE が入れ替わる）
  --fault-oob-read       目印の1バイトを範囲の外から読む（組み立て時の検査が止める）
  --fault-stack-overread 戻り先の奥を読む（組み立て時の検査が止める）
"""

import argparse
import json
import pathlib
import random
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

SECTOR_SIZE = 256

# ---- 控えの置き場（セクタ先頭からのオフセット） --------------------------------
REC_OFF = 0xDC          # 控え全体の先頭
ANCHOR = 0x80           # IX = セクタ先頭 + ANCHOR。(IX+d) が [先頭, 先頭+255] を過不足なく覆う
MAGIC = b"B2P1"
END_VALUE = 0x5A
K_MARKERS = 8           # 目印を調べるセクタ数
TAG0 = 0x31             # k 番目の目印の4バイト目 = TAG0 + k - 1
MARK_BYTES = (0x42, 0x32, 0x4D)   # 'B' '2' 'M'

# 控えの中のフィールド (offset, length)。ループで積み出す語の順に並べてある。
FIELDS = {
    "magic": (0, 4),
    "P":     (4, 2),    # POP した値 = CALL の直後の番地（自分の番地の自己申告）
    "IY":    (6, 2),
    "IX":    (8, 2),
    "HL":    (10, 2),
    "DE":    (12, 2),
    "BC":    (14, 2),
    "F2":    (16, 1),   # LD A,I の直後の F（bit2 = P/V = IFF2）
    "I":     (17, 1),   # LD A,I で得た I レジスタ
    "F":     (18, 1),
    "A":     (19, 1),
    "SP":    (20, 2),   # 入口の SP（CALL で積まれた戻り先を指す）
    "RET":   (22, 2),   # スタックの先頭2バイト
    "MK":    (24, K_MARKERS),
    "END":   (24 + K_MARKERS, 1),
}
REC_LEN = 24 + K_MARKERS + 1

ARMS = ("ret", "halt", "dihalt")
FAULTS = ("base-off", "swap-order", "oob-read", "stack-overread")
MARKER_LAYOUTS = ("seq", "rev", "head1", "none")


class ProbeBuildError(Exception):
    pass


# ====================================================================
# 最小の Z80 実行器（このコードが使う命令だけ。他は例外 = 静的な語彙の制限）
# ====================================================================

class Unsupported(Exception):
    pass


class AccessViolation(Exception):
    pass


class Z80Mini:
    """生成するコードが使う命令だけを実装した実行器。読み書きの番地を全部記録する。"""

    def __init__(self, mem):
        self.m = bytearray(mem)
        self.pc = 0
        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.ix = self.iy = self.sp = 0
        self.i = 0
        self.iff = 0
        self.reads = []      # (addr, kind)
        self.writes = []     # (addr, value, pc)
        self.fetched = []    # 命令先頭 pc の列
        self.cur_pc = 0
        self.checker = None  # 読み出し許可の判定 (addr,kind,pc)

    # --- レジスタ対 ---
    def hl(self): return (self.h << 8) | self.l
    def set_hl(self, v): v &= 0xFFFF; self.h, self.l = v >> 8, v & 0xFF
    def de(self): return (self.d << 8) | self.e
    def set_de(self, v): v &= 0xFFFF; self.d, self.e = v >> 8, v & 0xFF
    def bc(self): return (self.b << 8) | self.c
    def set_bc(self, v): v &= 0xFFFF; self.b, self.c = v >> 8, v & 0xFF
    def af(self): return (self.a << 8) | self.f
    def set_af(self, v): v &= 0xFFFF; self.a, self.f = v >> 8, v & 0xFF

    # --- メモリ ---
    def rd(self, addr, kind):
        addr &= 0xFFFF
        self.reads.append((addr, kind))
        if self.checker:
            self.checker(addr, kind, self.cur_pc)
        return self.m[addr]

    def wr(self, addr, val):
        addr &= 0xFFFF
        self.writes.append((addr, val & 0xFF, self.cur_pc))
        self.m[addr] = val & 0xFF

    def fetch(self):
        v = self.m[self.pc & 0xFFFF]
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        hi = self.fetch()
        return lo | (hi << 8)

    def push16(self, v):
        self.sp = (self.sp - 1) & 0xFFFF
        self.wr(self.sp, v >> 8)
        self.sp = (self.sp - 1) & 0xFFFF
        self.wr(self.sp, v & 0xFF)

    def pop16(self):
        lo = self.rd(self.sp, "stack")
        self.sp = (self.sp + 1) & 0xFFFF
        hi = self.rd(self.sp, "stack")
        self.sp = (self.sp + 1) & 0xFFFF
        return lo | (hi << 8)

    def _sub_flags(self, a, v):
        r = (a - v) & 0xFF
        self.f = (0x80 if r & 0x80 else 0) | (0x40 if r == 0 else 0) | 0x02 | (0x01 if a < v else 0)
        return r

    def reg_get(self, n):
        return {0: self.b, 1: self.c, 2: self.d, 3: self.e, 4: self.h, 5: self.l, 7: self.a}[n]

    def reg_set(self, n, v):
        v &= 0xFF
        if n == 0: self.b = v
        elif n == 1: self.c = v
        elif n == 2: self.d = v
        elif n == 3: self.e = v
        elif n == 4: self.h = v
        elif n == 5: self.l = v
        elif n == 7: self.a = v
        else: raise Unsupported(f"reg {n}")

    def idx_d(self):
        d = self.fetch()
        return d - 256 if d >= 128 else d

    def step(self):
        """1命令実行。戻り値: 'ret' / 'halt' / None"""
        self.cur_pc = self.pc
        self.fetched.append(self.pc)
        op = self.fetch()
        if op == 0x00: return None
        if op == 0x06: self.b = self.fetch(); return None
        if op == 0x0E: self.c = self.fetch(); return None
        if op == 0x11: self.set_de(self.fetch16()); return None
        if op == 0x21: self.set_hl(self.fetch16()); return None
        if op == 0x3E: self.a = self.fetch(); return None
        if op == 0x5F: self.e = self.a; return None
        if op == 0x90: self.a = self._sub_flags(self.a, self.b); return None
        if op == 0xBB: self._sub_flags(self.a, self.e); return None
        if op == 0xFE: self._sub_flags(self.a, self.fetch()); return None
        if op == 0x71: self.wr(self.hl(), self.c); return None
        if op == 0x72: self.wr(self.hl(), self.d); return None
        if op == 0x73: self.wr(self.hl(), self.e); return None
        if op == 0x23: self.set_hl(self.hl() + 1); return None
        if op == 0x19: self.set_hl(self.hl() + self.de()); return None
        if op == 0x39: self.set_hl(self.hl() + self.sp); return None
        if op in (0x10, 0x18, 0x20):
            d = self.fetch()
            d = d - 256 if d >= 128 else d
            if op == 0x10:
                self.b = (self.b - 1) & 0xFF
                take = self.b != 0
            elif op == 0x18:
                take = True
            else:
                take = not (self.f & 0x40)
            if take:
                self.pc = (self.pc + d) & 0xFFFF
            return None
        if op == 0x76: return "halt"
        if op == 0xF3: self.iff = 0; return None
        if op == 0xC9:
            self.pc = self.pop16()
            return "ret"
        if op == 0xCD:
            t = self.fetch16()
            self.push16(self.pc)
            self.pc = t
            return None
        if op in (0xC5, 0xD5, 0xE5, 0xF5):
            v = {0xC5: self.bc, 0xD5: self.de, 0xE5: self.hl, 0xF5: self.af}[op]()
            self.push16(v)
            return None
        if op in (0xC1, 0xD1, 0xE1, 0xF1):
            v = self.pop16()
            {0xC1: self.set_bc, 0xD1: self.set_de, 0xE1: self.set_hl, 0xF1: self.set_af}[op](v)
            return None
        if op == 0xCB:
            op2 = self.fetch()
            if op2 & 0xC7 == 0xC1:       # SET b,C だけ
                self.c |= 1 << ((op2 >> 3) & 7)
                return None
            raise Unsupported(f"CB {op2:02X}")
        if op == 0xED:
            op2 = self.fetch()
            if op2 == 0x57:              # LD A,I
                self.a = self.i
                self.f = ((self.f & 0x01) | (0x80 if self.a & 0x80 else 0)
                          | (0x40 if self.a == 0 else 0) | (0x04 if self.iff else 0))
                # 未文書化の bit5/bit3 は I の写しにしない（QUASI88 のコアも写さないことを
                # 実測で確かめた。意味のある判定は P/V だけ）
                return None
            raise Unsupported(f"ED {op2:02X}")
        if op in (0xDD, 0xFD):
            ixy = "ix" if op == 0xDD else "iy"
            op2 = self.fetch()
            if op2 == 0xE5:
                self.push16(getattr(self, ixy))
                return None
            if op2 == 0xE1:
                setattr(self, ixy, self.pop16())
                return None
            if op2 == 0x19 and ixy == "iy":
                self.iy = (self.iy + self.de()) & 0xFFFF
                return None
            if op2 == 0x7E and ixy == "iy":
                d = self.idx_d()
                self.a = self.rd(self.iy + d, "iy")
                return None
            if ixy == "ix":
                if op2 == 0x36:
                    d = self.idx_d()
                    n = self.fetch()
                    self.wr(self.ix + d, n)
                    return None
                if (op2 & 0xF8) == 0x70 and op2 != 0x76:
                    d = self.idx_d()
                    self.wr(self.ix + d, self.reg_get(op2 & 7))
                    return None
                if (op2 & 0xC7) == 0x46 and op2 != 0x76:
                    d = self.idx_d()
                    self.reg_set((op2 >> 3) & 7, self.rd(self.ix + d, "ix"))
                    return None
            raise Unsupported(f"{op:02X} {op2:02X}")
        raise Unsupported(f"{op:02X}")


def linear_starts(code):
    """コードを線形に読んだ命令の先頭オフセットの集合（Z80Mini の語彙だけ）。"""
    out = []
    i = 0
    n = len(code)
    while i < n:
        out.append(i)
        op = code[i]
        if op in (0xCB, 0xED):
            ln = 2
        elif op in (0xDD, 0xFD):
            op2 = code[i + 1]
            if op2 in (0xE5, 0xE1, 0x19):
                ln = 2
            elif op2 == 0x36:
                ln = 4
            else:
                ln = 3
        elif op in (0x06, 0x0E, 0x3E, 0xFE, 0x10, 0x18, 0x20):
            ln = 2
        elif op in (0x11, 0x21, 0xCD):
            ln = 3
        else:
            ln = 1
        i += ln
    return out


# ====================================================================
# 命令列の組み立て
# ====================================================================

class Em:
    def __init__(self):
        self.b = bytearray()
        self.labels = {}
        self.fix = []
        self.stores = []    # 控えへの書き込み命令の記録

    def pos(self): return len(self.b)
    def emit(self, *bs): self.b.extend(bs)
    def label(self, n): self.labels[n] = self.pos()

    def jr(self, op, name):
        self.emit(op, 0)
        self.fix.append((self.pos() - 1, name))

    def resolve(self):
        for at, name in self.fix:
            rel = self.labels[name] - (at + 1)
            if not -128 <= rel <= 127:
                raise ProbeBuildError(f"相対分岐が届かない: {name}")
            self.b[at] = rel & 0xFF

    @staticmethod
    def w(v): return v & 0xFF, (v >> 8) & 0xFF


def d_of(rec_field_off):
    d = REC_OFF + rec_field_off - ANCHOR
    if not -128 <= d <= 127:
        raise ProbeBuildError(f"(IX+d) の d が範囲外: {d}")
    return d & 0xFF


def build_code(arm, load_addr, entry_off, faults):
    """コードを組む。戻り値: (code_bytes, info)。code は entry_off 位置に置く前提。"""
    em = Em()
    E = em.emit

    # --- 入口: 入った直後の状態を積んで控える ---
    E(0xF5)                       # PUSH AF
    E(0xED, 0x57)                 # LD A,I
    E(0xF5)                       # PUSH AF  (A=I, F=LD A,I の直後)
    if "swap-order" in faults:
        E(0xD5)                   # PUSH DE   (故障注入: BC と DE を積む順を入れ替える)
        E(0xC5)                   # PUSH BC
    else:
        E(0xC5)                   # PUSH BC
        E(0xD5)                   # PUSH DE
    E(0xE5)                       # PUSH HL
    E(0xDD, 0xE5)                 # PUSH IX
    E(0xFD, 0xE5)                 # PUSH IY
    E(0xCD, 0, 0)                 # CALL here  (オペランドは最後に埋める)
    call_op_at = em.pos() - 2
    here_code_off = em.pos()
    E(0xE1)                       # POP HL      ; HL = here の絶対番地（自分の番地の素）
    shift = 0
    if "base-off" in faults:
        E(0x23)                   # INC HL      (故障注入: 控える値だけ +1。アンカーは下で補正)
        shift = 1
    E(0xE5)                       # PUSH HL     ; 控える用に残す
    k1 = (ANCHOR - entry_off - here_code_off - shift) & 0xFFFF
    E(0x11, *Em.w(k1))            # LD DE,K1
    E(0x19)                       # ADD HL,DE   ; HL = セクタ先頭 + ANCHOR
    E(0xE5)                       # PUSH HL
    E(0xDD, 0xE1)                 # POP IX      ; IX = 先頭 + ANCHOR

    # 見出し
    for j, ch in enumerate(MAGIC):
        em.stores.append({"kind": "fixed", "pc": entry_off + em.pos(), "field": FIELDS["magic"][0] + j})
        E(0xDD, 0x36, d_of(FIELDS["magic"][0] + j), ch)

    # 積んだ語を 8 個、順に控えへ（P, IY, IX, HL, DE, BC, AF(I), AF）
    E(0xDD, 0xE5)                 # PUSH IX
    E(0xE1)                       # POP HL
    E(0x11, *Em.w((REC_OFF + FIELDS["P"][0] - ANCHOR) & 0xFFFF))   # LD DE,..
    E(0x19)                       # ADD HL,DE   ; HL = 控えの P の位置
    E(0x06, 8)                    # LD B,8
    em.label("l1")
    E(0xD1)                       # POP DE
    em.stores.append({"kind": "seq", "pc": entry_off + em.pos(), "first": FIELDS["P"][0], "stride": 2, "count": 8})
    E(0x73)                       # LD (HL),E
    E(0x23)                       # INC HL
    em.stores.append({"kind": "seq", "pc": entry_off + em.pos(), "first": FIELDS["P"][0] + 1, "stride": 2, "count": 8})
    E(0x72)                       # LD (HL),D
    E(0x23)                       # INC HL
    em.jr(0x10, "l1")             # DJNZ l1

    # 入口の SP（8語を取り終えた時点の SP ＝ 入口の SP）
    E(0x21, 0, 0)                 # LD HL,0
    E(0x39)                       # ADD HL,SP
    for j, r in enumerate((5, 4)):          # L, H
        em.stores.append({"kind": "fixed", "pc": entry_off + em.pos(), "field": FIELDS["SP"][0] + j})
        E(0xDD, 0x70 + r, d_of(FIELDS["SP"][0] + j))

    # スタックの先頭2バイト（戻り先）。読んだらすぐ同じ値を積み戻す
    E(0xE1)                       # POP HL
    if "stack-overread" in faults:
        E(0xE1)                   # POP HL (故障注入: 戻り先の奥を読む)
        E(0xE5)                   # PUSH HL
    E(0xE5)                       # PUSH HL
    for j, r in enumerate((5, 4)):
        em.stores.append({"kind": "fixed", "pc": entry_off + em.pos(), "field": FIELDS["RET"][0] + j})
        E(0xDD, 0x70 + r, d_of(FIELDS["RET"][0] + j))

    # 目印の探索
    E(0xDD, 0xE5)                            # PUSH IX
    E(0xFD, 0xE1)                            # POP IY
    E(0x11, 0x00, 0x01)                      # LD DE,0100h
    E(0xFD, 0x19)                            # ADD IY,DE   ; IY = 先頭 + ANCHOR + 256
    E(0xDD, 0xE5)                            # PUSH IX
    E(0xE1)                                  # POP HL
    E(0x11, *Em.w((REC_OFF + FIELDS["MK"][0] - ANCHOR) & 0xFFFF))
    E(0x19)                                  # ADD HL,DE   ; HL = 控えの MK の位置
    E(0x06, K_MARKERS)                       # LD B,K
    em.label("l2")
    E(0x3E, (TAG0 + K_MARKERS) & 0xFF)       # LD A,TAG0+K
    E(0x90)                                  # SUB B       ; A = k 番目のタグ
    E(0x5F)                                  # LD E,A
    E(0x0E, 0x00)                            # LD C,0
    for j in range(3):
        disp = (-128 + j) & 0xFF
        if "oob-read" in faults and j == 2:
            disp = (-128 + 8) & 0xFF         # 故障注入: 範囲の外の1バイトを読む
        E(0xFD, 0x7E, disp)                  # LD A,(IY+d)
        E(0xFE, MARK_BYTES[j])               # CP 'B'/'2'/'M'
        em.jr(0x20, f"s{j}")                 # JR NZ,skip
        E(0xCB, 0xC1 | (j << 3))             # SET j,C
        em.label(f"s{j}")
    E(0xFD, 0x7E, (-125) & 0xFF)             # LD A,(IY-125)
    E(0xBB)                                  # CP E
    em.jr(0x20, "s3")
    E(0xCB, 0xC1 | (3 << 3))                 # SET 3,C
    em.label("s3")
    em.stores.append({"kind": "seq", "pc": entry_off + em.pos(), "first": FIELDS["MK"][0], "stride": 1, "count": K_MARKERS})
    E(0x71)                                  # LD (HL),C
    E(0x23)                                  # INC HL
    E(0x11, 0x00, 0x01)                      # LD DE,0100h
    E(0xFD, 0x19)                            # ADD IY,DE
    em.jr(0x10, "l2")                        # DJNZ l2

    # 終わりの印
    em.stores.append({"kind": "fixed", "pc": entry_off + em.pos(), "field": FIELDS["END"][0]})
    E(0xDD, 0x36, d_of(FIELDS["END"][0]), END_VALUE)

    # --- 腕 ---
    if arm == "ret":
        def ld_r_ix(r, field):
            E(0xDD, 0x46 | (r << 3), d_of(field))     # LD r,(IX+d)
        ld_r_ix(5, FIELDS["IY"][0]); ld_r_ix(4, FIELDS["IY"][0] + 1)   # LD L / LD H
        E(0xE5); E(0xFD, 0xE1)                                         # PUSH HL ; POP IY
        ld_r_ix(5, FIELDS["F"][0]); ld_r_ix(4, FIELDS["A"][0])
        E(0xE5); E(0xF1)                                               # PUSH HL ; POP AF
        ld_r_ix(1, FIELDS["BC"][0]); ld_r_ix(0, FIELDS["BC"][0] + 1)   # LD C / LD B
        ld_r_ix(3, FIELDS["DE"][0]); ld_r_ix(2, FIELDS["DE"][0] + 1)   # LD E / LD D
        ld_r_ix(5, FIELDS["IX"][0]); ld_r_ix(4, FIELDS["IX"][0] + 1)
        E(0xE5)                                                        # PUSH HL (IX の値を積む)
        ld_r_ix(5, FIELDS["HL"][0]); ld_r_ix(4, FIELDS["HL"][0] + 1)
        E(0xDD, 0xE1)                                                  # POP IX
        E(0xC9)                                                        # RET
    elif arm == "halt":
        em.label("h"); E(0x76); em.jr(0x18, "h")
    elif arm == "dihalt":
        E(0xF3); em.label("h"); E(0x76); em.jr(0x18, "h")
    else:
        raise ProbeBuildError(f"腕が不正: {arm}")

    em.resolve()
    call_target = (load_addr + entry_off + here_code_off) & 0xFFFF
    em.b[call_op_at] = call_target & 0xFF
    em.b[call_op_at + 1] = call_target >> 8
    info = {
        "here_sector_off": entry_off + here_code_off,
        "code_len": len(em.b),
        "stores": em.stores,
    }
    return bytes(em.b), info


def assemble_sector(arm, load_addr, entry_off, faults=()):
    """検査なしでセクタを組む（verify の中から呼ぶ）。"""
    faults = tuple(faults)
    for f in faults:
        if f not in FAULTS:
            raise ProbeBuildError(f"故障注入の名前が不正: {f}")
    if arm not in ARMS:
        raise ProbeBuildError(f"腕が不正: {arm}")
    if not 0 <= entry_off <= 64:
        raise ProbeBuildError("entry_off は 0〜64")
    code, info = build_code(arm, load_addr, entry_off, faults)
    if entry_off + len(code) > REC_OFF:
        raise ProbeBuildError(f"コードが控えの位置に届く: {entry_off}+{len(code)} > {REC_OFF:#x}")
    sector = bytearray(SECTOR_SIZE)          # 先頭の NOP 滑り台（0x00）と余りは 0
    sector[entry_off:entry_off + len(code)] = code
    for i in range(REC_OFF, REC_OFF + REC_LEN):
        sector[i] = 0xFF                     # 控えの領域は 0xFF（書かれたかどうかが見える）
    layout = {
        "magic": MAGIC.decode(),
        "arm": arm,
        "faults": list(faults),
        "load_addr": load_addr,
        "entry_off": entry_off,
        "rec_off": REC_OFF,
        "rec_len": REC_LEN,
        "fields": {k: list(v) for k, v in FIELDS.items()},
        "end_value": END_VALUE,
        "k_markers": K_MARKERS,
        "tag0": TAG0,
        "here_sector_off": info["here_sector_off"],
        "code_len": info["code_len"],
        "stores": info["stores"],
    }
    return bytes(sector), layout


# ====================================================================
# 追補1 第4節の禁止の検査（組み立て時）
# ====================================================================

def expected_marker(k):
    return bytes(MARK_BYTES) + bytes([TAG0 + k - 1])


def run_probe_sim(sector, layout, base, fill, seed, regs, iff, i_reg, sp0, ret_addr,
                  marker_overrides=None, start_off=0, check=True, mem_init=None):
    """sector を base に置いて入口から実行する。戻り値: (sim, outcome)。
    fill: 'match'(目印が全部合う) / 'zero' / 'random'。それ以外のメモリは乱数。"""
    rng = random.Random(seed)
    K = layout["k_markers"]
    if mem_init is not None:
        mem = bytearray(mem_init)       # 器具の自己検査: 試験 ROM が作った実際のメモリ像
    else:
        mem = bytearray(rng.randrange(256) for _ in range(65536))
        for k in range(1, K + 1):
            a = base + 256 * k
            if fill == "match":
                mem[a:a + 4] = expected_marker(k)
            elif fill == "zero":
                mem[a:a + 4] = bytes(4)
            # random: そのまま
    if marker_overrides:
        for a, v in marker_overrides.items():
            mem[a] = v
    mem[base:base + SECTOR_SIZE] = sector
    mem[sp0] = ret_addr & 0xFF
    mem[sp0 + 1] = ret_addr >> 8
    sim = Z80Mini(mem)
    sim.pc = base + start_off
    sim.sp = sp0
    sim.set_af(regs["AF"]); sim.set_bc(regs["BC"]); sim.set_de(regs["DE"]); sim.set_hl(regs["HL"])
    sim.ix = regs["IX"]; sim.iy = regs["IY"]
    sim.i = i_reg
    sim.iff = iff

    own_written = set()
    orig_top = (mem[sp0], mem[sp0 + 1])

    def checker(addr, kind, pc):
        # 命令を実行している最中の読み出しの許可判定
        if kind == "ix":
            ok = base <= addr < base + SECTOR_SIZE
        elif kind == "iy":
            ok = any(addr == base + 256 * k + j for k in range(1, K + 1) for j in range(4))
        elif kind == "stack":
            ok = addr in (sp0, sp0 + 1) or addr in own_written
        else:
            ok = False
        if not ok:
            raise AccessViolation(f"許可範囲外の読み出し: {kind} addr={addr:04X} (base={base:04X})")

    if check:
        sim.checker = checker
    outcome = {"ended": None}
    # 書き込みの追跡（スタックの積み込みを own_written へ）
    orig_wr = sim.wr

    def wr(addr, val):
        orig_wr(addr, val)
        a = addr & 0xFFFF
        if a < sp0:
            own_written.add(a)
    sim.wr = wr

    halts = 0
    for _ in range(20000):
        r = sim.step()
        if r == "ret":
            outcome["ended"] = "ret"
            break
        if r == "halt":
            halts += 1
            if halts >= 2:
                outcome["ended"] = "halt"
                break
    else:
        raise ProbeBuildError("実行器が終わらない")
    outcome["orig_top"] = orig_top
    return sim, outcome


def verify_sector(arm, entry_off, faults, bases=(0xC000, 0xB123, 0x9A00)):
    """組み立て時の静的・動的な検査。通らなければ ProbeBuildError。"""
    rng = random.Random(0xB2)
    for base in bases:
        sector, layout = assemble_sector(arm, base, entry_off, faults)
        K = layout["k_markers"]
        regs = {n: rng.randrange(65536) for n in ("AF", "BC", "DE", "HL", "IX", "IY")}
        iff = rng.randrange(2)
        i_reg = rng.randrange(256)
        sp0 = 0xF000
        ret_addr = 0x0123
        reads_ref = None
        executed = set()
        for fill, seed in (("match", 1), ("zero", 2), ("random", 3)):
            try:
                sim, out = run_probe_sim(sector, layout, base, fill, seed, regs, iff, i_reg, sp0, ret_addr,
                                         start_off=0)
            except AccessViolation as e:
                raise ProbeBuildError(f"追補1 第4節の禁止に触れる: {e}")
            except Unsupported as e:
                raise ProbeBuildError(f"許可していない命令: {e}")
            # 実行した命令がセクタの中だけであること
            bad = [p for p in sim.fetched if not base <= p < base + SECTOR_SIZE]
            if bad:
                raise ProbeBuildError(f"自分のセクタの外の命令を実行した: {bad[0]:04X}")
            # 書き込みの許可: 自分のセクタ / スタックの下 / 入口の SP の先頭2バイト（同じ値の積み戻し）
            for addr, val, pc in sim.writes:
                if base <= addr < base + SECTOR_SIZE:
                    continue
                if sp0 - 64 <= addr < sp0:
                    continue
                if addr in (sp0, sp0 + 1):
                    exp = out["orig_top"][addr - sp0]
                    if val != exp:
                        raise ProbeBuildError("入口の SP の先頭2バイトを別の値で書いた")
                    continue
                raise ProbeBuildError(f"許可範囲外への書き込み: {addr:04X}")
            seq = [(a, k) for a, k in sim.reads]
            if reads_ref is None:
                reads_ref = seq
            elif seq != reads_ref:
                raise ProbeBuildError("読み出し番地の列が目印の置き方で変わる（制御が読んだ値に依存している）")
            executed.update(sim.fetched)
            if not faults:
                _functional_check(sim, out, layout, base, fill, regs, iff, i_reg, sp0, ret_addr)
        # 線形に読んだ命令がすべて実行された
        code_start = base + entry_off
        starts = linear_starts(sector[entry_off:entry_off + layout["code_len"]])
        for s in starts:
            if code_start + s not in executed:
                raise ProbeBuildError(f"実行されない命令が紛れている: コード +{s}")
    return True


def _functional_check(sim, out, layout, base, fill, regs, iff, i_reg, sp0, ret_addr):
    """故障注入が無いとき、控えと RET 腕の復元が期待どおりか。"""
    rec = base + layout["rec_off"]
    F = layout["fields"]

    def g(name):
        o, n = F[name]
        return int.from_bytes(bytes(sim.m[rec + o: rec + o + n]), "little")

    if bytes(sim.m[rec:rec + 4]) != MAGIC:
        raise ProbeBuildError("見出しが書かれていない")
    exp = {
        "P": base + layout["here_sector_off"],
        "IY": regs["IY"], "IX": regs["IX"], "HL": regs["HL"], "DE": regs["DE"], "BC": regs["BC"],
        "A": regs["AF"] >> 8, "F": regs["AF"] & 0xFF,
        "I": i_reg, "SP": sp0, "RET": ret_addr, "END": END_VALUE,
    }
    for k, v in exp.items():
        if g(k) != (v & 0xFFFF if F[k][1] == 2 else v & 0xFF):
            raise ProbeBuildError(f"控えの {k} が期待と違う")
    if ((g("F2") >> 2) & 1) != iff:
        raise ProbeBuildError("割り込みの許可状態の控えが期待と違う")
    mk = bytes(sim.m[rec + F["MK"][0]: rec + F["MK"][0] + F["MK"][1]])
    if fill == "match" and mk != bytes([0x0F] * layout["k_markers"]):
        raise ProbeBuildError("目印が全部合う置き方なのに控えが全部 0F でない")
    if fill == "zero" and mk != bytes(layout["k_markers"]):
        raise ProbeBuildError("目印が無い置き方なのに控えが全部 00 でない")
    if layout["arm"] == "ret":
        if out["ended"] != "ret":
            raise ProbeBuildError("RET 腕が RET で終わらない")
        if sim.pc != ret_addr or sim.sp != sp0 + 2:
            raise ProbeBuildError("RET 後の戻り先または SP が合わない")
        if (sim.af(), sim.bc(), sim.de(), sim.hl(), sim.ix, sim.iy) != \
                (regs["AF"], regs["BC"], regs["DE"], regs["HL"], regs["IX"], regs["IY"]):
            raise ProbeBuildError("RET 腕がレジスタを入口の状態へ戻していない")
    else:
        if out["ended"] != "halt":
            raise ProbeBuildError("止まる腕が HALT で終わらない")
        if layout["arm"] == "dihalt" and sim.iff != 0:
            raise ProbeBuildError("dihalt が DI していない")


def build_sector(arm, load_addr, entry_off, faults=()):
    """検査つきでセクタを組む。"""
    verify_sector(arm, entry_off, tuple(faults))
    return assemble_sector(arm, load_addr, entry_off, faults)


# ====================================================================
# 媒体
# ====================================================================

def marker_coords(layout_name):
    if layout_name == "seq":
        return [(0, 0, k + 1) for k in range(1, K_MARKERS + 1)]
    if layout_name == "rev":
        return [(0, 0, 10 - k) for k in range(1, K_MARKERS + 1)]
    if layout_name == "head1":
        return [(0, 1, k) for k in range(1, K_MARKERS + 1)]
    if layout_name == "none":
        return []
    raise ProbeBuildError(f"目印の置き方が不正: {layout_name}")


def sector_content(c, h, r, boot_sector, markers):
    """l3-disk-format 第4節の空のデータディスクの規則 ＋ (0,0,1) の起動用コード ＋ 目印セクタ。
    割り当て表3セクタは 0xFF（位置 74・75 だけ 0xA0）、(18,1,13) は 0x00、他は 0xFF。"""
    if (c, h, r) == (0, 0, 1):
        return boot_sector
    if (c, h, r) in markers:
        return markers[(c, h, r)]
    if (c, h, r) in ((18, 1, 14), (18, 1, 15), (18, 1, 16)):
        t = bytearray([0xFF]) * SECTOR_SIZE
        t[74] = 0xA0
        t[75] = 0xA0
        return bytes(t)
    if (c, h, r) == (18, 1, 13):
        return bytes(SECTOR_SIZE)
    return bytes([0xFF]) * SECTOR_SIZE


def build_disk(sector, marker_layout):
    """2D（40シリンダ・2ヘッド・16セクタ・256バイト）の D88 像。
    ヘッダ・トラック表・セクタIDの書き方は tools/make_m6fc_blank_disk.py と同じ。"""
    from make_l3_testdisk import (DISK_DELETED_FALSE, DISK_DENSITY_DOUBLE, DISK_PROTECT_FALSE,
                                  DISK_TYPE_2D, N_CODE, STATUS_NORMAL)
    markers = {}
    for k, coord in enumerate(marker_coords(marker_layout), start=1):
        markers[coord] = expected_marker(k) + bytes([0xFF]) * (SECTOR_SIZE - 4)
    header = bytearray(32)
    header[26] = DISK_PROTECT_FALSE
    header[27] = DISK_TYPE_2D
    table = bytearray(164 * 4)
    body = bytearray()
    offset = 32 + 164 * 4
    for c in range(40):
        for h in range(2):
            trk = bytearray()
            for r in range(1, 17):
                hdr = bytearray(16)
                hdr[0], hdr[1], hdr[2], hdr[3] = c, h, r, N_CODE
                hdr[4], hdr[5] = 16, 0
                hdr[6] = DISK_DENSITY_DOUBLE
                hdr[7] = DISK_DELETED_FALSE
                hdr[8] = STATUS_NORMAL
                hdr[14], hdr[15] = SECTOR_SIZE & 0xFF, SECTOR_SIZE >> 8
                trk += hdr + sector_content(c, h, r, sector, markers)
            struct.pack_into("<I", table, (c * 2 + h) * 4, offset)
            body += trk
            offset += len(trk)
    struct.pack_into("<I", header, 28, offset)
    return bytes(header) + bytes(table) + bytes(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--load-addr", required=True, type=lambda v: int(v, 0))
    ap.add_argument("--entry-offset", type=lambda v: int(v, 0), default=0)
    ap.add_argument("--marker-layout", choices=MARKER_LAYOUTS, default="seq")
    ap.add_argument("--out-disk", type=pathlib.Path)
    ap.add_argument("--out-sector", type=pathlib.Path)
    ap.add_argument("--out-layout", type=pathlib.Path)
    for f in FAULTS:
        ap.add_argument(f"--fault-{f}", action="store_true")
    args = ap.parse_args()
    faults = tuple(f for f in FAULTS if getattr(args, "fault_" + f.replace("-", "_")))
    if not 0 <= args.load_addr <= 0xFFFF:
        print("エラー: --load-addr は 0〜0xFFFF", file=sys.stderr)
        return 2
    outs = [p for p in (args.out_disk, args.out_sector, args.out_layout) if p]
    for p in outs:
        if p.exists():
            print(f"エラー: 出力先が既に存在する（上書きしない）: {p}", file=sys.stderr)
            return 2
    try:
        sector, layout = build_sector(args.arm, args.load_addr, args.entry_offset, faults)
        disk = build_disk(sector, args.marker_layout) if args.out_disk else None
    except ProbeBuildError as e:
        print(f"NG: {e}", file=sys.stderr)
        return 4
    layout["marker_layout"] = args.marker_layout
    if args.out_sector:
        args.out_sector.parent.mkdir(parents=True, exist_ok=True)
        args.out_sector.write_bytes(sector)
    if args.out_layout:
        args.out_layout.parent.mkdir(parents=True, exist_ok=True)
        args.out_layout.write_text(json.dumps(layout, indent=1, ensure_ascii=False), encoding="utf-8")
    if disk is not None:
        args.out_disk.parent.mkdir(parents=True, exist_ok=True)
        args.out_disk.write_bytes(disk)
    print(f"OK: arm={args.arm} load_addr={args.load_addr:04X} entry_off={args.entry_offset} "
          f"code_len={layout['code_len']} 検査(3箇所×3置き方)合格")
    return 0


if __name__ == "__main__":
    sys.exit(main())
