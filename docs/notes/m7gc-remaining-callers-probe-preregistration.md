# m7gc: `FDC_SEEK`残り6呼び出し元への同一探針の事前登録

実施日: 2026-09-04

## 位置づけ

本稿は`m7fx`が「読解では決まらない」「別意味のバイトを読んでいる」に
分類した残りの呼び出し元へ、`m7fy`／`m7fz`が交換#6経路（#6-ii）で確立した
探針（`REQ_HDR+2` bit0の`clear`/`set`故障注入＋陽性対照）を広げる事前登録
である。**本稿では測定しない。エミュレータは動かさない。`src/`・`tools/`は
一切変更しない。実装と測定は次稿以降で行う。**

段番号は0起点で統一し、種別名を併記する。1起点で書く箇所（`m7fz`・
`m7gb`が使う`--list-all-stages`の段番号）はそのつど「1起点」と明示する。

## 対象6箇所（`m7fx`の分類のうち既定ビルドで生きている残り）

`m7fx`（[m7fx](m7fx-fdc-seek-propagation-callers-reading.md)）が数えた
既定ビルド6箇所のうち、交換#6（#6-ii）は`m7fy`/`m7fz`で測定済みなので
対象外。残り6箇所（#6-iを含む6-iiiのフォールスルーは対象、#6-i自体は
交換#3本来の経路で「正常」に分類済みのため測定不要）を対象とする。

| 記号 | 呼び出し元 | `m7fx`の分類 | 本稿での識別子案（`--probe-site`） |
|---|---|---|---|
| #1 | `_general_read_request` | 読解では決まらない | `general_read_request` |
| #2 | `_bulk_read_do` | 読解では決まらない | `bulk_read_do` |
| #4 | `_recv_dispatch_hdr_done` | 読解では決まらない（到達するかも不明） | `recv_dispatch_hdr_done` |
| #5 | `_recv_dispatch_write_sector`（WRITE経路） | 別意味のバイトを読んでいる | `recv_dispatch_write_sector` |
| #6-iii | `_exchange11_prepare_sector`→`_exchange3_prepare_sector`フォールスルー | 読解では決まらない | `exchange11_fallthrough` |
| #7 | `_exchange14_prepare_first_read` | 読解では決まらない | `exchange14_prepare_first_read` |

（#3は`break_dispatch_return`専用の故障注入コードで既定ビルドには生成
されないため対象外。`m7fx`の表と同じ扱い。）

## 現在の行番号確認（本稿執筆時点の`src/l3_service/make_subrom.py`）

`m7fx`執筆後にコード（`m7fy`/`m7fz`の3フラグ追加）が入っているため、行番号を
確認し直した。

- `FDC_SEEK`（1571行）: 入口で`a.push_af()`（1572行）。既定ビルド
  （`break_drive_selector=False`）では続けて`REQ_HDR+2`を読みbit0を
  `REQ_UNIT_HEAD`へ`OR`合成する（1575-1583行）。目的シリンダは
  `a.pop_af()`後にOUT（1587行）。
- `_seek_sense_f7_shared`（1605行）: `a.ld_e(0x00); a.call("FDC_SEEK")`
  （1606-1607行）。呼び出し元が積んだAをそのままFDCへ渡す。
- `_seek_sense_f7_read_shared`（1614行）: `_seek_sense_f7_shared`を呼ぶ
  だけ（1615行）。
- `_general_read_request`（1746行）: `FDC_SEEK`呼び出しは1772行
  （`a.call("FDC_SEEK")  # A = C のまま`）。直前1761-1770行でHL=REQ_HDR+4へ
  Cを書き込み、Aにその値を残したまま`a.ld_e(0x00)`（1770行）を経て
  1772行の呼び出しに至る。
- `_bulk_read_do`（1840行）: `FDC_SEEK`呼び出しは1857行。直前1850-1856行で
  `BULK_C`（`REQ_HDR`+`BR_CPOS`位置）を読みAに残したまま`a.ld_e(0x00)`
  （1856行）を経て1857行の呼び出しに至る。
