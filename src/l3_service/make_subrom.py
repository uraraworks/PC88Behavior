#!/usr/bin/env python3
"""
make_subrom.py — L3 サービスルーチン（自作サブROM / DISK.ROM 相当）を組み立てる

根拠は `docs/spec/l3-subrom.md`（第4版）**だけ**である。公式 ROM も
公式ディスクの内容も一度も参照していない。

  なぜ Python でバイト列を組むのか: `src/l1_ipl/make_ipl_rom.py`（M4）と
  同じ理由。外部依存ゼロで第三者が `python3 make_subrom.py <出力先>` だけで
  同じ ROM を再生成できる。

## このファイルが実装するもの（仕様書 6節・1.10〜1.13節）

- SEND/RECV の1バイト送受信ハンドシェイク（$FC/$FD/$FE/$FF 経由）。
  main 側の手順（1.10節）に **サブ側から見て正しく応答する**こと
  （6節5項。main のコードは自作できないので、mainが期待する外部
  インタフェースとしてここは固定である）。
- 256バイト単位の読み出し要求（固定8バイトヘッダ＋2バイト引数、1.11節）
  の解釈。ヘッダの2バイト引数をどう解釈してどの256バイトを返すかは
  内部実装が自由（5.1節）なので、本実装では byte3=シリンダ、byte4=
  セクタとして扱う（独自解釈。仕様書はこの対応を断定していない）。
- μPD765 相当の FDC（`$FA`=ステータス、`$FB`=データ）を使ったセクタ
  読み出し。**コマンド体系は公開仕様（μPD765/8272データシート）に
  従って自分で書く**。公式ROMと同じFDCコマンド列を出す必要はない
  （仕様書 0節）。

## このファイルが実装しないもの

- 起動時の高速バルクモード（5635件のバースト転送、1.6節・1.10節）。
  仕様書 3節「未確定として残すこと」に明記されているとおり、
  「サブが要求を受けてから最初に応答するまでの遅延・手順」の測定は
  未着手であり、バルクモードの起動条件・トリガーの具体的な手順は
  仕様書に記載が無い。**推測で埋めない**という規律（CLAUDE.md）に
  従い、ここでは実装しない。`tools/verify_l3.sh` の報告を参照。
- 書き込み側（267バイト連続SENDバースト）。仕様書 6節7項により
  本マイルストーンのスコープ外。

## $FA/$FB のポート番号について

サブが FDC とどう通信するかは内部実装なので本来自由（仕様書0節）だが、
**このハーネス（vendor/quasi88-libretro）の FDC デバイスは $FA/$FB に
固定配置されている**（サブ CPU から見えるアドレス空間の物理配置。
GPL の第三者エミュレータ実装 `src/pc88sub.c`・`src/fdc.c` を確認した。
`docs/spec/l3-subrom.md` 2.1節が pio.c を読んだのと同じ扱いで、
公式ROMとは無関係・読むことは規律上の禁止対象外）。ポート番号は
選べないが、**そこに何のバイト列を送るか（コマンド体系）は
公開仕様に従って自分で決めている**。

## $FE/$FF の意味論について

$FF の8種のフェーズコード（0x08-0x0F）と、それが相手側の $FE に
どう見えるかは、仕様書 1.12節（確定した語彙）と 1.10節（手順の型）
から導ける。8255 相当の PIO がビットセット/リセット方式で
ポートCの上位ニブルを操作することは、vendor の `src/pio.c`
（同じく GPL 第三者実装、公式ROM無関係）で確認した一般的な PIO
のふるまいであり、公開されている8255の一般仕様とも一致する。
サブ側の応答値（0x80/0x82/0x12/0x14/0x20/0x21/0x40/0x41）は
仕様書 1.13節に記載されている値をそのまま使う。
"""

import argparse
import pathlib
import sys

# --------------------------------------------------------------------------
# ポート（仕様書 1.4節・1.7〜1.9節・1.12〜1.13節、および上記docstring）
# --------------------------------------------------------------------------

