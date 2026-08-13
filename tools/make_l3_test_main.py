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
（座標は仕様書1.29節の位置4/6へ置く）を SEND で送り、
交換#3の1バイト応答をRECVする。続けて交換#4の2バイト要求をSENDし、
256バイトの応答を RECV で受け取って、その場で捨てて次へ進む。
受け取った値そのものは `--io-log` の main 側 IN $FC 列に残るので、
判定は verify_l3.sh 側（ログを読む）で行う。

## 仕様書第7版（1.16節）への追随

自作サブROM（`src/l3_service/make_subrom.py`）が1.16節の起動順序を
実装した結果、subは起動直後に**RECVプリミティブを1回**（応答のSENDは
返さない）実行してから初期化を続ける仕様になった。これはmain側から見れば
「起動直後にSEND（1.10節のSENDプリミティブ）を1回行う」ことに対応する
（`docs/notes/m6k-mixed-divergence.md`第4部で、公式main側の対応する
最初の動作もこの1回のSENDであることを確認済み）。本ファイルの
`MAIN`ラベルの先頭に、ヘッダ送信ループより前にこのSENDを1回追加した。
送る値そのもの（実データ）は仕様書からは分からず、また5.1節の原則
（値の意味論は内部実装が自由）どおり試験駆動側の値の選択は検証に
影響しないため、固定の`0x00`を送る（値は判定に使わない——判定は
256バイト応答の内容一致のみで行う）。

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

## `--dispatch-switch-test`（第9版で追加）

`src/l3_service/make_subrom.py` の第9版で見つかったバグ（RECV/SEND
プリミティブを1回終えてもディスパッチャへ戻らない）の回帰テスト用。

**厳守**: このシナリオは自作サブROMの実装を見ずに、仕様書1.10節が
定義する main 側の SEND/RECV プリミティブの**組み合わせ方**だけを
根拠に書く。1.10節はSEND/RECVを独立した1バイト単位のプリミティブとして
定義しており、「ヘッダは必ず8バイト連続で送らなければならない」という
制約はどこにも書かれていない——それは自作サブROM側の内部実装の
都合（5.1節、内部実装は自由）に過ぎない。ユーザーが2026-08-12に
報告した公式環境での混成ROM実走では、公式mainが実際に「1バイトだけ
SENDしたところでRECVへ切り替える」挙動を示した。本シナリオは
それを、mainの手順として正当な範囲内（1.10節の範囲内で任意の順序に
SEND/RECVを組み合わせられる）で再現したものであり、「1バイトだけ」
ではなく「8バイトのSEND（＝妥当な読み出し要求ヘッダそのもの）を
送ったあと、応答の1バイト目だけRECVしてすぐ次へ進む」という形を
取る（応答を256バイト全部受け取らずに次の操作へ移る、という点が
「まだ何かの途中でも次のプリミティブへ切り替わりうる」ことの
モデル化になっている）。これにより、以降で送る本来のヘッダ要求列の
バイト境界を汚さずに、旧実装（8バイト・256バイトを「一塊」として
決め打ちする構造）だけが引っかかる状況を作れる。

## `--run-continuation-test`（第11版で追加）

`src/l3_service/make_subrom.py` 第11版で見つかったバグ（RECVを1バイト
完遂するたびに無条件でIDLE_DISPATCHへ戻る旧構造が、mainの複数バイト
連続SEND(run)の途中でmain/sub相互デッドロックを起こす）の回帰テスト用。
`docs/notes/m6n-run-boundary.md`・仕様書1.20節が根拠。

