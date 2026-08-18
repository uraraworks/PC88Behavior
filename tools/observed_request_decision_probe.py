#!/usr/bin/env python3
"""tools/observed_request_decision_probe.py — 要求グループ→応答決定関数
(`_observed_single_by_request`)を、**組み上がったROMバイト列の上で実際に
実行して**検査する（公式環境不要）。

なぜ要るか（第52版・m7ap）: この決定関数は tools/verify_l3.sh では一度も
踏まれない。実際に故障注入で確かめた——表の応答値を1ビット変えても、表の
並び順を逆にしても、verify_l3.sh の出力は1文字も変わらなかった。つまり
「verify_l3.sh が変更前後で同一だった」ことはこの関数について何も証明
しない。ここで独立の検出力を用意する。

やり方: 決定関数が使う命令だけを解釈する極小Z80を持ち、`build_subrom()`が
出力したコード配列そのものを`_observed_single_by_request`から実行する。
SEND_BYTE / SEND_BOOT_SINGLE_TRACKED への CALL、または
`_observed_request_next_9`（フォールバック）への到達で停止し、そのときの
Aレジスタ（応答値）と停止理由（送信ルーチンの種別）を結果とする。

これを、仕様側の参照モデル（OBSERVED_SINGLE_RESPONSE_BY_REQUEST を上から
順に見て最初に一致したものを採る、という定義そのもの）と突き合わせる。
実装（Z80バイト列）と定義（Pythonの表）を両側から突き合わせる形になる。

値について: ここで扱う応答値は自作サブROMが送る値であり、公式ROM・公式
ディスクの内容ではない。表示するのも一致/不一致とケース番号だけにする。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "src", "l3_service"))
import make_subrom as m  # noqa: E402


class MiniZ80:
    """決定関数が使う命令だけを解釈する極小Z80。

    未知のオペコードに当たったら例外にする（黙って読み飛ばさない——
    読み飛ばすと「検出しない検査」になる）。
    """

    STOP_SEND_BYTE = "SEND_BYTE"
    STOP_SEND_TRACKED = "SEND_BOOT_SINGLE_TRACKED"
    STOP_FALLBACK = "_observed_request_next_9"

    def __init__(self, code, labels, ram):
        self.mem = bytearray(0x10000)
        self.mem[: len(code)] = bytes(code)
        for addr, val in ram.items():
            self.mem[addr] = val
        self.labels = labels
        self.stop_at = {labels[n]: n for n in
                        (self.STOP_SEND_BYTE, self.STOP_SEND_TRACKED,
                         self.STOP_FALLBACK)}
        self.a = self.b = self.c = 0
        self.d = self.e = self.h = self.l = 0
        self.zf = False
        self.pc = 0

    # --- レジスタ対 ---
    def _hl(self):
        return (self.h << 8) | self.l

    def _set_hl(self, v):
        v &= 0xFFFF
        self.h, self.l = v >> 8, v & 0xFF

    def _de(self):
        return (self.d << 8) | self.e

    def _set_de(self, v):
        v &= 0xFFFF
        self.d, self.e = v >> 8, v & 0xFF

    def _imm8(self):
        v = self.mem[self.pc]
        self.pc += 1
        return v

    def _imm16(self):
        v = self.mem[self.pc] | (self.mem[self.pc + 1] << 8)
        self.pc += 2
        return v

    def _rel(self):
        d = self.mem[self.pc]
        self.pc += 1
        return self.pc + (d - 256 if d >= 0x80 else d)

    def _cp(self, v):
        self.zf = (self.a == v)

    def run(self, start, max_steps=100000):
        """(停止理由, A) を返す。"""
        self.pc = start
        for _ in range(max_steps):
            if self.pc in self.stop_at:
                return self.stop_at[self.pc], self.a
            op = self.mem[self.pc]
            self.pc += 1
            if op == 0x21:    # LD HL,nn
                self._set_hl(self._imm16())
            elif op == 0x11:  # LD DE,nn
                self._set_de(self._imm16())
            elif op == 0x7E:  # LD A,(HL)
                self.a = self.mem[self._hl()]
            elif op == 0x1A:  # LD A,(DE)
                self.a = self.mem[self._de()]
            elif op == 0x3A:  # LD A,(nn)
                self.a = self.mem[self._imm16()]
            elif op == 0x3E:  # LD A,n
                self.a = self._imm8()
            elif op == 0x4F:  # LD C,A
                self.c = self.a
            elif op == 0x47:  # LD B,A
                self.b = self.a
            elif op == 0x23:  # INC HL
                self._set_hl(self._hl() + 1)
            elif op == 0x13:  # INC DE
                self._set_de(self._de() + 1)
            elif op == 0xB7:  # OR A
                self.zf = (self.a == 0)
            elif op == 0xFE:  # CP n
                self._cp(self._imm8())
            elif op == 0xB9:  # CP C
                self._cp(self.c)
            elif op == 0xBE:  # CP (HL)
                self._cp(self.mem[self._hl()])
            elif op == 0xC3:  # JP nn
                self.pc = self._imm16()
            elif op == 0xCA:  # JP Z,nn
                t = self._imm16()
                if self.zf:
                    self.pc = t
            elif op == 0xC2:  # JP NZ,nn
                t = self._imm16()
                if not self.zf:
                    self.pc = t
            elif op == 0x18:  # JR e
                self.pc = self._rel()
            elif op == 0x28:  # JR Z,e
                t = self._rel()
                if self.zf:
                    self.pc = t
            elif op == 0x20:  # JR NZ,e
                t = self._rel()
                if not self.zf:
                    self.pc = t
            elif op == 0x10:  # DJNZ e
                t = self._rel()
                self.b = (self.b - 1) & 0xFF
                if self.b:
                    self.pc = t
            elif op == 0xCD:  # CALL nn — 送信ルーチン呼び出しで停止する
                t = self._imm16()
                if t in self.stop_at:
                    return self.stop_at[t], self.a
                raise RuntimeError(
                    f"想定外のCALL先 0x{t:04X}（決定関数の構造が変わった）")
            else:
                raise RuntimeError(
                    f"極小Z80が知らないオペコード 0x{op:02X} at 0x{self.pc-1:04X}")
        raise RuntimeError("停止しなかった（無限ループ）")


def reference_model(run_len, hdr_bytes):
    """定義そのもの: 表を上から見て、run_lenと先頭バイト列が一致する最初の
    エントリを採る。無ければフォールバック。
    戻り値は (停止理由, 応答値) で MiniZ80.run と同じ形。"""
    for i, (hdr, resp) in enumerate(m.OBSERVED_SINGLE_RESPONSE_BY_REQUEST):
        if run_len != len(hdr):
            continue
        if all(hdr_bytes[k] == hdr[k] for k in range(len(hdr))):
            tracked = i in m.OBSERVED_SINGLE_TRACKED_ENTRIES
            return (MiniZ80.STOP_SEND_TRACKED if tracked
                    else MiniZ80.STOP_SEND_BYTE), resp
    return MiniZ80.STOP_FALLBACK, None


def run_case(a, run_len, hdr_bytes):
    ram = {m.RUN_LEN: run_len}
    for k, v in enumerate(hdr_bytes):
        ram[m.REQ_HDR + k] = v
    cpu = MiniZ80(a.code, a.labels, ram)
    return cpu.run(a.labels["_observed_single_by_request"])


def compare(a, run_len, hdr_bytes):
    """実装と定義の突き合わせ。一致すればNone、違えば説明文字列を返す。"""
    got = run_case(a, run_len, hdr_bytes)
    want = reference_model(run_len, hdr_bytes)
    if got[0] != want[0]:
        return f"停止理由が違う 実装={got[0]} 定義={want[0]}"
    if want[1] is not None and got[1] != want[1]:
        return "応答値が違う（値は伏せる）"
    return None
