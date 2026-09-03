# m7fu: 軸Fのための容量圧縮を事前登録する

実施日: 2026-09-03

## 位置づけ

本稿は`m7ft`の結論を受けたものである。`m7ft`は、起動バッチ両側
（batch2・batch5）で`REQ_HDR+2`を明示する修正（軸F、最良の符号化は
案F1、+7バイト相当）が、8構成×`PC88_BULK_READ_INTERVENTION_LIMIT`=1〜4の
全32構成のうち`restore_request_kind_length6`@LIMIT=4の1構成だけで
`find_out_of_window_blocks`（窓外9バイト）により`build()`が
`SystemExit`になることを実測した。`m7ft`は「圧縮による余地の確保は
別作業」として、実装せず容量制約の記録に留めた。

本稿はその「別作業」を担当し、**挙動を1ビットも変えない容量圧縮**の
候補を実測し、9バイト以上の削減が可能かどうかを確定させる。実装は
まだ行わない。`m7ez`が「圧縮による余地の確保は別作業」とした課題を、
このリポジトリで実際に使われた手口（後述）に沿って引き取る。

**本稿の担当分はビルド確認までである。エミュレータでの測定・
`conform_l3.sh`の実行は行っていない。作業終了時に`src/`は元の状態へ
戻し、`git diff`は空である。**

段番号は0起点で統一し、種別名を必ず併記する
（`--list-all-stages`は1起点、`m7fp`の教訓）。

## 何を減らす必要があるか

`restore_request_kind_length6`@LIMIT=4で、軸F案F1（+7バイト、実測では
整列パディングの影響で使用量差は+11バイトだった。下記「再確認」節）を
適用すると、`find_out_of_window_blocks`が窓外コード**9バイト**
（ブロック`_observed_request_next_9`）を報告して`SystemExit`になる。
したがって、**このブロックが窓（0x0800）の外へ出ないところまで、
他のどこかで9バイト以上を削れればよい。**

### 再確認: `m7ft`の結果と同じ環境であることの確認

候補を測る前に、変更を一切加えていない`src/l3_service/make_subrom.py`と
軸F案F1だけを一時的に当てた版の両方で32構成の`build()`を実行し、
`m7ft`の実測値と一致することを確認した。

- 無変更（ベースライン）: `default`@LIMIT=4 = 2042バイト、
  `restore_request_kind_length6`@LIMIT=4 = 2050バイト。32構成すべて成功。
- 軸F案F1のみ: `default`@LIMIT=4 = 2053バイト（+11。整列パディングの
  影響で`m7ft`が記す参考値と同じく+7ちょうどにはならない）。
  `restore_request_kind_length6`@LIMIT=4だけが`find_out_of_window_blocks`
  （窓外9バイト、ブロック`_observed_request_next_9`）で`SystemExit`。
  それ以外の31構成は成功。

`m7ft`の記録と完全に一致した。この一致を、以降の圧縮候補の実測が
同じ土台の上で行われていることの確認として扱う。

## 圧縮候補の調査

まず`build_subrom()`が組み立てた`Asm`インスタンスの`a.labels`から
ラベルごとの区間サイズを算出し（`/tmp`配下の使い捨てスクリプトで
`build(metadata=meta)`を呼び、`meta["labels"]`とROM総長からラベル間の
差分を取っただけで、ROM内容は一切見ていない）、大きいブロックと、
窓境界（0x0800）付近のブロックを特定した。次に、`git log --oneline |
grep -i 圧縮`で見つかる過去の圧縮コミット（`829b259`容量圧縮64バイト
・`73000f1`の測定、`25dff34`交換応答決定関数のテーブル駆動化420バイト、
`7d5d43a`交換#14テーブル駆動化139バイト）と、`m7bz-save-reachability.md`
「実装と容量」節（AF保存除去・SENSE INTERRUPT末尾のRET Z/JP化・起動時
連続状態ゼロループ化）を読み、このリポジトリで実際に使われた手口
（末尾呼び出し化、共通部分列のサブルーチン化、テーブル駆動化）を確認
した上で、現在のコードに残っている同種の重複を探した。

