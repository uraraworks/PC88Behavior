#!/usr/bin/env python3
"""
make_ipl_rom.py — L1 IPL（起動時のハードウェア初期化）の N88.ROM を組み立てる

根拠は `docs/spec/l1-ipl.md` **だけ**である。測定ログ（`measurements/`）も
公式 ROM も参照していない。仕様書 付録A の初期化区間 350 件と第3節の定常状態
7 件を、このファイルに `SPEC_INIT` / `SPEC_STEADY` として転記してある。

  なぜ Python でバイト列を組むのか:
  この環境に Z80 アセンブラが無い。外部依存ゼロなら第三者が
  `python3 make_ipl_rom.py <出力先>` だけで同じ ROM を再生成できる。
  出自の主張が「信じてくれ」ではなく再現性で立つ。

  ここで出力するバイト列はすべて自分で書いたものである。
  公式 ROM のバイト列は一切含まない。

## 二重の検査

1. **組み立て時**: OUT を出すヘルパが「出す予定の OUT 列」を同時に記録し、
   ROM を書き出す前に `SPEC_INIT` と一致することを検査する。ループや
   サブルーチンに畳んだ箇所も、畳んだ回数ぶん記録される。
   ここが落ちれば ROM は書き出されない。
2. **実行時**: `q88measure --io-log` で実際に走らせ、`tools/cmp_io.py` で
   基準と比較する（仕様書 第7節）。

1 だけでは「そう出すつもりのコードを書いた」ことしか言えない。
2 まで通って初めて「実際にそう出た」になる。

## 構造にした箇所と、していない箇所

意味が読めている箇所（パレット、USART 初期化、CRTC/DMA、拡張 ROM スキャン、
キースキャン）はループ・サブルーチンにした。**意味が読めていない箇所**
——特にポート 32/71 の 4th ROM バンク切り替えが延々と続く区間——は、
`out_range()` で付録A の該当範囲をそのまま並べている。
公式版はその切り替えの間に 4th ROM 内のルーチンを呼んでいるはずだが、
自作 IPL には呼ぶ相手が居ない。**分かったふりをせず、範囲参照のまま残す。**

## メモリ配置について

番地は自由である（仕様書 第0節 / `docs/PLAN.md` ゴール A）。
公式 ROM がどの番地に何を置いているかは知らないし、合わせる必要も無い。
"""

import argparse
import pathlib
import sys

# --------------------------------------------------------------------------
# 仕様書からの転記（docs/spec/l1-ipl.md 付録A）
# --------------------------------------------------------------------------