P_FDC_STAT = 0xFA   # IN: FDC メインステータス。bit7=RQM（仕様書1.7節）
P_FDC_DATA = 0xFB   # IN/OUT: FDC データ/コマンド
P_TC       = 0xF8   # IN: FDC へ TC（ターミナルカウント）を送る（vendor src/pc88sub.c）
P_PIO_A    = 0xFC   # sub からは OUT で main の $FD 書き込みが IN で読める（SEND受信）
P_PIO_B    = 0xFD   # sub の OUT がここに出ると main の IN $FC に見える（RECV送信）
P_PIO_C    = 0xFE   # ハンドシェイク状態。IN=相手の状態、OUT=自分の状態（直接書き込み）

RQM  = 0x80   # $FA bit7
DIO  = 0x40   # $FA bit6（1='FDCからホストへ'方向）

# ---- ポートC（$FE/$FF）の実測による訂正 ----
#
# 当初は「CH ニブルの bit0..3 が、相手が読む値の bit4..7 に素直に
# 対応する」と読んでいたが、実際に q88measure で自作 subrom と
# 自作 main ドライバ（tools/make_l3_test_main.py）を組ませて動かすと
# main/sub 双方が起動直後の待ちループから一歩も進まないデッドロックに
# なった。ハーネスの `vendor/quasi88-libretro/src/pio.c`
# `pio_read_C()` を読み直すと、上位ニブルは相手側の **CL**、
# 下位ニブルは相手側の **CH** から来る「たすき掛け」配線だった
# （GPLの第三者実装。公式ROM無関係。読むことは規律上の禁止対象外——
#  仕様書 2.1節が pio.c を読んだのと同じ扱い）。
#
# main は $FF に 0x08-0x0F しか書かない（1.10節）——これは常に
# 自分の CH ビットだけを操作する（CL は触らない）。したがって
# sub が IN $FE で見るのは常に「下位ニブル」側にだけ現れる:
#   main の CH bit3 (0x0F/0x0E) → sub は mask 0x08 で見る
#   main の CH bit0 (0x09/0x08) → sub は mask 0x01 で見る
#   main の CH bit1 (0x0B/0x0A) → sub は mask 0x02 で見る
#   main の CH bit2 (0x0D/0x0C) → sub は mask 0x04 で見る
#
# 同様に、sub が OUT $FE (直接書き込み) で出した1バイトは、main 側では
# ニブルが入れ替わって見える（上位⇔下位）。ここは「相手読みが
# 成立することを確かめてから信用する」（このリポジトリの規律）を
# 実地でやった結果の訂正であり、公式ROMや第三者解析物は一切
# 参照していない——動かして直接測った。
FE_SEND_START = 0x08   # main が OUT $FF,0x0F（クリアで 0x0E）
FE_SEND_DATA  = 0x01   # main が OUT $FF,0x09（クリアで 0x08）
FE_RECV_START = 0x02   # main が OUT $FF,0x0B（クリアで 0x0A）
FE_RECV_ACK   = 0x04   # main が OUT $FF,0x0D（クリアで 0x0C）

# sub 自身の ack（OUT $FE 直接書き込み）。main 側はニブルが入れ替わって
# 見えるので、mask 0x0N を書くと main 側では 0xN0 として観測される
# （tools/make_l3_test_main.py の待ちマスクと対にすること）。
ACK_SEND_START = 0x01   # main 側 mask 0x10
ACK_SEND_DATA  = 0x02   # main 側 mask 0x20
ACK_RECV_START = 0x04   # main 側 mask 0x40
ACK_RECV_ACK   = 0x08   # main 側 mask 0x80