- `_recv_dispatch_write_sector`（1809行）: `_seek_sense_f7_shared`呼び出しは
  1819行。直前1816-1818行で`WRITE_PREV2`を`rra`した値をAに残す。
- `_recv_dispatch_hdr_done`（2338行）: `FDC_SEEK`呼び出しは2348行。直前
  2344-2347行でREQ_HDR+4をAへ読み`a.ld_e(0x00)`（2347行）を経て2348行の
  呼び出しに至る。
- `_exchange3_prepare_sector`（2360行）: 入口2365-2366行で
  `a.ld_hl_imm(REQ_HDR + 4); a.ld_a_hl()`とAを**フレッシュに読み直す**
  （呼び出し元が残したAは使わない）。その後2371行で
  `_seek_sense_f7_read_shared`を呼ぶ。
- `_exchange11_prepare_sector`（2427行）: `_exchange3_prepare_sector`への
  `jr`は2448行。
- `_exchange14_prepare_first_read`（2457行）: `_seek_sense_f7_read_shared`
  呼び出しは2476行。直前2470-2474行でREQ_HDR+1の値をAへ読み、
  `REQ_H`とREQ_HDR+4の両方へ書いたあと、Aを変更せずに2476行の呼び出しに
  至る。

## 注入位置と、各箇所でAが目的シリンダとして`FDC_SEEK`に届くかの確認

`cyl`（`INC A`）が陽性対照として成立するのは、**注入位置の直後で`FDC_SEEK`
（または共有ルーチンを経て`FDC_SEEK`）へ制御が渡るまでの間に、Aが目的
シリンダ以外の値で上書きされない場合に限る**。6箇所を読解で確認した結果、
5箇所は成立するが、**1箇所（#6-iii）は成立しない**ことが分かった。

| 部位 | 注入位置（直前） | 注入直後からFDC_SEEKまでにAは再読込されるか | `cyl`成立 |
|---|---|---|---|
| #1 | 1772行`a.call("FDC_SEEK")`の直前（1770-1771行の間） | されない（Aはそのまま目的シリンダとしてFDC_SEEKへ渡る） | 成立 |
| #2 | 1857行`a.call("FDC_SEEK")`の直前（1856-1857行の間） | されない | 成立 |
| #4 | 2348行`a.call("FDC_SEEK")`の直前（2347-2348行の間） | されない | 成立 |
| #5 | 1819行`a.call("_seek_sense_f7_shared")`の直前（1818-1819行の間） | されない（共有ルーチンはAを読み直さずFDC_SEEKへ渡す） | 成立 |
| #6-iii | 2448行`a.jr("_exchange3_prepare_sector")`の直前（2447-2448行の間） | **される**（`_exchange3_prepare_sector`が入口2365-2366行でREQ_HDR+4からAをフレッシュに読み直す。フォールスルー元が残したAは捨てられる） | **不成立** |
| #7 | 2476行`a.call("_seek_sense_f7_read_shared")`の直前（2474-2475行の間） | されない | 成立 |

**#6-iiiの訂正:** 事前登録の元設計（親の指示）は「`cyl`: `a.db(0x3C)`
（`INC A`）」を6箇所共通の符号化として想定していたが、#6-iiiでは
この位置に`INC A`を置いても**末端のSEEKシリンダには一切反映されない**
（`_exchange3_prepare_sector`が直後にAを上書きする）。この位置は元々
#6-i（交換#3本来の経路）と共有しており、`_exchange3_prepare_sector`の
入口がREQ_HDR+4を読み直す設計になっていること自体は`m7fy`が確認済み
（`_exchange6_prepare_sector`が転記だけ済ませて`REQ_HDR+4`を残す設計と
同型）。**したがって#6-iiiの`cyl`だけは、Aではなく`REQ_HDR+4`（フォール
スルー時点でまだ`_exchange11_prepare_sector`が書き換えていない、目的
シリンダの転記先）を直接動かす形にする。** 符号化案:
`a.ld_hl_imm(REQ_HDR + 4)` + `a.db(0x34)`（`INC (HL)`、`m7fw`が容量圧縮で
使ったのと同じ命令）。この位置（2447-2448行の間）でHLは他に使われて
いないため、`ld_hl_imm`によるHL上書きは無害である。

