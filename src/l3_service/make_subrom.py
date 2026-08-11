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

## $FE/$FF の意味論について（第6版で全面改訂）

**旧版（第5版まで）の実装は誤りだった。** 以前はここで「ポートCは
たすき掛け配線で、sub 側が `OUT $FE` に直接マスク値を書き込む」という
理論を採用していたが、これは自作サブROM＋自作試験用mainドライバ
（`tools/make_l3_test_main.py`）同士を組ませて動かした結果を根拠にして
おり、**双方が自作である以上「仕様書どおりの相手」を検証したことには
ならなかった**（誤解を共有したまま両者が「動く」ように調整し合って
いた）。公式サブROMを公式環境で実走させた測定（`docs/spec/l3-subrom.md`
1.15節・6節10項）により、**公式subは`$FE`に一度も書き込まない**ことが
確定した。したがって本版では `OUT $FE` を一切行わない。

sub がすることは `OUT $FF` にフェーズコード（1.12節の8値の部分集合）を
書くことだけであり、相手（main）の`$FF`書き込みが`$FE`側にどう映るかは
PIOハードウェアの仕事であって sub 側コードが関与しない。sub は
`IN $FE` で相手の状態を読み、仕様書 1.15節の遷移表に記載された
**到達値**（矢印の右側・`⇄`の右側の値）に達するまで待つ。

具体的な待ちと目標値（1.15節の表をそのまま転記。矢印/`⇄`の右側の値を
「到達したら抜ける」目標値として採用した——これは値そのものを変えない
範囲でのポーリングコードの書き方の選択であり、5.1節「内部実装は自由」
の範囲内である）:

| sub の待ち | 仕様書の遷移 | 目標値 |
|---|---|---|
| RECVプリミティブ・手順2（相手のデータ準備待ち） | `20→21` / `28→21` | `0x21` |
| RECVプリミティブ・手順6（相手の受理解除待ち） | `41→40` | `0x40` |
| SENDプリミティブ・手順1（相手の受信準備待ち） | `00→02` | `0x02` |
| SENDプリミティブ・手順4（相手の受理確認待ち） | `12⇄14` | `0x14` |

SENDプリミティブ手順6（「`IN $FE` でステータス相当を読む（スピン）」）は
仕様書が「次に続く手順により抜け値が変わる境界的な待ち」と明記して
おり（1.15節・3節、未確定のまま残されている）、確定した目標値が無い。
**推測でループ条件を作らない**という規律に従い、ここは単発の
`IN $FE` 読み捨て（ブロックしない）とする。main視点のSENDプリミティブ
（1.10節）でも対応する最終手順は「`IN $FE`（結果ステータス）」と
単発読みとして書かれており、待ちループとしては定義されていない
ことと整合する。
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
P_PIO_C    = 0xFE   # ハンドシェイク状態。sub は IN のみ（仕様書6節10項: subはOUTしない）

RQM  = 0x80   # $FA bit7
DIO  = 0x40   # $FA bit6（1='FDCからホストへ'方向）

# ---- $FF フェーズコード語彙（仕様書1.12節。SEND系/RECV系で共通） ----
PH_SEND_START_SET = 0x0F   # （sub SENDでは使わない。main SENDの語彙）
PH_SEND_START_CLR = 0x0E   # （同上）
PH_SEND_DATA_SET  = 0x09
PH_SEND_DATA_CLR  = 0x08
PH_RECV_START_SET = 0x0B
PH_RECV_START_CLR = 0x0A
PH_RECV_ACK_SET   = 0x0D
PH_RECV_ACK_CLR   = 0x0C