# 初期化区間の OUT 列 350 件。発生順。番号は付録A の行番号に対応する。
SPEC_INIT = [
    (0x53,0xFF), (0x32,0xA8), (0x54,0x80), (0x54,0xC0), (0x54,0x00), (0x54,0x40),  # 1-6
    (0x55,0x07), (0x55,0x40), (0x56,0x37), (0x56,0x40), (0x57,0x3F), (0x57,0x40),  # 7-12
    (0x58,0x00), (0x58,0x47), (0x59,0x07), (0x59,0x47), (0x5A,0x37), (0x5A,0x47),  # 13-18
    (0x5B,0x3F), (0x5B,0x47), (0x32,0xA9), (0x71,0xFF), (0xE6,0x00), (0x30,0x22),  # 19-24
    (0x40,0x11), (0x31,0x00), (0xEB,0x00), (0x31,0x00), (0x30,0x23), (0x40,0x19),  # 25-30
    (0x51,0x00), (0x68,0xA0), (0x64,0xC8), (0x64,0xF3), (0x65,0x5F), (0x65,0x89),  # 31-36
    (0x50,0xCE), (0x50,0x93), (0x50,0x73), (0x50,0x38), (0x50,0x13), (0x51,0x43),  # 37-42
    (0x68,0xE4), (0x51,0x20), (0x40,0x11), (0x31,0x00), (0x30,0x23), (0x40,0x19),  # 43-48
    (0x51,0x00), (0x68,0xA0), (0x64,0xC8), (0x64,0xF3), (0x65,0x5F), (0x65,0x89),  # 49-54
    (0x50,0xCE), (0x50,0x93), (0x50,0x73), (0x50,0x38), (0x50,0x13), (0x51,0x43),  # 55-60
    (0x68,0xE4), (0x51,0x20), (0x40,0x11), (0xC1,0x00), (0xC3,0x00), (0xC1,0x00),  # 61-66
    (0xC3,0x00), (0xC1,0x00), (0xC3,0x00), (0xC1,0x40), (0xC3,0x40), (0xC1,0x4E),  # 67-72
    (0xC3,0x4E), (0xC1,0x10), (0xC3,0x10), (0xC8,0xFF), (0xCA,0xFF), (0xE4,0xFF),  # 73-78
    (0x32,0xA9), (0x71,0xFF), (0x71,0xFE), (0x32,0xA9), (0x54,0x00), (0x54,0x40),  # 79-84
    (0x55,0x07), (0x55,0x40), (0x56,0x38), (0x56,0x40), (0x57,0x3F), (0x57,0x40),  # 85-90
    (0x58,0x00), (0x58,0x47), (0x59,0x07), (0x59,0x47), (0x5A,0x38), (0x5A,0x47),  # 91-96
    (0x5B,0x3F), (0x5B,0x47), (0x54,0x80), (0x54,0xC0), (0x53,0x00), (0x5C,0x00),  # 97-102
    (0x5F,0x00), (0x5D,0x00), (0x5F,0x00), (0x5E,0x00), (0x5F,0x00), (0x32,0xA8),  # 103-108
    (0x71,0xFE), (0x32,0xA9), (0x71,0xFE), (0x31,0x19), (0x40,0x01), (0x31,0x19),  # 109-114
    (0x53,0xF0), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0xE6,0x02), (0x32,0xAA),  # 115-120
    (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0xE6,0x03), (0x32,0xAA), (0x71,0xFE),  # 121-126
    (0x32,0xA9), (0x71,0xFF), (0x31,0x19), (0xE4,0x02), (0xE4,0xFF), (0x31,0x19),  # 127-132
    (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0xE6,0x03), (0x32,0xAA),  # 133-138
    (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFE),  # 139-144
    (0x32,0xA8), (0x71,0xFE), (0x32,0xA9), (0x71,0xFE), (0x71,0xFF), (0x32,0xA9),  # 145-150
    (0x71,0xFF), (0x31,0x19), (0xE4,0x02), (0xF8,0x00), (0xF8,0x00), (0xE6,0x02),  # 151-156
    (0xE4,0xFF), (0x31,0x19), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF),  # 157-162
    (0x31,0x19), (0xE4,0x01), (0x51,0x80), (0x50,0x00), (0x50,0x00), (0xE4,0xFF),  # 163-168
    (0x31,0x19), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x71,0xFD),  # 169-174
    (0x71,0xFF), (0x71,0xFB), (0x71,0xFF), (0x71,0xF7), (0x71,0xFF), (0x71,0xEF),  # 175-180
    (0x71,0xFF), (0x71,0xDF), (0x71,0xFF), (0x71,0xBF), (0x71,0xFF), (0x71,0x7F),  # 181-186
    (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF),  # 187-192
    (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9),  # 193-198
    (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE),  # 199-204
    (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA),  # 205-210
    (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF),  # 211-216
    (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF),  # 217-222
    (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9),  # 223-228
    (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF),  # 229-234
    (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9),  # 235-240
    (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE),  # 241-246
    (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA),  # 247-252
    (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF),  # 253-258
    (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF),  # 259-264
    (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9),  # 265-270
    (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF),  # 271-276
    (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9),  # 277-282
    (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE),  # 283-288
    (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA),  # 289-294
    (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF),  # 295-300
    (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF),  # 301-306
    (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xA9),  # 307-312
    (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9), (0x71,0xFF),  # 313-318
    (0x31,0x19), (0xE4,0x01), (0x51,0x80), (0x50,0x12), (0x50,0x01), (0xE4,0xFF),  # 319-324
    (0x31,0x19), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE),  # 325-330
    (0x32,0xA9), (0x71,0xFF), (0x32,0xA9), (0x71,0xFF), (0x71,0xFF), (0x32,0xAA),  # 331-336
    (0x71,0xFE), (0x32,0xA9), (0x71,0xFF), (0x32,0xAA), (0x71,0xFE), (0x32,0xA9),  # 337-342
    (0x71,0xFF), (0x31,0x19), (0xE4,0x01), (0x51,0x81), (0x50,0x16), (0x50,0x01),  # 343-348
    (0xE4,0xFF), (0x31,0x19),                                                      # 349-350
]