**`INC A`（オペコード`0x3C`）・`INC (HL)`（オペコード`0x34`）・
`RES 0,(HL)`（オペコード`0xCB 0x86`）・`SET 0,(HL)`（オペコード
`0xCB 0xC6`）は、いずれもZ80の定義済み命令である。** 公開命令表の事実で
あり、公式ROMの解析結果ではない。本リポジトリの`Asm`クラス（498行の
`db()`）にはこれらのニーモニックが実装されていないため、`db()`で直接
発行する、という書き方にする。「未定義命令」ではなく「本リポジトリの
`Asm`クラスに未実装」である。

## `clear`/`set`（`REQ_HDR+2`のbit0）の副作用が無いことの確認

6箇所すべてで、注入位置直前までに`REQ_HDR+2`自体を書き換えるコードは
無い（`_general_read_request`はREQ_HDR+3・+4・+6、`_bulk_read_do`は
`BR_CPOS`位置とBULK_C、`_recv_dispatch_write_sector`は`WRITE_PREV2`、
`_recv_dispatch_hdr_done`はREQ_HDR全体のHDR_PTR巻き戻しのみ、
`_exchange11_prepare_sector`はREQ_HDR+3・+4・+5・+6・REQ_H・
REQ_UNIT_HEAD、`_exchange14_prepare_first_read`はREQ_HDR+1・+4・REQ_H・
REQ_UNIT_HEADを読み書きするが、いずれも`REQ_HDR+2`には触れない）。
`RES 0,(HL)`/`SET 0,(HL)`はAレジスタにもフラグにも触れない（(HL)先の
メモリだけを書き換えるZ80のビット操作命令）。したがって`clear`/`set`は
各箇所のAレジスタ・DEレジスタ（`ld_e(0x00)`が別途行う値）・既存の
REQ_HDR+4等の転記処理を一切壊さない。

## `cyl`（`INC A`／#6-iiiのみ`INC (HL)`）の副作用確認

`INC A`はCフラグ以外の全フラグを変える（Z80仕様上の一般則）が、
`FDC_SEEK`は入口で`a.push_af()`しており（1572行）、SEEKコマンド送出後に
`a.pop_af()`（1587行）で復元してから目的シリンダをOUTする。5箇所
（#1・#2・#4・#5・#7）はいずれも`FDC_SEEK`（または共有ルーチン経由で
`FDC_SEEK`）を直接・間接に呼ぶだけであり、`FDC_SEEK`のpush_af/pop_afが
フラグを吸収するため、呼び出し元の後続処理へフラグの影響は伝播しない
（`m7fy`が`break_exchange6_cylinder`について確認したのと同じ論法）。
`INC (HL)`（#6-iiiの`cyl`）もフラグを変えるが、影響先は`FDC_SEEK`が
push_af/pop_afで保護する対象と同じであり、かつHL自体は`_exchange3_
prepare_sector`の入口（2365行`a.ld_hl_imm(REQ_HDR + 4)`）で即座に
上書きされるため、HLの残留値が後続へ影響することもない。

## 事前登録する介入（CLI設計）

箇所ごとにフラグを増やさず、CLIへ2引数を追加する:

- `--probe-site {general_read_request,bulk_read_do,recv_dispatch_hdr_done,recv_dispatch_write_sector,exchange11_fallthrough,exchange14_prepare_first_read}`
- `--probe-mode {clear,set,cyl}`

**両方の指定が無ければ何も生成しない。既定ビルドはバイト単位で不変
（新規コード生成条件が両フラグの組み合わせにガードされるため）。**
`--probe-site`のみ・`--probe-mode`のみの片方だけ指定は無効な組み合わせ
として`build_subrom()`が拒否する（実装時に決める）。

選ばれた1箇所にだけ、上表の注入位置（`FDC_SEEK`／共有ルーチン呼び出しの
直前、#6-iiiのみ`jr`の直前）へ、モードに応じて次のいずれか1つを置く:

- `clear`: `a.ld_hl_imm(REQ_HDR + 2)` + `a.db(0xCB, 0x86)`（`RES 0,(HL)`）
- `set`: `a.ld_hl_imm(REQ_HDR + 2)` + `a.db(0xCB, 0xC6)`（`SET 0,(HL)`）
- `cyl`: `a.db(0x3C)`（`INC A`）。**ただし`exchange11_fallthrough`のみ**
  `a.ld_hl_imm(REQ_HDR + 4)` + `a.db(0x34)`（`INC (HL)`）に置き換える
  （上記「#6-iiiの訂正」節の理由による）。

## 事前登録する合格条件（測定前に固定する。後から動かさない）

判定に数値比較を使わない。

1. **既定ビルドのバイト不変**: 実装後の既定ビルド（`--probe-site`未指定）
   が、実装前（現HEAD）の既定ビルドとSHA-256で完全一致すること。固定長
   8192バイトなのでファイルサイズは指標に使わない。バイト一致であれば
   既存経路（起動・WRITE・READ・容量関門）への退行は起こりえない、
   という論法を明記する（`m7fw`・`m7fy`が使った論法の踏襲）。
2. **容量関門**: 6箇所×3モード＝18通りすべてで`build()`が`SystemExit`を
   出さないこと。判定は`SystemExit`の有無だけで行う。
3. **成果物が変わったこと**: 18通りのROMが、既定ビルドとSHA-256で
   異なること（`build_subrom()`が実際に注入コードを生成したことの確認。
   自分で作った検査が対象を素通りしていないかの最低限の確認）。
4. **箇所ごとの陽性対照**: 各箇所の`cyl`が末端に差を出すこと。**差が
   出ない箇所は「到達していない」であり、その箇所の`clear`/`set`の結果を
   解釈してはならない。**「差なし＝安全」と読まない。この区別を必ず
   箇所ごとの表に残す。
5. **判定規則を先にベースラインへ当てる**: `tools/compare_l3_entry_fdc.py`
   ・`tools/check_l3_screen_output.py`の判定規則を、まずベースライン2run
   同士へ当てて「差なし」と出ることを確認してから、注入版へ当てる
   （`m7fy`条件4・`m7fz`段階3・`m7gb`と同じ手順）。
6. **決定論性**: 差が出た条件は2run測って伏せ字後バイト列の自己一致を
   確認する。重すぎて1runにとどめた条件があれば、**どれを1runにしたか
   明記する**（`m7gb`が「差が出なかった条件は1runでよい、明記する」と
   した基準に合わせる）。

一つでも欠ければ合格と呼ばない。

## 事前登録する予測（測定前に、箇所ごとにではなく類型として書く）

各箇所は次のいずれかに分類されるはずである。**測定前にこの分類表を
固定する。どの箇所がどれになるかは予測しない（推測で決めない）。**

- **P1「到達し、bit0が効く」**: `cyl`が差を出し、`set`も差を出す
  → 交換#6（`m7fz`のH1）と同じ潜在的な混線がその箇所にもある。
- **P2「到達するが、bit0は効かない」**: `cyl`は差を出すが、`clear`も
  `set`も差を出さない → その箇所ではドライブ指定が末端に影響しない。
- **P3「到達しない」**: `cyl`が差を出さない → 既定ビルドの実行経路に
  入っていない（`m7fx`は#4がこれになる可能性を読解時点で指摘している）。
- **P4「現状は0だが効く」**: `cyl`は差を出し、`set`は差を出すが`clear`は
  差を出さない → 交換#6（`m7fz`）と同じ形。今は偶数（またはbit0=0相当）で
  助かっているだけ。

## 測定条件の候補（`m7gb`が示した制約の下で）

本ハーネスで変えられる条件は限られる（`m7gb`: 起動可能なN88-BASIC
ディスクは実質`N88_FE.D88`の1本のみ）。ただし、**#1・#2・#5・#7は
FILES経路（`m7ft`の分類）なので、起動区間専用だった交換#6より打鍵・
シナリオの自由度が効く可能性がある。**