# --------------------------------------------------------------------------
# ごく小さな Z80 アセンブラ（src/l1_ipl/make_ipl_rom.py の Asm を踏襲）
# --------------------------------------------------------------------------


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
            if not 0 <= b <= 0xFF:
                raise ValueError(f"バイト範囲外: {b:#x}")
            self.code.append(b)

    def dw_imm(self, nn):
        self.db(nn & 0xFF, (nn >> 8) & 0xFF)

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

    # ---- 命令 ----
    def di(self):        self.db(0xF3)
    def ei(self):         self.db(0xFB)
    def ret(self):        self.db(0xC9)
    def nop(self):        self.db(0x00)
    def inc_hl(self):     self.db(0x23)
    def dec_b(self):      self.db(0x05)
    def inc_c(self):      self.db(0x0C)
    def ld_a_hl(self):    self.db(0x7E)
    def ld_hl_a(self):    self.db(0x77)
    def ld_a_b(self):     self.db(0x78)
    def ld_a_c(self):     self.db(0x79)
    def ld_b_a(self):     self.db(0x47)
    def ld_c_a(self):     self.db(0x4F)
    def push_af(self):    self.db(0xF5)
    def pop_af(self):     self.db(0xF1)
    def push_bc(self):    self.db(0xC5)
    def pop_bc(self):     self.db(0xC1)
    def push_hl(self):    self.db(0xE5)
    def pop_hl(self):     self.db(0xE1)

    def ld_a(self, n):    self.db(0x3E, n)
    def ld_b(self, n):    self.db(0x06, n)
    def ld_c(self, n):    self.db(0x0E, n)
    def and_a(self, n):   self.db(0xE6, n)
    def or_n(self, n):    self.db(0xF6, n)
    def cp_n(self, n):    self.db(0xFE, n)
    def ld_sp(self, nn):  self.db(0x31, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_imm(self, nn): self.db(0x21, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl(self, name):   self.db(0x21); self._abs(name)
    def call(self, name):    self.db(0xCD); self._abs(name)
    def jp(self, name):      self.db(0xC3); self._abs(name)
    def jr(self, name):      self.db(0x18); self._rel(name)
    def jr_nz(self, name):   self.db(0x20); self._rel(name)
    def jr_z(self, name):    self.db(0x28); self._rel(name)
    def djnz(self, name):    self.db(0x10); self._rel(name)

    def in_port(self, port):
        """IN A,(port)"""
        self.db(0xDB, port)

    def out_a(self, port):
        """OUT (port),A（A の値をそのまま出す。記録はしない——l3は
        OUT列比較の対象ではなく、末端(main の IN $FD)だけが適合条件
        （仕様書5.1節））。"""
        self.db(0xD3, port)

    def out_imm(self, port, value):
        self.ld_a(value)
        self.out_a(port)


# --------------------------------------------------------------------------
# RAM 配置（サブ側は 0x4000-0x7FFF のみ書き込み可。vendor sub_mem_write）
# --------------------------------------------------------------------------

STACK      = 0x6000
SECTOR_BUF = 0x4000    # 256バイトのセクタ読み出しバッファ
REQ_HDR    = 0x4200    # 8バイトの要求ヘッダ（byte0..7）

ROM_SIZE = 0x2000      # DISK.ROM の上限（vendor memory.c: load_rom(...,0x2000,...)）


def build_subrom(break_response=False):
    """break_response: 検証器（tools/verify_l3.sh）をわざと壊すためのフラグ。
    応答256バイトの先頭1バイトを1ビットだけ反転させる。verify_l3.sh の
    「わざと壊して検出できるか確認する」手順で使う。ここで壊す1ビットは
    ROM由来ではなく、自作の応答データに対する自己テスト用の変更。"""
    a = Asm(0x0000)

    # ====================================================================
    # リセットベクタ
    # ====================================================================
    a.di()
    a.ld_sp(STACK)
    # ポートCを「相手側を読む」モードに設定する（vendor src/pio.c
    # pio_set_mode。既定値のままだと IN $FE は自分の書き込みを読み返す
    # だけで、main<->sub のハンドシェイクが成立しない。bit7=モード設定、
    # bit4=Aポート自分読み(既定どおりRead。これを崩すとIN $FCが
    # 自分の書き込みを読み返してしまう——実機で踏んだ罠)、
    # bit3=CH相手読み、bit0=CL相手読み。bit1(Bポート)は既定のWRITEを
    # 維持（触らない=0）。main 側（試験用ドライバ）も起動時に同じ値を
    # 書く（tools/make_l3_test_main.py）。
    a.out_imm(0xFF, 0x99)
    a.call("FDC_SPECIFY")
    a.jp("MAIN_LOOP")

    # ====================================================================
    # ハンドシェイク・プリミティブ（仕様書 1.10・1.12・1.13節）
    # ====================================================================

    # ---- 相手(main)の $FE ビットが立つ/下がるのを待つ ----
    # マスク別に8つの待ちルーチンを用意する（B レジスタ渡しにせず、
    # マスクごとに専用ルーチンにしたほうがコードが単純になる）。
    for name, mask in (
        ("WAIT_SEND_START_SET", FE_SEND_START),
        ("WAIT_SEND_START_CLR", FE_SEND_START),
        ("WAIT_SEND_DATA_SET",  FE_SEND_DATA),
        ("WAIT_SEND_DATA_CLR",  FE_SEND_DATA),
        ("WAIT_RECV_START_SET", FE_RECV_START),
        ("WAIT_RECV_START_CLR", FE_RECV_START),
        ("WAIT_RECV_ACK_SET",   FE_RECV_ACK),
        ("WAIT_RECV_ACK_CLR",   FE_RECV_ACK),
    ):
        a.label(name)
        a.label(name + "_LOOP")
        a.in_port(P_PIO_C)
        a.and_a(mask)
        if name.endswith("_SET"):
            a.jr_z(name + "_LOOP")     # ビットが立つまで待つ
        else:
            a.jr_nz(name + "_LOOP")    # ビットが下がるまで待つ
        a.ret()

    # ---- RECV_BYTE: main が SEND した1バイトを受け取る。結果は A ----
    # 仕様書1.10節 SEND（main視点）の手順そのものに、サブ側から見て
    # 正しく応答する（6節5項）。ack の具体的な値は自作（上のポートC
    # 訂正メモのとおり、実測で確かめた配線に合わせた自前の設計。
    # 5.1節「PIOの内部実装は自由」の範囲内）。
    a.label("RECV_BYTE")
    a.call("WAIT_SEND_START_SET")     # main が 0x0F を書いた
    a.out_imm(P_PIO_C, ACK_SEND_START)
    a.call("WAIT_SEND_START_CLR")     # main が 0x0E を書いた
    a.call("WAIT_SEND_DATA_SET")      # main が $FD に書いてから 0x09
    a.in_port(P_PIO_A)                # main OUT $FD は sub IN $FC で読める
    a.push_af()
    a.out_imm(P_PIO_C, ACK_SEND_DATA)
    a.call("WAIT_SEND_DATA_CLR")      # main が 0x08 を書いた（サイクル終了）
    a.pop_af()
    a.ret()

    # ---- SEND_BYTE: 1バイトを main へ送る。引数は A ----
    # 仕様書1.10節 RECV（main視点）の手順に、サブ側から見て正しく応答する。
    a.label("SEND_BYTE")
    a.push_af()
    a.call("WAIT_RECV_START_SET")     # main が 0x0B を書いた
    a.pop_af()
    a.out_a(P_PIO_B)                  # sub OUT $FD は main IN $FC で読める
    a.out_imm(P_PIO_C, ACK_RECV_START)
    a.call("WAIT_RECV_START_CLR")     # main が 0x0A を書いた（読み取り済）
    a.call("WAIT_RECV_ACK_SET")       # main が 0x0D を書いた
    a.out_imm(P_PIO_C, ACK_RECV_ACK)
    a.call("WAIT_RECV_ACK_CLR")       # main が 0x0C を書いた（サイクル終了）
    a.ret()

    # ====================================================================
    # FDC（μPD765 相当。$FA=ステータス、$FB=データ。公開仕様に基づく実装）
    # ====================================================================

    # ---- FDC がホストへデータを渡す準備ができるまで待って IN する ----
    a.label("FDC_IN")
    a.label("_fdc_in_wait")
    a.in_port(P_FDC_STAT)
    a.and_a(RQM | DIO)
    a.cp_n(RQM | DIO)
    a.jr_nz("_fdc_in_wait")
    a.in_port(P_FDC_DATA)
    a.ret()

    # ---- ホストから FDC へ1バイト送る（コマンド/パラメータ共通） ----
    a.label("FDC_OUT")               # 引数: A = 送る値
    a.push_af()
    a.label("_fdc_out_wait")
    a.in_port(P_FDC_STAT)
    a.and_a(RQM | DIO)
    a.cp_n(RQM)
    a.jr_nz("_fdc_out_wait")
    a.pop_af()
    a.out_a(P_FDC_DATA)
    a.ret()

    # ---- SPECIFY（起動時に1回。SRT/HUT/HLT の値は公開仕様のパラメータで、
    #      ROM由来ではない。タイミング固定値は自由に選べる） ----
    a.label("FDC_SPECIFY")
    a.ld_a(0x03); a.call("FDC_OUT")     # コマンド: SPECIFY
    a.ld_a(0xDF); a.call("FDC_OUT")     # SRT/HUT
    a.ld_a(0x02); a.call("FDC_OUT")     # HLT/ND
    a.ret()

    # ---- SENSE INTERRUPT STATUS（結果2バイトは読み捨てる） ----
    a.label("FDC_SENSE_INT")
    a.ld_a(0x08); a.call("FDC_OUT")
    a.call("FDC_IN")   # r0
    a.call("FDC_IN")   # r1
    a.ret()

    # ---- RECALIBRATE（ドライブ0をトラック0へ）----
    a.label("FDC_RECALIBRATE")
    a.ld_a(0x07); a.call("FDC_OUT")     # コマンド: RECALIBRATE
    a.ld_a(0x00); a.call("FDC_OUT")     # unit=0, head=0
    a.call("FDC_SENSE_INT")
    a.ret()

    # ---- SEEK（引数: A=目的シリンダ） ----
    a.label("FDC_SEEK")
    a.push_af()
    a.ld_a(0x0F); a.call("FDC_OUT")     # コマンド: SEEK
    a.ld_a(0x00); a.call("FDC_OUT")     # unit=0, head=0
    a.pop_af();  a.call("FDC_OUT")      # 目的シリンダ
    a.call("FDC_SENSE_INT")
    a.ret()

    # ---- READ DATA 1セクタ（256バイト固定・N=1）。
    #      引数: (REQ_C)=シリンダ, (REQ_R)=セクタ番号。
    #      結果は SECTOR_BUF の256バイトに入る。 ----
    a.label("FDC_READ_SECTOR")
    # コマンド: READ DATA。MF(bit6)=1 必須——このハーネスの FDC は
    # sec_buf.density(セクタのID部の密度)と command.MF の一致を見る
    # （vendor src/fdc.c sector_density_mismatch()）。
    # DISK_DENSITY_DOUBLE=0x00（tools/make_l3_testdisk.py の density=0x00
    # 相当）に対しては MF=1（倍密度コマンド）が要る。実測して確かめた
    # （最初 MF=0 で送っていたら Missing Address Mark で毎回失敗した）。
    a.ld_a(0x46); a.call("FDC_OUT")
    a.ld_a(0x00); a.call("FDC_OUT")     # unit=0, head=0
    a.ld_hl_imm(REQ_HDR + 3); a.ld_a_hl(); a.call("FDC_OUT")   # C = シリンダ(byte3)
    a.ld_a(0x00); a.call("FDC_OUT")     # H = 0
    a.ld_hl_imm(REQ_HDR + 4); a.ld_a_hl(); a.call("FDC_OUT")   # R = セクタ(byte4)
    a.ld_a(0x01); a.call("FDC_OUT")     # N = 1 (256バイト/セクタ)
    a.ld_hl_imm(REQ_HDR + 4); a.ld_a_hl(); a.call("FDC_OUT")   # EOT = R（このセクタで終わり）
    a.ld_a(0x2A); a.call("FDC_OUT")     # GPL
    a.ld_a(0xFF); a.call("FDC_OUT")     # DTL（N!=0なので無視される）

    # データ転送: 256バイト（B=0 を DJNZ で 256 回まわす定石）。
    # FDC_IN は A を破壊するので、ループカウンタ(B)・書き込み先(HL)は
    # 呼び出しの前後で自然に保持される（FDC_IN/FDC_OUT は BC/HL に触れない）。
    a.ld_hl_imm(SECTOR_BUF)
    a.ld_b(0x00)
    a.label("_read_loop")
    a.call("FDC_IN")
    a.ld_hl_a()          # (HL) <- A
    a.inc_hl()
    a.djnz("_read_loop")

    a.in_port(P_TC)                     # TC を送ってセクタ転送を終える
    # 結果フェーズ（ST0,ST1,ST2,C,H,R,N の7バイト）は読み捨てる
    for _ in range(7):
        a.call("FDC_IN")
    a.ret()

    # ====================================================================
    # メインループ（仕様書 1.11節: 固定8バイトヘッダの読み出し要求）
    #
    #   02 01 00 <b3> <b4> 06 12 60
    #
    # byte0/1/2/5/6/7 は全件で固定（1.11節）。本実装はこれらを検査せず
    # 読み飛ばす——固定値チェックの有無は「mainが受け取るデータ列」
    # （適合条件、5.1節）に影響しないため、内部実装として単純な方を選ぶ。
    # byte3/byte4 をシリンダ・セクタとして扱う（独自解釈、6節6項）。
    # ====================================================================
    a.label("MAIN_LOOP")
    a.call("FDC_RECALIBRATE")
    a.label("REQ_LOOP")
    # 8バイトのヘッダを RECV で受け取り、REQ_HDR に順に格納する
    a.ld_hl_imm(REQ_HDR)
    a.ld_b(8)
    a.label("_hdr_loop")
    a.call("RECV_BYTE")
    a.ld_hl_a()
    a.inc_hl()
    a.djnz("_hdr_loop")

    # シリンダへシーク
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.call("FDC_SEEK")

    # セクタを読み出し、256バイトを SEND で送り返す
    a.call("FDC_READ_SECTOR")
    if break_response:
        a.ld_hl_imm(SECTOR_BUF)
        a.ld_a_hl()
        a.db(0xEE, 0x01)          # XOR A,0x01（先頭1バイトを1ビット反転）
        a.ld_hl_a()
    a.ld_hl_imm(SECTOR_BUF)
    a.ld_b(0x00)
    a.label("_resp_loop")
    a.ld_a_hl()
    a.call("SEND_BYTE")
    a.inc_hl()
    a.djnz("_resp_loop")

    a.jr("REQ_LOOP")

    return a


def build(break_response=False):
    a = build_subrom(break_response=break_response)
    a.resolve()
    code = bytes(a.code)
    if len(code) > ROM_SIZE:
        raise SystemExit(f"ROM に収まらない: {len(code)} > {ROM_SIZE}")
    rom = bytearray([0x00] * ROM_SIZE)
    rom[: len(code)] = code
    return rom, len(code)


def main():
    ap = argparse.ArgumentParser(
        description="L3 サブROム（DISK.ROM相当）を組み立てる（docs/spec/l3-subrom.md）")
    ap.add_argument("outdir")
    ap.add_argument("--break-response", action="store_true",
                     help="検証器をわざと壊すためのフラグ（tools/verify_l3.sh 用）。"
                          "応答256バイトの先頭を1ビット反転させる。")
    args = ap.parse_args()
    rom, used = build(break_response=args.break_response)
    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "DISK.ROM").write_bytes(rom)
    print(f"生成した: {d/'DISK.ROM'} ({ROM_SIZE} bytes, コード {used} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
