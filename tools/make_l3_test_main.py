#!/usr/bin/env python3
"""
make_l3_test_main.py — L3 自作サブROMを検証するための「試験用 main 側ドライバ」

**これは公式 N88.ROM の代替品ではない。BASIC を一切実装しない。**
`docs/spec/l3-subrom.md` 1.10・1.12・1.13節に記載されている main 側の
SEND/RECV 手順を、そのまま Z80 コードに書き起こしただけの試験治具である。

なぜこれが要るか（tools/verify_l3.sh 参照）:
  公式 ROM を使わずに自作サブROM（`src/l3_service/make_subrom.py`）の
  プロトコル応答を検証したい。公式 main ROM は BASIC の起動処理まで
  含む巨大なコードで、しかも再実装は本マイルストーンの対象外（L4）。
  そこで「仕様書に書かれている SEND/RECV 手順だけを行う、ごく小さい
  試験用 main」を別に用意し、自作サブROMと組ませて q88measure で走らせる。

  これにより、公式 ROM 無しで「自作サブROMは、仕様書どおりの手順を
  踏む相手に対して正しく応答するか」を検証できる（L1 の
  `tools/verify_l1.sh` が公式ROM無しで検証できているのと同じ型）。

やること: 固定した (シリンダ, セクタ) の列について、8バイトヘッダ
（`02 01 00 <cyl> <sec> 06 12 60`。仕様書1.11節）を SEND で送り、
256バイトの応答を RECV で受け取って、その場で捨てて次へ進む。
受け取った値そのものは `--io-log` の main 側 IN $FC 列に残るので、
判定は verify_l3.sh 側（ログを読む）で行う。

## 第6版での訂正（重要）

旧版はここで「ポートCはたすき掛け配線」という理論のもと、main 側からも
`OUT $FE` に直接マスク値を書き込んでいた。これは
`src/l3_service/make_subrom.py`（旧版）と本ファイル（旧版）を組ませて
動かした結果を根拠にしており、**自作サブROMと自作mainドライバが互いの
誤解に合わせて辻褄を合わせていただけ**だった（このファイルの本来の
存在意義——「仕様書どおりの手順を踏む相手」を用意すること——を
自ら破っていた）。

本版は `docs/spec/l3-subrom.md` 1.10節（main視点SEND/RECVの手順）・
1.12節（$FFフェーズコード語彙）・1.13節（main視点の`$FE`待ち遷移表）
**だけ**を根拠に書き直した。main は仕様書どおり `$FF` にフェーズコードを
書き、`$FE` は読むだけで一度も書き込まない。**自作サブROM
（`src/l3_service/make_subrom.py`）の実装に合わせて調整することは
しない**——それは今回の失敗の再生産になる。両者が別々に仕様書だけを
見て書かれ、それでも組んで動く、という一致だけが検証の意味を持つ。
"""

import argparse
import pathlib
import sys

P_PIO_A = 0xFC   # main の IN $FC = sub の OUT $FD（RECV）
P_PIO_B = 0xFD   # main の OUT $FD = sub の IN $FC（SEND）
P_PIO_C = 0xFE

N88_SIZE = 0x8000
DISK_STUB_SIZE = 0x0800
STACK = 0xF000