`_observed_single_by_request`の決定関数は`m7ap`で既にテーブル駆動化
済みであり、これ以上の同種圧縮は見送った（該当コードは表引き
インタプリタ1個であり、繰り返しパターンの候補が見当たらなかった）。

### 候補C1: SEEK→SENSE DRIVE STATUS→単発F7の共有列をサブルーチン化

`FDC_SEEK`の直後に`FDC_SENSE_DRIVE_STATUS`を呼び、その直後に
`OUT $F7`（`BOOT_F7_VALUE`固定）を単発発行する4命令の並び
（`ld_e(0x00); call FDC_SEEK; call FDC_SENSE_DRIVE_STATUS;
out_imm(P_STROBE, BOOT_F7_VALUE)`）が、コード中に**3箇所**、一字一句
同じ形で存在した。

- WRITE直前（`_recv_dispatch_write_sector`、この後は`call
  FDC_WRITE_SECTOR`へ続く）
- 交換#3準備（`_exchange3_prepare_sector`、この後は`call
  FDC_READ_SECTOR; ld_a(1); ld_mem_a(SECTOR_READY)`へ続く）
- 交換#14準備（`_exchange14_prepare_first_read`、この後は交換#3と
  全く同じ3命令へ続く）

交換#3・交換#14の2箇所はさらにその後ろ3命令（`call FDC_READ_SECTOR;
ld_a(0x01); ld_mem_a(SECTOR_READY)`）まで完全に一致していたため、
これも合わせて共有した。

新設した2つのサブルーチン（`FDC_SEEK`の直後、`FDC_WRITE_SECTOR`定義の
前に置いた。到達は3・2箇所からの`call`のみで、フォールスルーは無い）:

```
_seek_sense_f7_shared:
    ld_e(0x00); call FDC_SEEK; call FDC_SENSE_DRIVE_STATUS
    out_imm(P_STROBE, BOOT_F7_VALUE); ret
_seek_sense_f7_read_shared:
    call _seek_sense_f7_shared; call FDC_READ_SECTOR
    ld_a(0x01); ld_mem_a(SECTOR_READY); ret