# ---- sub視点の $FE 待ち目標値（仕様書1.15節。上のdocstring表と同じ） ----
FE_RECV_DATA_READY = 0x21   # RECVプリミティブ手順2（20→21 / 28→21）
FE_RECV_ACK_DONE    = 0x40  # RECVプリミティブ手順6（41→40）
FE_SEND_RECV_READY  = 0x02  # SENDプリミティブ手順1（00→02）
FE_SEND_ACK_DONE     = 0x14  # SENDプリミティブ手順4（12⇄14。到達値を目標に採用）

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
    # ポートC（$FF/$FE）に関する明示的なモード設定は行わない。
    # 旧版はここで `OUT $FF,0x99` という初期化を行っていたが、その値は
    # 仕様書のどこにも根拠が無い（1.12節が確定しているsubのOUT $FF値は
    # 08-0Eの7種のみで0x99は含まれない）。旧版の値は自作サブROM＋自作
    # 試験用mainドライバ同士を動かして辻褄合わせした結果であり、今回の
    # 見直しの対象そのものである。**仕様に無いので入れない。**
    a.call("FDC_SPECIFY")
    a.jp("MAIN_LOOP")

    # ====================================================================
    # ハンドシェイク・プリミティブ（仕様書 1.15節。sub視点で確定した手順）
    #
    # sub は $FF にフェーズコードを書くだけで、$FE には一度も書き込まない
    # （仕様書6節10項）。$FE は相手(main)の$FF書き込みがハードウェア越しに
    # 見える読み取り専用の窓であり、sub 側コードはその値がどう作られるかに
    # 関与しない——ここが旧版（たすき掛け理論・OUT $FE直接書き込み）から
    # の最大の変更点。
    # ====================================================================

    # ---- IN $FE をポーリングし、指定の目標値に達するまで待つ ----
    for name, target in (
        ("WAIT_FE_RECV_DATA_READY", FE_RECV_DATA_READY),
        ("WAIT_FE_RECV_ACK_DONE",   FE_RECV_ACK_DONE),
        ("WAIT_FE_SEND_RECV_READY", FE_SEND_RECV_READY),
        ("WAIT_FE_SEND_ACK_DONE",   FE_SEND_ACK_DONE),
    ):
        a.label(name)
        a.label(name + "_LOOP")
        a.in_port(P_PIO_C)
        a.cp_n(target)
        a.jr_nz(name + "_LOOP")
        a.ret()

    # ---- RECV_BYTE: main の SEND を受け取る。結果は A ----
    # 仕様書1.15節「sub視点のRECVプリミティブ」の手順1〜7をそのまま。
    a.label("RECV_BYTE")
    a.out_imm(0xFF, PH_RECV_START_SET)      # 手順1: OUT $FF,0x0B
    a.call("WAIT_FE_RECV_DATA_READY")       # 手順2: 相手のデータ準備待ち(→0x21)
    a.out_imm(0xFF, PH_RECV_START_CLR)      # 手順3: OUT $FF,0x0A
    a.in_port(P_PIO_A)                      # 手順4: IN $FC（main OUT $FDと対応）
    a.push_af()
    a.out_imm(0xFF, PH_RECV_ACK_SET)        # 手順5: OUT $FF,0x0D
    a.call("WAIT_FE_RECV_ACK_DONE")         # 手順6: 相手の受理解除待ち(→0x40)
    a.out_imm(0xFF, PH_RECV_ACK_CLR)        # 手順7: OUT $FF,0x0C
    a.pop_af()
    a.ret()

    # ---- SEND_BYTE: main の RECV に応答して1バイト送る。引数は A ----
    # 仕様書1.15節「sub視点のSENDプリミティブ」の手順1〜6をそのまま。
    # 0x0F/0x0E相当の書き込みは4条件で一度も観測されなかった（1.15節）ので
    # ここでは書かない。
    a.label("SEND_BYTE")
    a.push_af()
    a.call("WAIT_FE_SEND_RECV_READY")       # 手順1: 相手の受信準備待ち(→0x02)
    a.pop_af()
    a.out_a(P_PIO_B)                        # 手順2: OUT $FD（main IN $FCと対応）
    a.out_imm(0xFF, PH_SEND_DATA_SET)       # 手順3: OUT $FF,0x09
    a.call("WAIT_FE_SEND_ACK_DONE")         # 手順4: 相手の受理確認待ち(→0x14)
    a.out_imm(0xFF, PH_SEND_DATA_CLR)       # 手順5: OUT $FF,0x08
    a.in_port(P_PIO_C)                      # 手順6: ステータス相当を単発で読み捨てる
    # ↑ 仕様書は手順6を「次に続く手順により抜け値が変わる境界的な待ち」
    # と明記し、確定した目標値を示していない（3節）。推測でループ条件を
    # 作らないため、ここではブロックしない単発読みに留める。main視点の
    # SENDプリミティブ（1.10節）でも対応する最終手順は単発の
    # 「IN $FE（結果ステータス）」であり、待ちループとしては定義されて
    # いないことと矛盾しない。
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