**厳守**: このシナリオも自作サブROMの実装を見ずに、仕様書1.10節
「main側にはSEND/RECVという2つの定型ハンドシェイク・プリミティブが
ある」の記述**だけ**を根拠に書く。1.10節はSENDプリミティブの最初の
手順`OUT $FF 0F`を「省略される場合あり」と明記しており、
`docs/notes/m6-main-to-sub.md` 1.1節・`docs/notes/m6n-run-boundary.md`
1節は、複数バイトを連続送信する場面ではこの省略が**先頭バイト以外の
継続バイトで**高い比率（4条件で84〜99%）で起きることを確認している。
本シナリオはこれを、mainの手順として正当な範囲内（1.10節が明記する
「省略される場合あり」の範囲内）で再現する: 8バイトの読み出し要求
ヘッダを送る際、**1バイト目だけ通常のSEND（`OUT $FF 0F`を含む）**、
**2〜8バイト目は`OUT $FF 0F`を省略したSEND**で送る。旧実装
（RECVを1回終えるたびに無条件でIDLE_DISPATCHへ戻り、そこで
何も書かずに`$FE`を読みに行くだけの構造）は、mainが継続バイトの
`bit1=1`待ち（`OUT $FF 0F`を省略した直後の待ち）に入っているのに
subが何も書かずに待つだけなので、相互デッドロックしてスピンし続ける
はずである。**このシナリオが実際に旧実装（本コミット直前の版）で
落ちることを確認してから、`tools/verify_l3.sh`に組み込んだ**
（下のモジュール末尾コメント・`tools/verify_l3.sh`参照）。

## `--fixed-byte-cutoff-test`（第13版で追加）

`src/l3_service/make_subrom.py` 第13版で見つかったバグ
（`docs/notes/m6k-mixed-divergence.md`第10部が診断した「サブが
ラウンド境界を無視して受信バイトを通算8バイト貯めてから8バイト
ヘッダとして解釈してしまう」旧構造）の回帰テスト用。仕様書1.18節が
確定した「起動シーケンスは可変長ラウンドのSEND→RECV往復で、
256バイト応答が返る3ラウンドのSEND側バイト数は8/6/8とばらついた」
という構造（各ラウンドはそれ単独で完結し、8バイトぴったりとは限らない）
を根拠にする。

**厳守**: このシナリオも自作サブROMの実装を見ずに、仕様書1.10節
「SEND/RECVは独立した1バイト単位のプリミティブ」の記述**だけ**を
根拠に書く。「8バイトの読み出し要求ヘッダは必ず1つの連続SEND runで
送らなければならない」という制約はどこにも無い——1.18節はむしろ
逆に、8バイトちょうどではないラウンド（2バイト・1バイト・5バイト等）
が実在することを確定させている。本シナリオは、2バイト・1バイト・
5バイトの3つの独立したラウンド（それぞれSENDで送り、直後に1バイトの
RECVで応答を受ける——1.18節が確定した「ラウンドごとに応答が返る」
構造そのもの）を送り、合計すると（値の並びだけを見れば）8バイトの
読み出し要求ヘッダと同じ形になるように仕組む。旧実装（ラウンド境界を
無視し、通算8バイトで打ち切る構造）は、この3ラウンド目の応答として
本来のST3（1バイト）ではなく256バイトの応答フェーズを開始してしまい、
mainが1バイトしかRECVしないまま次のラウンド（通常のREQUESTS列）へ
進むため、以降のプロトコルが壊れる。新実装（run境界＝bit1の観測で
打ち切る構造）は各ラウンドを独立に扱うため、3ラウンドいずれも
1バイトのST3応答で完結し、後続のREQUESTSは正常に完了するはずである。
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