class Asm:
    def __init__(self, org=0x0000):
        self.code = bytearray()
        self.org = org
        self.labels = {}
        self.fixups = []

    @property
    def pc(self):
        return self.org + len(self.code)

    def label(self, name):
        if name in self.labels:
            raise ValueError(f"ラベル重複: {name}")
        self.labels[name] = self.pc

    def db(self, *bs):
        for b in bs:
            self.code.append(b & 0xFF)

    def _abs(self, name):
        self.fixups.append((len(self.code), name, "abs"))
        self.db(0x00, 0x00)

    def _rel(self, name):
        self.fixups.append((len(self.code), name, "rel"))
        self.db(0x00)

    def resolve(self):
        for pos, name, kind in self.fixups:
            addr = self.labels[name]
            if kind == "abs":
                self.code[pos] = addr & 0xFF
                self.code[pos + 1] = (addr >> 8) & 0xFF
            else:
                delta = addr - (self.org + pos + 1)
                if not -128 <= delta <= 127:
                    raise ValueError(f"相対ジャンプが届かない: {name}")
                self.code[pos] = delta & 0xFF

    def di(self):         self.db(0xF3)
    def ret(self):        self.db(0xC9)
    def inc_hl(self):     self.db(0x23)
    def ld_a_hl(self):    self.db(0x7E)
    def ld_hl_a(self):    self.db(0x77)
    def push_af(self):    self.db(0xF5)
    def pop_af(self):     self.db(0xF1)
    def ld_a(self, n):    self.db(0x3E, n)
    def ld_b(self, n):    self.db(0x06, n)
    def and_a(self, n):   self.db(0xE6, n)
    def cp_n(self, n):    self.db(0xFE, n)
    def ld_sp(self, nn):  self.db(0x31, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_imm(self, nn): self.db(0x21, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl(self, name):   self.db(0x21); self._abs(name)
    def call(self, name):    self.db(0xCD); self._abs(name)
    def jp(self, name):      self.db(0xC3); self._abs(name)
    def jr_nz(self, name):   self.db(0x20); self._rel(name)
    def jr_z(self, name):    self.db(0x28); self._rel(name)
    def djnz(self, name):    self.db(0x10); self._rel(name)

    def in_port(self, port):  self.db(0xDB, port)
    def out_a(self, port):    self.db(0xD3, port)
    def out_imm(self, port, value):
        self.ld_a(value)
        self.out_a(port)


HDR_BUF = 0xF800   # main RAM 上の作業領域（テキストVRAM等と衝突しない番地）


def build(requests):
    """requests: [(cyl, sec), ...] の列。それぞれヘッダを送り256バイト受ける。"""
    a = Asm(0x0000)
    a.di()
    a.ld_sp(STACK)
    a.jp("MAIN")

    # (pio_set_mode 呼び出しは MAIN 冒頭で行う。下記 a.label("MAIN") 参照)

    # ---- $FE 待ち目標値（仕様書1.13節。矢印/`⇄`の右側の値を目標に採用。
    #      make_subrom.py の docstring と同じ選び方——値そのものを変えない
    #      範囲でのポーリングコードの書き方の選択） ----
    #   SEND前（相手の受信準備待ち）: 80⇄82        → 目標 0x82
    #   SEND後（相手の受理確認待ち）: 12⇄14        → 目標 0x14
    #   RECV前（相手のデータ準備待ち）: 20⇄21       → 目標 0x21
    #   RECV後（相手の受理解除待ち）: 40⇄41        → 目標 0x41

    # ---- SEND_MAIN: 1バイト送信（main視点、仕様書1.10節 SEND そのまま） ----
    #   引数: A = 送るバイト
    a.label("SEND_MAIN")
    a.push_af()
    a.out_imm(0xFF, 0x0F)                # OUT FF,0F
    a.label("_send_wait1")
    a.in_port(0xFE)
    a.cp_n(0x82)
    a.jr_nz("_send_wait1")               # 相手の受信準備待ち（→0x82）
    a.out_imm(0xFF, 0x0E)                # OUT FF,0E
    a.pop_af()
    a.out_a(0xFD)                        # OUT FD,<byte>
    a.out_imm(0xFF, 0x09)                # OUT FF,09
    a.label("_send_wait2")
    a.in_port(0xFE)
    a.cp_n(0x14)
    a.jr_nz("_send_wait2")               # 相手の受理確認待ち（→0x14）
    a.out_imm(0xFF, 0x08)                # OUT FF,08
    a.in_port(0xFE)                      # 結果ステータス（単発読み、読み捨て。1.10節どおり待ちループにしない）
    a.ret()

    # ---- RECV_MAIN: 1バイト受信（main視点、仕様書1.10節 RECV そのまま） ----
    #   結果: A = 受け取ったバイト
    a.label("RECV_MAIN")
    a.out_imm(0xFF, 0x0B)                # OUT FF,0B
    a.label("_recv_wait1")
    a.in_port(0xFE)
    a.cp_n(0x21)
    a.jr_nz("_recv_wait1")               # 相手のデータ準備待ち（→0x21）
    a.out_imm(0xFF, 0x0A)                # OUT FF,0A
    a.in_port(0xFC)                      # IN FC = 実データ（sub OUT $FD）
    a.push_af()
    a.out_imm(0xFF, 0x0D)                # OUT FF,0D
    a.label("_recv_wait2")
    a.in_port(0xFE)
    a.cp_n(0x41)
    a.jr_nz("_recv_wait2")               # 相手の受理解除待ち（→0x41）
    a.out_imm(0xFF, 0x0C)                # OUT FF,0C
    a.pop_af()
    a.ret()

    # ---- 要求ヘッダ（仕様書1.11節: 02 01 00 <cyl> <sec> 06 12 60） ----
    hdr_labels = []
    for i, (cyl, sec) in enumerate(requests):
        name = f"HDR_{i}"
        hdr_labels.append(name)
        a.label(name)
        a.db(0x02, 0x01, 0x00, cyl, sec, 0x06, 0x12, 0x60)

    # ---- 本編 ----
    a.label("MAIN")
    # ポートCの明示的なモード設定は行わない（0x99は仕様書に根拠が無い旧版の
    # 値だった。src/l3_service/make_subrom.py のリセットベクタと対称に、
    # ここでも削除した）。
    for name in hdr_labels:
        # ヘッダ8バイトを SEND で送る
        a.ld_hl(name)
        a.ld_b(8)
        a.label(f"_hdrsend_{name}")
        a.ld_a_hl()
        a.call("SEND_MAIN")
        a.inc_hl()
        a.djnz(f"_hdrsend_{name}")

        # 応答256バイトを RECV で受け取る（内容は iolog に残るので破棄でよい）
        a.ld_b(0x00)
        a.label(f"_resprecv_{name}")
        a.call("RECV_MAIN")
        a.djnz(f"_resprecv_{name}")

    a.label("DONE")
    a.db(0x18, 0xFE)   # JR $（その場停止）

    a.resolve()
    return a


def build_disk_stub():
    rom = bytearray([0x00] * DISK_STUB_SIZE)
    rom[0x0000:0x0002] = bytes([0x18, 0xFE])   # JR $（この試験では使わない）
    return rom


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir")
    ap.add_argument("--requests", default="0:1,0:2,3:5",
                     help="cyl:sec のカンマ区切り列（既定: 0:1,0:2,3:5）")
    args = ap.parse_args()

    requests = []
    for tok in args.requests.split(","):
        c, s = tok.split(":")
        requests.append((int(c), int(s)))

    a = build(requests)
    code = bytes(a.code)
    if len(code) > N88_SIZE:
        raise SystemExit(f"ROM に収まらない: {len(code)} > {N88_SIZE}")
    rom = bytearray([0x00] * N88_SIZE)
    rom[: len(code)] = code

    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "N88.ROM").write_bytes(rom)
    print(f"生成した: {d/'N88.ROM'} ({N88_SIZE} bytes, コード {len(code)} bytes)")
    print(f"要求列: {requests}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