- **#5（`_recv_dispatch_write_sector`、WRITE経路）**: `m7ga`/`m7gb`の
  `write_protect`条件（`10 PRINT "T"\nSAVE"Q8P"\n`）がSAVE＝WRITE要求を
  発行させる既存条件であり、そのまま流用できる可能性が高い。ただし
  `write_protect`という条件名自体は`m7ga`が別目的（B:媒体状態）で付けた
  ものなので、本稿の`--probe-site recv_dispatch_write_sector`とは
  独立に、SAVE操作を含む打鍵列（B:媒体状態は問わない）で試すのが妥当。
- **#1（`_general_read_request`）・#2（`_bulk_read_do`）**: `tools/
  conform_l3.sh`・`m7ft`系のノートが使う`FILES`コマンド後の一般READ・
  バルクREAD区間に対応すると考えられるが、**どの打鍵・framesで確実に
  踏むかは本稿の読解範囲では特定できていない**。次稿の測定実施時に、
  まず`cyl`（またはP6-iiiの`INC (HL)`）を陽性対照として様々な打鍵条件へ
  当て、`tools/compare_l3_entry_fdc.py --list-all-stages`で段の差の有無
  から到達を確かめる、という`m7fy`/`m7fz`と同じ手順を踏む。
- **#7（`_exchange14_prepare_first_read`）**: `m7fy`が触れた1.34節の
  交換#14（累積7/11/12件境界）に対応し、起動区間内（`N88_FE.D88`起動）で
  踏まれると考えられるが、これも段番号の特定は次稿で行う。
- **#4（`_recv_dispatch_hdr_done`）**: `m7fx`が「到達するかも不明」とした
  とおり、到達経路自体が不確かである。測定条件は**未特定**とし、
  `cyl`陽性対照が差を出すかどうかで到達の有無をまず判定する
  （差が出なければP3「到達しない」として扱い、追加の条件探索は次稿の
  判断に委ねる）。
- **#6-iii（`_exchange11_prepare_sector`フォールスルー）**: 1.33節の
  交換#11に対応し、起動区間内（`N88_FE.D88`起動）で踏まれると考えられる。
  `m7fz`が交換#6を段20(SEEK)と特定した手順（`--list-all-stages`の出現順
  当てはめ＋陽性対照での検証）を、交換#11の段でも同様に適用できる
  可能性が高いが、具体的な段番号は次稿で測定して特定する。

いずれも確定的な特定はできていない。**次稿の測定実施時に、各箇所の
`cyl`（#6-iiiは`INC (HL)`版）を陽性対照として先に当て、到達の有無と
段位置を実測で確定してから`clear`/`set`の結果を解釈する**という
`m7fy`/`m7fz`の手順をそのまま踏襲する。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は読んでいない。本稿は既存の`docs/spec/l3-subrom.md`・
`docs/notes/m7fx-*.md`・`docs/notes/m7fy-*.md`・`docs/notes/m7fz-*.md`・
`docs/notes/m7gb-*.md`と自作`src/l3_service/make_subrom.py`のコード読解
のみで構成した。値（バイト値・データポート値・シリンダ値・画面本文）は
一切書いていない。Z80の命令オペコード（`0x3C`・`0x34`・`0xCB 0x86`・
`0xCB 0xC6`）は公開命令表の事実として明記したが、これは禁止事項が対象と
する「ROM由来のバイト列」ではない。行番号・ラベル名・分岐条件のみを
記録した。測定・ビルド・エミュレータ実行はいずれも行っていない。

## 根拠リンク

[m7fx](m7fx-fdc-seek-propagation-callers-reading.md)・
[m7fy](m7fy-exchange6-drive-bit-preregistration.md)・
[m7fz](m7fz-exchange6-drive-bit-results.md)・
[m7ga](m7ga-odd-cylinder-condition-search-preregistration.md)・
[m7gb](m7gb-odd-cylinder-condition-search-results.md)・
[m7fw](m7fw-boot-drive-selector-adoption.md)・
[m7fu](m7fu-capacity-compression-preregistration.md)・
`docs/spec/l3-subrom.md` 1.32節・1.33節・1.35節・1.36節・1.46節・1.56節・
自作`src/l3_service/make_subrom.py`。