```

WRITE直前の呼び出し元は`call _seek_sense_f7_shared; call
FDC_WRITE_SECTOR`に、交換#3・交換#14の呼び出し元は`call
_seek_sense_f7_read_shared`一発に置き換えた。

**振る舞いを変えないと言える根拠:**

- **命令列そのものは1バイトも変えていない。** 3箇所に重複していた命令列を
  1箇所へ移動し、元の位置には同じ命令列を実行する`call`を置いただけ
  （純粋なコード移動）。実行される命令の種類・順序・引数は移動前後で
  同一であり、追加されたのは`call`/`ret`の対応する1組だけである。
- **フラグ・レジスタへの依存は各呼び出し元で確認した。** `FDC_SEEK`は
  入口で`push_af()`するため、目的シリンダ（A）は呼び出し元が直前の
  `ld_hl_a()`（メモリへの退避）より前に確定させている値であり、共有列の
  先頭`ld_e(0x00)`はAに触れないため、Aは共有列の前後で変化しない
  （3箇所すべてで確認）。`FDC_SENSE_DRIVE_STATUS`は`REQ_HDR+2` bit0を
  読むだけでEには依存しない（1524行）。共有列の最後
  `out_imm(P_STROBE, BOOT_F7_VALUE)`はA・フラグを`LD A,n`で確定させる
  だけで前段の値に依存しない。したがって共有列の入口で必要な前提は
  「Aに目的シリンダが入っていること」だけであり、これは3箇所すべてで
  共有列の直前に満たされている。
- **共有列を抜けた後、各呼び出し元の残りコードがフラグに依存していない
  ことを確認した。** WRITE直前は直後に`call FDC_WRITE_SECTOR`（自分で
  A・コマンドを設定し直す）、交換#3・#14は直後に`call FDC_READ_SECTOR`
  （同様）で、いずれも前段のフラグ・Aを読まない。
- **スタック段数は3箇所とも+1レベル増える**（元は`call FDC_SEEK`が
  直接の呼び出し元だったが、今は`call _seek_sense_f7_shared`→内部で
  `call FDC_SEEK`となるため、その間は1段深い）。`STACK`は0x7FFEで、
  この深さ増分がスタックオーバーフローを起こさないことは、本稿では
  **実測していない**（`m7ca`が`FDC_BEGIN`統合で同種の1段追加をした
  前例に沿った判断であり、既存の32構成`build()`チェックはスタック
  深さを検査しないため、確認できなかったこととして明記する）。
- **`break_dispatch_return`構成では、この2つのサブルーチンは
  未到達コードになる。** `break_dispatch_return=True`のとき、
  `MAIN_LOOP`以降は`if break_dispatch_return:`側の別実装（第9版相当の
  旧構造）が使われ、上記3箇所の呼び出し元コードは一切コンパイルされない
  （Pythonの`if`が生成そのものを分岐させるため）。一方、共有
  サブルーチン2つは`FDC_SEEK`の直後に無条件に配置したため、この構成では
  呼ばれない状態で存在する（約25バイトの死にコードが増える）。
  `find_out_of_window_blocks`は`KNOWN_UNREACHABLE_LABELS`に明示された
  ラベルだけを除外する保守的な判定であり、この2つの新ラベルは
  `KNOWN_UNREACHABLE_LABELS`に含めていない（`FDC_SEEK`・
  `FDC_READ_SECTOR`など既存の共有ルーチンも同様に、使わない構成が
  あっても常時定義されている既存パターンに倣った）。この扱いにより
  窓外判定は誤って抑制されない。実測（下表）でも
  `break_dispatch_return`は32構成すべて成功した。

### 候補T1・T2: 末尾呼び出し化（`call X; ret` → `jp X`）

「他に検討したが実装しなかった」わけではなく実測した2箇所。第69版
（`FDC_SEEK`→`FDC_SENSE_INT`）・第70版（`m7by`、`FDC_RECALIBRATE`）と
同じ手口を、現在のコードに残る`call X`直後`ret`の並びに機械的に適用
できるか探した。

- T1: `FDC_IN_7`の呼び出し直後の`ret`（1631行付近、READ経路の末尾）。
  `call FDC_IN_7; ret`→`jp FDC_IN_7`。
- T2: `BULK_SEND_BEGIN`内の`call WAIT_FE_RECV_DATA_READY; ret`
  （2624行付近）。`jp WAIT_FE_RECV_DATA_READY`に置き換え。

**振る舞いを変えないと言える根拠:** いずれも「`call`で戻り番地を
積んでから戻り先ルーチンを呼び、そのルーチンが`ret`で戻ってきた直後に
無条件`ret`するだけ」という形であり、`jp`化しても戻り先ルーチンの
`ret`が直接、元の呼び出し元（`call`でこの関数を呼んだ側）へ戻る。
最終的な戻り先・A・フラグ・スタック段数は変わらない。この論法は
`m7ca`が同じ変換に使ったものと同一であり、機械的に確認できた。

2箇所とも1バイトずつ削減（`call`3バイト+`ret`1バイト=4バイトが
`jp`3バイトに縮む）で、合計2バイト。単独では9バイトに遠く届かない。

### 検討したが候補にしなかったもの

- `_observed_single_by_request`のテーブル駆動化は`m7ap`で既に実施済み
  （420バイト削減）であり、同種の圧縮余地は見当たらなかった。
- `FDC_BEGIN`へのコマンド先頭バイト送出統合、起動FDC列のE再利用、
  高速バルク5入口の共有は`m7ca`で既に実施済み（計64バイト削減）で
  あり、重複しない範囲を探した結果が候補C1である。
- 死にコードの除去は、`find_out_of_window_blocks`が
  `KNOWN_UNREACHABLE_LABELS`で明示的に管理している既知の到達不能
  ラベル以外に、新たに「到達しない」とコードだけで確認できるブロックを
  見つけられなかったため、候補にしなかった。

## 実測結果

候補ごとに`src/l3_service/make_subrom.py`へ一時的に当て、8構成×
`PC88_BULK_READ_INTERVENTION_LIMIT`=1〜4の全32通りで`build()`を直接
呼び出し、`SystemExit`の有無だけで判定した（`m7fg`が確定した基準。
数値比較は使わない。使用量は参考として併記する）。検証スクリプトは
`/tmp`配下に置き、リポジトリへは追加していない。試した候補はすべて
適用後に`git diff`を確認し、破棄して元に戻した。

| 候補 | 手口 | `default`@LIMIT=4 | `restore_request_kind_length6`@LIMIT=4 | 32構成中の`SystemExit`件数 | 軸F案F1を重ねた場合の32構成 |
|---|---|---:|---:|---:|---|
| （ベースライン） | — | 2042 | 2050 | 0/32 | 31/32（`restore_request_kind_length6`@4のみ窓外9バイトで不成立） |
| C1 | 3箇所重複のサブルーチン化 | 2024（**-18**） | 2032（**-18**） | **0/32** | **0/32（全32構成成功）** |
| T1+T2 | 末尾呼び出し化2箇所 | 2040（-2） | 2048（-2） | 0/32 | 1/32失敗（`restore_request_kind_length6`@4、窓外9バイトのまま。2バイトでは不足） |
| C1+T1+T2 | 上記全部 | （未個別測定。下記「組み合わせ」参照） | | | |
| C1+F1 | C1を適用したうえで軸F案F1を重ねる | 2031 | 2039 | — | **0/32（全32構成成功）** |
| C1+T1+T2+F1 | 圧縮全部＋軸F案F1 | （下記参照） | 2037 | — | **0/32（全32構成成功）** |

（C1+T1+T2+F1の完全な32構成表は取得済みだが、C1単独で既に目的を
達成しているため、本稿では代表値のみ記す。すべて成功。）

**候補C1単独で-18バイト**が実測でき、これは必要な9バイトを上回る。
候補C1を軸F案F1に重ねると、`restore_request_kind_length6`@LIMIT=4は
2039バイトとなり、窓予算2048バイトに対して**9バイトの余裕**を残して
全32構成が成功した。T1+T2（-2バイト）は単独では不十分だが、C1に
重ねればさらに余裕が増える（C1+T1+T2+F1で2037バイト、余裕11バイト）。

## どの候補を採るか

**候補C1（SEEK→SENSE DRIVE STATUS→単発F7の共有列のサブルーチン化、
-18バイト）を採る。** 単独で軸F（案F1、+7〜11バイト）を重ねても全32
構成で`build()`が成功することを実測した。これは`m7ez`・`m7ft`が
「圧縮による余地の確保は別作業」として残していた課題を解消する。

T1・T2（末尾呼び出し化、計-2バイト）は単独では不十分だが、C1との
併用で余裕を追加で確保できることを確認した。実装時にどちらを採るかは
（C1のみか、C1+T1+T2か）今回は決めない——**本稿の役割は「9バイト以上
削れる圧縮が存在するかどうか」を確定させることであり、実装の判断は
軸Fの実装時に行う。**

## 合格条件（次に実装・測定するときのために固定する。緩めない）

1. **発行I/O列がベースラインと完全に一致すること。** 起動区間・
   入口区間・WRITE経路のすべてで、1件も違わない。ログ全体の比較で
   示す。**圧縮は振る舞いを変えないのだから、これは「ほぼ一致」ではなく
   「完全一致」でなければならない。**
2. `READ DATA` 9段・`SEEK` 11段・起動区間のunit/headが、すべて
   ベースラインと一致すること。
3. `tools/conform_l3.sh`の適合条件1〜5が全合格・SKIP 0件・rc=0。
4. **全32ビルド構成で`build()`が`SystemExit`を出さずに成功すること**
   （数値比較は使わない。`m7fg`が確定した2関門——
   `find_fetch_window_straddles`・`find_out_of_window_blocks`——の
   有無だけで判定する）。
5. **軸F案F1（+7バイト相当）を重ねたときに全32構成で`build()`が
   通ること。** 圧縮の目的がこれなので、必ず確認する（本稿で実測済み。
   実装時に再確認する）。

一つでも欠ければ合格と呼ばない。

## 陽性対照（先に登録する）

- 圧縮版の自作サブROMのSHA-256がベースラインと異なること（固定長8192
  バイトなのでファイルサイズ差は使わない）。
- q88measureへ実際に渡した`--rom-dir`内のSHAが圧縮版と一致することを
  毎回確認する。
- **「I/O列が完全一致」という検査が、差を検出できることの陽性対照を
  必ず取る。** わざと振る舞いを変えた版（既存の故障注入フラグ
  ——例えば`break_write_ack`・`break_response`——のどれか、あるいは
  意図的に候補C1の共有列の順序を入れ替えるなどして壊した版）で、同じ
  検査が差を報告することを確認する。**常に一致を返す検査は必ず通過
  する。** この陽性対照が取れなければ合否を判定しない。
- 本稿ではこの陽性対照そのものは実行していない（エミュレータ測定を
  伴うため）。実装・測定のセッションで必ず先に取ること。

## 段番号の扱い

`compare_l3_entry_fdc.py --list-all-stages`の段番号は全コマンド列の
通し番号で1起点であり、既存ノート（`m7ey`・`m7fs`など）の段番号は
0起点である。将来この容量圧縮を実装・測定する際は、0起点で統一し
段の種別名を必ず併記する（`m7fp`の教訓）。

## 解釈規則

- 「I/O列が一致した」は「圧縮が正しい」を意味するが、それは検査が
  差を検出できることが前提である。陽性対照が先。
- 物理的に説明がつかない観測が出たら、観測系を疑って測り直す
  （`m7fp`の教訓）。
- 容量関門の判定は`m7fg`が確定した基準（`build()`の`SystemExit`機構）
  だけを使う。「使用量 ≤ 窓」のような数値比較は判定に使わない。

## 今回やらないこと

- 軸F（batch2・batch5のドライブ明示）の実装そのもの。圧縮が正式に
  入ってから、`m7ft`の合格条件・陽性対照に沿って別途行う。
- `conform_l3.sh`の値表示問題（`disclosure-2026-09-03.md`）の修正。
- 振る舞いを変える最適化（本稿の候補はすべて挙動不変であることを
  確認できたものだけを対象にした。確認できないものは候補にしていない）。
- エミュレータでの測定、`conform_l3.sh`の実行（親セッションが担当する）。
- どの圧縮候補（C1のみかC1+T1+T2か）を最終的に採用するかの決定
  （軸Fの実装セッションで決める）。

## 情報境界

公式ROM、公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は読んでいない。読んだのは`src/l3_service/make_subrom.py`
（自作コード）、`build()`が返す使用量・`SystemExit`の有無・その理由
文字列、`a.labels`（ラベル名とアドレスのみ、ROM内容は含まない）、
このリポジトリの過去のコミットメッセージ（`git log`）だけである。
公式側のデータポート値、FDCパラメータ値、結果バイト値、画面本文は
表示も転記もしていない。エミュレータは起動していない。

## 検証

`src/l3_service/make_subrom.py`は候補ごとに一時的に変更してビルドを
試し、そのつど元へ戻した。作業終了時に`tools/check_cleanroom.sh`を
実行してrcを確認し、`git status`で`src/`・`tools/`に変更が無いこと、
`private/`由来の混入が無いことを確認した（下記コミット時に記載）。
`tools/`は変更していない。`tools/conform_l3.sh`は実行していない。
エミュレータは起動していない。

根拠: [m7ez](m7ez-drive-selector-fix-blocked-by-window.md)・
[m7fg](m7fg-capacity-criterion-was-wrong.md)・
[m7fp](m7fp-axis-d-remeasurement-verification.md)・
[m7fr](m7fr-boot-drive-selector-preregistration.md)・
[m7fs](m7fs-boot-drive-selector-results.md)・
[m7ft](m7ft-boot-drive-selector-both-sides-preregistration.md)・
`m7ca`（`829b259`容量圧縮コミット、`docs/notes/m7ca-behavior-preserving-capacity.md`）・
`m7ap`（`25dff34`テーブル駆動化コミット、
`docs/notes/m7ap-decision-table-and-window-budget.md`）・
`m7bz`（`docs/notes/m7bz-save-reachability.md`「実装と容量」節）・
L3仕様1.46節・3節・自作`src/l3_service/make_subrom.py`。