# 定常状態（351 件目以降）。仕様書 第3節・付録A 末尾。
SPEC_STEADY = [
    (0x31,0x19), (0xE4,0x01), (0x51,0x81), (0x50,0x16), (0x50,0x01),
    (0xE4,0xFF), (0x31,0x19),
]

# 付録A の 344-350 が定常状態の 7 件と一致する。つまり初期化本体は 343 件で、
# 定常ループの 1 周目がそのまま 344-350 になる。ここで確かめておく。
assert SPEC_INIT[343:] == SPEC_STEADY, "付録A 末尾7件が定常状態と一致しない"

INIT_BODY = 343   # 定常ループに入るまでに出す OUT の件数

# --------------------------------------------------------------------------
# ROM の形と、意味の分かっているポート
# --------------------------------------------------------------------------

N88_SIZE = 0x8000   # 32KB。0000-7FFF に載る
DISK_SIZE = 0x0800  # サブ CPU 用。ディスクを使わないので止まるだけ
FILL = 0x00

STACK = 0xF000      # メイン RAM。テキスト VRAM (F3C8) より下に置く

P_SYSCTRL1 = 0x30   # OUT: システムコントロール(1) / IN: DIP スイッチ(1)
P_SYSCTRL2 = 0x31   # OUT: システムコントロール(2) / IN: DIP スイッチ(2)
P_MODE     = 0x32   # モード指定・4th ROM バンク（第5c節）
P_STROBE   = 0x40   # IN: bit5 = VRTC（第5a節①）
P_CRTC_DAT = 0x50
P_CRTC_CMD = 0x51
P_DISPMIX  = 0x53   # 画面の重ね合わせ。0=表示する
P_PAL      = 0x54   # 54-5B の 8 スロット
P_GVRAM    = 0x5C   # 5C/5D/5E = GVRAM0/1/2 選択、5F = メイン RAM 選択
P_DMA_ADDR = 0x64   # CH-2（CRTC 用）アドレス
P_DMA_TC   = 0x65   # CH-2 ターミナルカウント
P_DMA_MODE = 0x68
P_EXTROM   = 0x71   # 拡張 ROM バンク。b0-b7 が ROM1〜ROM8
P_USART1   = 0xC1
P_USART2   = 0xC3
P_KANJI_END = 0xEB
P_INTSTAT  = 0xE4
P_INTMASK  = 0xE6

P_KEY_TOP  = 0x0B   # キースキャン。0B から 00 へ降順（第3節・第4b節）
P_KEY_N    = 12

VRTC_BIT   = 0x20   # IN 40 の bit5


# --------------------------------------------------------------------------
# ごく小さな Z80 アセンブラ
# --------------------------------------------------------------------------

