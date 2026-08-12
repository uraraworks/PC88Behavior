#!/usr/bin/env python3
"""
make_subrom.py — L3 サービスルーチン（自作サブROM / DISK.ROM 相当）を組み立てる

根拠は `docs/spec/l3-subrom.md`（第7版）**だけ**である。公式 ROM も
公式ディスクの内容も一度も参照していない。

  なぜ Python でバイト列を組むのか: `src/l1_ipl/make_ipl_rom.py`（M4）と
  同じ理由。外部依存ゼロで第三者が `python3 make_subrom.py <出力先>` だけで
  同じ ROM を再生成できる。

## このファイルが実装するもの（仕様書 6節・1.10〜1.13節・1.15〜1.17節）

- 起動順序（1.16節・6節11項）。`OUT $F7,0x08` → `OUT $FF,0x91` →
  単発`IN $FE`読み2回 → RECVプリミティブ1回（**応答のSENDは行わない**）
  → `OUT $F8,0x05` → `OUT $F8,0xFF` → FDC初期化、という4条件で
  1バイトも違わず一致した手順をそのまま再現する。$FF=0x91・単発
  $FE読みの意味論は未確定（3節）だが、値そのものは確定しているため
  観測どおり再現する（推測ではなく観測の再現）。
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
- 書き込み側（267バイト連続SENDバースト）と、そのsub側対応物と
  見られる「ストリーミングRECVループ」（1.17節）。仕様書 6節7項・
  12項により本マイルストーンのスコープ外。
- **値に基づくディスパッチ（1.17節・6節12項）。** 通常のRECV+SEND
  応答ペアとストリーミングRECVループを切り替える条件は、RECV
  プリミティブで受け取るデータの値（伏せ字済みで読めない）に依存する
  可能性が高いという以上のことが確定できていない。**推測で分岐条件を
  作らない**という規律に従い、本実装は確定済みの構造（起動時RECV1回、
  定常状態のRECV直後の即時SEND応答）のみを実装し、値による分岐は
  一切行わない。

## アイドル判別（第8版で追加。`docs/notes/m6l-idle-dispatch.md`・仕様書3節）

`docs/notes/m6k-mixed-divergence.md`第1部で報告された混成ROM実走の
デッドロックは、旧版のディスパッチャ（`REQ_LOOP`が毎回、何も確認せず
いきなり`OUT $FF,0x0B`（RECVプリミティブ手順1）を書いていたこと）が
直接原因だった。mainが逆に「subが送る番」を期待している局面で、
subが先に「RECVする（＝mainが送る番だと決め打つ）」と宣言してしまい、
互いに相手の`$FE`遷移を待ち続けて止まっていた。

**確定している範囲だけで直す。** `IDLE_DISPATCH`は`$FF`へ何も書かずに
`IN $FE`を読み、以下の2値のどちらかに達するまでポーリングする:

- `0x08`（`FE_IDLE_TO_RECV`）: 仕様書1.17節・`docs/notes/m6k-mixed-divergence.md`
  第5部の「アイドル待ち」（`pc=00CC`）が4条件・観測全252件で例外なく
  到達し、その直後に必ずRECVへ進んでいた**確定済みの観測値**。
  本実装のテスト用main（`tools/make_l3_test_main.py`）はヘッダ送信を
  main視点SENDプリミティブ（`OUT $FF,0x0F`始まり）で開始するため、
  同じ`$FF`フェーズコード列がsub側`$FE`に反映され、同じ`0x08`に
  到達するはずだという想定のもとで採用している（本ハーネスの
  PIOクロス配線は同一の`vendor/quasi88-libretro`コアが両ROM組に共通
  なので、想定は成立するはずだが、これ自体は本ノートの追加測定
  ではなく既存資産からの類推であることを明記する）。
- `0x02`（`FE_IDLE_TO_SEND`）: 仕様書1.15節「sub視点のSENDプリミティブ
  手順1」が待つ到達値と同じ。**これは確定した判別条件ではない。**
  実測コーパス（`measurements/m6c-sub-*`・`m6g-d0-boot-run{1,2}`）には
  「アイドル待ちから直接SENDへ進む」事例が1件も無く（1.17節）、
  この値がアイドル時のバレ読みで実際にこの意味で現れるかどうかは
  未検証である。**仕様書の確定範囲（1.15節のSEND手順1の到達値）から
  導いた暫定構造であり、値の裏付けは無い。**

`0x02`に達したら`SEND_BYTE`を1回呼んで`IDLE_DISPATCH`へ戻る
（送るバイトの値は、第9版まで`0x00`固定だった。**値の正しさは
目標ではない**という前提は変わらないが、仕様書6節14項（第9版で
追加）により「でっちあげた値」を送ること自体を方針違反と判断し、
第9版で`FDC_SENSE_DRIVE_STATUS`（μPD765 SENSE DRIVE STATUS、
結果フェーズ1バイト=ST3）を実際に発行してその結果バイトを送る形に
差し替えた。このバイトの意味論が未確定であることは変わらないので、
正しい値を推測して埋めるのではなく「FDCへ実際に問い合わせて得た値を
返す」構造にすることでデッドロック回避と方針の両方を満たす）。
`0x08`に達したら8バイトヘッダのRECV受信（`REQ_HEADER_RECV`）へ進む。
どちらでもない中間値のあいだはポーリングを続ける（`WAIT_FE_*`と同じ、
目標値に達するまで単純に回すスタイル）。

## プリミティブ1回ごとにディスパッチャへ戻る（第9版で修正）

**第8版の実装には別のバグがあった。** `IDLE_DISPATCH`は導入したものの、
`REQ_HEADER_RECV`（8バイトヘッダ受信）と応答送信（256バイト）を
それぞれ「一塊」として実装し、塊の**途中**では`IDLE_DISPATCH`に戻らず
`RECV_BYTE`/`SEND_BYTE`を機械的に8回・256回連続で呼んでいた。

ユーザーが2026-08-12に報告した公式環境での混成ROM実走で、これが
デッドロックを起こすことが分かった。sub側のイベント列（畳み込み後）は、
起動時RECV1回のあとIDLE_DISPATCHが1回だけ働いて8バイトヘッダ受信に
入り、1バイト目のRECVは成立した（`IN $FC`でデータを受け取り
`OUT $FF 0x0C`でRECVプリミティブの手順7まで完了）。ところが**その直後、
`IDLE_DISPATCH`に戻らず**、`_hdr_loop`のDJNZがそのまま2バイト目の
RECV開始（`OUT $FF 0x0B`）に落ち、そのまま`$FE`待ちで永久停止した。
同じ時刻、公式mainは`OUT $FF`（1.10節main側RECVプリミティブの開始
＝「subが送る番」）を出して`IN $FE`でスピンし、タイムアウトしていた。
つまり**mainは8バイト連続で送るとは限らず、1バイトだけ送って
RECVへ切り替えることがある**——sub側が「一度RECVに入ったら8バイト
連続で来る」と決め打ちしていたこと自体が誤りだった。

**確定している範囲だけで直す。** `REQ_HEADER_RECV`・応答送信を
「塊」として実装するのをやめ、RAM上のポインタ（`HDR_PTR`・
`RESP_PTR`・`RESP_ACTIVE`）で進行状態を持たせ、**`RECV_BYTE`/
`SEND_BYTE`を1回呼ぶたびに必ず`IDLE_DISPATCH`へ戻る**構造にした。
8バイト集まったら（あるいは256バイト送り終えたら）その場で
次の処理（シーク・読み出し・応答準備、または応答フェーズの終了）を
行うが、**次に何をするか（RECVを続けるかSENDに切り替わるか）は
毎回`IDLE_DISPATCH`が`$FE`を読んで決める**。アイドル判別条件
そのもの（`0x02`が未確定であること）は変えていない。

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
P_STROBE   = 0xF7   # 起動時ハンドシェイクで書く（仕様書1.5節・1.16節。用途は未確定）

# ---- 起動順序で使う固定値（仕様書1.16節。4条件で1バイトも違わず一致） ----
BOOT_F7_VALUE = 0x08
BOOT_FF_VALUE = 0x91   # 1.12節の8種のフェーズコード語彙のいずれにも属さない
BOOT_F8_VALUE_1 = 0x05
BOOT_F8_VALUE_2 = 0xFF

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

# ---- アイドル判別（上のdocstring「アイドル判別」節を参照。第8版で追加） ----
FE_IDLE_TO_RECV = 0x08   # 確定: 1.17節「アイドル待ち(pc=00CC)」の到達値(4条件252件で例外なし)
FE_IDLE_TO_SEND = FE_SEND_RECV_READY  # 未確定: SENDプリミティブ手順1の到達値からの類推(裏付け無し)

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
    def or_a(self):        self.db(0xB7)   # OR A（キャリーを0にするためだけに使う）
    def sbc_hl_de(self):    self.db(0xED, 0x52)   # SBC HL,DE（ED 42はSBC HL,BC。取り違え注意）

    def ld_a(self, n):    self.db(0x3E, n)
    def ld_b(self, n):    self.db(0x06, n)
    def ld_c(self, n):    self.db(0x0E, n)
    def and_a(self, n):   self.db(0xE6, n)
    def or_n(self, n):    self.db(0xF6, n)
    def cp_n(self, n):    self.db(0xFE, n)
    def ld_sp(self, nn):  self.db(0x31, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_de_imm(self, nn): self.db(0x11, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_imm(self, nn): self.db(0x21, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_mem(self, addr): self.db(0x2A, addr & 0xFF, (addr >> 8) & 0xFF)  # LD HL,(nn)
    def ld_mem_hl(self, addr): self.db(0x22, addr & 0xFF, (addr >> 8) & 0xFF)  # LD (nn),HL
    def ld_a_mem(self, addr):  self.db(0x3A, addr & 0xFF, (addr >> 8) & 0xFF)  # LD A,(nn)
    def ld_mem_a(self, addr):  self.db(0x32, addr & 0xFF, (addr >> 8) & 0xFF)  # LD (nn),A
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

# ---- ディスパッチャの進行状態（第9版で追加。上のdocstring「プリミティブ
#      1回ごとにディスパッチャへ戻る」参照）----
HDR_PTR     = 0x4300   # 2バイト: ヘッダ受信中の書き込み位置(REQ_HDR..REQ_HDR+8)
RESP_PTR    = 0x4302   # 2バイト: 応答送信中の読み出し位置(SECTOR_BUF..SECTOR_BUF+256)
RESP_ACTIVE = 0x4304   # 1バイト: 0=応答フェーズでない、非0=応答送信中

ROM_SIZE = 0x2000      # DISK.ROM の上限（vendor memory.c: load_rom(...,0x2000,...)）


def build_subrom(break_response=False, break_dispatch_return=False):
    """break_response: 検証器（tools/verify_l3.sh）をわざと壊すためのフラグ。
    応答256バイトの先頭1バイトを1ビットだけ反転させる。verify_l3.sh の
    「わざと壊して検出できるか確認する」手順で使う。ここで壊す1ビットは
    ROM由来ではなく、自作の応答データに対する自己テスト用の変更。

    break_dispatch_return: 第9版で修正したバグ（RECV_BYTE/SEND_BYTEを
    1回終えてもIDLE_DISPATCHへ戻らず、8バイトヘッダ・256バイト応答を
    「一塊」として決め打ちしていた旧構造）を意図的に再現するフラグ。
    tools/verify_l3.sh の回帰テストが検出力を持つことを確認するためだけ
    に使う。既定（False）では新構造（プリミティブ1回ごとに
    IDLE_DISPATCHへ戻る）を使う。"""
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
    a.jp("BOOT_HANDSHAKE")

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
    # 起動順序（仕様書 1.16節。4条件で1バイトも違わず一致した手順を
    # そのまま再現する）。
    #
    #   OUT $F7,0x08 → OUT $FF,0x91 → IN $FE(単発)×2 →
    #   RECVプリミティブ1回(応答のSENDは行わない) →
    #   OUT $F8,0x05 → OUT $F8,0xFF → FDC初期化
    #
    # 手順3〜4の単発IN $FEの意味論・手順5で受け取るバイトの用途は
    # 未確定（仕様書3節）。値そのものは確定しているので、mainが外部
    # インタフェースとして要求している可能性を考え、観測どおり再現する
    # （推測ではなく観測の再現。仕様書6節11項）。
    #
    # 6節12項（判別条件は未確定）に従い、手順5で受け取ったバイトの値を
    # 見て分岐すること（推測によるディスパッチ）はしない——結果は捨てる。
    # ====================================================================
    a.label("BOOT_HANDSHAKE")
    a.out_imm(P_STROBE, BOOT_F7_VALUE)     # 手順1: OUT $F7,0x08
    a.out_imm(0xFF, BOOT_FF_VALUE)         # 手順2: OUT $FF,0x91
    a.in_port(P_PIO_C)                     # 手順3: IN $FE（単発、読み捨て）
    a.in_port(P_PIO_C)                     # 手順4: IN $FE（単発、読み捨て）
    a.call("RECV_BYTE")                    # 手順5: RECVプリミティブ1回（応答なし）
    a.out_imm(P_TC, BOOT_F8_VALUE_1)       # 手順6: OUT $F8,0x05
    a.out_imm(P_TC, BOOT_F8_VALUE_2)       # 手順7: OUT $F8,0xFF
    a.call("FDC_SPECIFY")                  # 手順8: FDC初期化開始
    a.jp("MAIN_LOOP")

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

    # ---- SENSE DRIVE STATUS（第9版で追加。仕様書6節14項）。
    # μPD765/8272 系データシートに定義されたコマンド0x04。他のコマンドと
    # 違い割り込み待ち・実行フェーズ（データ転送）を持たず、コマンド
    # フェーズ2バイト（コマンド＋unit/head）を送った直後に結果フェーズ
    # 1バイト（ST3）を返す、もっとも単純な「コマンド→結果」の往復。
    # 呼ぶたびに毎回ホスト側の状態（RECALIBRATE/SEEK/READ実行中かどうか）
    # に関わらず一意に定義された結果が返るため、他のFDCシーケンスの
    # 副作用を気にせず独立に呼べる。結果（ST3）はAレジスタに残す。
    a.label("FDC_SENSE_DRIVE_STATUS")
    a.ld_a(0x04); a.call("FDC_OUT")     # コマンド: SENSE DRIVE STATUS
    a.ld_a(0x00); a.call("FDC_OUT")     # unit=0, head=0
    a.call("FDC_IN")                    # 結果フェーズ: ST3（1バイト、Aに残る）
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

    if break_dispatch_return:
        # ====================================================================
        # 第9版で修正したバグをわざと再現する版（tools/verify_l3.sh の
        # 回帰テストが検出力を持つことを確認するためだけに使う。上の
        # build_subrom() docstring・第9版のモジュールdocstring参照）。
        # RECV_BYTE/SEND_BYTEを1回終えてもIDLE_DISPATCHへ戻らず、
        # 8バイトヘッダ・256バイト応答を「一塊」として決め打ちしていた
        # 旧構造をそのまま復元する。
        # ====================================================================
        a.label("MAIN_LOOP")
        a.call("FDC_RECALIBRATE")
        a.label("REQ_LOOP")

        a.label("IDLE_DISPATCH")
        a.in_port(P_PIO_C)
        a.cp_n(FE_IDLE_TO_SEND)
        a.jr_z("IDLE_SEND_BRANCH")
        a.cp_n(FE_IDLE_TO_RECV)
        a.jr_z("REQ_HEADER_RECV")
        a.jr("IDLE_DISPATCH")

        a.label("IDLE_SEND_BRANCH")
        # 仕様書6節14項: でっちあげた値ではなく、SENSE DRIVE STATUS
        # の結果フェーズ(ST3)を実際に叩いて得た値をそのまま返す
        # （下のSEND_DISPATCH_IDLEと同じ方針。この分岐は
        # --break-dispatch-return の回帰専用でありディスパッチ復帰の
        # 有無だけを検出対象にしているため、送る値自体はどちらでもよいが
        # 本番構造と揃える）。
        a.call("FDC_SENSE_DRIVE_STATUS")
        a.call("SEND_BYTE")
        a.jr("IDLE_DISPATCH")

        a.label("REQ_HEADER_RECV")
        a.ld_hl_imm(REQ_HDR)
        a.ld_b(8)
        a.label("_hdr_loop")
        a.call("RECV_BYTE")
        a.ld_hl_a()
        a.inc_hl()
        a.djnz("_hdr_loop")

        a.ld_hl_imm(REQ_HDR + 3)
        a.ld_a_hl()
        a.call("FDC_SEEK")

        a.call("FDC_READ_SECTOR")
        if break_response:
            a.ld_hl_imm(SECTOR_BUF)
            a.ld_a_hl()
            a.db(0xEE, 0x01)
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

    # ====================================================================
    # メインループ（仕様書 1.11節: 固定8バイトヘッダの読み出し要求）
    #
    #   02 01 00 <b3> <b4> 06 12 60
    #
    # byte0/1/2/5/6/7 は全件で固定（1.11節）。本実装はこれらを検査せず
    # 読み飛ばす——固定値チェックの有無は「mainが受け取るデータ列」
    # （適合条件、5.1節）に影響しないため、内部実装として単純な方を選ぶ。
    # byte3/byte4 をシリンダ・セクタとして扱う（独自解釈、6節6項）。
    #
    # 第9版で修正: 8バイトヘッダ受信・256バイト応答送信を「一塊」として
    # 扱わない。RAM上の進行状態（HDR_PTR/RESP_PTR/RESP_ACTIVE）を使い、
    # RECV_BYTE/SEND_BYTEを1回呼ぶたびに必ずIDLE_DISPATCHへ戻る
    # （上のモジュールdocstring「プリミティブ1回ごとにディスパッチャへ
    # 戻る」参照）。
    # ====================================================================
    a.label("MAIN_LOOP")
    # 進行状態を初期化する（起動直後の1回だけ）
    a.ld_hl_imm(REQ_HDR)
    a.ld_mem_hl(HDR_PTR)
    a.ld_a(0x00)
    a.ld_mem_a(RESP_ACTIVE)
    a.call("FDC_RECALIBRATE")

    # ---- アイドル判別（上のdocstring「アイドル判別」節を参照） ----
    # $FF へ何も書かずに $FE を読み、どちらの側かが確定するまで待つ。
    # 0x08 は確定済みの観測値（1.17節「アイドル待ち」）、0x02 は
    # 1.15節SEND手順1の到達値からの類推であり未確定（docstring参照）。
    # どのプリミティブ(RECV_DISPATCH/SEND_DISPATCH)を1回終えても、
    # 必ずここへ戻ってくる——次に何をするかは毎回ここが決める。
    a.label("IDLE_DISPATCH")
    a.in_port(P_PIO_C)
    a.cp_n(FE_IDLE_TO_SEND)
    a.jr_z("SEND_DISPATCH")
    a.cp_n(FE_IDLE_TO_RECV)
    a.jr_z("RECV_DISPATCH")
    a.jr("IDLE_DISPATCH")

    # ---- RECV_DISPATCH: RECVを1回だけ行い、必ずIDLE_DISPATCHへ戻る。
    #      HDR_PTRがREQ_HDR+8に達したら8バイト集まったということなので、
    #      その場でシーク・読み出し・応答フェーズの準備を行う
    #      （これも「決め打ちで次にSENDへ進む」のではなく、応答準備が
    #      整うだけ——実際にSENDするかどうかは次回以降のIDLE_DISPATCHが
    #      $FEを読んで決める）。 ----
    a.label("RECV_DISPATCH")
    a.call("RECV_BYTE")               # A = 受け取ったバイト
    a.ld_hl_mem(HDR_PTR)
    a.ld_hl_a()                       # (HDR_PTR位置) <- A
    a.inc_hl()
    a.ld_mem_hl(HDR_PTR)
    a.ld_de_imm(REQ_HDR + 8)
    a.or_a()
    a.sbc_hl_de()                     # HDR_PTR(更新後) - (REQ_HDR+8)
    a.jr_nz("IDLE_DISPATCH")          # まだ8バイト集まっていない

    # 8バイト集まった: 次のヘッダ受信に備えてポインタを巻き戻す
    a.ld_hl_imm(REQ_HDR)
    a.ld_mem_hl(HDR_PTR)

    # シリンダへシーク
    a.ld_hl_imm(REQ_HDR + 3)
    a.ld_a_hl()
    a.call("FDC_SEEK")

    # セクタを読み出し、応答フェーズを開始する（実際のSENDは行わない）
    a.call("FDC_READ_SECTOR")
    if break_response:
        a.ld_hl_imm(SECTOR_BUF)
        a.ld_a_hl()
        a.db(0xEE, 0x01)          # XOR A,0x01（先頭1バイトを1ビット反転）
        a.ld_hl_a()
    a.ld_hl_imm(SECTOR_BUF)
    a.ld_mem_hl(RESP_PTR)
    a.ld_a(0x01)
    a.ld_mem_a(RESP_ACTIVE)
    a.jr("IDLE_DISPATCH")

    # ---- SEND_DISPATCH: SENDを1回だけ行い、必ずIDLE_DISPATCHへ戻る。
    #      応答フェーズ中(RESP_ACTIVE!=0)ならSECTOR_BUFの次の1バイトを
    #      送る。応答フェーズでなければ、従来どおり暫定の0x00を送る
    #      （docstring「アイドル判別」節参照。値の正しさは目標ではない）。
    a.label("SEND_DISPATCH")
    a.ld_a_mem(RESP_ACTIVE)
    a.or_a()
    a.jr_z("SEND_DISPATCH_IDLE")

    a.ld_hl_mem(RESP_PTR)
    a.ld_a_hl()
    a.call("SEND_BYTE")
    a.ld_hl_mem(RESP_PTR)
    a.inc_hl()
    a.ld_mem_hl(RESP_PTR)
    a.ld_de_imm(SECTOR_BUF + 256)
    a.or_a()
    a.sbc_hl_de()                     # RESP_PTR(更新後) - (SECTOR_BUF+256)
    a.jr_nz("IDLE_DISPATCH")          # まだ256バイト送り終えていない

    # 256バイト送り終えた: 応答フェーズを終了する
    a.ld_a(0x00)
    a.ld_mem_a(RESP_ACTIVE)
    a.jr("IDLE_DISPATCH")

    a.label("SEND_DISPATCH_IDLE")
    # 第9版で変更: 応答フェーズ外（8バイトヘッダがまだ揃っていない
    # 段階、たとえば仕様書1.18節のラウンド#0のような短い要求形式）で
    # 1バイト応答を求められた場合、以前は 0x00 を決め打ちで返していた。
    # 仕様書6節14項により、これは「でっちあげた値」であり方針違反と
    # 判断した。ここでは値を推測する代わりに、FDC_SENSE_DRIVE_STATUS
    # （SENSE DRIVE STATUS、コマンド0x04）を実際に発行し、μPD765が
    # 結果フェーズで返す ST3 バイトをそのまま送る。値の中身が公式版と
    # 一致するかどうかは分からないままでよい——分からないことを埋める
    # のではなく「FDCへ実際に問い合わせて返す」構造を選ぶことで、
    # 値を知らないまま構成上正しい返答経路にする（仕様書6節14項）。
    a.call("FDC_SENSE_DRIVE_STATUS")
    a.call("SEND_BYTE")
    a.jr("IDLE_DISPATCH")

    return a


def build(break_response=False, break_dispatch_return=False):
    a = build_subrom(break_response=break_response,
                      break_dispatch_return=break_dispatch_return)
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
    ap.add_argument("--break-dispatch-return", action="store_true",
                     help="第9版で修正したバグ（RECV/SEND完遂後にIDLE_DISPATCHへ"
                          "戻らない旧構造）をわざと再現するフラグ（tools/verify_l3.sh "
                          "の回帰テストの検出力確認用）。")
    args = ap.parse_args()
    rom, used = build(break_response=args.break_response,
                       break_dispatch_return=args.break_dispatch_return)
    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "DISK.ROM").write_bytes(rom)
    print(f"生成した: {d/'DISK.ROM'} ({ROM_SIZE} bytes, コード {used} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