def build(requests, dispatch_switch_test=False, run_continuation_test=False,
          fixed_byte_cutoff_test=False):
    """requests: [(cyl, sec), ...] の列。交換#3/#4を経て256バイト受ける。

    dispatch_switch_test: 上のdocstring「--dispatch-switch-test」参照。
    起動直後のSEND1回のあと、通常の要求ループへ入る前に「8バイトの
    ヘッダをSENDし、応答の1バイト目だけRECVしてすぐ次へ進む」割り込み
    シナリオを1回挟む。

    run_continuation_test: 上のdocstring「--run-continuation-test」参照。
    8バイトヘッダの1バイト目だけ通常のSEND(`OUT $FF 0F`あり)、
    2〜8バイト目は`OUT $FF 0F`を省略したSENDで送り、応答256バイトを
    全部RECVしてから通常の要求ループへ入る。

    fixed_byte_cutoff_test: 上のdocstring「--fixed-byte-cutoff-test」参照。
    2バイト・1バイト・5バイトの3つの独立したラウンド（それぞれSEND後に
    1バイトRECV）を送り、通常の要求ループへ入る前に挟む。"""
    a = Asm(0x0000)
    a.di()
    a.ld_sp(STACK)
    a.jp("MAIN")

    # (pio_set_mode 呼び出しは MAIN 冒頭で行う。下記 a.label("MAIN") 参照)

    # ---- $FE 待ちのビット判定（第11版で全面改訂。仕様書1.19節参照）----
    # 旧版はここを目標値との完全一致(`CP`)で判定していたが、これは
    # 1.13節が「まれに`02⇄80⇄82`」と既に明記していた副次パターン
    # （`0x82`ではなく`0x02`で抜けるケース）を取りこぼす。実際に
    # `--run-continuation-test`（第11版で追加）を走らせたところ、
    # 継続バイトの待ち（`_send_cont_wait1`）がまさに`0x02`で止まる
    # 事例を踏み、完全一致判定のまま無限にスピンすることを確認した。
    # `src/l3_service/make_subrom.py`が第10版で行ったのと同じ理由・
    # 同じ根拠（仕様書1.19節が確定した単一ビット）で、こちらも
    # `AND`によるビット判定に置き換える。
    #   SEND前（相手の受信準備待ち）: bit1=1（仕様書1.19節、0例外）
    #   SEND後（相手の受理確認待ち）: bit2=1（仕様書1.19節、bit1=0も同格）
    #   RECV前（相手のデータ準備待ち）: bit0=1（仕様書1.19節、0例外）
    #   RECV後（相手の受理解除待ち）: bit0=0（仕様書1.19節、0例外）
    FE_BIT_SEND_BEFORE = 0x02   # bit1
    FE_BIT_SEND_AFTER  = 0x04   # bit2
    FE_BIT_RECV_BEFORE = 0x01   # bit0
    FE_BIT_RECV_AFTER  = 0x01   # bit0

    # ---- SEND_MAIN: 1バイト送信（main視点、仕様書1.10節 SEND そのまま） ----
    #   引数: A = 送るバイト
    a.label("SEND_MAIN")
    a.push_af()
    a.out_imm(0xFF, 0x0F)                # OUT FF,0F
    a.label("_send_wait1")
    a.in_port(0xFE)
    a.and_a(FE_BIT_SEND_BEFORE)
    a.jr_z("_send_wait1")                # 相手の受信準備待ち（bit1=1で抜ける）
    a.out_imm(0xFF, 0x0E)                # OUT FF,0E
    a.pop_af()
    a.out_a(0xFD)                        # OUT FD,<byte>
    a.out_imm(0xFF, 0x09)                # OUT FF,09
    a.label("_send_wait2")
    a.in_port(0xFE)
    a.and_a(FE_BIT_SEND_AFTER)
    a.jr_z("_send_wait2")                # 相手の受理確認待ち（bit2=1で抜ける）
    a.out_imm(0xFF, 0x08)                # OUT FF,08
    a.in_port(0xFE)                      # 結果ステータス（単発読み、読み捨て。1.10節どおり待ちループにしない）
    a.ret()

    # ---- SEND_MAIN_CONT: SEND_MAINと同じだが`OUT $FF 0F`を省略する
    #      （仕様書1.10節「省略される場合あり」。上のdocstring
    #      「--run-continuation-test」参照。runの継続バイトを模す）----
    #   引数: A = 送るバイト
    a.label("SEND_MAIN_CONT")
    a.push_af()
    a.label("_send_cont_wait1")
    a.in_port(0xFE)
    a.and_a(FE_BIT_SEND_BEFORE)
    a.jr_z("_send_cont_wait1")           # 相手の受信準備待ち。0Fを書かずに直接待つ
    a.out_imm(0xFF, 0x0E)                # OUT FF,0E
    a.pop_af()
    a.out_a(0xFD)                        # OUT FD,<byte>
    a.out_imm(0xFF, 0x09)                # OUT FF,09
    a.label("_send_cont_wait2")
    a.in_port(0xFE)
    a.and_a(FE_BIT_SEND_AFTER)
    a.jr_z("_send_cont_wait2")           # 相手の受理確認待ち（bit2=1で抜ける）
    a.out_imm(0xFF, 0x08)                # OUT FF,08
    a.in_port(0xFE)                      # 結果ステータス（単発読み、読み捨て）
    a.ret()

    # ---- RECV_MAIN: 1バイト受信（main視点、仕様書1.10節 RECV そのまま） ----
    #   結果: A = 受け取ったバイト
    a.label("RECV_MAIN")
    a.out_imm(0xFF, 0x0B)                # OUT FF,0B
    a.label("_recv_wait1")
    a.in_port(0xFE)
    a.and_a(FE_BIT_RECV_BEFORE)
    a.jr_z("_recv_wait1")                # 相手のデータ準備待ち（bit0=1で抜ける）
    a.out_imm(0xFF, 0x0A)                # OUT FF,0A
    a.in_port(0xFC)                      # IN FC = 実データ（sub OUT $FD）
    a.push_af()
    a.out_imm(0xFF, 0x0D)                # OUT FF,0D
    a.label("_recv_wait2")
    a.in_port(0xFE)
    a.and_a(FE_BIT_RECV_AFTER)
    a.jr_nz("_recv_wait2")               # 相手の受理解除待ち（bit0=0で抜ける）
    a.out_imm(0xFF, 0x0C)                # OUT FF,0C
    a.pop_af()
    a.ret()

    # ---- RECV_MAIN_PAIR: 交換#4多バイト応答の連続2位置を1フェーズで受信 ----
    # 仕様書1.31節。値は保持せず、2回のIN $FCをI/Oログへ残す。
    a.label("RECV_MAIN_PAIR")
    a.out_imm(0xFF, 0x0B)
    a.label("_recv_pair_wait1")
    a.in_port(0xFE)
    a.and_a(FE_BIT_RECV_BEFORE)
    a.jr_z("_recv_pair_wait1")
    a.out_imm(0xFF, 0x0A)
    a.in_port(0xFC)                      # 位置1
    a.out_imm(0xFF, 0x0D)
    a.label("_recv_pair_wait2")
    a.in_port(0xFE)
    a.and_a(FE_BIT_RECV_AFTER)
    a.jr_nz("_recv_pair_wait2")
    a.in_port(0xFC)                      # 位置2（受理解除後のラッチ）
    a.out_imm(0xFF, 0x0C)
    a.ret()

    # ---- 要求ヘッダ（仕様書1.29節: 位置4=C、位置6=R/EOT） ----
    hdr_labels = []
    for i, (cyl, sec) in enumerate(requests):
        name = f"HDR_{i}"
        hdr_labels.append(name)
        a.label(name)
        a.db(0x02, 0x01, 0x00, 0x00, cyl, 0x00, sec, 0x06)

    # 仕様書1.23節で確定している交換#4要求の長さは2バイトである。
    # 値の意味は未確定なので、この自己検証治具では任意の固定値を用いる。
    # 自作同士の試験に過ぎず公式mainとの適合根拠にはしない。
    a.label("EXCHANGE4_REQUEST")
    a.db(0x00, 0x00)

    # ---- --dispatch-switch-test 用の割り込みヘッダ（上のdocstring参照）。
    #      requests[0] と同じ (cyl,sec) を使う——値そのものに意味は無く、
    #      単に「有効な読み出し要求として成立するヘッダを送る」ことだけが
    #      目的（FDCシークが失敗しない範囲に収める）。 ----
    dispatch_switch_hdr = None
    if dispatch_switch_test:
        cyl0, sec0 = requests[0]
        dispatch_switch_hdr = "DISPATCH_SWITCH_HDR"
        a.label(dispatch_switch_hdr)
        a.db(0x02, 0x01, 0x00, 0x00, cyl0, 0x00, sec0, 0x06)

    # ---- --run-continuation-test 用のヘッダ（上のdocstring参照）。
    #      requests[0] と同じ (cyl,sec) を使う——dispatch_switch_hdrと
    #      同じ理由（有効な読み出し要求として成立させるためだけで、
    #      値そのものに意味は無い）。 ----
    run_cont_hdr = None
    if run_continuation_test:
        cyl0, sec0 = requests[0]
        run_cont_hdr = "RUN_CONT_HDR"
        a.label(run_cont_hdr)
        a.db(0x02, 0x01, 0x00, 0x00, cyl0, 0x00, sec0, 0x06)

    # ---- --fixed-byte-cutoff-test 用の3ラウンド（上のdocstring参照）。
    #      値の並びを通しで見ると requests[0] と同じ8バイトヘッダになる
    #      ように仕組む（位置4/6のcyl/secが有効な範囲に収まるように
    #      requests[0]の値を使う——旧実装が誤って読み出し要求として
    #      解釈してしまってもFDCシークが失敗せず、検出したい protocol
    #      の食い違いだけが明確に出るようにするため）。 ----
    fbc_round_a = fbc_round_b = fbc_round_c = None
    if fixed_byte_cutoff_test:
        cyl0, sec0 = requests[0]
        fbc_round_a = "FBC_ROUND_A"   # 2バイト
        a.label(fbc_round_a)
        a.db(0x02, 0x01)
        fbc_round_b = "FBC_ROUND_B"   # 1バイト
        a.label(fbc_round_b)
        a.db(0x00)
        fbc_round_c = "FBC_ROUND_C"   # 5バイト（先頭2バイトがcyl/sec）
        a.label(fbc_round_c)
        a.db(0x00, cyl0, 0x00, sec0, 0x06)

    # ---- 本編 ----
    a.label("MAIN")
    # ポートCの明示的なモード設定は行わない（0x99は仕様書に根拠が無い旧版の
    # 値だった。src/l3_service/make_subrom.py のリセットベクタと対称に、
    # ここでも削除した）。

    # 起動直後のSEND1回（仕様書1.16節。上のdocstring「仕様書第7版への
    # 追随」参照）。subはこれをRECVプリミティブで受け取り、応答は返さない。
    a.ld_a(0x00)
    a.call("SEND_MAIN")

    if dispatch_switch_test:
        # 割り込みシナリオ（上のdocstring「--dispatch-switch-test」参照）:
        # 交換#3/#4を1組完遂してから次へ進む。第38版以前は8バイト要求の
        # 直後に256バイト応答が来る旧境界を前提に途中で打ち切っていたが、
        # 現仕様では交換#4の2バイト要求なしに多バイト応答を始めてはならない。
        a.ld_hl(dispatch_switch_hdr)
        a.ld_b(8)
        a.label("_dsw_hdrsend")
        a.ld_a_hl()
        a.call("SEND_MAIN")
        a.inc_hl()
        a.djnz("_dsw_hdrsend")
        a.call("RECV_MAIN")   # 交換#3の単発応答
        a.ld_hl("EXCHANGE4_REQUEST")
        a.ld_b(2)
        a.label("_dsw_exchange4_send")
        a.ld_a_hl()
        a.call("SEND_MAIN")
        a.inc_hl()
        a.djnz("_dsw_exchange4_send")
        a.ld_b(0x80)
        a.label("_dsw_exchange4_recv")
        a.call("RECV_MAIN_PAIR")
        a.djnz("_dsw_exchange4_recv")

    if run_continuation_test:
        # runシナリオ（上のdocstring「--run-continuation-test」参照）:
        # 1バイト目だけ通常のSEND(0Fあり)、2〜8バイト目は0Fを省略した
        # SENDでヘッダを送り、交換#3の1バイトを受ける。交換#4の2バイト
        # 要求を続け、256バイトを全部RECVする。
        a.ld_hl(run_cont_hdr)
        a.ld_a_hl()
        a.call("SEND_MAIN")          # 1バイト目(先頭): 0Fあり
        a.inc_hl()
        a.ld_b(7)
        a.label("_rct_hdrsend_cont")
        a.ld_a_hl()
        a.call("SEND_MAIN_CONT")     # 2〜8バイト目(継続): 0Fを省略
        a.inc_hl()
        a.djnz("_rct_hdrsend_cont")

        a.call("RECV_MAIN")
        a.ld_hl("EXCHANGE4_REQUEST")
        a.ld_b(2)
        a.label("_rct_exchange4_send")
        a.ld_a_hl()
        a.call("SEND_MAIN")
        a.inc_hl()
        a.djnz("_rct_exchange4_send")

        a.ld_b(0x80)
        a.label("_rct_resprecv")
        a.call("RECV_MAIN_PAIR")
        a.djnz("_rct_resprecv")

    if fixed_byte_cutoff_test:
        # 3つの独立したラウンド（上のdocstring「--fixed-byte-cutoff-test」
        # 参照）: それぞれSENDで送り、直後に1バイトだけRECVする
        # （1.18節が確定した「ラウンドごとに応答が返る」構造そのもの）。
        for name, length in ((fbc_round_a, 2), (fbc_round_b, 1), (fbc_round_c, 5)):
            a.ld_hl(name)
            a.ld_b(length)
            a.label(f"_fbc_send_{name}")
            a.ld_a_hl()
            a.call("SEND_MAIN")
            a.inc_hl()
            a.djnz(f"_fbc_send_{name}")
            a.call("RECV_MAIN")   # ラウンド応答（旧実装ならST3のはずが256バイト応答の先頭バイトに化ける）

    for name in hdr_labels:
        # ヘッダ8バイトを SEND で送る
        a.ld_hl(name)
        a.ld_b(8)
        a.label(f"_hdrsend_{name}")
        a.ld_a_hl()
        a.call("SEND_MAIN")
        a.inc_hl()
        a.djnz(f"_hdrsend_{name}")

        # 交換#3の意味未特定応答を1バイトRECVする。
        a.call("RECV_MAIN")

        # 交換#4の2バイト要求をSENDする。値は未確定だが、現行仕様と実装が
        # 確定している交換境界・応答長を自己検証するため長さを厳密に守る。
        a.ld_hl("EXCHANGE4_REQUEST")
        a.ld_b(2)
        a.label(f"_exchange4_send_{name}")
        a.ld_a_hl()
        a.call("SEND_MAIN")
        a.inc_hl()
        a.djnz(f"_exchange4_send_{name}")

        # 交換#4応答256バイトを RECV する（内容は iolog に残る）。
        a.ld_b(0x80)
        a.label(f"_resprecv_{name}")
        a.call("RECV_MAIN_PAIR")
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
    ap.add_argument("--dispatch-switch-test", action="store_true",
                     help="上のdocstring「--dispatch-switch-test」参照。"
                          "make_subrom.py 第9版の回帰テスト用シナリオを挟む。")
    ap.add_argument("--run-continuation-test", action="store_true",
                     help="上のdocstring「--run-continuation-test」参照。"
                          "make_subrom.py 第11版の回帰テスト用シナリオ"
                          "（0F省略の連続SEND run）を挟む。")
    ap.add_argument("--fixed-byte-cutoff-test", action="store_true",
                     help="上のdocstring「--fixed-byte-cutoff-test」参照。"
                          "make_subrom.py 第13版の回帰テスト用シナリオ"
                          "（2+1+5バイトの独立した3ラウンド）を挟む。")
    args = ap.parse_args()

    requests = []
    for tok in args.requests.split(","):
        c, s = tok.split(":")
        requests.append((int(c), int(s)))

    a = build(requests, dispatch_switch_test=args.dispatch_switch_test,
              run_continuation_test=args.run_continuation_test,
              fixed_byte_cutoff_test=args.fixed_byte_cutoff_test)
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