class Asm:
    """バイト列とラベルを組み立てつつ、「出す予定の OUT 列」を記録する。"""

    def __init__(self, org=0x0000):
        self.code = bytearray()
        self.org = org
        self.labels = {}
        self.fixups = []
        self.expect = []
        self._sinks = [self.expect]

    # ---- 位置とラベル ----
    @property
    def pc(self):
        return self.org + len(self.code)

    def label(self, name):
        if name in self.labels:
            raise ValueError(f"ラベル重複: {name}")
        self.labels[name] = self.pc

    def db(self, *bs):
        for b in bs:
            if not 0 <= b <= 0xFF:
                raise ValueError(f"バイト範囲外: {b:#x}")
            self.code.append(b)

    def _abs(self, name):
        self.fixups.append((len(self.code), name, "abs"))
        self.db(0x00, 0x00)

    def _rel(self, name):
        self.fixups.append((len(self.code), name, "rel"))
        self.db(0x00)

    def resolve(self):
        for pos, name, kind in self.fixups:
            if name not in self.labels:
                raise ValueError(f"未定義ラベル: {name}")
            addr = self.labels[name]
            if kind == "abs":
                self.code[pos] = addr & 0xFF
                self.code[pos + 1] = (addr >> 8) & 0xFF
            else:
                delta = addr - (self.org + pos + 1)
                if not -128 <= delta <= 127:
                    raise ValueError(f"相対ジャンプが届かない: {name} ({delta})")
                self.code[pos] = delta & 0xFF

    # ---- 記録の付け替え（サブルーチン本体を組むとき用）----
    class _Capture:
        def __init__(self, asm):
            self.asm = asm
            self.taken = []

        def __enter__(self):
            self.asm._sinks.append(self.taken)
            return self

        def __exit__(self, *exc):
            self.asm._sinks.pop()
            return False

    def capture(self):
        return Asm._Capture(self)

    def record(self, port, value):
        self._sinks[-1].append((port, value))

    def record_all(self, pairs):
        self._sinks[-1].extend(pairs)

    # ---- 命令 ----
    def di(self):       self.db(0xF3)
    def ei(self):       self.db(0xFB)
    def ret(self):      self.db(0xC9)
    def reti(self):     self.db(0xED, 0x4D)
    def retn(self):     self.db(0xED, 0x45)
    def inc_hl(self):   self.db(0x23)
    def inc_c(self):    self.db(0x0C)
    def dec_c(self):    self.db(0x0D)
    def ld_a_hl(self):  self.db(0x7E)
    def out_c_a(self):  self.db(0xED, 0x79)
    def in_a_c(self):   self.db(0xED, 0x78)

    def ld_a(self, n):   self.db(0x3E, n)
    def ld_b(self, n):   self.db(0x06, n)
    def ld_c(self, n):   self.db(0x0E, n)
    def and_a(self, n):  self.db(0xE6, n)
    def ld_sp(self, nn): self.db(0x31, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl(self, name):  self.db(0x21); self._abs(name)
    def call(self, name):   self.db(0xCD); self._abs(name)
    def jp(self, name):     self.db(0xC3); self._abs(name)
    def jr(self, name):     self.db(0x18); self._rel(name)
    def jr_nz(self, name):  self.db(0x20); self._rel(name)
    def jr_z(self, name):   self.db(0x28); self._rel(name)
    def djnz(self, name):   self.db(0x10); self._rel(name)

    def in_port(self, port):
        """IN A,(port)。IN は適合条件に入らない（第6節）ので記録しない。"""
        self.db(0xDB, port)

    # ---- OUT（記録つき）----
    def out(self, port, value):
        self.ld_a(value)
        self.db(0xD3, port)
        self.record(port, value)

    def out_seq(self, pairs):
        for port, value in pairs:
            self.out(port, value)

    def out_range(self, lo, hi):
        """付録A の lo 番から hi 番（1始まり・両端含む）をそのまま並べる。

        意味が読めていない区間で使う。範囲を明示することで、
        どこを理解せずに置いたのかが後から分かる。
        """
        self.out_seq(SPEC_INIT[lo - 1:hi])


# --------------------------------------------------------------------------
# サブルーチン
# --------------------------------------------------------------------------

def sub_wait_vrtc(a):
    """VRTC（垂直帰線）の立ち上がり/立ち下がりを待つ。

    仕様書 第5a節①: `IN 40` の bit5 が VRTC。P2 で値が `CC` → `EC` に
    変わるまで読み続けていた待ちの正体。**回数はタイミング依存なので
    適合条件ではない**（第2節 P2 の注記）。
    """
    a.label("WAIT_VRTC_HIGH")
    a.in_port(P_STROBE)
    a.and_a(VRTC_BIT)
    a.jr_z("WAIT_VRTC_HIGH")
    a.ret()

    a.label("WAIT_VRTC_LOW")
    a.in_port(P_STROBE)
    a.and_a(VRTC_BIT)
    a.jr_nz("WAIT_VRTC_LOW")
    a.ret()


def sub_palette(a):
    """HL のテーブルから 54-5B へ 2 バイトずつ書く。

    仕様書 第5c節: アナログ 512 色モード。b7-6 が 00=PR/PB、01=PG。
    P0 と P3 で 3・7 組目だけ値が違う（37 → 38）。**なぜ違うかは
    仕様書でも未解決**なので、テーブルを 2 つ持つ形にして理由を埋めない。
    """
    a.label("PALETTE")
    a.ld_c(P_PAL)
    a.ld_b(8)
    a.label("_pal_loop")
    a.ld_a_hl(); a.out_c_a(); a.inc_hl()      # PR/PB
    a.ld_a_hl(); a.out_c_a(); a.inc_hl()      # PG
    a.inc_c()
    a.djnz("_pal_loop")
    a.ret()


def palette_outs(table):
    """PALETTE が出す OUT 列（16 件）を求める。"""
    return [(P_PAL + i, table[2 * i + k]) for i in range(8) for k in (0, 1)]


def sub_usart(a):
    """C1/C3 に同じ値を 6 組。8251 の初期化手順（仕様書 第5b節）。

    ダミー書き込み 3 回 → 40（内部リセット）→ モード指定 → コマンド。
    ポート名を知る前に採った測定値が 8251 の手順と独立に一致した箇所。
    """
    a.label("USART")
    a.ld_hl("T_USART")
    a.ld_b(6)
    a.label("_usart_loop")
    a.ld_a_hl()
    a.db(0xD3, P_USART1)
    a.db(0xD3, P_USART2)
    a.inc_hl()
    a.djnz("_usart_loop")
    a.ret()


T_USART = (0x00, 0x00, 0x00, 0x40, 0x4E, 0x10)
USART_OUTS = [(p, v) for v in T_USART for p in (P_USART1, P_USART2)]


def sub_screen_init(a):
    """P2 — テキスト画面を DMA で CRTC に流す設定（仕様書 第5a節②）。

    **2 回実行される。理由は仕様書 第8節で未解決のまま。**
    理由を推測せず、サブルーチンにして 2 回呼ぶ形で回数だけ合わせる。
    """
    a.label("SCREEN_INIT")
    a.call("WAIT_VRTC_HIGH")
    a.out_seq([
        (P_SYSCTRL2, 0x00),
        (P_SYSCTRL1, 0x23),
        (P_STROBE,   0x19),
    ])
    a.call("WAIT_VRTC_LOW")
    a.call("WAIT_VRTC_HIGH")
    a.out_seq([
        (P_CRTC_CMD, 0x00),
        (P_DMA_MODE, 0xA0),   # 全チャネル禁止にしてから触る
        (P_DMA_ADDR, 0xC8),   # CH-2 の DMA アドレス F3C8（テキスト VRAM）
        (P_DMA_ADDR, 0xF3),
        (P_DMA_TC,   0x5F),   # ターミナルカウント
        (P_DMA_TC,   0x89),
        (P_CRTC_DAT, 0xCE),   # CRTC パラメータ 5 バイト
        (P_CRTC_DAT, 0x93),
        (P_CRTC_DAT, 0x73),
        (P_CRTC_DAT, 0x38),
        (P_CRTC_DAT, 0x13),
        (P_CRTC_CMD, 0x43),   # CRTC コマンド
        (P_DMA_MODE, 0xE4),   # EN=0100 = CH-2 のみ許可
        (P_CRTC_CMD, 0x20),
    ])
    a.call("WAIT_VRTC_LOW")
    a.call("WAIT_VRTC_HIGH")
    a.out(P_STROBE, 0x11)
    a.ret()


def sub_extrom_scan(a):
    """拡張 ROM スキャン（付録A 174-188）。

    `71` の b0-b7 が ROM1〜ROM8（第5a節）。ビット 1 から 7 まで 0 を
    歩かせ、そのつど FF に戻している。各スロットの有無を見る形に読める。
    b0（FE）は直前のバンク切り替えが触っている。
    テーブル 15 件をそのまま流す。
    """
    a.label("EXTROM_SCAN")
    a.ld_hl("T_EXTROM")
    a.ld_c(P_EXTROM)
    a.ld_b(len(T_EXTROM))
    a.label("_ext_loop")
    a.ld_a_hl()
    a.out_c_a()
    a.inc_hl()
    a.djnz("_ext_loop")
    a.ret()


T_EXTROM = (0xFD, 0xFF, 0xFB, 0xFF, 0xF7, 0xFF, 0xEF, 0xFF,
            0xDF, 0xFF, 0xBF, 0xFF, 0x7F, 0xFF, 0xFF)
EXTROM_OUTS = [(P_EXTROM, v) for v in T_EXTROM]


def sub_group(a):
    """付録A 189-314 で 18 回繰り返される 7 件の組。

    形は「32/71 でバンクを切り替えて戻す」の 2 回ぶんに 71<-FF が 1 つ
    余ったもの。**18 回何をしているのかは分からない。** 公式版は 4th ROM
    内のルーチンを呼んでいるはずだが、自作 IPL には呼ぶ相手が居ない。
    切り替えの列だけを再現する。
    """
    a.label("GROUP")
    a.out_seq([
        (P_MODE, 0xAA), (P_EXTROM, 0xFE),
        (P_MODE, 0xA9), (P_EXTROM, 0xFF),
        (P_MODE, 0xA9), (P_EXTROM, 0xFF),
        (P_EXTROM, 0xFF),
    ])
    a.ret()


GROUP_REPEAT = 18


def sub_keyscan(a):
    """キースキャン。0B から 00 へ降順に 12 ポート（仕様書 第4b節）。

    押されているビットが 0。IN なので適合条件には入らない。
    """
    a.label("KEYSCAN")
    a.ld_c(P_KEY_TOP)
    a.ld_b(P_KEY_N)
    a.label("_key_loop")
    a.in_a_c()
    a.dec_c()
    a.djnz("_key_loop")
    a.ret()


# --------------------------------------------------------------------------
# 本体
# --------------------------------------------------------------------------

def build_n88(stop_after=None):
    """N88.ROM を組み立てる。

    stop_after: 途中段階の ROM を作るための指定（"P0"/"P2"/"P3"/"P4"/None）。
                仕様書 第6節「実装の順序」に従って段階的に比較するために使う。
                指定した段階まで出したら、そこで止まって無限ループに入る。
    """
    a = Asm(0x0000)

    # ---- リセットベクタ ----
    a.di()
    a.ld_sp(STACK)
    a.jp("MAIN")

    # 0038h / 0066h。割り込みは使わない設計だが、飛び込んだときに
    # 暴走しないよう戻れるようにしておく。
    while a.pc < 0x0038:
        a.db(FILL)
    a.ei(); a.reti()
    while a.pc < 0x0066:
        a.db(FILL)
    a.retn()

    # ---- サブルーチン ----
    sub_wait_vrtc(a)
    sub_palette(a)
    sub_usart(a)
    sub_extrom_scan(a)
    sub_keyscan(a)
    with a.capture() as cap:
        sub_screen_init(a)
    screen_outs = list(cap.taken)
    with a.capture() as cap:
        sub_group(a)
    group_outs = list(cap.taken)

    # ---- テーブル ----
    a.label("T_USART");  a.db(*T_USART)
    a.label("T_EXTROM"); a.db(*T_EXTROM)
    # パレット。仕様書 第5c節の表。並びは PR/PB, PG の 2 バイト × 8 スロット。
    T_PAL_P0 = (0x00,0x40, 0x07,0x40, 0x37,0x40, 0x3F,0x40,
                0x00,0x47, 0x07,0x47, 0x37,0x47, 0x3F,0x47)
    T_PAL_P3 = (0x00,0x40, 0x07,0x40, 0x38,0x40, 0x3F,0x40,
                0x00,0x47, 0x07,0x47, 0x38,0x47, 0x3F,0x47)
    a.label("T_PAL_P0"); a.db(*T_PAL_P0)
    a.label("T_PAL_P3"); a.db(*T_PAL_P3)

    # ======================================================================
    a.label("MAIN")

    # ---- P0. リセット直後（付録A 1-22）----
    a.in_port(P_SYSCTRL1)                    # DIP スイッチ(1)
    a.out(P_DISPMIX, 0xFF)                   # 全プレーン非表示（第5a節④）
    a.in_port(P_SYSCTRL2)                    # DIP スイッチ(2)
    a.out(P_MODE, 0xA8)                      # PMODE=1 アナログ512色（第5c節）
    a.out(P_PAL, 0x80)                       # バックグラウンド BR/BB = 0
    a.out(P_PAL, 0xC0)                       # バックグラウンド BG = 0
    a.ld_hl("T_PAL_P0"); a.call("PALETTE")
    a.record_all(palette_outs(T_PAL_P0))
    a.out(P_MODE, 0xA9)                      # 4th ROM バンク 1
    a.out(P_EXTROM, 0xFF)
    a.in_port(P_SYSCTRL1)
    a.in_port(P_SYSCTRL2)
    a.in_port(0x09)                          # キースキャンの1つ（第2節 P0 末尾）
    if stop_after == "P0":
        return _finish(a, 22)

    # ---- P1. 画面初期化の前置き（付録A 23-27。1 回だけ）----
    a.out_seq([
        (P_INTMASK,   0x00),                 # 割り込み全マスク
        (P_SYSCTRL1,  0x22),
        (P_STROBE,    0x11),
        (P_SYSCTRL2,  0x00),
        (P_KANJI_END, 0x00),                 # 漢字 ROM 読み出し終了
    ])

    # ---- P2. 画面初期化（付録A 28-63）。2 回実行する ----
    for _ in range(2):
        a.call("SCREEN_INIT")
        a.record_all(screen_outs)
    if stop_after == "P2":
        return _finish(a, 63)

    # ---- P3. 周辺の初期化とパレット再設定（付録A 64-107）----
    a.call("USART"); a.record_all(USART_OUTS)          # 64-75
    a.out_seq([
        (0xC8, 0xFF),                        # RS-232C ch.1 使用禁止ゲート
        (0xCA, 0xFF),                        # 同 ch.2
        (P_INTSTAT, 0xFF),
    ])
    a.out_range(79, 82)                      # 32/71 の操作。意味は不明
    a.ld_hl("T_PAL_P3"); a.call("PALETTE")   # 83-98
    a.record_all(palette_outs(T_PAL_P3))
    a.out_seq([
        (P_PAL, 0x80), (P_PAL, 0xC0),        # バックグラウンドカラー
        (P_DISPMIX, 0x00),                   # 全プレーン表示
        # GVRAM0/1/2 を順に選んでメイン RAM に戻す（第5c節）
        (P_GVRAM + 0, 0x00), (P_GVRAM + 3, 0x00),
        (P_GVRAM + 1, 0x00), (P_GVRAM + 3, 0x00),
        (P_GVRAM + 2, 0x00), (P_GVRAM + 3, 0x00),
    ])
    if stop_after == "P3":
        return _finish(a, 107)

    # ---- P4. 割り込みの許可（付録A 108-188）----
    # 108-173 は 32/71 のバンク切り替えに割り込み設定が挟まる区間。
    # 切り替えが何を呼んでいるのかが分からないので、範囲参照で置く。
    # 読める部分だけ注記する:
    #   112-115  31<-19 / 40<-01 / 31<-19 / 53<-F0  画面を表示状態にする
    #   119      E6<-02  VRMF（VRTC 割り込み）のみ許可
    #   124,137  E6<-03  RTMF + VRMF
    #   154-155  F8<-00  FDC 制御
    #   165-167  51<-80 / 50<-00 / 50<-00  CRTC カーソル位置
    a.out_range(108, 173)
    a.call("EXTROM_SCAN"); a.record_all(EXTROM_OUTS)   # 174-188
    if stop_after == "P4":
        return _finish(a, 188)

    # ---- 189-314. 7 件 × 18 回 ----
    a.ld_b(GROUP_REPEAT)
    a.label("_group_loop")
    a.db(0xC5)                               # PUSH BC（GROUP は B を壊さないが保険）
    a.call("GROUP")
    a.db(0xC1)                               # POP BC
    a.djnz("_group_loop")
    for _ in range(GROUP_REPEAT):
        a.record_all(group_outs)

    # ---- 315-343. 残りの初期化 ----
    a.out_range(315, 343)

    # ---- 定常状態（付録A 344-350 が 1 周目）----
    # 公式版の周期がどう作られているかは仕様書に無い。
    # 第3節の 20 イベントに `IN 40` が無いので割り込み駆動だと思われるが、
    # **仕様書に書かれていないので推測で割り込みを組まない。**
    # ここでは VRTC の立ち上がりを待って 1 周させる（第5a節①の待ちと同じ形）。
    # 周回数は適合条件ではない（第6節「比較しないもの」）。
    a.label("STEADY")
    a.call("WAIT_VRTC_LOW")
    a.call("WAIT_VRTC_HIGH")
    a.out_seq([
        (P_SYSCTRL2, 0x19),
        (P_INTSTAT,  0x01),
        (P_CRTC_CMD, 0x81),
        (P_CRTC_DAT, 0x16),
        (P_CRTC_DAT, 0x01),
    ])
    a.in_port(P_CRTC_CMD)                    # IN 51 → 10（第3節）
    a.call("KEYSCAN")                        # IN 0B..00
    a.out_seq([
        (P_INTSTAT,  0xFF),
        (P_SYSCTRL2, 0x19),
    ])
    a.jp("STEADY")

    return _finish(a, len(SPEC_INIT))


def _finish(a, n_expected):
    """予定した OUT 列を検査してから ROM イメージを返す。

    ここが落ちたら ROM は書き出さない。**物差しを通らないものを
    作らない**（docs/PLAN.md）。
    """
    a.label("HALT_LOOP")
    a.jr("HALT_LOOP")
    a.resolve()

    want = SPEC_INIT[:n_expected]
    got = a.expect
    if got != want:
        n = min(len(want), len(got))
        i = next((k for k in range(n) if want[k] != got[k]), n)
        raise SystemExit(
            f"組み立て時検査で不一致: {i+1} 件目\n"
            f"  仕様書: {_fmt(want[i] if i < len(want) else None)}\n"
            f"  生成器: {_fmt(got[i] if i < len(got) else None)}\n"
            f"  件数 仕様書={len(want)} 生成器={len(got)}"
        )

    if len(a.code) > N88_SIZE:
        raise SystemExit(f"ROM に収まらない: {len(a.code)} > {N88_SIZE}")

    rom = bytearray([FILL] * N88_SIZE)
    rom[:len(a.code)] = a.code
    return rom, len(a.code), len(got)


def _fmt(p):
    return "(なし)" if p is None else f"OUT {p[0]:02X} <- {p[1]:02X}"


def build_disk():
    """サブ CPU 用。ディスクを使わないので何もせず止まる。

    仕様書 第1節: ディスクを入れない限りサブ CPU は 1 命令も実行しない。
    """
    rom = bytearray([FILL] * DISK_SIZE)
    rom[0x0000:0x0002] = bytes([0x18, 0xFE])   # JR $
    return rom


def main():
    ap = argparse.ArgumentParser(
        description="L1 IPL の N88.ROM を組み立てる（docs/spec/l1-ipl.md 第6節）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", help="ROM を書き出すディレクトリ")
    ap.add_argument("--stop-after", choices=["P0", "P2", "P3", "P4"], default=None,
                    help="途中段階まで出して止める（第6節「実装の順序」の段階比較用）")
    args = ap.parse_args()

    rom, used, n_out = build_n88(args.stop_after)
    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "N88.ROM").write_bytes(rom)
    (d / "DISK.ROM").write_bytes(build_disk())

    stage = args.stop_after or "全段階"
    print(f"生成した: {d/'N88.ROM'} ({N88_SIZE} bytes, コード {used} bytes)")
    print(f"生成した: {d/'DISK.ROM'} ({DISK_SIZE} bytes)")
    print(f"段階: {stage} / 組み立て時検査 OK（OUT {n_out} 件が付録A と一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
